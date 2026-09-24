"""
Job Finder - Corporate API Backend (Flask)
Serves job data from MySQL database

Run:
    python api.py
    Then open http://localhost:5000 in browser
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import remote_job_scraper as rjs
import json
from datetime import datetime
import threading
import os
import mysql.connector
from mysql.connector import Error
import io
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text as pdf_extract_text
import mammoth
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
CORS(app)

# Resume upload constraints
ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_RESUME_TEXT_CHARS = 30  # Minimum text to consider resume parseable

app.config['MAX_CONTENT_LENGTH'] = MAX_RESUME_SIZE_BYTES

# MySQL Configuration
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'aditya@2004',
    'database': 'job_portal',
    'autocommit': True
}

def get_db_connection():
    """Get MySQL connection"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        print(f"[ERROR] Database connection failed: {e}")
        return None

def init_db():
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
            print("[ERROR] Failed to connect to database after creation")
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
        cursor.close()
        conn.close()
        print("[OK] Database initialized successfully")
        return True
    except Error as e:
        print(f"[ERROR] Database initialization failed: {e}")
        return False

def load_jobs_from_db():
    """Load all jobs from MySQL database"""
    try:
        conn = get_db_connection()
        if not conn:
            return []

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM jobs ORDER BY added_at DESC")
        jobs = cursor.fetchall()

        # Parse JSON fields
        for job in jobs:
            if job.get('domains'):
                try:
                    job['domains'] = json.loads(job['domains'])
                except:
                    job['domains'] = ['General']

        cursor.close()
        conn.close()
        return jobs
    except Error as e:
        print(f"[ERROR] Failed to load jobs from database: {e}")
        return []

def save_jobs_to_db(jobs):
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
                ON DUPLICATE KEY UPDATE added_at = NOW()
                """
                cursor.execute(insert_query, (
                    job.get('source'), job.get('title'), job.get('company'),
                    job.get('work_type'), job.get('country'), job.get('location'),
                    job.get('job_type'), job.get('category'), job.get('salary'),
                    job.get('date'), job.get('start_date'), job.get('end_date'),
                    job.get('url'), domains, datetime.now()
                ))
            except Error as e:
                print(f"[ERROR] Failed to insert job: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"[ERROR] Failed to save jobs to database: {e}")
        return False

def is_fresher_job(job):
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

def detect_job_domain(job):
    """Detect job domain from title, category, and description"""
    title = (job.get('title') or '').lower()
    category = (job.get('category') or '').lower()
    description = (job.get('description') or '').lower()
    text = f"{title} {category} {description}"

    detected_domains = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                detected_domains.append(domain)
                break

    return detected_domains if detected_domains else ['General']

def filter_jobs(all_jobs, keyword="", work_type="", country="", job_type="", fresher_only=False, page=1, limit=20):
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

def get_statistics():
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

def extract_text_from_resume(file_storage):
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

def extract_resume_keywords(resume_text):
    """Detect which domains a resume's text touches using domain keyword vocabulary."""
    text = resume_text.lower()
    matched = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(domain)
    return matched or ["General"]

def build_job_text(job):
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

def score_job_match(resume_text, jobs):
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
def get_sources():
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
def fetch_jobs():
    """Fetch jobs from selected sources and store in file"""
    try:
        data = request.json
        selected = data.get("sources", [])

        sources = {s.__name__.replace("scrape_", ""): s for s in rjs.SCRAPERS}
        enabled = [sources[name] for name in selected if name in sources]

        all_jobs = []
        status = {}

        print(f"\n[*] Fetching from {len(enabled)} sources...")

        for scraper in enabled:
            name = scraper.__name__.replace("scrape_", "")
            try:
                print(f"  Scraping {name}...", end="")
                results = scraper()
                all_jobs.extend(results)
                status[name] = {"success": True, "count": len(results)}
                print(f" [OK] {len(results)} jobs")
            except Exception as e:
                status[name] = {"success": False, "error": str(e)[:50]}
                print(f" [ERROR] Error: {str(e)[:40]}")

        jobs = rjs.dedupe(all_jobs)
        print(f"\n[OK] Total unique jobs: {len(jobs)}")

        # Filter to keep only fresher jobs
        fresher_jobs = [j for j in jobs if is_fresher_job(j)]
        print(f"[*] Filtered to fresher jobs: {len(fresher_jobs)} jobs")

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
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/match-resume", methods=["POST"])
def match_resume():
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

        top_n = int(request.args.get("top_n", 20))
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
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
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
        result["storage"] = "file-based"

        return jsonify(result)

    except Exception as e:
        return jsonify({"jobs": [], "total": 0, "page": 1, "pages": 0, "error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Get job statistics from file storage"""
    try:
        stats = get_statistics()
        stats["from_cache"] = False
        stats["storage"] = "file-based"
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export", methods=["GET"])
def export_jobs():
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

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db-info", methods=["GET"])
def db_info():
    """Get database information"""
    try:
        jobs = load_jobs_from_db()
        stats = get_statistics()

        return jsonify({
            "database": "MySQL",
            "status": "✓ Active",
            "total_jobs": len(jobs),
            "statistics": stats,
            "host": MYSQL_CONFIG['host'],
            "database": MYSQL_CONFIG['database'],
            "note": "Data stored in MySQL database."
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "✗ Error"}), 500


@app.route("/api/clear-jobs", methods=["DELETE"])
def clear_jobs():
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
        return jsonify({"success": True, "message": "All jobs cleared"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/test-alert", methods=["POST"])
def test_alert():
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
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cache-info", methods=["GET"])
def cache_info():
    """Get cache information"""
    return jsonify({
        "cache": {
            "status": "disabled",
            "note": "Redis is currently disabled"
        },
        "storage": "file-based (JSON)"
    })


@app.route("/api/cache-clear", methods=["DELETE"])
def cache_clear():
    """Cache operations (no-op)"""
    return jsonify({"success": True, "message": "Cache disabled - no action needed"})


@app.route("/api/scheduler-status", methods=["GET"])
def scheduler_status():
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
            "note": "PostgreSQL and Redis disabled"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def index():
    """Serve web UI"""
    return open("index.html", encoding="utf-8").read(), 200, {"Content-Type": "text/html"}


if __name__ == "__main__":
    print("\n" + "="*60)
    print("[*] Job Portal API Starting (MySQL)...")
    print("="*60)

    # Initialize database
    if init_db():
        print("[OK] Storage: MySQL Database")
        print("[OK] Host: localhost")
        print("[OK] Database: job_portal")
        print("[OK] User: root")
        print("[OK] Server: http://localhost:5000")
        print("="*60 + "\n")
        app.run(debug=True, port=5000)
    else:
        print("[ERROR] Failed to initialize database. Please check:")
        print("  - MySQL server is running")
        print("  - Credentials are correct (root / aditya@2004)")
        print("  - Port 3306 is accessible")
        print("="*60 + "\n")
