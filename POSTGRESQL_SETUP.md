# 🐘 PostgreSQL Setup Guide

## Overview

Your Job Portal has been **migrated from MySQL to PostgreSQL**. This guide explains the setup process.

---

## Prerequisites

### 1. Install PostgreSQL

**Windows:**
- Download from: https://www.postgresql.org/download/windows/
- Version: 12 or higher recommended
- During installation, note the password you set for the `postgres` user

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Linux (Ubuntu):**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### 2. Install Python Driver

```bash
pip install psycopg2-binary
```

---

## Configuration

### Update PostgreSQL Credentials

Edit `postgres_db.py`:

```python
POSTGRES_CONFIG = {
    'host': 'localhost',
    'user': 'postgres',
    'password': 'YOUR_PASSWORD_HERE',  # ← Change this
    'database': 'job_portal',
    'port': 5432
}
```

Replace `YOUR_PASSWORD_HERE` with the password you set during PostgreSQL installation.

---

## Initialize Database

### Automatic (Recommended)

```bash
python api.py
```

This will:
1. Create the `job_portal` database
2. Create all required tables
3. Start the Flask server

### Manual Setup

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE job_portal;

# Exit psql
\q

# Then run
python api.py
```

---

## Verify Installation

### 1. Check PostgreSQL Connection

```bash
psql -U postgres -d job_portal -c "SELECT version();"
```

Expected output: PostgreSQL version information

### 2. Check Tables Created

```bash
psql -U postgres -d job_portal -c "\dt"
```

Expected output:
```
           List of relations
 Schema |    Name    | Type  |  Owner
--------+------------+-------+----------
 public | fetch_log  | table | postgres
 public | jobs       | table | postgres
 public | stats      | table | postgres
```

### 3. Test API Connection

```bash
curl http://localhost:5000/api/db-info
```

Expected output:
```json
{
  "database": "PostgreSQL",
  "status": "✓ Connected",
  "total_jobs": 0,
  "statistics": {...}
}
```

---

## Usage

### Start Server

```bash
python api.py
```

### Run Scheduler

```bash
python scheduler.py --daemon
```

### Test Scrapers

```bash
python diagnose.py
```

---

## Advantages of PostgreSQL

✅ **Open Source** - Free to use  
✅ **Powerful** - Advanced features  
✅ **Reliable** - ACID compliance  
✅ **Scalable** - Handles large datasets  
✅ **Flexible** - JSON support (JSONB)  
✅ **Performance** - Excellent for complex queries  
✅ **Community** - Large and active community  

---

## Common Commands

### Connect to Database

```bash
psql -U postgres -d job_portal
```

### List All Jobs

```sql
SELECT COUNT(*) FROM jobs;
```

### View Latest Jobs

```sql
SELECT title, company, added_at FROM jobs ORDER BY added_at DESC LIMIT 10;
```

### View Statistics

```sql
SELECT work_type, COUNT(*) FROM jobs GROUP BY work_type;
```

### Clear All Jobs

```sql
DELETE FROM jobs;
```

### Backup Database

```bash
pg_dump -U postgres job_portal > backup.sql
```

### Restore Database

```bash
psql -U postgres job_portal < backup.sql
```

---

## Troubleshooting

### Error: "Connection refused"

**Cause:** PostgreSQL not running

**Fix:**
```bash
# Windows
pg_ctl -D "C:\Program Files\PostgreSQL\15\data" start

# macOS
brew services start postgresql@15

# Linux
sudo systemctl start postgresql
```

### Error: "FATAL: Ident authentication failed"

**Cause:** Password incorrect

**Fix:**
1. Edit `postgres_db.py`
2. Update password to match PostgreSQL installation
3. Restart server

### Error: "database job_portal does not exist"

**Cause:** Database not created

**Fix:**
```bash
python api.py  # This will create it
```

### Can't Connect to psql

**Fix:**
```bash
# Set password
ALTER USER postgres WITH PASSWORD 'your_new_password';

# Then update postgres_db.py with new password
```

---

## Performance Tips

1. **Index Frequently Queried Columns:**
```sql
CREATE INDEX idx_job_source ON jobs(source);
CREATE INDEX idx_job_country ON jobs(country);
```

2. **Vacuum Database Regularly:**
```bash
psql -U postgres -d job_portal -c "VACUUM ANALYZE;"
```

3. **Monitor Log Size:**
```bash
psql -U postgres -d job_portal -c "SELECT pg_database_size('job_portal');"
```

---

## Upgrade PostgreSQL

```bash
# Windows: Use installer
# macOS: brew upgrade postgresql@15
# Linux: sudo apt-get install postgresql
```

---

## Production Deployment

For production, consider:

1. **Use a dedicated PostgreSQL server** (not localhost)
2. **Enable SSL/TLS** for connections
3. **Setup automated backups**
4. **Configure connection pooling** (PgBouncer)
5. **Monitor performance** with pg_stat_statements
6. **Set up replication** for high availability

---

## Docker (Optional)

Run PostgreSQL in Docker:

```bash
docker pull postgres:15
docker run --name job-portal-db \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  -d postgres:15

# Create database
docker exec -it job-portal-db psql -U postgres -c "CREATE DATABASE job_portal;"
```

---

## Files Modified

- ✅ `api.py` - Now uses `postgres_db` instead of `mysql_db`
- ✅ `scheduler.py` - Now uses `postgres_db` instead of `mysql_db`
- ✅ `postgres_db.py` - New PostgreSQL database module (created)
- ✅ `mysql_db.py` - Kept for reference (not used)

---

## Next Steps

1. Install PostgreSQL
2. Update password in `postgres_db.py`
3. Run `python api.py`
4. Open http://localhost:5000
5. Test with "Fetch Jobs" button

---

## Support

For PostgreSQL issues:
- Docs: https://www.postgresql.org/docs/
- Stack Overflow: Tag `postgresql`
- Official Community: https://www.postgresql.org/community/

For Job Portal issues:
- Check `QUICK_COMMANDS.md`
- Run `python diagnose.py`
- Check logs in terminal

---

**PostgreSQL Migration Complete!** 🎉
