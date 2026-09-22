# 🔄 Migration Guide: MySQL → PostgreSQL

## Overview

This guide explains how to migrate your existing Job Portal data from MySQL to PostgreSQL.

---

## Prerequisites

✅ MySQL database running with existing jobs  
✅ PostgreSQL installed and configured  
✅ `postgres_db.py` configured with correct credentials  
✅ Both databases accessible

---

## Migration Steps

### Step 1: Backup MySQL Data

```bash
mysqldump -u root -paditya@2004 job_portal > mysql_backup.sql
```

### Step 2: Verify PostgreSQL is Ready

```bash
python api.py  # This creates PostgreSQL database and tables
```

### Step 3: Export MySQL Data to CSV

Use `mysql_db.py` to export:

```python
import mysql.connector

# Connect to MySQL
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='aditya@2004',
    database='job_portal'
)

cursor = conn.cursor()
cursor.execute("SELECT * FROM jobs")

# Write to CSV
import csv
with open('jobs_export.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'url', 'title', 'company', 'work_type', 
                     'country', 'location', 'job_type', 'category', 
                     'salary', 'date', 'source', 'added_at'])
    writer.writerows(cursor.fetchall())

cursor.close()
conn.close()

print("✓ Exported jobs_export.csv")
```

### Step 4: Import to PostgreSQL

```python
import psycopg2
import csv
from datetime import datetime

# Connect to PostgreSQL
conn = psycopg2.connect(
    host='localhost',
    user='postgres',
    password='postgres',
    database='job_portal',
    port=5432
)

cursor = conn.cursor()

# Read and insert from CSV
with open('jobs_export.csv', 'r') as f:
    reader = csv.DictReader(f)
    
    for row in reader:
        try:
            cursor.execute("""
                INSERT INTO jobs (url, title, company, work_type, country,
                                 location, job_type, category, salary, date, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row['url'], row['title'], row['company'], row['work_type'],
                row['country'], row['location'], row['job_type'], row['category'],
                row['salary'], row['date'], row['source']
            ))
        except psycopg2.Error as e:
            print(f"Error importing row {row['url']}: {e}")

conn.commit()
cursor.close()
conn.close()

print("✓ Data imported to PostgreSQL")
```

### Step 5: Verify Migration

Check record count matches:

```bash
# MySQL
mysql -u root -paditya@2004 job_portal -e "SELECT COUNT(*) FROM jobs;"

# PostgreSQL
psql -U postgres -d job_portal -c "SELECT COUNT(*) FROM jobs;"
```

Both should show the same count.

### Step 6: Switch Application

1. Ensure `postgres_db.py` is configured correctly
2. Ensure `api.py` imports `postgres_db` (✓ already done)
3. Restart Flask server:

```bash
python api.py
```

4. Verify data is accessible:

```bash
curl http://localhost:5000/api/db-info
```

---

## Automated Migration Script

Save as `migrate_db.py`:

```python
#!/usr/bin/env python3
"""
Automated migration from MySQL to PostgreSQL
"""

import mysql.connector
import psycopg2
from psycopg2 import Error

# MySQL config
mysql_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'aditya@2004',
    'database': 'job_portal'
}

# PostgreSQL config
postgres_config = {
    'host': 'localhost',
    'user': 'postgres',
    'password': 'postgres',
    'database': 'job_portal',
    'port': 5432
}

def migrate():
    """Migrate all data from MySQL to PostgreSQL"""
    
    print("=" * 60)
    print("🔄 Starting migration: MySQL → PostgreSQL")
    print("=" * 60)
    
    try:
        # Connect to MySQL
        print("\n1. Connecting to MySQL...")
        mysql_conn = mysql.connector.connect(**mysql_config)
        mysql_cursor = mysql_conn.cursor(dictionary=True)
        print("   ✓ MySQL connected")
        
        # Connect to PostgreSQL
        print("2. Connecting to PostgreSQL...")
        pg_conn = psycopg2.connect(**postgres_config)
        pg_cursor = pg_conn.cursor()
        print("   ✓ PostgreSQL connected")
        
        # Get all jobs from MySQL
        print("3. Reading jobs from MySQL...")
        mysql_cursor.execute("SELECT * FROM jobs")
        jobs = mysql_cursor.fetchall()
        print(f"   ✓ Found {len(jobs)} jobs")
        
        # Insert into PostgreSQL
        print("4. Inserting jobs into PostgreSQL...")
        inserted = 0
        skipped = 0
        
        for job in jobs:
            try:
                pg_cursor.execute("""
                    INSERT INTO jobs (url, title, company, work_type, country,
                                     location, job_type, category, salary, date, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    job['url'], job['title'], job['company'], job['work_type'],
                    job['country'], job['location'], job['job_type'], job['category'],
                    job['salary'], job['date'], job['source']
                ))
                inserted += 1
            except Error as e:
                if "unique constraint" in str(e).lower():
                    skipped += 1
                else:
                    print(f"   Error with job {job['url']}: {e}")
        
        pg_conn.commit()
        print(f"   ✓ Inserted {inserted} jobs")
        print(f"   ⚠️  Skipped {skipped} duplicates")
        
        # Verify
        print("5. Verifying migration...")
        pg_cursor.execute("SELECT COUNT(*) FROM jobs")
        pg_count = pg_cursor.fetchone()[0]
        mysql_cursor.execute("SELECT COUNT(*) FROM jobs")
        mysql_count = mysql_cursor.fetchone()[0]
        
        if pg_count == mysql_count:
            print(f"   ✓ Migration successful!")
            print(f"   ✓ Total records: {pg_count}")
        else:
            print(f"   ⚠️  Record count mismatch:")
            print(f"      MySQL: {mysql_count}")
            print(f"      PostgreSQL: {pg_count}")
        
        # Cleanup
        mysql_cursor.close()
        mysql_conn.close()
        pg_cursor.close()
        pg_conn.close()
        
        print("\n" + "=" * 60)
        print("✅ Migration completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
```

Usage:

```bash
python migrate_db.py
```

---

## Verification Checklist

After migration:

- [ ] PostgreSQL database created
- [ ] All tables created
- [ ] Jobs count matches MySQL
- [ ] API responds to requests
- [ ] Web UI loads
- [ ] Search/filter works
- [ ] Export to CSV works
- [ ] Statistics calculate correctly

---

## Rollback (If Needed)

If you need to go back to MySQL:

1. Stop Flask server
2. Restore MySQL backup:

```bash
mysql -u root -paditya@2004 job_portal < mysql_backup.sql
```

3. Edit `api.py` and `scheduler.py` to import `mysql_db` instead of `postgres_db`
4. Restart server

---

## Troubleshooting

### Error: "Duplicate entry for url"

**Cause:** Job already exists in PostgreSQL

**Fix:** These are legitimate duplicates, they're being skipped (normal)

### Error: "column does not exist"

**Cause:** Schema mismatch

**Fix:** Ensure PostgreSQL tables created properly:

```bash
python api.py  # Recreates tables
```

### Error: "Connection refused"

**Cause:** PostgreSQL not running

**Fix:**
```bash
# Start PostgreSQL
pg_ctl -D "C:\Program Files\PostgreSQL\15\data" start
```

### Data not showing after migration

**Cause:** Still connecting to MySQL

**Fix:** Verify `api.py` imports `postgres_db`:

```python
import postgres_db  # Should show this
```

---

## Data Integrity

After migration:

```python
# Verify all fields migrated correctly
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    user='postgres',
    password='postgres',
    database='job_portal'
)

cursor = conn.cursor()

# Check for NULL values
cursor.execute("""
    SELECT COUNT(*) FROM jobs 
    WHERE url IS NULL OR title IS NULL
""")

null_count = cursor.fetchone()[0]
print(f"Records with NULL critical fields: {null_count}")

# Check date range
cursor.execute("""
    SELECT MIN(added_at), MAX(added_at) FROM jobs
""")

min_date, max_date = cursor.fetchone()
print(f"Date range: {min_date} to {max_date}")

cursor.close()
conn.close()
```

---

## Performance Optimization

After migration, optimize:

```sql
-- Create indexes
CREATE INDEX idx_jobs_source ON jobs(source);
CREATE INDEX idx_jobs_country ON jobs(country);
CREATE INDEX idx_jobs_added_at ON jobs(added_at);

-- Analyze
ANALYZE jobs;

-- Vacuum
VACUUM jobs;
```

---

## Cleanup

After successful migration:

```bash
# Keep backups but they're no longer needed
rm mysql_backup.sql

# MySQL can be uninstalled if not needed
# PostgreSQL is now your primary database
```

---

## Success!

Your Job Portal is now running on PostgreSQL! 🎉

---

**Migration Guide Complete**
