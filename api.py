"""
Job Finder - Corporate API Backend (Flask)
Serves job data from file-based storage (PostgreSQL & Redis disabled)

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

app = Flask(__name__)
CORS(app)

# File-based storage (PostgreSQL & Redis disabled)
JOBS_FILE = "jobs_data.json"

def load_jobs_from_file():
    """Load jobs from JSON file"""
    if os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_jobs_to_file(jobs):
    """Save jobs to JSON file"""
    try:
        with open(JOBS_FILE, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving jobs: {e}")
        return False

def is_fresher_job(job):
    """Detect if a job is suitable for freshers/entry-level"""
    fresher_keywords = [
        'fresher', 'intern', 'entry-level', 'entry level', 'junior',
        'graduate', 'trainee', 'apprentice', 'new grad', 'beginner',
        'no experience', 'without experience', '0-1 year', 'undergraduate',
        'placement', 'associate', 'assistant'
    ]

    title = (job.get('title') or '').lower()
    category = (job.get('category') or '').lower()
    description = (job.get('description') or '').lower()

    # Check if any fresher keyword is in title, category, or description
    for keyword in fresher_keywords:
        if keyword in title or keyword in category or keyword in description:
            return True

    return False

def detect_job_domain(job):
    """Detect job domain from title, category, and description"""
    title = (job.get('title') or '').lower()
    category = (job.get('category') or '').lower()
    description = (job.get('description') or '').lower()
    text = f"{title} {category} {description}"

    # Domain keywords mapping
    domains = {
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

    detected_domains = []
    for domain, keywords in domains.items():
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
    jobs = load_jobs_from_file()

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

        # Load existing jobs
        existing_jobs = load_jobs_from_file()

        # Add timestamps and domain detection to new jobs
        for job in fresher_jobs:
            if 'added_at' not in job:
                job['added_at'] = datetime.now().isoformat()
            # Add domain detection
            if 'domains' not in job:
                job['domains'] = detect_job_domain(job)

        # Merge with existing (remove duplicates by URL)
        existing_urls = {j.get('url'): j for j in existing_jobs}
        new_urls = {j.get('url'): j for j in fresher_jobs}
        existing_urls.update(new_urls)

        final_jobs = list(existing_urls.values())

        # Save to file
        save_jobs_to_file(final_jobs)

        stats = get_statistics()

        return jsonify({
            "success": True,
            "jobs_count": len(jobs),
            "inserted": len(jobs),
            "skipped": 0,
            "total_stored": len(final_jobs),
            "status": status,
            "stats": stats,
            "last_fetch": datetime.now().isoformat()
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

        all_jobs = load_jobs_from_file()

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
        jobs = load_jobs_from_file()

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
        jobs = load_jobs_from_file()
        stats = get_statistics()

        return jsonify({
            "database": "File-based (JSON)",
            "status": "✓ Active",
            "total_jobs": len(jobs),
            "statistics": stats,
            "file": JOBS_FILE,
            "note": "PostgreSQL and Redis are disabled. Data stored in JSON file."
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "✗ Error"}), 500


@app.route("/api/clear-jobs", methods=["DELETE"])
def clear_jobs():
    """Clear all jobs"""
    try:
        save_jobs_to_file([])
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
    print("[*] Job Portal API Starting (File-based Storage)...")
    print("="*60)
    print("[OK] Storage: File-based (JSON)")
    print("[OK] PostgreSQL: Disabled")
    print("[OK] Redis: Disabled")
    print("[OK] Server: http://localhost:5000")
    print("[OK] Data file: jobs_data.json")
    print("="*60)
    print("\n[NOTE] Once you install PostgreSQL and Redis,")
    print("   change back to postgres_db and redis_cache imports.\n")
    print("="*60 + "\n")

    app.run(debug=True, port=5000)
