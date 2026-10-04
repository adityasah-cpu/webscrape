"""
Job Finder - Corporate API Backend (Flask)
Serves job data from MySQL database

Run:
    python api.py
    Then open http://localhost:5000 in browser
"""

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import remote_job_scraper as rjs
import enggroom_scraper
import json
import re
from datetime import datetime, timedelta
import threading
import time
import os
import mysql.connector
from mysql.connector import Error
from mysql.connector.abstracts import MySQLConnectionAbstract
import io
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from pdfminer.high_level import extract_text as pdf_extract_text
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

# Configure rate limiting to prevent API abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
)

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
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
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

# Resume upload constraints
# jpg/jpeg/png accepted directly for candidates who photograph a paper
# resume rather than scanning it to PDF - OCR is the only way to read those.
ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx", "txt", "jpg", "jpeg", "png"}
MAX_RESUME_SIZE_BYTES = int(os.getenv('MAX_RESUME_SIZE', 5 * 1024 * 1024))  # 5 MB
MIN_RESUME_TEXT_CHARS = int(os.getenv('MIN_RESUME_TEXT', 30))
OCR_MAX_PAGES = int(os.getenv('OCR_MAX_PAGES', 5))  # cap worst-case OCR latency

app.config['MAX_CONTENT_LENGTH'] = MAX_RESUME_SIZE_BYTES

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
JOBS_CACHE_TTL_SECONDS = int(os.getenv('JOBS_CACHE_TTL_SECONDS', 15))
MAX_JOBS_FETCH = int(os.getenv('MAX_JOBS_FETCH', 5000))  # Safety cap on rows loaded per query
_jobs_cache = {"data": None, "timestamp": 0}
_jobs_cache_lock = threading.Lock()

def invalidate_jobs_cache() -> None:
    """Clear the in-memory jobs cache after a write (insert/delete)."""
    with _jobs_cache_lock:
        _jobs_cache["data"] = None
        _jobs_cache["timestamp"] = 0

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
            url VARCHAR(500) UNIQUE,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            domains JSON,
            description TEXT,
            INDEX idx_source (source),
            INDEX idx_work_type (work_type),
            INDEX idx_country (country(100)),
            INDEX idx_url (url)
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
            source VARCHAR(100),
            discipline VARCHAR(100),
            resource_type VARCHAR(100),
            title VARCHAR(255),
            url VARCHAR(500) UNIQUE,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_discipline (discipline),
            INDEX idx_resource_type (resource_type)
        )
        """)
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

def load_jobs_from_db(use_cache: bool = True) -> List[Dict[str, Any]]:
    """Load jobs from MySQL database, with a short-lived in-memory cache to
    avoid repeatedly re-fetching/re-parsing the full table on rapid successive
    requests. Capped at MAX_JOBS_FETCH rows as a safety limit."""
    if use_cache:
        with _jobs_cache_lock:
            age = time.time() - _jobs_cache["timestamp"]
            if _jobs_cache["data"] is not None and age < JOBS_CACHE_TTL_SECONDS:
                return _jobs_cache["data"]

    try:
        conn = get_db_connection()
        if not conn:
            return []

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM jobs ORDER BY added_at DESC LIMIT %s", (MAX_JOBS_FETCH,))
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
            _jobs_cache["data"] = jobs
            _jobs_cache["timestamp"] = time.time()

        return jobs
    except Error as e:
        logger.error(f"Failed to load jobs from database: {e}")
        return []

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
}

def _truncate_for_column(value: Any, column: str) -> Any:
    if value is None:
        return value
    max_len = _COLUMN_MAX_LENGTHS.get(column)
    text = str(value)
    if max_len and len(text) > max_len:
        return text[:max_len]
    return value

def save_jobs_to_db(jobs: List[Dict[str, Any]]) -> Dict[str, int]:
    """Save jobs to MySQL database. Returns {"saved": N, "failed": N} so
    callers can tell actual persistence success from attempted count -
    per-row failures (e.g. a value too long for a column) are caught and
    logged per job, but previously vanished silently since the caller only
    ever saw a bare True/False for the whole batch."""
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
                INSERT INTO jobs (source, title, company, work_type, country, location,
                                 job_type, category, salary, date, start_date, end_date, url,
                                 domains, description, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source = VALUES(source), title = VALUES(title), company = VALUES(company),
                    work_type = VALUES(work_type), country = VALUES(country), location = VALUES(location),
                    job_type = VALUES(job_type), category = VALUES(category), salary = VALUES(salary),
                    date = VALUES(date), start_date = VALUES(start_date), end_date = VALUES(end_date),
                    domains = VALUES(domains), description = VALUES(description), added_at = NOW()
                """
                cursor.execute(insert_query, (
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
        invalidate_jobs_cache()
        return result
    except Error as e:
        logger.error(f"Failed to save jobs to database: {e}")
        result["failed"] = len(jobs) - result["saved"]
        return result
    except Exception as e:
        logger.error(f"Unexpected error while saving jobs: {e}")
        result["failed"] = len(jobs) - result["saved"]
        return result

def save_resources_to_db(resources: List[Dict[str, Any]]) -> Dict[str, int]:
    """Save resource index entries (metadata only) to MySQL."""
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
                    INSERT INTO resources (source, discipline, resource_type, title, url, added_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        source = VALUES(source), discipline = VALUES(discipline),
                        resource_type = VALUES(resource_type), title = VALUES(title),
                        added_at = NOW()
                """, (
                    r.get('source'), r.get('discipline'), r.get('resource_type'),
                    r.get('title'), r.get('url'), datetime.now()
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

def load_resources_from_db() -> List[Dict[str, Any]]:
    """Load all resource index entries from MySQL."""
    try:
        conn = get_db_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM resources ORDER BY discipline, resource_type")
        resources = cursor.fetchall()
        cursor.close()
        conn.close()
        return resources
    except Error as e:
        logger.error(f"Failed to load resources from database: {e}")
        return []

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
DOMAIN_KEYWORDS = {
    'AIML': [
        'ai', 'artificial intelligence', 'machine learning', 'ml', 'deep learning',
        'neural network', 'nlp', 'computer vision', 'llm', 'generative ai', 'chatgpt',
        'tensorflow', 'pytorch', 'data scientist', 'nlp engineer', 'cv engineer',
        'ai engineer', 'ml engineer', 'ai/ml'
    ],
    'Data Analytics': [
        'data analyst', 'analytics', 'data analytics', 'business intelligence',
        'bi developer', 'tableau', 'power bi', 'sql', 'analytics engineer',
        'reporting', 'dashboard', 'data warehouse', 'etl', 'data pipeline'
    ],
    'Blockchain': [
        'blockchain', 'crypto', 'web3', 'solidity', 'smart contract', 'ethereum',
        'defi', 'nft', 'dapp', 'distributed ledger', 'consensus', 'blockchain developer',
        'smart contract developer', 'web3 developer', 'cryptocurrency'
    ],
    'AR VR': [
        'augmented reality', 'virtual reality', 'ar', 'vr', 'metaverse', 'mixed reality',
        'xr', 'immersive', '3d graphics', 'unity', 'unreal engine', 'ar developer',
        'vr developer', 'ar/vr', 'ar vr'
    ],
    'Cybersecurity': [
        'cybersecurity', 'security engineer', 'security analyst', 'infosec', 'pentester',
        'penetration testing', 'ethical hacker', 'soc', 'siem', 'vulnerability', 'malware',
        'incident response', 'security operations', 'network security', 'application security',
        'cloud security', 'security architect'
    ]
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

    start = (page - 1) * limit
    end = start + limit

    return {
        "jobs": filtered[start:end],
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }

def get_statistics() -> Dict[str, Any]:
    """Calculate statistics from jobs"""
    jobs = load_jobs_from_db()

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

def get_analytics(days: int = 14, top_n: int = 10) -> Dict[str, Any]:
    """Aggregate analytics for the dashboard: summary counts, a jobs-added
    time series, domain/work-type distribution, and top sources/countries/
    companies. Built entirely from load_jobs_from_db() (Python-side
    aggregation) so it benefits from the same in-memory cache as other
    endpoints rather than issuing extra DB queries."""
    jobs = load_jobs_from_db()

    if not jobs:
        return {
            "summary": {"total_jobs": 0, "added_today": 0, "added_this_week": 0,
                        "total_companies": 0, "total_sources": 0},
            "jobs_over_time": [],
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

    def top(counts: Dict[str, int], n: int) -> List[Dict[str, Any]]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]
        ]

    jobs_over_time = [
        {"date": day, "count": day_counts[day]}
        for day in sorted(day_counts.keys())
    ]

    return {
        "summary": {
            "total_jobs": len(jobs),
            "added_today": added_today,
            "added_this_week": added_this_week,
            "total_companies": len({j.get('company') for j in jobs if j.get('company')}),
            "total_sources": len({j.get('source') for j in jobs if j.get('source')}),
        },
        "jobs_over_time": jobs_over_time,
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

def extract_resume_keywords(resume_text: str) -> List[str]:
    """Detect which domains a resume's text touches using domain keyword vocabulary."""
    text = resume_text.lower()
    matched = []
    for domain, patterns in _DOMAIN_KEYWORD_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            matched.append(domain)
    return matched or ["General"]

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
        result = save_resources_to_db(resources)
        return jsonify({
            "success": True,
            "fetched": len(resources),
            "saved": result["saved"],
            "failed": result["failed"],
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch resources: {e}")
        return jsonify({"success": False, "error": "Failed to fetch resources. Please try again."}), 500


@app.route("/api/resources", methods=["GET"])
def get_resources() -> Any:
    """List the stored resource index, optionally filtered by discipline."""
    try:
        discipline = request.args.get("discipline", "")
        resources = load_resources_from_db()
        if discipline:
            resources = [r for r in resources if r.get("discipline") == discipline]
        return jsonify({"success": True, "resources": resources, "total": len(resources)})
    except Exception as e:
        logger.error(f"Failed to get resources: {e}")
        return jsonify({"success": False, "error": "Failed to load resources. Please try again."}), 500


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
    }
    return jsonify(sources)


@app.route("/api/fetch", methods=["POST"])
@limiter.limit("5 per minute")
def fetch_jobs() -> Any:
    """Fetch jobs from selected sources and store in file"""
    try:
        data = request.json
        selected = data.get("sources", [])

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
        save_result = save_jobs_to_db(jobs)
        if save_result["failed"]:
            logger.warning(
                f"{save_result['failed']} of {len(jobs)} jobs failed to save "
                f"(see per-job 'Failed to insert job' errors above for why)"
            )

        stats = get_statistics()

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

        all_jobs = load_jobs_from_db()
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
    except Exception as e:
        logger.error(f"Failed to match resume: {e}")
        return jsonify({"success": False, "error": "Failed to process resume. Please try again."}), 500


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

        all_jobs = load_jobs_from_db()

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

    except Exception as e:
        logger.error(f"Failed to get jobs: {e}")
        return jsonify({"jobs": [], "total": 0, "page": 1, "pages": 0, "error": "Failed to load jobs. Please try again."}), 500


@app.route("/api/stats", methods=["GET"])
def get_stats() -> Any:
    """Get job statistics from database"""
    try:
        stats = get_statistics()
        stats["from_cache"] = False
        stats["storage"] = "mysql"
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
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
        data = get_analytics(days=days, top_n=top_n)
        data["success"] = True
        return jsonify(data)
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
        jobs = load_jobs_from_db()

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

    except Exception as e:
        logger.error(f"Failed to export jobs: {e}")
        return jsonify({"error": "Failed to export jobs. Please try again."}), 500


@app.route("/api/db-info", methods=["GET"])
def db_info() -> Any:
    """Get database information"""
    try:
        jobs = load_jobs_from_db()
        stats = get_statistics()

        return jsonify({
            "database_engine": "MySQL",
            "status": "✓ Active",
            "total_jobs": len(jobs),
            "statistics": stats,
            "host": MYSQL_CONFIG['host'],
            "database": MYSQL_CONFIG['database'],
            "note": "Data stored in MySQL database."
        })
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return jsonify({"error": "Failed to load database info. Please try again.", "status": "✗ Error"}), 500


@app.route("/api/clear-jobs", methods=["DELETE"])
@limiter.limit("3 per minute")
def clear_jobs() -> Any:
    """Clear all jobs"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "error": "Database connection failed"}), 500
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs")
        conn.commit()
        cursor.close()
        conn.close()
        invalidate_jobs_cache()
        return jsonify({"success": True, "message": "All jobs cleared"})
    except Exception as e:
        logger.error(f"Failed to clear jobs: {e}")
        return jsonify({"success": False, "error": "Failed to clear jobs. Please try again."}), 500


@app.route("/api/test-alert", methods=["POST"])
@limiter.limit("5 per hour")
def test_alert() -> Any:
    """Test alert configuration"""
    try:
        import alerts
        data = request.json
        alert_config = data.get("config", {})

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
    """Get in-memory jobs cache information"""
    with _jobs_cache_lock:
        has_data = _jobs_cache["data"] is not None
        age = time.time() - _jobs_cache["timestamp"] if has_data else None

    return jsonify({
        "cache": {
            "status": "active" if has_data else "empty",
            "ttl_seconds": JOBS_CACHE_TTL_SECONDS,
            "age_seconds": round(age, 1) if age is not None else None,
            "cached_jobs": len(_jobs_cache["data"]) if has_data else 0,
            "note": "In-memory cache for jobs table reads. Redis is not used."
        },
        "storage": "mysql"
    })


@app.route("/api/cache-clear", methods=["DELETE"])
def cache_clear() -> Any:
    """Manually invalidate the in-memory jobs cache"""
    invalidate_jobs_cache()
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
    if init_db():
        logger.info(f"Storage: MySQL Database")
        logger.info(f"Host: {MYSQL_CONFIG['host']}")
        logger.info(f"Database: {MYSQL_CONFIG['database']}")
        logger.info(f"User: {MYSQL_CONFIG['user']}")
        logger.info(f"Server: http://localhost:5000")
        logger.info("=" * 60)
        logger.info("API Ready to serve requests")
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
    else:
        logger.error("Failed to initialize database. Please check:")
        logger.error("  - MySQL server is running")
        logger.error("  - Database credentials in .env file are correct")
        logger.error("  - Port 3306 is accessible")
        logger.error("=" * 60)
