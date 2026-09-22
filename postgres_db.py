"""
PostgreSQL Database Module for Job Portal
Stores jobs in PostgreSQL database instead of MySQL
"""

import psycopg2
from psycopg2 import Error
from datetime import datetime
import json

# PostgreSQL Connection Config
POSTGRES_CONFIG = {
    'host': 'localhost',
    'user': 'postgres',
    'password': 'postgres',  # Change this to your PostgreSQL password
    'database': 'job_portal',
    'port': 5432
}

def get_connection():
    """Get PostgreSQL connection"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        return conn
    except Error as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None


def init_database():
    """Create database and tables if they don't exist"""
    try:
        # First connect to default postgres database to create job_portal database
        config = POSTGRES_CONFIG.copy()
        config['database'] = 'postgres'

        conn = psycopg2.connect(**config)
        conn.autocommit = True
        cursor = conn.cursor()

        # Create database if not exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'job_portal'")
        if not cursor.fetchone():
            cursor.execute("CREATE DATABASE job_portal")
            print("✓ Database 'job_portal' created")
        else:
            print("✓ Database 'job_portal' already exists")

        cursor.close()
        conn.close()

        # Now connect to job_portal database and create tables
        conn = get_connection()
        cursor = conn.cursor()

        # Create jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id SERIAL PRIMARY KEY,
                url VARCHAR(500) UNIQUE NOT NULL,
                title VARCHAR(255),
                company VARCHAR(255),
                work_type VARCHAR(50),
                country VARCHAR(100),
                location VARCHAR(255),
                job_type VARCHAR(50),
                category VARCHAR(100),
                salary VARCHAR(100),
                date VARCHAR(50),
                source VARCHAR(100),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create stats table to cache statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id SERIAL PRIMARY KEY,
                stat_key VARCHAR(100),
                stat_value JSONB,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create fetch_log table to track when jobs were fetched
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fetch_log (
                id SERIAL PRIMARY KEY,
                sources TEXT,
                jobs_count INTEGER,
                status TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("✓ Tables created successfully")

    except Error as e:
        print(f"Error initializing database: {e}")


def insert_jobs(jobs_list):
    """Insert or update jobs in database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        inserted = 0
        skipped = 0

        for job in jobs_list:
            try:
                cursor.execute("""
                    INSERT INTO jobs (url, title, company, work_type, country,
                                     location, job_type, category, salary, date, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    job.get('url', ''),
                    job.get('title', ''),
                    job.get('company', ''),
                    job.get('work_type', ''),
                    job.get('country', ''),
                    job.get('location', ''),
                    job.get('job_type', ''),
                    job.get('category', ''),
                    job.get('salary', ''),
                    job.get('date', ''),
                    job.get('source', '')
                ))
                inserted += 1
            except Error as e:
                if "unique constraint" in str(e).lower():
                    skipped += 1
                else:
                    print(f"Error inserting job: {e}")

        conn.commit()
        cursor.close()
        conn.close()

        return {"inserted": inserted, "skipped": skipped}

    except Error as e:
        print(f"Error inserting jobs: {e}")
        return {"inserted": 0, "skipped": 0}


def get_jobs(keyword="", work_type="", country="", job_type="", page=1, limit=20):
    """Get filtered jobs from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Build WHERE clause
        conditions = []
        params = []

        if keyword:
            conditions.append("(title ILIKE %s OR company ILIKE %s)")
            keyword_param = f"%{keyword}%"
            params.extend([keyword_param, keyword_param])

        if work_type:
            conditions.append("work_type = %s")
            params.append(work_type)

        if country:
            conditions.append("country ILIKE %s")
            params.append(f"%{country}%")

        if job_type:
            conditions.append("job_type ILIKE %s")
            params.append(f"%{job_type}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM jobs WHERE {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Get paginated results
        offset = (page - 1) * limit
        query = f"""
            SELECT id, url, title, company, work_type, country, location,
                   job_type, category, salary, date, source, added_at
            FROM jobs
            WHERE {where_clause}
            ORDER BY added_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        cursor.execute(query, params)

        rows = cursor.fetchall()

        # Convert rows to dictionaries
        columns = ['id', 'url', 'title', 'company', 'work_type', 'country',
                   'location', 'job_type', 'category', 'salary', 'date', 'source', 'added_at']
        jobs = [dict(zip(columns, row)) for row in rows]

        cursor.close()
        conn.close()

        pages = (total + limit - 1) // limit

        return {
            "jobs": jobs,
            "total": total,
            "page": page,
            "pages": pages
        }

    except Error as e:
        print(f"Error fetching jobs: {e}")
        return {"jobs": [], "total": 0, "page": page, "pages": 0}


def get_statistics():
    """Get job statistics from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Total jobs
        cursor.execute("SELECT COUNT(*) as total FROM jobs")
        total = cursor.fetchone()[0]

        # Jobs by work type
        cursor.execute("""
            SELECT work_type, COUNT(*) as count
            FROM jobs
            GROUP BY work_type
        """)
        by_work_type = {row[0]: row[1] for row in cursor.fetchall()}

        # Jobs by country
        cursor.execute("""
            SELECT SPLIT_PART(country, ';', 1) as country, COUNT(*) as count
            FROM jobs
            GROUP BY SPLIT_PART(country, ';', 1)
            LIMIT 20
        """)
        by_country = {row[0]: row[1] for row in cursor.fetchall()}

        # Jobs by source
        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM jobs
            GROUP BY source
        """)
        by_source = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.close()
        conn.close()

        return {
            "total": total,
            "by_work_type": by_work_type,
            "by_country": by_country,
            "by_source": by_source
        }

    except Error as e:
        print(f"Error fetching statistics: {e}")
        return {"total": 0, "by_work_type": {}, "by_country": {}, "by_source": {}}


def get_last_fetch():
    """Get last fetch timestamp"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT fetched_at FROM fetch_log
            ORDER BY fetched_at DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        return result[0].isoformat() if result else None

    except Error as e:
        print(f"Error fetching last fetch time: {e}")
        return None


def log_fetch(sources, jobs_count, status):
    """Log a fetch operation"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO fetch_log (sources, jobs_count, status)
            VALUES (%s, %s, %s)
        """, (json.dumps(sources), jobs_count, json.dumps(status)))

        conn.commit()
        cursor.close()
        conn.close()

    except Error as e:
        print(f"Error logging fetch: {e}")


def clear_jobs():
    """Clear all jobs from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM jobs")
        conn.commit()
        cursor.close()
        conn.close()
        print("✓ All jobs cleared from database")

    except Error as e:
        print(f"Error clearing jobs: {e}")


def get_job_count():
    """Get total count of jobs in database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM jobs")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        return count

    except Error as e:
        print(f"Error getting job count: {e}")
        return 0


def migrate_from_mysql():
    """Migrate data from MySQL to PostgreSQL (if needed)"""
    print("Migration function available for future use")
    pass
