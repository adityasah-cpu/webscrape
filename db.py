"""
SQLite database for job storage and tracking alerts.
Replaces CSV for persistence and dedup tracking.
"""

import sqlite3
from datetime import datetime

DB_FILE = "jobs.db"

def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Main jobs table
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            company TEXT,
            work_type TEXT,
            country TEXT,
            location TEXT,
            job_type TEXT,
            category TEXT,
            salary TEXT,
            date TEXT,
            source TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Track which jobs have been alerted on
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts_sent (
            job_id INTEGER PRIMARY KEY,
            alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alert_type TEXT,
            recipient TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)
    
    conn.commit()
    conn.close()


def insert_job(job_dict):
    """Insert or ignore job. Returns True if inserted, False if duplicate."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO jobs (url, title, company, work_type, country, location, 
                             job_type, category, salary, date, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_dict.get("url", ""),
            job_dict.get("title", ""),
            job_dict.get("company", ""),
            job_dict.get("work_type", ""),
            job_dict.get("country", ""),
            job_dict.get("location", ""),
            job_dict.get("job_type", ""),
            job_dict.get("category", ""),
            job_dict.get("salary", ""),
            job_dict.get("date", ""),
            job_dict.get("source", ""),
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Job URL already exists
        return False
    finally:
        conn.close()


def insert_jobs(jobs_list):
    """Insert multiple jobs. Returns count of new jobs."""
    count = 0
    for job in jobs_list:
        if insert_job(job):
            count += 1
    return count


def get_new_jobs(hours=24):
    """Fetch jobs added in the last N hours that haven't been alerted on."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"""
        SELECT j.* FROM jobs j
        LEFT JOIN alerts_sent a ON j.id = a.job_id
        WHERE j.added_at >= datetime('now', '-{hours} hours')
        AND a.job_id IS NULL
        ORDER BY j.added_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    
    # Convert to dict
    columns = ["id", "url", "title", "company", "work_type", "country", 
               "location", "job_type", "category", "salary", "date", "source", "added_at"]
    return [dict(zip(columns, row)) for row in rows]


def mark_alerted(job_id, alert_type, recipient):
    """Mark a job as alerted on."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO alerts_sent (job_id, alert_type, recipient)
        VALUES (?, ?, ?)
    """, (job_id, alert_type, recipient))
    conn.commit()
    conn.close()


def get_jobs_by_filter(work_type=None, country=None, job_type=None, keyword=None, limit=100):
    """Search jobs with filters."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    
    if work_type:
        query += " AND work_type = ?"
        params.append(work_type)
    if country:
        query += " AND country LIKE ?"
        params.append(f"%{country}%")
    if job_type:
        query += " AND job_type LIKE ?"
        params.append(f"%{job_type}%")
    if keyword:
        query += " AND (title LIKE ? OR company LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    
    query += " ORDER BY added_at DESC LIMIT ?"
    params.append(limit)
    
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    
    columns = ["id", "url", "title", "company", "work_type", "country", 
               "location", "job_type", "category", "salary", "date", "source", "added_at"]
    return [dict(zip(columns, row)) for row in rows]


def export_csv(filename="jobs.csv"):
    """Export all jobs to CSV."""
    import csv
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT url, title, company, work_type, country, location, job_type, category, salary, date, source FROM jobs ORDER BY added_at DESC")
    rows = c.fetchall()
    conn.close()
    
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["URL", "Title", "Company", "Work Type", "Country", "Location", "Job Type", "Category", "Salary", "Date", "Source"])
        writer.writerows(rows)
    
    return len(rows)


def get_stats():
    """Get stats on stored jobs."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total, COUNT(DISTINCT source) as sources FROM jobs")
    total, sources = c.fetchone()
    c.execute("SELECT work_type, COUNT(*) as count FROM jobs GROUP BY work_type")
    by_type = dict(c.fetchall())
    conn.close()
    return {"total": total, "sources": sources, "by_type": by_type}


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
