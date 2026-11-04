"""
Job Finder - Corporate API Backend (Flask)
Serves job data from MySQL database

Run:
    python api.py
    Then open http://localhost:5000 in browser
"""

from flask import Flask, jsonify, request, Response, session
from flask_cors import CORS
import remote_job_scraper as rjs
import enggroom_scraper
import hackathon_scraper
import json
import re
from datetime import datetime, timedelta
import threading
import time
import os
import mysql.connector
import requests
from mysql.connector import Error
from mysql.connector.abstracts import MySQLConnectionAbstract
import io
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from pdfminer.high_level import extract_text as pdf_extract_text
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests
import mammoth
import fitz  # PyMuPDF - rasterizes PDF pages to images for OCR fallback
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from typing import Any, Dict, List, Optional

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure CORS with allowed origins
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5000').split(',')
CORS(app, origins=cors_origins, allow_headers=['Content-Type'], methods=['GET', 'POST', 'DELETE'])

# Session secret for the Flask session cookie that marks a user as signed
# in after Google Sign-In verification. A real value should live in .env
# (FLASK_SECRET_KEY) so sessions survive a server restart; falls back to a
# per-process random key (logged clearly) rather than hard-failing startup,
# since auth is opt-in on top of an already-working app - the fallback
# just means everyone gets signed out on restart until a real key is set.
_flask_secret = os.getenv('FLASK_SECRET_KEY')
if not _flask_secret:
    import secrets as _secrets
    _flask_secret = _secrets.token_hex(32)
    logger.warning(
        "FLASK_SECRET_KEY not set in .env - using a random per-process key. "
        "Every running server restart will sign all users out. Set "
        "FLASK_SECRET_KEY in .env for persistent sessions."
    )
app.secret_key = _flask_secret
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Only send the session cookie over HTTPS. Defaults to False so local
# development on http://localhost works in every browser - some browsers
# (e.g. Safari) refuse to store a Secure cookie from a plain-http origin,
# which made sign-in fail silently even though the server was fine. Set
# SESSION_COOKIE_SECURE=True in .env for any HTTPS deployment.
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Google Sign-In (Google Identity Services). GOOGLE_CLIENT_ID must match the
# client_id configured in the frontend's Sign In With Google button - a
# token signed for a different client ID is rejected by verify_oauth2_token
# below, which is the actual security check (not just "a token exists").
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
if not GOOGLE_CLIENT_ID:
    logger.warning(
        "GOOGLE_CLIENT_ID not set in .env - Google Sign-In will reject every "
        "sign-in attempt until it's configured."
    )

# Configure rate limiting to prevent API abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
)


class DatabaseUnavailableError(Exception):
    """Raised when MySQL cannot be reached, or a query fails because the
    connection is gone. Routes/loaders deliberately do NOT swallow this into
    an empty list: "the database is down" and "this user has no rows" look
    identical to the UI otherwise, so a user would see an empty dashboard
    instead of an error and assume their data was lost. The application-level
    handler below turns it into a 503 JSON response.
    """

# Add security headers
@app.after_request
def set_security_headers(response: Response) -> Response:
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # index.html is fully self-contained (no external scripts/styles/CDNs),
    # so this can block all external resource loading outright while still
    # allowing the page's existing inline <script>/<style>/onclick= handlers
    # to work. Doesn't replace escaping untrusted job data (already done),
    # but blocks the common "inject an external script/img tag" XSS pattern
    # as defense-in-depth, plus clickjacking/base-tag/form-hijack protection.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        # accounts.google.com/gsi/client is the Google Identity Services
        # library the Sign In With Google button is built from.
        "script-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/client; "
        # The Inter font (CampusOne design-token pass) is loaded from Google
        # Fonts: its stylesheet comes from fonts.googleapis.com, and that
        # stylesheet's own @font-face rules pull the actual font files from
        # fonts.gstatic.com. Without allowlisting both, the browser silently
        # blocks the request and the page falls back to the system font -
        # confirmed live via a blocked network request in Audit #9.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com/gsi/style; "
        "font-src 'self' https://fonts.gstatic.com; "
        # lh3.googleusercontent.com serves the signed-in user's Google
        # profile picture.
        "img-src 'self' data: https://lh3.googleusercontent.com; "
        "connect-src 'self' https://accounts.google.com; "
        "frame-src https://accounts.google.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    # Disable browser features this app never uses, as defense-in-depth
    # against a future XSS trying to abuse them (e.g. geolocation tracking).
    response.headers['Permissions-Policy'] = (
        "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
    )
    return response

@app.errorhandler(429)
def ratelimit_handler(e: Exception) -> tuple:
    """Return a clean JSON response when rate limits are exceeded"""
    logger.warning(f"Rate limit exceeded: {request.remote_addr} - {request.path}")
    return jsonify({
        "success": False,
        "error": "Too many requests. Please slow down and try again shortly.",
        "retry_after": str(e.description)
    }), 429

@app.errorhandler(413)
def payload_too_large_handler(e: Exception) -> tuple:
    """Flask's default 413 response is an HTML error page, which breaks the
    frontend's fetch().json() parsing on an oversized resume upload."""
    return jsonify({
        "success": False,
        "error": f"File too large. Maximum size is {MAX_RESUME_SIZE_BYTES // (1024 * 1024)} MB."
    }), 413


# ---------------------------------------------------------------------------
# JSON error contract
# ---------------------------------------------------------------------------
# Every /api/* consumer parses the response as JSON. Flask's defaults return
# HTML pages for 404/405/415/500, so a typo, a wrong method, or any unhandled
# exception used to make the frontend's res.json() throw - leaving the UI on
# a stale/loading state with only a console error. These handlers guarantee
# the API always answers with {"success": false, "error": ...}.

def _api_error(status: int, message: str) -> tuple:
    return jsonify({"success": False, "error": message}), status


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(415)
def handle_http_error(e: HTTPException) -> Any:
    if not request.path.startswith("/api/"):
        return e  # non-API URLs (e.g. a typo in the page path) keep Flask's page
    messages = {
        400: "Bad request.",
        404: "Not found.",
        405: "Method not allowed.",
        415: "Unsupported media type.",
    }
    code = getattr(e, "code", 400) or 400
    return _api_error(code, messages.get(code, "Request failed."))


@app.errorhandler(DatabaseUnavailableError)
def handle_database_unavailable(e: DatabaseUnavailableError) -> Any:
    logger.error(f"Database unavailable while handling {request.method} {request.path}")
    return _api_error(503, "The database is currently unavailable. Please try again shortly.")


@app.errorhandler(Exception)
def handle_unexpected_exception(e: Exception) -> Any:
    # HTTPExceptions (404/405/413/415/429) already have dedicated handlers.
    if isinstance(e, HTTPException):
        return e
    logger.exception(f"Unhandled exception on {request.method} {request.path}")
    return _api_error(500, "Something went wrong. Please try again.")

# ============ GOOGLE SIGN-IN (login gate) ============
# Every /api/* route except the ones listed here requires a signed-in
# session. The frontend itself (index.html) is still served unauthenticated
# so the sign-in page/overlay can load at all - it's the API calls behind
# it that are gated, which is what actually protects data/actions.
_AUTH_EXEMPT_ENDPOINTS = {"google_sign_in", "auth_me", "auth_config", "static", "index", "health"}

@app.before_request
def require_login():
    if not request.path.startswith("/api/"):
        return None  # only gate the API, not the frontend/static files
    if request.endpoint in _AUTH_EXEMPT_ENDPOINTS:
        return None
    if not session.get("user"):
        # Development mode: auto-login if GOOGLE_CLIENT_ID is not set
        if not GOOGLE_CLIENT_ID:
            session["user"] = {
                "email": "dev@localhost",
                "name": "Developer",
                "picture": None
            }
            logger.info("Development mode: auto-logged in as dev@localhost (GOOGLE_CLIENT_ID not set)")
            return None
        return jsonify({"success": False, "error": "Not signed in. Please sign in with Google."}), 401
    return None

@app.route("/api/auth/google", methods=["POST"])
@limiter.limit("20 per minute")
def google_sign_in() -> Any:
    """Verify a Google Identity Services ID token and start a session.
    The token's signature, expiry, and audience (must match
    GOOGLE_CLIENT_ID) are all checked by verify_oauth2_token - a forged or
    expired token is rejected there, not by anything in this function."""
    try:
        data = request.get_json(silent=True) or {}
        credential = data.get("credential")
        if not credential:
            return jsonify({"success": False, "error": "No credential provided."}), 400

        if not GOOGLE_CLIENT_ID:
            return jsonify({"success": False, "error": "Google Sign-In is not configured on the server."}), 500

        try:
            payload = google_id_token.verify_oauth2_token(
                credential, google_auth_requests.Request(), GOOGLE_CLIENT_ID
            )
        except ValueError as ve:
            logger.warning(f"Google Sign-In token verification failed: {ve}")
            return jsonify({"success": False, "error": "Invalid or expired sign-in token."}), 401

        user = {
            "email": payload.get("email"),
            "name": payload.get("name"),
            "picture": payload.get("picture"),
        }
        session["user"] = user
        session.permanent = True
        logger.info(f"Signed in: {user['email']}")
        return jsonify({"success": True, "user": user})

    except Exception as e:
        logger.error(f"Google Sign-In failed: {e}")
        return jsonify({"success": False, "error": "Sign-in failed. Please try again."}), 500

@app.route("/api/auth/config", methods=["GET"])
def auth_config() -> Any:
    """Public config endpoint: hands the frontend the Google OAuth Client ID
    from .env so it isn't hardcoded in index.html. The Client ID is not a
    secret - it's meant to be visible to the browser (it's embedded in the
    Sign In With Google button either way); only the client secret, which
    this app never uses, would need to stay server-only."""
    return jsonify({"success": True, "google_client_id": GOOGLE_CLIENT_ID})

@app.route("/api/auth/me", methods=["GET"])
def auth_me() -> Any:
    """Report the current session's signed-in user, if any. Deliberately
    exempt from the login gate above - the frontend calls this on page
    load to decide whether to show the app or the sign-in overlay, which
    would be impossible if this endpoint itself required being signed in."""
    user = session.get("user")

    # Development mode: if GOOGLE_CLIENT_ID not configured, always return dev user
    if not GOOGLE_CLIENT_ID:
        user = {
            "email": "dev@localhost",
            "name": "Developer",
            "picture": None
        }
        session["user"] = user

    return jsonify({"success": True, "authenticated": bool(user), "user": user})

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout() -> Any:
    session.pop("user", None)
    return jsonify({"success": True})

# Resume upload constraints
# jpg/jpeg/png accepted directly for candidates who photograph a paper
# resume rather than scanning it to PDF - OCR is the only way to read those.
ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx", "txt", "jpg", "jpeg", "png"}
MAX_RESUME_SIZE_BYTES = int(os.getenv('MAX_RESUME_SIZE', 5 * 1024 * 1024))  # 5 MB
MIN_RESUME_TEXT_CHARS = int(os.getenv('MIN_RESUME_TEXT', 30))
OCR_MAX_PAGES = int(os.getenv('OCR_MAX_PAGES', 5))  # cap worst-case OCR latency

app.config['MAX_CONTENT_LENGTH'] = MAX_RESUME_SIZE_BYTES

# External ATS-scoring service (CUTM AI Gateway). As of this writing the
# endpoint is not yet live on the server (confirmed: every method 404s) -
# the integration below is built defensively against that, and against the
# response shape being slightly different than assumed once it does go
# live, since the exact contract hasn't been confirmed yet.
ATS_API_URL = os.getenv('ATS_API_URL', 'https://qwen.cutm.ac.in/api/ats/evaluate')
# Confirmed live: this endpoint takes ~2 minutes to respond (an LLM call
# behind the scenes), not the few seconds a typical REST call would take -
# a short timeout here would abort valid, still-processing requests.
ATS_API_TIMEOUT = int(os.getenv('ATS_API_TIMEOUT', 180))

# EasyOCR's Reader takes ~30s to initialize (downloads/loads detection +
# recognition models), so it's created lazily on first actual use rather
# than at app startup, and cached as a singleton - re-creating it per
# request would make every OCR-fallback resume take 30s longer than needed.
_ocr_reader = None
_ocr_reader_lock = threading.Lock()

def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_reader_lock:
            if _ocr_reader is None:  # re-check inside the lock
                import easyocr
                logger.info("Initializing OCR reader (first use - this takes ~30s)...")
                start = time.time()
                _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
                logger.info(f"OCR reader ready in {time.time() - start:.1f}s")
    return _ocr_reader

# Sanity cap on decoded pixel count before handing bytes to OCR. Without
# this, a small, well-within-5MB file (a PNG "decompression bomb" - tiny on
# disk, enormous once decoded) could force EasyOCR to allocate gigabytes of
# memory for a single resume upload, a DoS vector MAX_CONTENT_LENGTH alone
# doesn't guard against since it only limits the compressed upload size.
MAX_OCR_IMAGE_PIXELS = 40_000_000  # ~40MP, well above any real scanned page

def _validate_image_bytes(image_bytes: bytes) -> None:
    from PIL import Image
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
    except Exception as e:
        raise ValueError(f"Not a valid image: {str(e)[:100]}")
    if width * height > MAX_OCR_IMAGE_PIXELS:
        raise ValueError(
            f"Image resolution too large ({width}x{height}). "
            f"Please use a smaller/compressed image."
        )

def _ocr_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on a single image and return the recognized text."""
    _validate_image_bytes(image_bytes)
    reader = _get_ocr_reader()
    results = reader.readtext(image_bytes, detail=0, paragraph=True)
    return "\n".join(results)

def _ocr_pdf_bytes(pdf_bytes: bytes) -> str:
    """Rasterize each PDF page to an image and OCR it, up to OCR_MAX_PAGES.
    Used as a fallback when pdfminer finds no text layer (a scanned PDF)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_count = min(len(doc), OCR_MAX_PAGES)
        page_texts = []
        for page_num in range(page_count):
            pix = doc[page_num].get_pixmap(dpi=200)
            page_texts.append(_ocr_image_bytes(pix.tobytes("png")))
        return "\n".join(page_texts)
    finally:
        doc.close()

# MySQL Configuration - Using environment variables
MYSQL_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'job_portal'),
    'autocommit': True
}

# Validate critical configuration
if not MYSQL_CONFIG['password']:
    logger.error("[ERROR] Database password not set in .env file!")
    raise ValueError("DB_PASSWORD environment variable is required")

# The database name is interpolated directly into a CREATE DATABASE
# statement (identifiers can't be parameterized with %s placeholders), so
# validate it against a strict allowlist pattern rather than trusting it
# blindly - it comes from DB_NAME in .env, not end-user input, but this
# closes the gap in case that assumption ever changes.
if not re.match(r'^[A-Za-z0-9_]+$', MYSQL_CONFIG['database']):
    logger.error(f"Invalid DB_NAME: {MYSQL_CONFIG['database']!r}")
    raise ValueError("DB_NAME must contain only letters, digits, and underscores")

# In-memory cache for load_jobs_from_db() to avoid re-fetching/re-parsing the
# entire jobs table on every request (e.g. /api/jobs, /api/stats, /api/match-resume
# hitting within the same few seconds). Invalidated on any write (save/clear).
# Keyed per-user (by owner_email) - a single shared cache would leak one
# user's jobs into another user's response for up to JOBS_CACHE_TTL_SECONDS.
JOBS_CACHE_TTL_SECONDS = int(os.getenv('JOBS_CACHE_TTL_SECONDS', 15))
MAX_JOBS_FETCH = int(os.getenv('MAX_JOBS_FETCH', 5000))  # Safety cap on rows loaded per query
_jobs_cache: Dict[str, Dict[str, Any]] = {}
_jobs_cache_lock = threading.Lock()

def invalidate_jobs_cache(owner_email: Optional[str] = None) -> None:
    """Clear one user's in-memory jobs cache entry after a write (insert/delete).
    If owner_email is None, clear all users' cache entries (useful for test teardown)."""
    with _jobs_cache_lock:
        if owner_email is None:
            _jobs_cache.clear()
        else:
            _jobs_cache.pop(owner_email, None)

def current_user_email() -> Optional[str]:
    """The signed-in user's email, used as the ownership key for every
    per-user table. None only when called outside the login gate (the gate
    itself guarantees a session exists for every protected route)."""
    user = session.get("user")
    return user.get("email") if user else None

def get_db_connection() -> Optional[MySQLConnectionAbstract]:
    """Get MySQL connection"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in database connection: {e}")
        return None


def _ping_db() -> bool:
    """Cheap liveness probe: True only when MySQL actually answers a query.
    Checking this (rather than just "get_db_connection() returned an object")
    is what lets /api/health and /api/db-info report a real outage instead
    of a misleading "active" status."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Database ping failed: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route("/api/health", methods=["GET"])
def health() -> Any:
    """Unauthenticated liveness/readiness probe. Returns 200 when the app
    and database are both reachable, 503 when the database is down - so a
    monitor (or the person running it) can tell the difference between
    "nothing stored yet" and "the database is broken"."""
    db_ok = _ping_db()
    return jsonify({
        "success": True,
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "timestamp": datetime.now().isoformat(),
    }), (200 if db_ok else 503)

def init_db() -> bool:
    """Initialize database and tables"""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_CONFIG['host'],
            user=MYSQL_CONFIG['user'],
            password=MYSQL_CONFIG['password']
        )
        cursor = conn.cursor()

        # Create database if not exists (name already validated at module load)
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_CONFIG['database']}`")
        cursor.close()
        conn.close()

        # Now connect to the database
        conn = get_db_connection()
        if not conn:
            logger.error("Failed to connect to database after creation")
            return False

        cursor = conn.cursor()

        # Create jobs table. category/country/location are VARCHAR(500) -
        # several scrapers join multiple tags/countries into one string
        # (e.g. Himalayas' category list, multi-country postings), which
        # was overflowing the original VARCHAR(100)/VARCHAR(255) limits and
        # silently losing those jobs (MySQL error 1406, caught per-row and
        # logged, never surfaced anywhere else). country keeps an index via
        # a 100-char prefix (an index can't cover a full long VARCHAR within
        # InnoDB's key-length limit, but exact/prefix lookups still work).
        create_table = """
        CREATE TABLE IF NOT EXISTS jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_email VARCHAR(255),
            source VARCHAR(100),
            title VARCHAR(255),
            company VARCHAR(255),
            work_type VARCHAR(50),
            country VARCHAR(500),
            location VARCHAR(500),
            job_type VARCHAR(50),
            category VARCHAR(500),
            salary VARCHAR(100),
            date VARCHAR(50),
            start_date VARCHAR(50),
            end_date VARCHAR(50),
            url VARCHAR(500),
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            domains JSON,
            description TEXT,
            INDEX idx_source (source),
            INDEX idx_work_type (work_type),
            INDEX idx_country (country(100)),
            INDEX idx_owner_email (owner_email),
            UNIQUE KEY uq_owner_url (owner_email, url)
        )
        """
        cursor.execute(create_table)
        conn.commit()

        # CREATE TABLE IF NOT EXISTS is a no-op when the table already exists
        # from an older schema version, so newer columns (e.g. start_date,
        # end_date, domains) never get added automatically. Migrate any
        # missing columns explicitly so inserts referencing them don't
        # silently fail with "Unknown column" errors.
        expected_columns = {
            "start_date": "ALTER TABLE jobs ADD COLUMN start_date VARCHAR(50)",
            "end_date": "ALTER TABLE jobs ADD COLUMN end_date VARCHAR(50)",
            "domains": "ALTER TABLE jobs ADD COLUMN domains JSON",
            "description": "ALTER TABLE jobs ADD COLUMN description TEXT",
            "owner_email": "ALTER TABLE jobs ADD COLUMN owner_email VARCHAR(255)",
        }
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'jobs'",
            (MYSQL_CONFIG['database'],)
        )
        existing_columns = {row[0] for row in cursor.fetchall()}

        for column_name, alter_sql in expected_columns.items():
            if column_name not in existing_columns:
                logger.warning(f"Migrating schema: adding missing column '{column_name}' to jobs table")
                cursor.execute(alter_sql)
                conn.commit()

        # Find which indexes actually exist - this table turns out to
        # predate idx_source/idx_work_type/idx_country entirely (SHOW INDEX
        # confirmed only PRIMARY and the url unique index are present), so
        # any migration step here must check before dropping/assuming an
        # index exists rather than crashing init_db() outright.
        cursor.execute("SHOW INDEX FROM jobs")
        existing_indexes = {row[2] for row in cursor.fetchall()}  # row[2] = Key_name

        # Per-user jobs migration: the old schema uniqued on `url` alone,
        # which breaks the moment two different users scrape the same real
        # external job (same URL, different owner_email) - the second
        # user's insert would silently collide with the first user's row.
        # Drop that old single-column constraint (its auto-generated index
        # name matches the column name, "url") and the separate explicit
        # idx_url index, then add a composite (owner_email, url) uniqueness
        # instead, which allows the same URL once per user.
        if "url" in existing_indexes:
            logger.warning("Migrating schema: dropping old single-column UNIQUE(url) on jobs table")
            cursor.execute("ALTER TABLE jobs DROP INDEX `url`")
            conn.commit()
            existing_indexes.discard("url")
        if "idx_url" in existing_indexes:
            cursor.execute("ALTER TABLE jobs DROP INDEX idx_url")
            conn.commit()
            existing_indexes.discard("idx_url")
        if "uq_owner_url" not in existing_indexes:
            logger.warning("Migrating schema: adding composite UNIQUE(owner_email, url) on jobs table")
            cursor.execute("ALTER TABLE jobs ADD UNIQUE KEY uq_owner_url (owner_email, url)")
            conn.commit()
            existing_indexes.add("uq_owner_url")

        # Widen columns that were observed too narrow for real-world scraped
        # data (category/country joined multi-value strings overflowing
        # VARCHAR(100)/VARCHAR(255), silently losing those jobs on every
        # insert attempt - MySQL error 1406). A table created before this
        # fix keeps its original narrower widths forever otherwise, since
        # CREATE TABLE IF NOT EXISTS never touches an existing table.
        target_widths = {"category": 500, "country": 500, "location": 500}
        cursor.execute(
            "SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'jobs' "
            "AND COLUMN_NAME IN ('category', 'country', 'location')",
            (MYSQL_CONFIG['database'],)
        )
        current_widths = {row[0]: row[1] for row in cursor.fetchall()}

        for column_name, target_width in target_widths.items():
            current = current_widths.get(column_name)
            if current is not None and current < target_width:
                logger.warning(
                    f"Migrating schema: widening column '{column_name}' "
                    f"from VARCHAR({current}) to VARCHAR({target_width})"
                )
                if column_name == "country" and "idx_country" in existing_indexes:
                    # country carries an index; MySQL can't fully index a
                    # VARCHAR(500) utf8mb4 column within InnoDB's key-length
                    # limit, so drop and recreate it with a prefix length.
                    cursor.execute("ALTER TABLE jobs DROP INDEX idx_country")
                    cursor.execute(f"ALTER TABLE jobs MODIFY COLUMN country VARCHAR({target_width})")
                    existing_indexes.discard("idx_country")  # recreated below
                else:
                    cursor.execute(f"ALTER TABLE jobs MODIFY COLUMN {column_name} VARCHAR({target_width})")
                conn.commit()

        # Ensure the indexes the code has always assumed exist actually do -
        # same class of drift as the columns above.
        expected_indexes = {
            "idx_source": "ALTER TABLE jobs ADD INDEX idx_source (source)",
            "idx_work_type": "ALTER TABLE jobs ADD INDEX idx_work_type (work_type)",
            "idx_country": "ALTER TABLE jobs ADD INDEX idx_country (country(100))",
            "idx_owner_email": "ALTER TABLE jobs ADD INDEX idx_owner_email (owner_email)",
        }
        for index_name, alter_sql in expected_indexes.items():
            if index_name not in existing_indexes:
                logger.warning(f"Migrating schema: adding missing index '{index_name}' to jobs table")
                cursor.execute(alter_sql)
                conn.commit()

        # Resource index table - stores only metadata (discipline, resource
        # type, title, link back to the source site), never the actual
        # downloadable project content hosted there.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_email VARCHAR(255),
            source VARCHAR(100),
            discipline VARCHAR(100),
            resource_type VARCHAR(100),
            title VARCHAR(255),
            url VARCHAR(500),
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_discipline (discipline),
            INDEX idx_resource_type (resource_type),
            INDEX idx_owner_email (owner_email),
            UNIQUE KEY uq_owner_url (owner_email, url)
        )
        """)
        conn.commit()

        # Migrate an existing resources table created before per-user
        # ownership existed, same reasoning as the jobs table above.
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'resources'",
            (MYSQL_CONFIG['database'],)
        )
        resources_columns = {row[0] for row in cursor.fetchall()}
        if "owner_email" not in resources_columns:
            logger.warning("Migrating schema: adding missing column 'owner_email' to resources table")
            cursor.execute("ALTER TABLE resources ADD COLUMN owner_email VARCHAR(255)")
            conn.commit()

        cursor.execute("SHOW INDEX FROM resources")
        resources_indexes = {row[2] for row in cursor.fetchall()}
        if "url" in resources_indexes:
            cursor.execute("ALTER TABLE resources DROP INDEX `url`")
            conn.commit()
            resources_indexes.discard("url")
        if "uq_owner_url" not in resources_indexes:
            logger.warning("Migrating schema: adding composite UNIQUE(owner_email, url) on resources table")
            cursor.execute("ALTER TABLE resources ADD UNIQUE KEY uq_owner_url (owner_email, url)")
            conn.commit()
        if "idx_owner_email" not in resources_indexes:
            cursor.execute("ALTER TABLE resources ADD INDEX idx_owner_email (owner_email)")
            conn.commit()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hackathons (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_email VARCHAR(255),
            source VARCHAR(100),
            title VARCHAR(255),
            organizer VARCHAR(255),
            location VARCHAR(255),
            prize_amount VARCHAR(100),
            themes VARCHAR(500),
            registrations_count VARCHAR(50),
            submission_dates VARCHAR(100),
            time_left VARCHAR(100),
            url VARCHAR(500),
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_source (source),
            INDEX idx_owner_email (owner_email),
            UNIQUE KEY uq_owner_url (owner_email, url)
        )
        """)
        conn.commit()

        # Migrate an existing hackathons table created before per-user
        # ownership existed, same reasoning as jobs/resources above.
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'hackathons'",
            (MYSQL_CONFIG['database'],)
        )
        hackathons_columns = {row[0] for row in cursor.fetchall()}
        if "owner_email" not in hackathons_columns:
            logger.warning("Migrating schema: adding missing column 'owner_email' to hackathons table")
            cursor.execute("ALTER TABLE hackathons ADD COLUMN owner_email VARCHAR(255)")
            conn.commit()

        cursor.execute("SHOW INDEX FROM hackathons")
        hackathons_indexes = {row[2] for row in cursor.fetchall()}
        if "url" in hackathons_indexes:
            cursor.execute("ALTER TABLE hackathons DROP INDEX `url`")
            conn.commit()
            hackathons_indexes.discard("url")
        if "uq_owner_url" not in hackathons_indexes:
            logger.warning("Migrating schema: adding composite UNIQUE(owner_email, url) on hackathons table")
            cursor.execute("ALTER TABLE hackathons ADD UNIQUE KEY uq_owner_url (owner_email, url)")
            conn.commit()
        if "idx_owner_email" not in hackathons_indexes:
            cursor.execute("ALTER TABLE hackathons ADD INDEX idx_owner_email (owner_email)")
            conn.commit()

        cursor.close()
        conn.close()
        logger.info("Database initialized successfully")
        return True
    except Error as e:
        logger.error(f"Database initialization failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        return False

def load_jobs_from_db(owner_email: str, use_cache: bool = True) -> List[Dict[str, Any]]:
    """Load one user's jobs from MySQL, with a short-lived in-memory cache to
    avoid repeatedly re-fetching/re-parsing their rows on rapid successive
    requests. Capped at MAX_JOBS_FETCH rows as a safety limit. Every caller
    must pass the signed-in user's email - there is no "load everyone's
    jobs" path, by design, now that jobs are per-user."""
    if use_cache:
        with _jobs_cache_lock:
            entry = _jobs_cache.get(owner_email)
            if entry is not None and (time.time() - entry["timestamp"]) < JOBS_CACHE_TTL_SECONDS:
                return entry["data"]

    try:
        conn = get_db_connection()
        if not conn:
            raise DatabaseUnavailableError("Could not connect to the database")

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM jobs WHERE owner_email = %s ORDER BY added_at DESC LIMIT %s",
            (owner_email, MAX_JOBS_FETCH)
        )
        jobs = cursor.fetchall()

        # Parse JSON fields
        for job in jobs:
            if job.get('domains'):
                try:
                    job['domains'] = json.loads(job['domains'])
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to parse domains for job {job.get('url')}: {e}")
                    job['domains'] = ['General']

        cursor.close()
        conn.close()

        with _jobs_cache_lock:
            _jobs_cache[owner_email] = {"data": jobs, "timestamp": time.time()}

        return jobs
    except DatabaseUnavailableError:
        raise
    except Error as e:
        logger.error(f"Failed to load jobs from database: {e}")
        raise DatabaseUnavailableError(str(e)) from e

# Must match the jobs table's actual VARCHAR column widths. Values are
# truncated to these lengths before insert as a defensive, permanent fix -
# widening a column only moves the same "Data too long for column" failure
# to the next unusually long value some scraper eventually produces (seen
# in practice: one Himalayas job's joined location list still exceeded a
# freshly-widened VARCHAR(500)). Truncating here means no future oversized
# value, in any field, from any source, can ever silently lose a job again.
_COLUMN_MAX_LENGTHS = {
    "source": 100, "title": 255, "company": 255, "work_type": 50,
    "country": 500, "location": 500, "job_type": 50, "category": 500,
    "salary": 100, "date": 50, "start_date": 50, "end_date": 50, "url": 500,
    "description": 4000,
    # resources table columns (reuses the same truncation helper/pattern)
    "discipline": 100, "resource_type": 100,
    # hackathons table columns
    "organizer": 255, "prize_amount": 100, "themes": 500,
    "registrations_count": 50, "submission_dates": 100, "time_left": 100,
}

def _truncate_for_column(value: Any, column: str) -> Any:
    if value is None:
        return value
    max_len = _COLUMN_MAX_LENGTHS.get(column)
    text = str(value)
    if max_len and len(text) > max_len:
        return text[:max_len]
    return value

def save_jobs_to_db(jobs: List[Dict[str, Any]], owner_email: str) -> Dict[str, int]:
    """Save jobs to MySQL database, scoped to one user. Returns
    {"saved": N, "failed": N} so callers can tell actual persistence
    success from attempted count - per-row failures (e.g. a value too long
    for a column) are caught and logged per job, but previously vanished
    silently since the caller only ever saw a bare True/False for the
    whole batch."""
    result = {"saved": 0, "failed": 0}
    try:
        conn = get_db_connection()
        if not conn:
            result["failed"] = len(jobs)
            return result

        cursor = conn.cursor()

        for job in jobs:
            domains = json.dumps(job.get('domains', ['General']))

            try:
                insert_query = """
                INSERT INTO jobs (owner_email, source, title, company, work_type, country, location,
                                 job_type, category, salary, date, start_date, end_date, url,
                                 domains, description, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source = VALUES(source), title = VALUES(title), company = VALUES(company),
                    work_type = VALUES(work_type), country = VALUES(country), location = VALUES(location),
                    job_type = VALUES(job_type), category = VALUES(category), salary = VALUES(salary),
                    date = VALUES(date), start_date = VALUES(start_date), end_date = VALUES(end_date),
                    domains = VALUES(domains), description = VALUES(description), added_at = NOW()
                """
                cursor.execute(insert_query, (
                    owner_email,
                    _truncate_for_column(job.get('source'), 'source'),
                    _truncate_for_column(job.get('title'), 'title'),
                    _truncate_for_column(job.get('company'), 'company'),
                    _truncate_for_column(job.get('work_type'), 'work_type'),
                    _truncate_for_column(job.get('country'), 'country'),
                    _truncate_for_column(job.get('location'), 'location'),
                    _truncate_for_column(job.get('job_type'), 'job_type'),
                    _truncate_for_column(job.get('category'), 'category'),
                    _truncate_for_column(job.get('salary'), 'salary'),
                    _truncate_for_column(job.get('date'), 'date'),
                    _truncate_for_column(job.get('start_date'), 'start_date'),
                    _truncate_for_column(job.get('end_date'), 'end_date'),
                    _truncate_for_column(job.get('url'), 'url'),
                    domains,
                    _truncate_for_column(job.get('description'), 'description'),
                    datetime.now()
                ))
                result["saved"] += 1
            except Error as e:
                result["failed"] += 1
                logger.error(f"Failed to insert job {job.get('url')}: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        invalidate_jobs_cache(owner_email)
        return result
    except Error as e:
        logger.error(f"Failed to save jobs to database: {e}")
        result["failed"] = len(jobs) - result["saved"]
        return result
    except Exception as e:
        logger.error(f"Unexpected error while saving jobs: {e}")
        result["failed"] = len(jobs) - result["saved"]
        return result

def save_resources_to_db(resources: List[Dict[str, Any]], owner_email: str) -> Dict[str, int]:
    """Save resource index entries (metadata only) to MySQL, scoped to one user."""
    result = {"saved": 0, "failed": 0}
    try:
        conn = get_db_connection()
        if not conn:
            result["failed"] = len(resources)
            return result

        cursor = conn.cursor()
        for r in resources:
            try:
                cursor.execute("""
                    INSERT INTO resources (owner_email, source, discipline, resource_type, title, url, added_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        source = VALUES(source), discipline = VALUES(discipline),
                        resource_type = VALUES(resource_type), title = VALUES(title),
                        added_at = NOW()
                """, (
                    owner_email,
                    _truncate_for_column(r.get('source'), 'source'),
                    _truncate_for_column(r.get('discipline'), 'discipline'),
                    _truncate_for_column(r.get('resource_type'), 'resource_type'),
                    _truncate_for_column(r.get('title'), 'title'),
                    _truncate_for_column(r.get('url'), 'url'),
                    datetime.now()
                ))
                result["saved"] += 1
            except Error as e:
                result["failed"] += 1
                logger.error(f"Failed to insert resource {r.get('url')}: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        return result
    except Error as e:
        logger.error(f"Failed to save resources to database: {e}")
        result["failed"] = len(resources) - result["saved"]
        return result

def load_resources_from_db(owner_email: str) -> List[Dict[str, Any]]:
    """Load one user's resource index entries from MySQL."""
    try:
        conn = get_db_connection()
        if not conn:
            raise DatabaseUnavailableError("Could not connect to the database")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM resources WHERE owner_email = %s ORDER BY discipline, resource_type",
            (owner_email,)
        )
        resources = cursor.fetchall()
        cursor.close()
        conn.close()
        return resources
    except DatabaseUnavailableError:
        raise
    except Error as e:
        logger.error(f"Failed to load resources from database: {e}")
        raise DatabaseUnavailableError(str(e)) from e

def save_hackathons_to_db(hackathons: List[Dict[str, Any]], owner_email: str) -> Dict[str, int]:
    """Save hackathon listings to MySQL, scoped to one user."""
    result = {"saved": 0, "failed": 0}
    try:
        conn = get_db_connection()
        if not conn:
            result["failed"] = len(hackathons)
            return result

        cursor = conn.cursor()
        for h in hackathons:
            try:
                cursor.execute("""
                    INSERT INTO hackathons (owner_email, source, title, organizer, location, prize_amount,
                                           themes, registrations_count, submission_dates,
                                           time_left, url, added_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        source = VALUES(source), title = VALUES(title), organizer = VALUES(organizer),
                        location = VALUES(location), prize_amount = VALUES(prize_amount),
                        themes = VALUES(themes), registrations_count = VALUES(registrations_count),
                        submission_dates = VALUES(submission_dates), time_left = VALUES(time_left),
                        added_at = NOW()
                """, (
                    owner_email,
                    _truncate_for_column(h.get('source'), 'source'),
                    _truncate_for_column(h.get('title'), 'title'),
                    _truncate_for_column(h.get('organizer'), 'organizer'),
                    _truncate_for_column(h.get('location'), 'location'),
                    _truncate_for_column(h.get('prize_amount'), 'prize_amount'),
                    _truncate_for_column(h.get('themes'), 'themes'),
                    _truncate_for_column(h.get('registrations_count'), 'registrations_count'),
                    _truncate_for_column(h.get('submission_dates'), 'submission_dates'),
                    _truncate_for_column(h.get('time_left'), 'time_left'),
                    _truncate_for_column(h.get('url'), 'url'),
                    datetime.now()
                ))
                result["saved"] += 1
            except Error as e:
                result["failed"] += 1
                logger.error(f"Failed to insert hackathon {h.get('url')}: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        return result
    except Error as e:
        logger.error(f"Failed to save hackathons to database: {e}")
        result["failed"] = len(hackathons) - result["saved"]
        return result

def load_hackathons_from_db(owner_email: str) -> List[Dict[str, Any]]:
    """Load one user's hackathon listings from MySQL, most recently added first."""
    try:
        conn = get_db_connection()
        if not conn:
            raise DatabaseUnavailableError("Could not connect to the database")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM hackathons WHERE owner_email = %s ORDER BY added_at DESC",
            (owner_email,)
        )
        hackathons = cursor.fetchall()
        cursor.close()
        conn.close()
        return hackathons
    except DatabaseUnavailableError:
        raise
    except Error as e:
        logger.error(f"Failed to load hackathons from database: {e}")
        raise DatabaseUnavailableError(str(e)) from e

def is_fresher_job(job: Dict[str, Any]) -> bool:
    """Detect if a job is ONLY for freshers/entry-level (0-1 years) or internships"""
    fresher_keywords = [
        'fresher', 'intern', 'internship', 'entry-level', 'entry level', 'entry-level graduate',
        'graduate', 'trainee', 'apprentice', 'new grad', 'beginner', 'new graduate',
        'no experience', 'without experience', '0-1 year', '0-1 years', 'zero experience',
        'placement', 'campus', 'university', 'college', 'newly graduate',
        'first job', 'first time', 'entry point', 'starter role', 'beginner friendly'
    ]

    # Keywords that indicate experienced roles - EXCLUDE these
    exclude_keywords = [
        'senior', 'expert', 'lead', 'principal', 'architect', '2+ years', '2-3 years',
        '3+ years', '3-5 years', '5+ years', '5-7 years', '7+ years', '10+ years',
        'years of experience', 'years experience', 'experienced professional',
        'mid-level', 'mid level', 'staff engineer', 'principal engineer'
    ]

    title = (job.get('title') or '').lower()
    category = (job.get('category') or '').lower()
    description = (job.get('description') or '').lower()
    text = f"{title} {category} {description}"

    # REJECT: If job explicitly requires experience, exclude it
    for keyword in exclude_keywords:
        if keyword in text:
            return False

    # STRICT: ONLY ACCEPT if job has explicit fresher/internship keywords
    for keyword in fresher_keywords:
        if keyword in text:
            return True

    # REJECT by default: If no explicit fresher keyword found, exclude it
    # This ensures ONLY genuine fresher/internship jobs are shown
    return False

def is_experienced_job(job: Dict[str, Any]) -> bool:
    """Detect if a job is suitable for an experienced candidate.

    Defined as the complement of is_fresher_job() so every job lands in
    exactly one bucket: a listing either explicitly targets freshers/
    interns (is_fresher_job), or it doesn't - and a listing with no
    experience signal at all is treated as open to experienced candidates
    by default, since that's the norm for real-world job postings that
    don't call out "fresher" explicitly."""
    return not is_fresher_job(job)

# Domain keywords mapping - shared with resume matching
# 44 domains covering CUTM's full multi-school program range (Engineering,
# Agriculture, Pharmacy/Health, Management), supplied by the university -
# cross-checked against the original 5-domain set before this expansion:
# AIML/Data Analytics/AR-VR/Cybersecurity were consolidated into the
# equivalently-named domains below (Data Science and Machine Learning /
# Data Analytics / Gaming and Immersive Learning (AR & VR) / Cyber Security)
# rather than kept as separate near-duplicates; Blockchain had no
# equivalent in the supplied list and was kept as an additional domain.
DOMAIN_KEYWORDS = {
    'Data Science and Machine Learning': [
        'ai', 'ml', 'data science', 'machine learning', 'deep learning', 'neural network',
        'nlp', 'computer vision', 'llm', 'generative ai', 'artificial intelligence', 'chatgpt',
        'tensorflow', 'pytorch', 'data scientist', 'ml engineer', 'ai engineer', 'ai/ml',
    ],
    'Software Technologies': [
        'software engineer', 'software developer', 'full stack', 'backend developer',
        'frontend developer', 'web development', 'java developer', 'python developer',
        'javascript developer', 'react developer', 'node.js', 'api development',
        'software architecture',
    ],
    'Aerial Surveying and Remote Sensing Applications': [
        'remote sensing', 'aerial survey', 'drone survey', 'photogrammetry', 'gis',
        'geospatial', 'lidar', 'satellite imagery', 'uav mapping', 'cartography',
    ],
    'Cloud Technologies': [
        'cloud engineer', 'cloud computing', 'aws', 'microsoft azure', 'google cloud',
        'gcp', 'devops', 'kubernetes', 'docker', 'cloud architecture',
        'cloud infrastructure', 'serverless', 'terraform',
    ],
    'Cyber Security': [
        'cybersecurity', 'cyber security', 'security engineer', 'security analyst',
        'infosec', 'pentester', 'penetration testing', 'ethical hacker', 'soc analyst',
        'siem', 'vulnerability assessment', 'network security', 'application security',
        'cloud security', 'security architect',
    ],
    'Embedded System Design': [
        'embedded systems', 'microcontroller', 'firmware', 'rtos', 'embedded engineer',
        'embedded c', 'arm cortex', 'fpga', 'pcb design', 'iot device',
    ],
    'Gaming and Immersive Learning (AR & VR)': [
        'augmented reality', 'virtual reality', 'game developer', 'game design', 'unity',
        'unreal engine', 'metaverse', 'mixed reality', 'immersive technology',
        'xr developer', '3d graphics', 'game engine', 'ar/vr', 'ar vr',
    ],
    'Chip Design and Fabrication Using VLSI': [
        'vlsi', 'chip design', 'asic design', 'semiconductor', 'rtl design', 'verilog',
        'vhdl', 'cmos', 'ic design', 'silicon fabrication', 'tape out',
    ],
    'Communication Systems': [
        'telecommunication', 'wireless communication', '5g', '4g lte', 'rf engineer',
        'signal processing', 'satellite communication', 'network protocol',
        'antenna design', 'optical communication',
    ],
    'Operation and Maintenance of Electrical Grid System & Transformers': [
        'power grid', 'electrical grid', 'transformer maintenance', 'substation',
        'power distribution', 'scada', 'grid operation', 'power system engineer',
        'transmission line', 'switchgear',
    ],
    'Industrial Automation': [
        'plc programming', 'industrial automation', 'automation engineer',
        'control systems', 'robotics automation', 'hmi', 'process automation',
        'instrumentation engineer', 'dcs',
    ],
    'Construction Planning Monitoring and Project Management': [
        'construction management', 'project planning', 'site supervisor',
        'construction monitoring', 'project scheduling', 'quantity surveyor',
        'construction project manager', 'primavera', 'civil project management',
    ],
    'Architectural and Structural Design': [
        'architect', 'structural engineer', 'structural design', 'autocad', 'revit',
        'building design', 'architectural design', 'structural analysis', 'staad pro',
        'bim modeling',
    ],
    'Composite Design and Manufacturing': [
        'composite materials', 'composite manufacturing', 'fiber reinforced',
        'carbon fiber', 'composite engineer', 'layup design',
        'resin transfer molding', 'composite structures',
    ],
    'Go to Market – Product Development': [
        'go to market', 'product development', 'product manager', 'product launch',
        'market strategy', 'product lifecycle', 'product management', 'gtm strategy',
    ],
    'Manufacturing (Conventional, CNC and Additive)': [
        'cnc machining', 'cnc programming', 'additive manufacturing', '3d printing',
        'manufacturing engineer', 'production engineer', 'machining operations',
        'tool design', 'manufacturing process',
    ],
    'Welding and Inspection': [
        'welding engineer', 'welding inspector', 'ndt inspection', 'weld quality',
        'welding technology', 'arc welding', 'tig welding', 'mig welding',
        'weld testing',
    ],
    'Automobile Engineering': [
        'automotive engineer', 'automobile engineering', 'vehicle design',
        'automotive design', 'ev engineer', 'electric vehicle', 'automotive systems',
        'powertrain', 'chassis design', 'automotive testing',
    ],
    'Computational Fluid Dynamics': [
        'cfd analysis', 'computational fluid dynamics', 'cfd engineer', 'ansys fluent',
        'fluid flow simulation', 'thermal analysis', 'aerodynamics simulation',
    ],
    'Renewable Energy Applications': [
        'renewable energy', 'solar energy', 'wind energy', 'solar panel',
        'energy systems', 'green energy', 'photovoltaic', 'solar engineer',
        'wind turbine', 'sustainable energy',
    ],
    'Cyber Security and Digital Forensics': [
        'digital forensics', 'cyber forensics', 'forensic analyst', 'malware analysis',
        'threat intelligence', 'forensic investigation', 'data recovery forensics',
    ],
    'Manufacturing Execution System': [
        'manufacturing execution system', 'mes implementation', 'shop floor control',
        'production tracking', 'factory automation software',
    ],
    'Data Analytics': [
        'data analyst', 'data analytics', 'business intelligence', 'tableau',
        'power bi', 'sql developer', 'data visualization', 'reporting analyst',
        'dashboard development', 'etl developer', 'data warehouse',
    ],
    'Business Analytics': [
        'business analyst', 'business analytics', 'business intelligence analyst',
        'market analysis', 'financial analytics', 'business insights',
        'kpi analysis', 'strategic analytics',
    ],
    'Smart Farm Machinery': [
        'smart farming equipment', 'farm machinery', 'precision agriculture',
        'agricultural automation', 'tractor technology', 'farm equipment engineer',
        'agri-robotics',
    ],
    'Organic Farming': [
        'organic farming', 'organic agriculture', 'organic certification',
        'sustainable farming', 'organic cultivation', 'biofertilizer',
        'organic produce',
    ],
    'Dairy Processing and Development': [
        'dairy processing', 'dairy technology', 'milk processing',
        'dairy product development', 'dairy engineer', 'dairy quality control',
        'dairy plant',
    ],
    'Intensive Aquaculture': [
        'aquaculture', 'fish farming', 'shrimp farming', 'aquaculture technology',
        'hatchery management', 'aquaculture production', 'fisheries science',
    ],
    'Seed Production Using Manual and Molecular Methods': [
        'seed production', 'seed technology', 'molecular breeding', 'seed science',
        'seed certification', 'plant breeding', 'hybrid seed',
    ],
    'Genetic Engineering & Genomics': [
        'genetic engineering', 'genomics', 'gene editing', 'crispr',
        'molecular biology', 'genome sequencing', 'biotechnology research',
        'gene expression',
    ],
    'Nutraceuticals': [
        'nutraceuticals', 'dietary supplements', 'functional foods',
        'nutraceutical formulation', 'nutrition science', 'herbal supplements',
    ],
    'Smart Agriculture': [
        'smart agriculture', 'precision farming', 'agri-tech', 'iot farming',
        'agricultural sensors', 'farm analytics', 'smart irrigation',
    ],
    'Protected Horticulture': [
        'protected horticulture', 'greenhouse farming', 'polyhouse cultivation',
        'horticulture technology', 'controlled environment agriculture',
        'nursery management',
    ],
    'Plant Tissue Culture and Vegetative Propagation': [
        'tissue culture', 'plant propagation', 'micropropagation',
        'vegetative propagation', 'plant cloning', 'in vitro culture',
    ],
    'Food Processing': [
        'food processing', 'food technology', 'food science',
        'food product development', 'food quality control', 'food packaging',
        'food engineer',
    ],
    'Agri Business Management': [
        'agribusiness', 'agri business management', 'agricultural marketing',
        'farm management', 'agri supply chain', 'agricultural economics',
    ],
    'Commodity and Food Storage': [
        'food storage', 'commodity storage', 'warehouse management',
        'grain storage', 'cold storage', 'post harvest management',
        'storage logistics',
    ],
    'Soil and Water Conservation Through Watershed': [
        'soil conservation', 'water conservation', 'watershed management',
        'soil and water engineering', 'irrigation management',
        'land and water resources',
    ],
    'Fish Processing Technology': [
        'fish processing', 'seafood processing', 'fish product development',
        'fish quality control', 'fisheries technology', 'fish preservation',
    ],
    'Pharmaceutical Chemistry': [
        'pharmaceutical chemistry', 'drug formulation', 'medicinal chemistry',
        'pharma research', 'pharmaceutical analysis', 'drug development',
        'pharmacology',
    ],
    'Health Care Assistancy': [
        'healthcare assistant', 'patient care', 'clinical assistant',
        'medical assistant', 'nursing assistant', 'healthcare support',
    ],
    'Good Health and Wellness': [
        'health and wellness', 'wellness coach', 'fitness trainer', 'public health',
        'preventive healthcare', 'wellness program', 'nutrition counseling',
    ],
    'Retail and Hospitality': [
        'retail management', 'hospitality management', 'customer service',
        'hotel management', 'retail operations', 'guest relations',
        'front office', 'food and beverage service',
    ],
    'Blockchain': [
        'blockchain', 'crypto', 'web3', 'solidity', 'smart contract', 'ethereum',
        'defi', 'nft', 'dapp', 'distributed ledger', 'blockchain developer',
        'smart contract developer', 'web3 developer', 'cryptocurrency',
    ],
}

# Word-boundary matching (not plain substring) so short keywords like "ai", "ml",
# "ar", "vr" don't false-positive inside unrelated words - e.g. "ai" inside
# "Retail", "ml" inside "HTML", "ar" inside "Car"/"Market"/"Guitar", "vr" inside
# assorted German compound words. Boundaries are any non-alphanumeric character
# (or start/end of string), so this still matches keywords embedded in phrases
# like "AI/ML Engineer" or "(AI)".
_DOMAIN_KEYWORD_PATTERNS = {
    domain: [
        re.compile(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])")
        for keyword in keywords
    ]
    for domain, keywords in DOMAIN_KEYWORDS.items()
}

def detect_job_domain(job: Dict[str, Any]) -> List[str]:
    """Detect job domain from title, category, and description"""
    title = (job.get('title') or '').lower()
    category = (job.get('category') or '').lower()
    description = (job.get('description') or '').lower()
    text = f"{title} {category} {description}"

    detected_domains = []
    for domain, patterns in _DOMAIN_KEYWORD_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            detected_domains.append(domain)

    return detected_domains if detected_domains else ['General']

def filter_jobs(
    all_jobs: List[Dict[str, Any]],
    keyword: str = "",
    work_type: str = "",
    country: str = "",
    job_type: str = "",
    experience_level: str = "",
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """Filter jobs based on criteria"""
    filtered = all_jobs

    if experience_level == "fresher":
        filtered = [j for j in filtered if is_fresher_job(j)]
    elif experience_level == "experienced":
        filtered = [j for j in filtered if is_experienced_job(j)]

    if keyword:
        keyword = keyword.lower()
        filtered = [j for j in filtered if keyword in (j.get('title') or '').lower() or
                   keyword in (j.get('company') or '').lower()]

    if work_type:
        filtered = [j for j in filtered if (j.get('work_type') or '').lower() == work_type.lower()]

    if country:
        filtered = [j for j in filtered if (j.get('country') or '').lower() == country.lower()]

    if job_type:
        filtered = [j for j in filtered if (j.get('job_type') or '').lower() == job_type.lower()]

    total = len(filtered)
    pages = (total + limit - 1) // limit if limit > 0 else 1

    # Computed over the full filtered set, before pagination slicing, so the
    # frontend's stat cards stay accurate even when total exceeds one page -
    # counting only the returned page (or an earlier hardcoded single-page
    # fetch) silently undercounted once the dataset grew past that page size.
    work_type_breakdown: Dict[str, int] = {}
    internship_count = 0
    for j in filtered:
        wt = j.get('work_type') or 'Unknown'
        work_type_breakdown[wt] = work_type_breakdown.get(wt, 0) + 1
        # job_type can be a comma-joined combination (e.g. "Contract,
        # Internship"), from norm_job_type() - not a single enum value - so
        # this checks for Internship as a component, not an exact match.
        if 'internship' in (j.get('job_type') or '').lower():
            internship_count += 1

    start = (page - 1) * limit
    end = start + limit

    return {
        "jobs": filtered[start:end],
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit,
        "work_type_breakdown": work_type_breakdown,
        "internship_count": internship_count,
    }

def get_statistics(owner_email: str) -> Dict[str, Any]:
    """Calculate statistics from one user's jobs"""
    jobs = load_jobs_from_db(owner_email)

    if not jobs:
        return {
            "total_jobs": 0,
            "by_work_type": {},
            "by_country": {},
            "by_category": {},
            "by_source": {},
            "last_updated": None
        }

    stats = {
        "total_jobs": len(jobs),
        "by_work_type": {},
        "by_country": {},
        "by_category": {},
        "by_source": {}
    }

    for job in jobs:
        work_type = job.get('work_type', 'Unknown')
        stats["by_work_type"][work_type] = stats["by_work_type"].get(work_type, 0) + 1

        country = job.get('country', 'Unknown')
        stats["by_country"][country] = stats["by_country"].get(country, 0) + 1

        category = job.get('category', 'Unknown')
        stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

        source = job.get('source', 'Unknown')
        stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

    return stats

def _job_added_date(job: Dict[str, Any]) -> Optional[datetime]:
    """Normalize the added_at field (native datetime from MySQL, or a string
    fallback) into a datetime, or None if it can't be parsed."""
    added_at = job.get('added_at')
    if isinstance(added_at, datetime):
        return added_at
    if isinstance(added_at, str) and added_at:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(added_at, fmt)
            except ValueError:
                continue
    return None

def get_analytics(owner_email: str, days: int = 14, top_n: int = 10) -> Dict[str, Any]:
    """Aggregate analytics for one user's dashboard: summary counts, a
    jobs-added time series, domain/work-type distribution, and top
    sources/countries/companies. Built entirely from load_jobs_from_db()
    (Python-side aggregation) so it benefits from the same in-memory cache
    as other endpoints rather than issuing extra DB queries."""
    jobs = load_jobs_from_db(owner_email)

    if not jobs:
        return {
            "summary": {"total_jobs": 0, "added_today": 0, "added_this_week": 0,
                        "total_companies": 0, "total_sources": 0},
            "jobs_over_time": [],
            "recency_breakdown": [],
            "by_domain": {},
            "by_work_type": {},
            "top_sources": [],
            "top_countries": [],
            "top_companies": [],
        }

    now = datetime.now()
    today = now.date()
    week_ago = today - timedelta(days=7)

    domain_counts: Dict[str, int] = {}
    work_type_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}
    country_counts: Dict[str, int] = {}
    company_counts: Dict[str, int] = {}
    day_counts: Dict[str, int] = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days)}

    added_today = 0
    added_this_week = 0

    # Buckets jobs by how long ago they were fetched (added_at), in order
    # from most to least recent, so the analytics page can show something
    # like "42 jobs fetched today, 310 fetched this month" instead of only
    # a daily time-series chart - a quicker read of overall dataset freshness.
    recency_buckets = [
        ("Today", 0, 0),
        ("Yesterday", 1, 1),
        ("This week", 2, 6),
        ("This month", 7, 29),
        ("1-3 months ago", 30, 89),
        ("Over 3 months ago", 90, None),
    ]
    recency_counts: Dict[str, int] = {label: 0 for label, _, _ in recency_buckets}
    unknown_fetch_date_count = 0

    for job in jobs:
        for domain in (job.get('domains') or ['General']):
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        work_type = job.get('work_type') or 'Unknown'
        work_type_counts[work_type] = work_type_counts.get(work_type, 0) + 1

        source = job.get('source') or 'Unknown'
        source_counts[source] = source_counts.get(source, 0) + 1

        country = job.get('country') or 'Unknown'
        country_counts[country] = country_counts.get(country, 0) + 1

        company = job.get('company') or 'Unknown'
        company_counts[company] = company_counts.get(company, 0) + 1

        added_dt = _job_added_date(job)
        if added_dt:
            added_date = added_dt.date()
            if added_date == today:
                added_today += 1
            if added_date >= week_ago:
                added_this_week += 1
            day_key = added_date.isoformat()
            if day_key in day_counts:
                day_counts[day_key] += 1

            days_ago = (today - added_date).days
            for label, lo, hi in recency_buckets:
                if days_ago >= lo and (hi is None or days_ago <= hi):
                    recency_counts[label] += 1
                    break
        else:
            unknown_fetch_date_count += 1

    def top(counts: Dict[str, int], n: int) -> List[Dict[str, Any]]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]
        ]

    jobs_over_time = [
        {"date": day, "count": day_counts[day]}
        for day in sorted(day_counts.keys())
    ]

    recency_breakdown = [
        {"label": label, "count": recency_counts[label]}
        for label, _, _ in recency_buckets
        if recency_counts[label] > 0
    ]
    if unknown_fetch_date_count:
        recency_breakdown.append({"label": "Unknown fetch date", "count": unknown_fetch_date_count})

    return {
        "summary": {
            "total_jobs": len(jobs),
            "added_today": added_today,
            "added_this_week": added_this_week,
            "total_companies": len({j.get('company') for j in jobs if j.get('company')}),
            "total_sources": len({j.get('source') for j in jobs if j.get('source')}),
        },
        "jobs_over_time": jobs_over_time,
        "recency_breakdown": recency_breakdown,
        "by_domain": domain_counts,
        "by_work_type": work_type_counts,
        "top_sources": top(source_counts, top_n),
        "top_countries": top(country_counts, top_n),
        "top_companies": top(company_counts, top_n),
    }

# ============ RESUME MATCHING HELPERS ============

def extract_text_from_resume(file_storage: FileStorage) -> str:
    """Extract text from uploaded resume (PDF, DOCX, TXT, or an image).
    Everything stays in memory - never written to disk. PDFs with no
    extractable text layer (scanned/photographed resumes) and direct image
    uploads fall back to OCR automatically."""
    filename = secure_filename(file_storage.filename or "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise ValueError(f"Unsupported file type: .{ext}. Allowed: {', '.join(ALLOWED_RESUME_EXTENSIONS)}")

    raw_bytes = file_storage.read()
    if not raw_bytes:
        raise ValueError("Uploaded file is empty")

    used_ocr = False
    try:
        if ext == "pdf":
            text = pdf_extract_text(io.BytesIO(raw_bytes))
            if len((text or "").strip()) < MIN_RESUME_TEXT_CHARS:
                # No usable text layer - likely a scanned/photographed PDF.
                logger.info(f"'{filename}': pdfminer found no text layer, falling back to OCR")
                used_ocr = True
                text = _ocr_pdf_bytes(raw_bytes)
        elif ext == "docx":
            result = mammoth.extract_raw_text(io.BytesIO(raw_bytes))
            text = result.value
        elif ext in ("jpg", "jpeg", "png"):
            used_ocr = True
            text = _ocr_image_bytes(raw_bytes)
        else:  # txt
            text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        raise ValueError(f"Could not parse this file: {str(e)[:100]}")

    text = (text or "").strip()
    if used_ocr:
        logger.info(f"'{filename}': OCR extracted {len(text)} characters")
    return text

def evaluate_ats_score(filename: str, raw_bytes: bytes) -> Dict[str, Any]:
    """Forward a resume file to the CUTM AI Gateway's ATS-evaluation endpoint
    and normalize its response to {"score": float, "feedback": str}.

    Confirmed live response shape (2026-11-03): {"ats_score": 85,
    "match_percentage": 95, "rating": "...", "summary": "...",
    "category_breakdown": {...}, "matched_keywords": [...],
    "missing_keywords": [...], "strengths": [...],
    "critical_issues": [...], "actionable_recommendations": [...], ...}.
    "feedback" is built from summary + actionable_recommendations +
    critical_issues rather than one field, since the real response spreads
    improvement guidance across several keys - none of which are a plain
    "feedback" field. Key-name fallbacks are kept for score in case the
    service's schema changes again.
    """
    try:
        response = requests.post(
            ATS_API_URL,
            files={"file": (filename, raw_bytes)},
            timeout=ATS_API_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise ValueError("ATS scoring service timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise ValueError("ATS scoring service is currently unreachable.")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"ATS scoring request failed: {str(e)[:150]}")

    if response.status_code != 200:
        raise ValueError(
            f"ATS scoring service returned an error (HTTP {response.status_code})."
        )

    try:
        data = response.json()
    except ValueError:
        raise ValueError("ATS scoring service returned an unreadable response.")

    score = None
    for key in ("ats_score", "score", "atsScore", "match_score", "match_percentage"):
        if key in data:
            score = data[key]
            break

    if score is None:
        raise ValueError("ATS scoring service response did not include a score.")

    try:
        score = round(float(score), 1)
    except (TypeError, ValueError):
        raise ValueError("ATS scoring service returned a non-numeric score.")

    # Build feedback from the real response's several improvement-guidance
    # fields rather than one key - "summary" gives the overall read,
    # "actionable_recommendations" is the actual to-do list, and
    # "critical_issues" flags anything that needs fixing first.
    sections = []
    summary = data.get("summary")
    if summary:
        sections.append(str(summary))

    critical_issues = data.get("critical_issues")
    if critical_issues:
        items = "\n".join(f"- {item}" for item in critical_issues)
        sections.append(f"Critical issues:\n{items}")

    recommendations = data.get("actionable_recommendations")
    if recommendations:
        items = "\n".join(f"- {item}" for item in recommendations)
        sections.append(f"Recommendations:\n{items}")

    missing_keywords = data.get("missing_keywords")
    if missing_keywords:
        sections.append(f"Missing keywords: {', '.join(missing_keywords)}")

    feedback = "\n\n".join(sections) if sections else None

    # Fall back to older guessed field names in case the service's schema
    # changes again and stops returning the fields checked above.
    if not feedback:
        for key in ("feedback", "context", "suggestions", "improvements", "message"):
            if data.get(key):
                feedback = data[key]
                break

    if isinstance(feedback, list):
        feedback = "\n".join(str(item) for item in feedback)
    elif feedback is not None and not isinstance(feedback, str):
        feedback = str(feedback)

    return {"score": score, "feedback": feedback or "No improvement suggestions provided."}

def extract_resume_keywords(resume_text: str) -> List[str]:
    """Detect which domains a resume's text touches using domain keyword vocabulary."""
    text = resume_text.lower()
    matched = []
    for domain, patterns in _DOMAIN_KEYWORD_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            matched.append(domain)
    return matched or ["General"]

# ============ LOCAL ATS CATEGORY ANALYSIS ============
# Transparent, rule-based scoring across 7 named categories, computed
# entirely in this codebase (no external API call) - unlike the CUTM
# Gateway's score, every check here is inspectable and documented. Each
# category returns a 0-100 score plus the specific findings that produced
# it, so a user can see exactly why a category scored the way it did.

_ACTION_VERBS = [
    'led', 'built', 'developed', 'designed', 'managed', 'implemented',
    'achieved', 'increased', 'decreased', 'reduced', 'created', 'launched',
    'optimized', 'improved', 'delivered', 'architected', 'automated',
    'streamlined', 'mentored', 'coordinated', 'negotiated', 'spearheaded',
    'drove', 'established', 'executed', 'generated', 'resolved', 'scaled',
]
_CLICHE_PHRASES = [
    'hard worker', 'hardworking', 'team player', 'go-getter', 'go getter',
    'detail-oriented', 'detail oriented', 'results-driven', 'results driven',
    'think outside the box', 'self-starter', 'self starter',
    'excellent communication skills', 'fast learner', 'people person',
    'responsible for', 'duties included', 'dynamic individual',
]
_SECTION_PATTERNS = {
    'Contact Info': r'\b(email|phone|linkedin)\b|[\w.+-]+@[\w-]+\.[\w.-]+',
    'Summary/Objective': r'\b(summary|objective|profile)\b',
    'Experience': r'\b(experience|employment history|work history)\b',
    'Education': r'\b(education|academic|university|college|b\.?tech|degree)\b',
    'Skills': r'\b(skills|technologies|technical skills)\b',
    'Projects': r'\bprojects?\b',
    'Certifications': r'\b(certifications?|certified)\b',
}
_QUANTIFIED_PATTERN = re.compile(
    r'\d+(\.\d+)?\s*(%|percent|x|k|m|million|billion|users|customers|hours|days|weeks|months|years|\$|rs\.?|₹|€|£)',
    re.IGNORECASE
)
_BIAS_DISCLOSURE_PATTERNS = {
    'Date of birth / age': r'\b(date of birth|d\.?o\.?b\.?|age\s*[:\-]?\s*\d{1,2}\b)',
    'Marital status': r'\b(marital status|married|single|divorced)\b',
    'Religion': r'\b(religion|hindu|muslim|christian|sikh|buddhist)\b',
    'Gender': r'\b(gender\s*[:\-]|sex\s*[:\-]\s*(male|female))\b',
    'Nationality/Photo': r'\b(nationality|photograph attached|photo attached)\b',
}
_DATE_RANGE_PATTERN = re.compile(
    r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})\s*'
    r'(?:[-–—to]+)\s*'
    r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4}|present|current)',
    re.IGNORECASE
)
_SENIOR_LANGUAGE = r'\b(senior|lead|principal|staff engineer|head of|director|\d{2}\+?\s*years)\b'
_ENTRY_LANGUAGE = r'\b(fresher|entry[\s-]level|recent graduate|intern(ship)?|0-1 years?|no experience)\b'


def _parse_resume_years_of_experience(text: str) -> float:
    """Best-effort estimate of total years of experience from date ranges
    like 'Jan 2021 - Present' or '2019 - 2023'. Heuristic, not exact -
    overlapping/concurrent roles aren't deduplicated."""
    total_months = 0
    for m in _DATE_RANGE_PATTERN.finditer(text):
        start_raw, end_raw = m.group(1), m.group(2)
        start_year = re.search(r'\d{4}', start_raw)
        if not start_year:
            continue
        start_year = int(start_year.group())
        if end_raw.lower() in ('present', 'current'):
            end_year = datetime.now().year
        else:
            end_year_match = re.search(r'\d{4}', end_raw)
            if not end_year_match:
                continue
            end_year = int(end_year_match.group())
        if 1980 <= start_year <= end_year <= datetime.now().year + 1:
            total_months += (end_year - start_year) * 12
    return round(total_months / 12, 1)


def analyze_resume_categories(resume_text: str) -> Dict[str, Any]:
    """Score a resume across 7 categories: Content, Sections, ATS Essentials,
    HR Red Flags, Discrimination (bias-disclosure risk), Seniority
    (consistency), and Tailoring. Entirely rule-based and local - no
    external API call, so every score is traceable to a specific check."""
    text = resume_text or ""
    text_lower = text.lower()
    word_count = len(text.split())
    categories: Dict[str, Dict[str, Any]] = {}

    # ---- Content: action verbs, quantified achievements, cliches ----
    action_verb_hits = sum(1 for v in _ACTION_VERBS if re.search(rf'\b{v}\b', text_lower))
    quantified_hits = len(_QUANTIFIED_PATTERN.findall(text))
    cliche_hits = [p for p in _CLICHE_PHRASES if p in text_lower]
    content_score = min(100, action_verb_hits * 6 + quantified_hits * 8) - len(cliche_hits) * 5
    content_score = max(0, min(100, content_score))
    content_findings = [
        f"{action_verb_hits} strong action verb(s) found",
        f"{quantified_hits} quantified achievement(s) found (numbers/%/metrics)",
    ]
    if cliche_hits:
        content_findings.append(f"Cliche phrase(s) to replace with specifics: {', '.join(cliche_hits)}")
    categories['content'] = {"score": content_score, "findings": content_findings}

    # ---- Sections: standard resume sections present ----
    sections_found = [name for name, pat in _SECTION_PATTERNS.items() if re.search(pat, text_lower)]
    sections_missing = [name for name in _SECTION_PATTERNS if name not in sections_found]
    sections_score = round(len(sections_found) / len(_SECTION_PATTERNS) * 100)
    sections_findings = [f"Found: {', '.join(sections_found) or 'none'}"]
    if sections_missing:
        sections_findings.append(f"Missing: {', '.join(sections_missing)}")
    categories['sections'] = {"score": sections_score, "findings": sections_findings}

    # ---- ATS Essentials: parsability basics ----
    has_email = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text))
    has_phone = bool(re.search(r'(\+?\d[\d\s\-()]{8,}\d)', text))
    too_short = word_count < 100
    too_long = word_count > 1500
    essentials_score = 100
    essentials_findings = []
    if not has_email:
        essentials_score -= 30
        essentials_findings.append("No email address detected")
    if not has_phone:
        essentials_score -= 20
        essentials_findings.append("No phone number detected")
    if too_short:
        essentials_score -= 30
        essentials_findings.append(f"Resume is very short ({word_count} words) - ATS parsers may see too little content")
    if too_long:
        essentials_score -= 15
        essentials_findings.append(f"Resume is very long ({word_count} words) - consider trimming to 1-2 pages")
    if not essentials_findings:
        essentials_findings.append("Email, phone, and reasonable length all present")
    categories['ats_essentials'] = {"score": max(0, essentials_score), "findings": essentials_findings}

    # ---- HR Red Flags: short tenures, no clear dates ----
    date_ranges = _DATE_RANGE_PATTERN.findall(text)
    red_flag_findings = []
    red_flag_score = 100
    if not date_ranges:
        red_flag_score -= 20
        red_flag_findings.append("No clear employment date ranges detected - harder for a recruiter to verify timeline")
    unprofessional_email = re.search(
        r'[\w.+-]*(sexy|cool|lol|xxx|hot|cute|baby|killer)[\w.+-]*@', text_lower
    )
    if unprofessional_email:
        red_flag_score -= 25
        red_flag_findings.append("Email address may read as unprofessional to a recruiter")
    if not red_flag_findings:
        red_flag_findings.append("No obvious red flags detected in this heuristic scan")
    categories['hr_red_flags'] = {"score": max(0, red_flag_score), "findings": red_flag_findings}

    # ---- Discrimination: bias-risk personal disclosures ----
    # Standard resume-writing guidance is to OMIT these to reduce
    # unconscious-bias risk in screening - their presence is a deduction,
    # not their absence.
    disclosures_found = [
        label for label, pat in _BIAS_DISCLOSURE_PATTERNS.items()
        if re.search(pat, text_lower)
    ]
    discrimination_score = max(0, 100 - len(disclosures_found) * 25)
    if disclosures_found:
        discrimination_findings = [
            f"Consider removing: {', '.join(disclosures_found)} (reduces unconscious-bias risk in screening)"
        ]
    else:
        discrimination_findings = ["No age/marital-status/religion/gender/nationality disclosures detected - good"]
    categories['discrimination'] = {"score": discrimination_score, "findings": discrimination_findings}

    # ---- Seniority: does the language match the inferred experience level ----
    years = _parse_resume_years_of_experience(text)
    has_senior_language = bool(re.search(_SENIOR_LANGUAGE, text_lower))
    has_entry_language = bool(re.search(_ENTRY_LANGUAGE, text_lower))
    seniority_score = 100
    seniority_findings = [f"Estimated experience from date ranges: ~{years} year(s)"]
    if has_senior_language and years < 2:
        seniority_score -= 40
        seniority_findings.append("Uses senior-level language (e.g. 'Senior'/'Lead') but detected experience is under 2 years")
    if has_entry_language and years >= 4:
        seniority_score -= 40
        seniority_findings.append("Uses entry-level language (e.g. 'Fresher'/'Intern') but detected experience is 4+ years")
    if not (has_senior_language and years < 2) and not (has_entry_language and years >= 4):
        seniority_findings.append("Language and estimated experience level appear consistent")
    categories['seniority'] = {"score": max(0, seniority_score), "findings": seniority_findings}

    # ---- Tailoring: domain-specific keyword density vs. generic filler ----
    domains = extract_resume_keywords(text)
    domain_specific = [d for d in domains if d != "General"]
    tailoring_score = min(100, len(domain_specific) * 30 + 30) - len(cliche_hits) * 5
    tailoring_score = max(0, min(100, tailoring_score))
    tailoring_findings = [
        f"Detected domain focus: {', '.join(domain_specific) if domain_specific else 'None - resume reads as generic'}"
    ]
    if cliche_hits:
        tailoring_findings.append(f"{len(cliche_hits)} generic filler phrase(s) reduce tailoring - use specific skills/tools instead")
    categories['tailoring'] = {"score": tailoring_score, "findings": tailoring_findings}

    overall_score = round(sum(c["score"] for c in categories.values()) / len(categories))

    return {"overall_score": overall_score, "categories": categories}


def build_job_text(job: Dict[str, Any]) -> str:
    """Build searchable text from a job object for TF-IDF matching.
    Title is repeated to weight it more heavily than the other short
    fields, and the full description (when a scraper provided one) is
    appended last so a resume's experience/projects/skills content has
    actual job content to match against, not just a title and a few tags."""
    parts = [
        job.get("title") or "",
        job.get("title") or "",
        job.get("company") or "",
        job.get("category") or "",
        job.get("job_type") or "",
        job.get("work_type") or "",
        job.get("location") or "",
        " ".join(job.get("domains") or []),
        job.get("description") or "",
    ]
    return " ".join(p for p in parts if p)

def score_job_match(resume_text: str, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score and rank jobs against resume text using TF-IDF + cosine similarity."""
    if not jobs:
        return []

    job_texts = [build_job_text(j) for j in jobs]
    corpus = [resume_text] + job_texts

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_features=5000,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)

    resume_vec = tfidf_matrix[0:1]
    job_vecs = tfidf_matrix[1:]

    similarities = cosine_similarity(resume_vec, job_vecs)[0]

    scored = []
    for job, sim in zip(jobs, similarities):
        job_copy = dict(job)
        job_copy["match_score"] = round(float(sim) * 100, 1)
        scored.append(job_copy)

    scored.sort(key=lambda j: j["match_score"], reverse=True)
    return scored

# ============ API ENDPOINTS ============

@app.route("/api/resources/fetch", methods=["POST"])
@limiter.limit("5 per minute")
def fetch_resources() -> Any:
    """Pull the EnggRoom resource index (discipline/resource-type/title/link
    metadata only - not the underlying project content) and store it."""
    try:
        resources = enggroom_scraper.scrape_enggroom_resources()
        result = save_resources_to_db(resources, current_user_email())
        if resources and result["saved"] == 0:
            # Nothing persisted at all - almost always the database, so
            # report an outage instead of a cheerful "0 saved".
            raise DatabaseUnavailableError("Could not persist any resources")
        return jsonify({
            "success": True,
            "fetched": len(resources),
            "saved": result["saved"],
            "failed": result["failed"],
        })
    except (HTTPException, DatabaseUnavailableError):
        raise
    except Exception as e:
        logger.error(f"Failed to fetch resources: {e}")
        return jsonify({"success": False, "error": "Failed to fetch resources. Please try again."}), 500


@app.route("/api/resources", methods=["GET"])
def get_resources() -> Any:
    """List the stored resource index, optionally filtered by discipline."""
    try:
        discipline = request.args.get("discipline", "")
        resources = load_resources_from_db(current_user_email())
        if discipline:
            resources = [r for r in resources if r.get("discipline") == discipline]
        return jsonify({"success": True, "resources": resources, "total": len(resources)})
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to get resources: {e}")
        return jsonify({"success": False, "error": "Failed to load resources. Please try again."}), 500


@app.route("/api/hackathons/fetch", methods=["POST"])
@limiter.limit("5 per minute")
def fetch_hackathons() -> Any:
    """Pull currently-open hackathons from Devpost's public API and store
    them."""
    try:
        hackathons = hackathon_scraper.scrape_devpost_hackathons()
        result = save_hackathons_to_db(hackathons, current_user_email())
        if hackathons and result["saved"] == 0:
            raise DatabaseUnavailableError("Could not persist any hackathons")
        return jsonify({
            "success": True,
            "fetched": len(hackathons),
            "saved": result["saved"],
            "failed": result["failed"],
        })
    except (HTTPException, DatabaseUnavailableError):
        raise
    except Exception as e:
        logger.error(f"Failed to fetch hackathons: {e}")
        return jsonify({"success": False, "error": "Failed to fetch hackathons. Please try again."}), 500


@app.route("/api/hackathons", methods=["GET"])
def get_hackathons() -> Any:
    """List the stored hackathon listings."""
    try:
        hackathons = load_hackathons_from_db(current_user_email())
        return jsonify({"success": True, "hackathons": hackathons, "total": len(hackathons)})
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to get hackathons: {e}")
        return jsonify({"success": False, "error": "Failed to load hackathons. Please try again."}), 500


@app.route("/api/sources", methods=["GET"])
def get_sources() -> Any:
    """Get all available sources, grouped to match remote_job_scraper.SCRAPERS"""
    sources = {
        "remote_boards": [
            {"id": "remotive", "name": "Remotive", "status": "✅"},
            {"id": "remoteok", "name": "RemoteOK", "status": "✅"},
            {"id": "himalayas", "name": "Himalayas", "status": "✅"},
            {"id": "jobicy", "name": "Jobicy", "status": "✅"},
            {"id": "weworkremotely", "name": "WeWorkRemotely", "status": "✅"},
        ],
        "all_jobs": [
            {"id": "arbeitnow", "name": "Arbeitnow", "status": "✅"},
            {"id": "adzuna", "name": "Adzuna (India)", "status": "✅",
             "note": "Requires free ADZUNA_APP_ID/ADZUNA_APP_KEY in .env"},
        ],
        "freshers": [
            {"id": "internshala", "name": "Internshala", "status": "✅"},
            {"id": "unstop", "name": "Unstop", "status": "✅"},
            {"id": "firstnaukri", "name": "FirstNaukri", "status": "✅"},
            {"id": "angellist", "name": "AngelList/Wellfound", "status": "✅"},
        ],
        "developer_jobs": [
            {"id": "devto", "name": "Dev.to", "status": "✅"},
            {"id": "upwork", "name": "Upwork", "status": "✅"},
            {"id": "toptal", "name": "Toptal", "status": "✅"},
        ],
        "career_pages": [
            {"id": "greenhouse", "name": "Greenhouse", "status": "✅"},
            {"id": "lever", "name": "Lever", "status": "✅"},
            {"id": "ashby", "name": "Ashby", "status": "✅"},
        ],
        "no_public_api": [
            {"id": "hackerrank", "name": "HackerRank", "status": "⚠️",
             "note": "No public job-listing API - login-gated, client-rendered. Selecting this returns 0 jobs."},
            {"id": "geeksforgeeks", "name": "GeeksforGeeks", "status": "⚠️",
             "note": "No public job-listing API - login-gated, JS-rendered. Selecting this returns 0 jobs."},
            {"id": "naipunyam", "name": "Naipunyam (AP Govt)", "status": "⚠️",
             "note": "No public job-listing API found - JS-rendered with no visible server data. Selecting this returns 0 jobs."},
        ],
    }
    return jsonify(sources)


@app.route("/api/fetch", methods=["POST"])
@limiter.limit("5 per minute")
def fetch_jobs() -> Any:
    """Fetch jobs from selected sources and store in file"""
    try:
        owner_email = current_user_email()
        # silent=True + or {}: a missing/invalid JSON body used to raise
        # AttributeError on data.get() and surface as a generic 500.
        data = request.get_json(silent=True) or {}
        selected = data.get("sources", [])
        if "sources" not in data:
            return jsonify({"success": False, "error": "No sources provided. Expected {\"sources\": [...]}."}), 400

        sources = {s.__name__.replace("scrape_", ""): s for s in rjs.SCRAPERS}
        enabled = [sources[name] for name in selected if name in sources]

        all_jobs = []
        status = {}

        logger.info(f"Fetching jobs from {len(enabled)} sources...")

        for scraper in enabled:
            name = scraper.__name__.replace("scrape_", "")
            try:
                logger.info(f"Scraping {name}...")
                results = scraper()
                all_jobs.extend(results)
                status[name] = {"success": True, "count": len(results)}
                logger.info(f"  {name}: {len(results)} jobs fetched")
            except Exception as e:
                status[name] = {"success": False, "error": str(e)[:50]}
                logger.error(f"  {name}: Failed - {str(e)[:40]}")

        jobs = rjs.dedupe(all_jobs)
        logger.info(f"Total unique jobs after deduplication: {len(jobs)}")

        # Store both fresher and experienced roles - the fresher/experienced
        # split now happens at query/match time (see is_fresher_job /
        # is_experienced_job), not by discarding one bucket at fetch time.
        fresher_count = sum(1 for j in jobs if is_fresher_job(j))
        experienced_count = len(jobs) - fresher_count
        logger.info(f"Fresher/internship: {fresher_count}, Experienced: {experienced_count}")

        # Add timestamps and domain detection to new jobs
        for job in jobs:
            if 'added_at' not in job:
                job['added_at'] = datetime.now().isoformat()
            # Add domain detection
            if 'domains' not in job:
                job['domains'] = detect_job_domain(job)

        # Save to database
        save_result = save_jobs_to_db(jobs, owner_email)
        if jobs and save_result["saved"] == 0:
            # Every single insert failed. That means the database, not the
            # job data (every field is defensively truncated), so report an
            # outage instead of returning "success: true, 0 saved".
            raise DatabaseUnavailableError("Could not persist any fetched jobs")
        if save_result["failed"]:
            logger.warning(
                f"{save_result['failed']} of {len(jobs)} jobs failed to save "
                f"(see per-job 'Failed to insert job' errors above for why)"
            )

        stats = get_statistics(owner_email)

        return jsonify({
            "success": True,
            "jobs_count": len(jobs),
            "inserted": len(jobs),
            "skipped": 0,
            "total_stored": save_result["saved"],
            "failed_to_store": save_result["failed"],
            "fresher_count": fresher_count,
            "experienced_count": experienced_count,
            "status": status,
            "stats": stats,
            "last_fetch": datetime.now().isoformat()
        })

    except HTTPException:
        # Let Werkzeug/Flask exceptions (e.g. 413 Payload Too Large from a
        # request body over MAX_CONTENT_LENGTH) reach their real error
        # handler instead of being masked as a generic 500 here.
        raise
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch jobs: {e}")
        return jsonify({"success": False, "error": "Failed to fetch jobs. Please try again."}), 500


@app.route("/api/match-resume", methods=["POST"])
@limiter.limit("10 per minute")
def match_resume() -> Any:
    """Upload a resume, extract text, score/rank current jobs against it.
    Nothing about the resume is persisted — parsed in memory, discarded
    after the response is built."""
    try:
        if "resume" not in request.files:
            return jsonify({"success": False, "error": "No resume file provided (expected form field 'resume')"}), 400

        file_storage = request.files["resume"]
        if not file_storage or file_storage.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        original_filename = file_storage.filename
        try:
            resume_text = extract_text_from_resume(file_storage)
        except ValueError as ve:
            logger.warning(f"Resume extraction failed for '{original_filename}': {ve}")
            return jsonify({"success": False, "error": str(ve)}), 400

        logger.info(f"Resume '{original_filename}': extracted {len(resume_text)} characters")
        # First 150 chars only, and only at DEBUG level - resume content is
        # personal data, so this never appears in the default INFO-level
        # console output, only if someone explicitly turns DEBUG logging on.
        logger.debug(f"Resume '{original_filename}' text preview: {resume_text[:150]!r}")

        if len(resume_text) < MIN_RESUME_TEXT_CHARS:
            logger.warning(f"Resume '{original_filename}': only {len(resume_text)} chars extracted, below the {MIN_RESUME_TEXT_CHARS}-char minimum")
            return jsonify({
                "success": False,
                "error": "Could not extract enough readable text from this resume. "
                         "Try a different file (avoid scanned/image-only PDFs)."
            }), 422

        # The candidate must say whether they're a fresher or experienced,
        # since that determines which pool of stored jobs (fresher-only vs
        # experienced-only) they get matched against - accepted from either
        # the form body or a query param for flexibility.
        experience_level = (request.form.get("experience_level")
                             or request.args.get("experience_level")
                             or "").strip().lower()
        if experience_level not in ("fresher", "experienced"):
            return jsonify({
                "success": False,
                "error": "experience_level is required and must be 'fresher' or 'experienced'"
            }), 400

        resume_domains = extract_resume_keywords(resume_text)
        logger.info(f"Resume '{original_filename}': detected domains {resume_domains}, experience_level={experience_level}")

        all_jobs = load_jobs_from_db(current_user_email())
        if experience_level == "fresher":
            candidate_jobs = [j for j in all_jobs if is_fresher_job(j)]
        else:
            candidate_jobs = [j for j in all_jobs if is_experienced_job(j)]

        if not candidate_jobs:
            logger.info(f"Resume '{original_filename}': no {experience_level} jobs in the DB to match against")
            return jsonify({
                "success": True,
                "matches": [],
                "total_jobs_considered": 0,
                "experience_level": experience_level,
                "resume_domains": resume_domains,
                "message": f"No {experience_level} jobs available yet. Fetch jobs first, then upload your resume."
            })

        # Validate and bound top_n parameter
        try:
            top_n = int(request.args.get("top_n", 20))
            if top_n < 1:
                top_n = 20
            if top_n > 100:
                top_n = 100  # Cap at 100 to prevent performance issues
        except (ValueError, TypeError):
            top_n = 20
            logger.warning("Invalid top_n parameter, using default value of 20")

        scored = score_job_match(resume_text, candidate_jobs)
        top_matches = scored[:top_n]

        if top_matches:
            top = top_matches[0]
            logger.info(
                f"Resume '{original_filename}': matched against {len(candidate_jobs)} {experience_level} jobs, "
                f"top result '{top['title']}' @ {top.get('company')} ({top['match_score']}%)"
            )

        return jsonify({
            "success": True,
            "matches": top_matches,
            "total_jobs_considered": len(candidate_jobs),
            "experience_level": experience_level,
            "resume_domains": resume_domains,
            "resume_chars_extracted": len(resume_text)
        })

    except HTTPException:
        raise
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to match resume: {e}")
        return jsonify({"success": False, "error": "Failed to process resume. Please try again."}), 500


@app.route("/api/ats-score", methods=["POST"])
@limiter.limit("10 per minute")
def ats_score() -> Any:
    """Upload a resume and get an ATS compatibility score + improvement
    feedback from the CUTM AI Gateway. The file is forwarded to the
    external service and otherwise never persisted, same as résumé
    matching. The external endpoint isn't confirmed live as of this
    writing - a failure here (unreachable/timeout/unexpected response)
    surfaces as a clear 502, not a generic 500."""
    try:
        if "resume" not in request.files:
            return jsonify({"success": False, "error": "No resume file provided (expected form field 'resume')"}), 400

        file_storage = request.files["resume"]
        if not file_storage or file_storage.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        filename = secure_filename(file_storage.filename or "")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_RESUME_EXTENSIONS:
            return jsonify({
                "success": False,
                "error": f"Unsupported file type: .{ext}. Allowed: {', '.join(ALLOWED_RESUME_EXTENSIONS)}"
            }), 400

        raw_bytes = file_storage.read()
        if not raw_bytes:
            return jsonify({"success": False, "error": "Uploaded file is empty"}), 400

        try:
            result = evaluate_ats_score(filename, raw_bytes)
        except ValueError as ve:
            logger.warning(f"ATS scoring failed for '{filename}': {ve}")
            return jsonify({"success": False, "error": str(ve)}), 502

        # Local, rule-based category breakdown (Content/Sections/ATS
        # Essentials/HR Red Flags/Discrimination/Seniority/Tailoring) -
        # computed independently of the external service, so it stays
        # available even if that service's own categories differ or
        # change. Re-extracts text from the same bytes already read above
        # (a fresh in-memory FileStorage, since the original stream was
        # already consumed by file_storage.read()).
        local_analysis = None
        try:
            text_fs = FileStorage(stream=io.BytesIO(raw_bytes), filename=filename)
            resume_text = extract_text_from_resume(text_fs)
            local_analysis = analyze_resume_categories(resume_text)
        except Exception as e:
            logger.warning(f"Local ATS category analysis failed for '{filename}': {e}")

        logger.info(f"ATS score for '{filename}': {result['score']}")
        return jsonify({
            "success": True,
            "score": result["score"],
            "feedback": result["feedback"],
            "local_analysis": local_analysis,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ATS score: {e}")
        return jsonify({"success": False, "error": "Failed to get ATS score. Please try again."}), 500


@app.route("/api/jobs", methods=["GET"])
def get_jobs() -> Any:
    """Get filtered jobs from file storage"""
    try:
        keyword = request.args.get("keyword", "").lower()
        work_type = request.args.get("work_type", "")
        country = request.args.get("country", "")
        job_type = request.args.get("job_type", "")
        sources = request.args.get("sources", "")
        domain = request.args.get("domain", "")
        # "fresher" | "experienced" | "" (all). Also accept the old boolean
        # ?fresher=true param for backward compatibility.
        experience_level = request.args.get("experience_level", "").lower()
        if not experience_level and request.args.get("fresher", "").lower() == "true":
            experience_level = "fresher"

        # Bounds-check page/limit: negative page numbers previously fed
        # Python's negative-index list slicing and silently returned
        # unrelated jobs instead of an empty page or an error.
        try:
            page = max(int(request.args.get("page", 1)), 1)
            limit = min(max(int(request.args.get("limit", 20)), 1), 1000)
        except (ValueError, TypeError):
            page, limit = 1, 20

        all_jobs = load_jobs_from_db(current_user_email())

        # Filter by sources if specified (can be comma-separated)
        if sources:
            source_list = [s.strip() for s in sources.split(",")]
            all_jobs = [j for j in all_jobs if j.get('source') in source_list]

        # Filter by domain if specified
        if domain and domain != "All":
            all_jobs = [j for j in all_jobs if domain in j.get('domains', [])]

        # Filter onsite jobs to Pan-India only
        if work_type and work_type.lower() == "onsite":
            india_keywords = ['india', 'bangalore', 'mumbai', 'delhi', 'hyderabad', 'pune',
                            'kolkata', 'chennai', 'ahmedabad', 'jaipur', 'lucknow', 'gurgaon',
                            'noida', 'gurugram', 'pan-india', 'pan india', 'across india']
            all_jobs = [j for j in all_jobs if any(
                keyword in (j.get('location', '') + ' ' + j.get('country', '')).lower()
                for keyword in india_keywords
            )]

        result = filter_jobs(all_jobs, keyword, work_type, country, job_type, experience_level, page, limit)
        result["from_cache"] = False
        result["storage"] = "mysql"

        return jsonify(result)

    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to get jobs: {e}")
        return jsonify({"jobs": [], "total": 0, "page": 1, "pages": 0, "error": "Failed to load jobs. Please try again."}), 500


@app.route("/api/stats", methods=["GET"])
def get_stats() -> Any:
    """Get job statistics from database"""
    try:
        stats = get_statistics(current_user_email())
        stats["from_cache"] = False
        stats["storage"] = "mysql"
        return jsonify(stats)
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        return jsonify({"error": "Failed to load statistics. Please try again."}), 500


@app.route("/api/analytics", methods=["GET"])
def analytics() -> Any:
    """Get dashboard analytics: summary counts, jobs-added time series,
    domain/work-type distribution, and top sources/countries/companies."""
    try:
        days = min(max(int(request.args.get("days", 14)), 1), 90)
        top_n = min(max(int(request.args.get("top_n", 10)), 1), 50)
    except (ValueError, TypeError):
        days, top_n = 14, 10

    try:
        data = get_analytics(current_user_email(), days=days, top_n=top_n)
        data["success"] = True
        return jsonify(data)
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        return jsonify({"success": False, "error": "Failed to load analytics. Please try again."}), 500


# Characters that Excel/LibreOffice/Google Sheets interpret as the start of
# a formula if they're the first character of a CSV cell. Job title/company/
# description come from 17 external, uncontrolled job-board listings - a
# malicious or compromised listing titled e.g. '=HYPERLINK("http://evil.com")'
# would execute as a live formula for anyone who exports and opens the CSV.
_CSV_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")

def _csv_safe(value: Any) -> Any:
    """Neutralize formula-injection payloads (CWE-1236) by prefixing a
    leading quote, which Excel/Sheets render literally instead of evaluating."""
    text = str(value) if value is not None else ""
    if text.startswith(_CSV_FORMULA_TRIGGER_CHARS):
        return "'" + text
    return value

@app.route("/api/export", methods=["GET"])
def export_jobs() -> Any:
    """Export jobs to CSV or JSON"""
    try:
        fmt = request.args.get("format", "csv")
        jobs = load_jobs_from_db(current_user_email())

        if fmt == "csv":
            import csv
            import io

            output = io.StringIO()
            fieldnames = rjs.FIELDS
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()

            for job in jobs:
                row = {field: _csv_safe(job.get(field, '')) for field in fieldnames}
                writer.writerow(row)

            return output.getvalue(), 200, {
                "Content-Disposition": "attachment; filename=jobs.csv",
                "Content-Type": "text/csv"
            }

        elif fmt == "json":
            return jsonify(jobs)

        else:
            return jsonify({"error": f"Unsupported export format: {fmt}. Use 'csv' or 'json'."}), 400

    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to export jobs: {e}")
        return jsonify({"error": "Failed to export jobs. Please try again."}), 500


@app.route("/api/db-info", methods=["GET"])
def db_info() -> Any:
    """Get database information. Actually pings MySQL first so an outage is
    reported as 503 "unreachable" instead of a cheerful 200 "✓ Active" with
    zero jobs (which used to make a broken database look like an empty one)."""
    try:
        if not _ping_db():
            return jsonify({
                "success": False,
                "database_engine": "MySQL",
                "status": "✗ Unreachable",
                "host": MYSQL_CONFIG['host'],
                "database": MYSQL_CONFIG['database'],
                "error": "Cannot connect to the database.",
            }), 503

        owner_email = current_user_email()
        jobs = load_jobs_from_db(owner_email)
        stats = get_statistics(owner_email)

        return jsonify({
            "success": True,
            "database_engine": "MySQL",
            "status": "✓ Active",
            "total_jobs": len(jobs),
            "statistics": stats,
            "host": MYSQL_CONFIG['host'],
            "database": MYSQL_CONFIG['database'],
            "note": "Data stored in MySQL database."
        })
    except DatabaseUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return jsonify({"error": "Failed to load database info. Please try again.", "status": "✗ Error"}), 500


@app.route("/api/clear-jobs", methods=["DELETE"])
@limiter.limit("3 per minute")
def clear_jobs() -> Any:
    """Clear the signed-in user's own jobs only - never another user's."""
    try:
        owner_email = current_user_email()
        conn = get_db_connection()
        if not conn:
            raise DatabaseUnavailableError("Could not connect to the database")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE owner_email = %s", (owner_email,))
        conn.commit()
        cursor.close()
        conn.close()
        invalidate_jobs_cache(owner_email)
        return jsonify({"success": True, "message": "All jobs cleared"})
    except (HTTPException, DatabaseUnavailableError):
        raise
    except Exception as e:
        logger.error(f"Failed to clear jobs: {e}")
        return jsonify({"success": False, "error": "Failed to clear jobs. Please try again."}), 500


@app.route("/api/test-alert", methods=["POST"])
@limiter.limit("5 per hour")
def test_alert() -> Any:
    """Test alert configuration"""
    try:
        import alerts
        data = request.get_json(silent=True) or {}
        alert_config = data.get("config") or {}
        if not alert_config:
            return jsonify({
                "success": False,
                "error": "No alert channels configured. Provide a telegram, email, or slack config."
            }), 400

        test_job = {
            "title": "Test Python Developer Position",
            "company": "Tech Company",
            "country": "India",
            "work_type": "Remote",
            "job_type": "Full-time",
            "salary": "50-70 LPA",
            "date": datetime.now().isoformat(),
            "source": "Test",
            "url": "https://example.com/job"
        }

        results = alerts.send_alert([test_job], alert_config)

        return jsonify({
            "success": True,
            "message": "Test alerts sent",
            "results": results
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send test alert: {e}")
        return jsonify({"success": False, "error": "Failed to send test alert. Check your alert configuration."}), 500


@app.route("/api/cache-info", methods=["GET"])
def cache_info() -> Any:
    """Get in-memory jobs cache information for the signed-in user's own entry."""
    owner_email = current_user_email()
    with _jobs_cache_lock:
        entry = _jobs_cache.get(owner_email)
        has_data = entry is not None
        age = time.time() - entry["timestamp"] if has_data else None

    return jsonify({
        "cache": {
            "status": "active" if has_data else "empty",
            "ttl_seconds": JOBS_CACHE_TTL_SECONDS,
            "age_seconds": round(age, 1) if age is not None else None,
            "cached_jobs": len(entry["data"]) if has_data else 0,
            "note": "In-memory cache for jobs table reads, keyed per user. Redis is not used."
        },
        "storage": "mysql"
    })


@app.route("/api/cache-clear", methods=["DELETE"])
def cache_clear() -> Any:
    """Manually invalidate the signed-in user's own in-memory jobs cache entry"""
    invalidate_jobs_cache(current_user_email())
    return jsonify({"success": True, "message": "Jobs cache cleared"})


@app.route("/api/scheduler-status", methods=["GET"])
def scheduler_status() -> Any:
    """Get scheduler configuration"""
    try:
        config_file = "scraper_config.json"
        config = {}

        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)

        return jsonify({
            "status": "active" if os.path.exists(config_file) else "not configured",
            "config": config,
            "config_file": config_file,
            "note": "Storage: MySQL. Scheduler config (if any) is separate from the jobs database."
        })
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return jsonify({"error": "Failed to load scheduler status. Please try again."}), 500


@app.route("/", methods=["GET"])
def index() -> Any:
    """Serve web UI"""
    try:
        with open("index.html", encoding="utf-8") as f:
            content = f.read()
        return content, 200, {"Content-Type": "text/html"}
    except FileNotFoundError:
        logger.error("index.html not found")
        return "Error: index.html not found", 404
    except Exception as e:
        logger.error(f"Error loading index.html: {e}")
        return f"Error loading page: {str(e)}", 500


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Job Portal API Starting (MySQL)...")
    logger.info("=" * 60)

    # Initialize database
    db_ready = init_db()
    if db_ready:
        logger.info(f"Storage: MySQL Database")
        logger.info(f"Host: {MYSQL_CONFIG['host']}")
        logger.info(f"Database: {MYSQL_CONFIG['database']}")
        logger.info(f"User: {MYSQL_CONFIG['user']}")
        logger.info(f"Server: http://localhost:5000")
        logger.info("=" * 60)
        logger.info("API Ready to serve requests")
    else:
        # Do NOT exit here. Previously a database problem meant the process
        # died at startup with no page to look at. Starting degraded lets
        # the UI load, sign-in work, /api/health report "degraded", and data
        # endpoints return a clear 503 - which is far easier to diagnose
        # than a server that silently isn't running.
        logger.error("Database initialization failed. Please check:")
        logger.error("  - MySQL server is running")
        logger.error("  - Database credentials in .env file are correct")
        logger.error("  - Port 3306 is accessible")
        logger.warning(
            "Starting anyway in DEGRADED mode: the page and sign-in will "
            "load, /api/health will report the database as down, and data "
            "endpoints will return HTTP 503 instead of empty results. "
            "Fix the config above and restart to recover."
        )
        logger.info(f"Server: http://localhost:5000")
        logger.info("=" * 60)

    # Debug mode enables Werkzeug's interactive debugger, which allows
    # arbitrary code execution from the browser on an unhandled
    # exception. Default to off; only enable via explicit opt-in in .env.
    flask_debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    if flask_debug:
        logger.warning("FLASK_DEBUG is enabled - do not expose this server beyond localhost")
    # threaded=True: with 17 selectable scraper sources (several doing
    # multi-page pagination with time.sleep(1) between pages), a single
    # /api/fetch call can now take minutes. Werkzeug's dev server is
    # single-threaded by default, which would freeze the ENTIRE app -
    # every other endpoint, even the static page - for that whole
    # duration. Safe to enable here since the one piece of shared
    # mutable state (the in-memory jobs cache) already uses its own
    # threading.Lock().
    app.run(debug=flask_debug, port=5000, threaded=True)
