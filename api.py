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
import json
import re
from datetime import datetime
import threading
import time
import os
import mysql.connector
from mysql.connector import Error
from mysql.connector.abstracts import MySQLConnectionAbstract
import io
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text as pdf_extract_text
import mammoth
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

# Resume upload constraints
ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_RESUME_SIZE_BYTES = int(os.getenv('MAX_RESUME_SIZE', 5 * 1024 * 1024))  # 5 MB
MIN_RESUME_TEXT_CHARS = int(os.getenv('MIN_RESUME_TEXT', 30))

app.config['MAX_CONTENT_LENGTH'] = MAX_RESUME_SIZE_BYTES

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

        # Create database if not exists
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']}")
        cursor.close()
        conn.close()

        # Now connect to the database
        conn = get_db_connection()
        if not conn:
            logger.error("Failed to connect to database after creation")
            return False

        cursor = conn.cursor()

        # Create jobs table
        create_table = """
        CREATE TABLE IF NOT EXISTS jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            source VARCHAR(100),
            title VARCHAR(255),
            company VARCHAR(255),
            work_type VARCHAR(50),
            country VARCHAR(255),
            location VARCHAR(255),
            job_type VARCHAR(50),
            category VARCHAR(100),
            salary VARCHAR(100),
            date VARCHAR(50),
            start_date VARCHAR(50),
            end_date VARCHAR(50),
            url VARCHAR(500) UNIQUE,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            domains JSON,
            INDEX idx_source (source),
            INDEX idx_work_type (work_type),
            INDEX idx_country (country),
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

def save_jobs_to_db(jobs: List[Dict[str, Any]]) -> bool:
    """Save jobs to MySQL database"""
    try:
        conn = get_db_connection()
        if not conn:
            return False

        cursor = conn.cursor()

        for job in jobs:
            domains = json.dumps(job.get('domains', ['General']))

            try:
                insert_query = """
                INSERT INTO jobs (source, title, company, work_type, country, location,
                                 job_type, category, salary, date, start_date, end_date, url, domains, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source = VALUES(source), title = VALUES(title), company = VALUES(company),
                    work_type = VALUES(work_type), country = VALUES(country), location = VALUES(location),
                    job_type = VALUES(job_type), category = VALUES(category), salary = VALUES(salary),
                    date = VALUES(date), start_date = VALUES(start_date), end_date = VALUES(end_date),
                    domains = VALUES(domains), added_at = NOW()
                """
                cursor.execute(insert_query, (
                    job.get('source'), job.get('title'), job.get('company'),
                    job.get('work_type'), job.get('country'), job.get('location'),
                    job.get('job_type'), job.get('category'), job.get('salary'),
                    job.get('date'), job.get('start_date'), job.get('end_date'),
                    job.get('url'), domains, datetime.now()
                ))
            except Error as e:
                logger.error(f"Failed to insert job {job.get('url')}: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        invalidate_jobs_cache()
        return True
    except Error as e:
        logger.error(f"Failed to save jobs to database: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while saving jobs: {e}")
        return False

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
    fresher_only: bool = False,
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """Filter jobs based on criteria"""
    filtered = all_jobs

    if fresher_only:
        filtered = [j for j in filtered if is_fresher_job(j)]

    if keyword:
        keyword = keyword.lower()
        filtered = [j for j in filtered if keyword in str(j.get('title', '')).lower() or
                   keyword in str(j.get('company', '')).lower()]

    if work_type:
        filtered = [j for j in filtered if j.get('work_type', '').lower() == work_type.lower()]

    if country:
        filtered = [j for j in filtered if j.get('country', '').lower() == country.lower()]

    if job_type:
        filtered = [j for j in filtered if j.get('job_type', '').lower() == job_type.lower()]

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

# ============ RESUME MATCHING HELPERS ============

def extract_text_from_resume(file_storage: FileStorage) -> str:
    """Extract text from uploaded resume (PDF, DOCX, or TXT).
    Everything stays in memory - never written to disk."""
    filename = secure_filename(file_storage.filename or "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise ValueError(f"Unsupported file type: .{ext}. Allowed: {', '.join(ALLOWED_RESUME_EXTENSIONS)}")

    raw_bytes = file_storage.read()
    if not raw_bytes:
        raise ValueError("Uploaded file is empty")

    try:
        if ext == "pdf":
            text = pdf_extract_text(io.BytesIO(raw_bytes))
        elif ext == "docx":
            result = mammoth.extract_raw_text(io.BytesIO(raw_bytes))
            text = result.value
        else:  # txt
            text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        raise ValueError(f"Could not parse this file: {str(e)[:100]}")

    text = (text or "").strip()
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
    """Build searchable text from a job object for TF-IDF matching."""
    parts = [
        job.get("title") or "",
        job.get("company") or "",
        job.get("category") or "",
        job.get("job_type") or "",
        job.get("work_type") or "",
        job.get("location") or "",
        " ".join(job.get("domains") or []),
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

@app.route("/api/sources", methods=["GET"])
def get_sources() -> Any:
    """Get all available sources"""
    sources = {
        "remote_boards": [
            {"id": "remotive", "name": "Remotive", "status": "✅"},
            {"id": "remoteok", "name": "RemoteOK", "status": "✅"},
            {"id": "himalayas", "name": "Himalayas", "status": "✅"},
        ],
        "freshers": [
            {"id": "internshala", "name": "Internshala", "status": "✅"},
            {"id": "firstnaukri", "name": "FirstNaukri", "status": "✅"},
        ],
        "all_jobs": [
            {"id": "arbeitnow", "name": "Arbeitnow", "status": "✅"},
        ],
        "career_pages": [],
        "developer_jobs": []
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

        # Filter to keep only fresher jobs
        fresher_jobs = [j for j in jobs if is_fresher_job(j)]
        logger.info(f"Filtered to fresher jobs: {len(fresher_jobs)} jobs")

        # Add timestamps and domain detection to new jobs
        for job in fresher_jobs:
            if 'added_at' not in job:
                job['added_at'] = datetime.now().isoformat()
            # Add domain detection
            if 'domains' not in job:
                job['domains'] = detect_job_domain(job)

        # Save to database
        save_jobs_to_db(fresher_jobs)

        stats = get_statistics()

        return jsonify({
            "success": True,
            "jobs_count": len(jobs),
            "inserted": len(jobs),
            "skipped": 0,
            "total_stored": len(fresher_jobs),
            "status": status,
            "stats": stats,
            "last_fetch": datetime.now().isoformat()
        })

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

        try:
            resume_text = extract_text_from_resume(file_storage)
        except ValueError as ve:
            return jsonify({"success": False, "error": str(ve)}), 400

        if len(resume_text) < MIN_RESUME_TEXT_CHARS:
            return jsonify({
                "success": False,
                "error": "Could not extract enough readable text from this resume. "
                         "Try a different file (avoid scanned/image-only PDFs)."
            }), 422

        all_jobs = load_jobs_from_db()
        if not all_jobs:
            return jsonify({
                "success": True,
                "matches": [],
                "total_jobs_considered": 0,
                "resume_domains": extract_resume_keywords(resume_text),
                "message": "No jobs available yet. Fetch jobs first, then upload your resume."
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

        scored = score_job_match(resume_text, all_jobs)
        top_matches = scored[:top_n]

        return jsonify({
            "success": True,
            "matches": top_matches,
            "total_jobs_considered": len(all_jobs),
            "resume_domains": extract_resume_keywords(resume_text),
            "resume_chars_extracted": len(resume_text)
        })

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
        fresher_only = request.args.get("fresher", "").lower() == "true"
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))

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

        result = filter_jobs(all_jobs, keyword, work_type, country, job_type, fresher_only, page, limit)
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
                row = {field: job.get(field, '') for field in fieldnames}
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
        app.run(debug=True, port=5000)
    else:
        logger.error("Failed to initialize database. Please check:")
        logger.error("  - MySQL server is running")
        logger.error("  - Database credentials in .env file are correct")
        logger.error("  - Port 3306 is accessible")
        logger.error("=" * 60)
