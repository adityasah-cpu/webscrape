# 🚀 Deployment Guide

**Status**: Ready for Deployment  
**Risk Level**: LOW  
**Estimated Deployment Time**: 30-45 minutes  
**Rollback Plan**: Available

---

## Pre-Deployment Checklist

### Environment Verification
- [ ] Python 3.8+ installed
- [ ] MySQL server running and accessible
- [ ] Git repository up to date
- [ ] `.env` file configured with secrets
- [ ] Google OAuth credentials configured
- [ ] All dependencies installed

### Code Verification
- [ ] Latest code pulled: `git pull origin main`
- [ ] All 15 issues fixed and committed
- [ ] No uncommitted changes: `git status` shows clean
- [ ] Database migration file present
- [ ] All files readable and accessible

### Backup & Rollback Plan
- [ ] Database backed up
- [ ] Previous version tagged: `git tag backup-v1.0.0`
- [ ] Rollback procedure documented
- [ ] Alert recipients configured

---

## Step-by-Step Deployment

### Phase 1: Pre-Deployment (10 minutes)

#### 1.1 Stop Current Application
```bash
# Check if running
ps aux | grep "python3 api.py"

# Stop gracefully
pkill -TERM -f "python3 api.py"

# Wait 5 seconds for graceful shutdown
sleep 5

# Force kill if needed
pkill -KILL -f "python3 api.py"
```

#### 1.2 Backup Database
```bash
# Create backup with timestamp
BACKUP_DIR="/backups/job_portal"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# MySQL backup
mysqldump -u root -p job_portal > $BACKUP_DIR/job_portal_$TIMESTAMP.sql

# Verify backup
ls -lh $BACKUP_DIR/job_portal_$TIMESTAMP.sql
```

#### 1.3 Tag Current Version
```bash
# Create backup tag
git tag backup-pre-deployment-$(date +%Y%m%d_%H%M%S)
git push origin --tags

# Verify tag created
git tag -l | tail -5
```

### Phase 2: Database Migration (5 minutes)

#### 2.1 Run Migration
```bash
# Run migration
mysql -u root -p job_portal < migration_location_dashboard.sql

# Verify no errors
echo "Check above for any ERROR messages"
```

#### 2.2 Verify Migration Success
```bash
# Check if tables exist
mysql -u root -p job_portal -e "SHOW TABLES;"

# Verify critical tables
mysql -u root -p job_portal -e "SHOW TABLES LIKE 'user%';"

# Check indexes
mysql -u root -p job_portal -e "SHOW INDEX FROM users;"

# Verify index count (should be 5 on users table)
mysql -u root -p job_portal -e "SELECT COUNT(*) as index_count FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_NAME='users';"

# Check location values (should all be NOT NULL)
mysql -u root -p job_portal -e "SELECT COUNT(*) as null_count FROM users WHERE location IS NULL;"
# Expected: 0
```

#### 2.3 Verify Data Integrity
```bash
# Count total users before/after
mysql -u root -p job_portal -e "SELECT COUNT(*) as total_users FROM users;"

# Check location distribution
mysql -u root -p job_portal -e "SELECT location, COUNT(*) as count FROM users GROUP BY location ORDER BY count DESC;"

# Verify no data loss
mysql -u root -p job_portal -e "SELECT COUNT(*) as admin_users FROM users WHERE is_admin = 1;"
```

### Phase 3: Application Deployment (10 minutes)

#### 3.1 Deploy Code
```bash
# Navigate to project
cd /path/to/job_portal

# Pull latest changes
git pull origin main

# Verify correct branch
git branch

# Show latest commits
git log --oneline -5
```

#### 3.2 Install Dependencies
```bash
# Create/activate virtual environment if needed
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install/upgrade dependencies
pip install -r requirements.txt

# Verify Flask-Limiter installed
pip list | grep -i limiter

# Verify MySQL driver installed
pip list | grep -i mysql
```

#### 3.3 Verify Configuration
```bash
# Check .env file exists
test -f .env && echo ".env exists" || echo "ERROR: .env missing"

# Check critical env vars
grep -E "DATABASE_URL|FLASK_ENV|GOOGLE_CLIENT" .env || echo "WARNING: Check env vars"

# Verify not in development mode for production
grep "FLASK_ENV=development" .env && echo "WARNING: Development mode!" || echo "✓ Production mode"
```

#### 3.4 Start Application
```bash
# Start with nohup for background running
nohup python3 api.py > server.log 2>&1 &

# Get process ID
PID=$!
echo "Started with PID: $PID"

# Wait for startup
sleep 3

# Verify running
ps aux | grep "python3 api.py" | grep -v grep

# Check if listening on port 5000
netstat -tuln | grep 5000
```

### Phase 4: Post-Deployment Verification (10 minutes)

#### 4.1 Health Check
```bash
# Test basic connectivity
curl http://localhost:5000/auth/me
# Expected: JSON response with user data or redirect

# Check logs for startup errors
tail -20 server.log
grep -i "error" server.log | head -10 || echo "✓ No errors in logs"
```

#### 4.2 Test Core Functionality
```bash
# 1. Test authentication
curl -X GET http://localhost:5000/auth/me

# 2. Test job endpoints
curl http://localhost:5000/api/jobs | jq '.' | head -50

# 3. Test admin endpoints
curl http://localhost:5000/api/admin/locations | jq '.'

# 4. Test event logging
curl -X POST http://localhost:5000/api/log-event \
  -H "Content-Type: application/json" \
  -d '{"event_type":"job_clicked","job_url":"test","job_title":"test"}'

# 5. Test rate limiting (should succeed)
curl http://localhost:5000/api/admin/location-stats/Vizianagaram

# 6. Make 61 rapid requests (should hit rate limit at #61)
for i in {1..65}; do curl -s http://localhost:5000/api/admin/location-stats/Vizianagaram | grep -o '"error"' && break || echo "Request $i: OK"; done
```

#### 4.3 Database Queries Performance
```bash
# Test dashboard performance
time mysql -u root -p job_portal -e "SELECT location, COUNT(*) FROM users GROUP BY location;"

# Should complete in <100ms
```

#### 4.4 Check Admin Dashboard
```bash
# Verify admin dashboard is accessible
curl -L http://localhost:5000/admin | grep -q "Admin" && echo "✓ Admin dashboard accessible" || echo "ERROR: Admin dashboard not found"
```

### Phase 5: Monitoring & Alerting (5 minutes)

#### 5.1 Set Up Log Monitoring
```bash
# Start tailing logs
tail -f server.log &
TAIL_PID=$!

# Monitor for 1 minute for errors
sleep 60

# Kill tail process
kill $TAIL_PID

# Summary of any errors
grep "ERROR\|WARNING" server.log | tail -20 || echo "✓ No errors in first minute"
```

#### 5.2 Configure Alerts
```bash
# Example: Alert if process dies
(while true; do ps aux | grep "python3 api.py" | grep -v grep || alert "Job Portal process died"; sleep 60; done) &

# Save process check PID
echo $! > /var/run/job_portal_monitor.pid
```

#### 5.3 Performance Baseline
```bash
# Record baseline metrics
echo "=== DEPLOYMENT BASELINE ===" > /var/log/job_portal_baseline.txt
echo "Timestamp: $(date)" >> /var/log/job_portal_baseline.txt
curl -I http://localhost:5000/api/admin/location-stats/Vizianagaram >> /var/log/job_portal_baseline.txt
echo "✓ Baseline recorded"
```

---

## Post-Deployment Tasks (Next 24-48 hours)

### Day 1 (First 24 hours)
- [ ] Monitor application logs every 2 hours
- [ ] Check database for errors: `grep "ERROR" server.log | wc -l` (should be <5)
- [ ] Verify no rate limit false positives
- [ ] Test admin functionality manually
- [ ] Check user event tracking: `SELECT COUNT(*) FROM user_events WHERE created_at > NOW() - INTERVAL 24 HOUR;`

### Day 2 (Next 24 hours)
- [ ] Review error logs for patterns
- [ ] Check performance metrics (query times, response times)
- [ ] Verify chart rendering without NaN/Infinity
- [ ] Test concurrent admin access
- [ ] Check session tracking accuracy

### Week 1
- [ ] Monitor production metrics daily
- [ ] Review admin feedback
- [ ] Optimize database queries if needed
- [ ] Document any issues found
- [ ] Plan for low-priority improvements

---

## Rollback Procedure (If Needed)

### Quick Rollback (Last 30 minutes)
```bash
# 1. Stop current application
pkill -f "python3 api.py"

# 2. Revert code to backup tag
git checkout backup-pre-deployment-<timestamp>
# Or to specific commit
git checkout <previous-stable-commit>

# 3. Restart application
nohup python3 api.py > server.log 2>&1 &

# 4. Verify running
ps aux | grep "python3 api.py" | grep -v grep

# 5. Database rollback (if schema changed)
# Restore from backup if needed:
# mysql -u root -p job_portal < /backups/job_portal/job_portal_<timestamp>.sql
```

### Full Rollback (Including Database)
```bash
# 1. Stop application
pkill -f "python3 api.py"

# 2. Restore database from backup
mysql -u root -p job_portal < /backups/job_portal/job_portal_$(date +%Y%m%d_%H%M%S --date='1 hour ago').sql

# 3. Revert code
git checkout backup-pre-deployment-<timestamp>

# 4. Restart
nohup python3 api.py > server.log 2>&1 &

# 5. Verify restored state
curl http://localhost:5000/auth/me
```

---

## Troubleshooting Guide

### Issue: Application won't start
```bash
# Check Python syntax
python3 -m py_compile api.py

# Check for port conflicts
netstat -tuln | grep 5000

# Check error logs
tail -50 server.log | grep -i "error\|traceback"

# Try starting in foreground to see errors
python3 api.py
```

### Issue: Database migration failed
```bash
# Check if tables exist
mysql -u root -p job_portal -e "SHOW TABLES;"

# Restore backup
mysql -u root -p job_portal < /backups/job_portal/latest_backup.sql

# Run migration again
mysql -u root -p job_portal < migration_location_dashboard.sql
```

### Issue: Rate limiting not working
```bash
# Check Flask-Limiter installation
python3 -c "from flask_limiter import Limiter; print('OK')"

# Verify limiter initialized in api.py
grep -n "limiter = Limiter" api.py
```

### Issue: Admin dashboard not loading
```bash
# Check file exists
test -f admin_dashboard.html && echo "File exists"

# Check file is readable
head -20 admin_dashboard.html

# Verify route works
curl http://localhost:5000/admin
```

---

## Deployment Success Criteria

✅ **All Must Pass Before Going Live**

- [ ] Application starts without errors
- [ ] Database migration succeeds
- [ ] All indexes created (verify: 16 total)
- [ ] Core API endpoints respond (Jobs, Auth, Admin)
- [ ] Rate limiting works (can verify with 65+ requests)
- [ ] Admin dashboard accessible
- [ ] Event tracking functioning
- [ ] Performance baseline meets targets (<200ms)
- [ ] No errors in logs for 30 minutes
- [ ] Database backups created and verified

---

## Emergency Contacts

**In case of critical issues during deployment:**

- Primary: Admin Email (admin@cutm.ac.in)
- Secondary: Development Team Lead
- Escalation: CTO or DevOps Lead

**For database issues:**
- DBA: Database Administrator contact
- Backup: Database backup location

---

## Documentation Links

- API Documentation: [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- Project Overview: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- Issue Summaries: [CRITICAL_FIXES_COMPLETED.md](CRITICAL_FIXES_COMPLETED.md)

---

**Deployment Ready**: ✅ YES  
**Estimated Duration**: 30-45 minutes  
**Risk Level**: LOW  
**Rollback Available**: YES  

**Go Live**: 🟢 APPROVED FOR DEPLOYMENT
