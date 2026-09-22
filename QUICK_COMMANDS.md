# 🚀 Quick Commands Reference

## 1️⃣ Start Everything

### Start Flask Server
```bash
cd C:\Users\Lucky\Downloads\job_portal
python api.py
```
➜ Open: http://localhost:5000

### Fetch Jobs Manually (Web)
1. Open http://localhost:5000
2. Check job sources
3. Click "Fetch Jobs"
4. Browse results

---

## 2️⃣ Automated Fetching

### Fetch Once
```bash
python scheduler.py
```
✅ Fetches jobs once, stores in MySQL, sends alerts

### Fetch Every N Hours (Daemon)
```bash
python scheduler.py --daemon
```
✅ Runs in background, fetches every 8 hours (configurable)

### Setup Cron Job (Linux/Mac)
```bash
python scheduler.py --cron
```
✅ Shows crontab command to setup automatic scheduling

---

## 3️⃣ Testing & Diagnostics

### Test All Scrapers
```bash
python diagnose.py
```
✅ Shows which sources work, which fail, error messages

### Test API Connection
```bash
curl http://localhost:5000/api/sources
```

### Test Alerts
```bash
curl -X POST http://localhost:5000/api/test-alert \
  -H "Content-Type: application/json" \
  -d '{"config": {"telegram": {"bot_token": "...", "chat_id": "..."}}}'
```

---

## 4️⃣ Database Operations

### View Database Info
```bash
curl http://localhost:5000/api/db-info
```

### Check Job Count
```bash
curl http://localhost:5000/api/stats
```

### Connect to MySQL
```bash
mysql -h localhost -u root -paditya@2004 -D job_portal
```

### Common MySQL Queries
```sql
-- Count total jobs
SELECT COUNT(*) FROM jobs;

-- See latest 10 jobs
SELECT title, company, date FROM jobs ORDER BY added_at DESC LIMIT 10;

-- Jobs by country
SELECT country, COUNT(*) as count FROM jobs GROUP BY country;

-- Jobs by source
SELECT source, COUNT(*) as count FROM jobs GROUP BY source;

-- Clear all jobs
DELETE FROM jobs;
```

---

## 5️⃣ Job Search Operations

### Fetch Specific Sources
```bash
curl -X POST http://localhost:5000/api/fetch \
  -H "Content-Type: application/json" \
  -d '{"sources": ["remotive", "remoteok", "himalayas"]}'
```

### Search by Keyword
```bash
curl "http://localhost:5000/api/jobs?keyword=python"
```

### Filter by Work Type
```bash
curl "http://localhost:5000/api/jobs?work_type=Remote"
```

### Search by Country
```bash
curl "http://localhost:5000/api/jobs?country=India"
```

### Combine Filters
```bash
curl "http://localhost:5000/api/jobs?keyword=python&work_type=Remote&country=India&page=1&limit=50"
```

### Export to CSV
```bash
curl "http://localhost:5000/api/export?format=csv" > jobs.csv
```

### Export to JSON
```bash
curl "http://localhost:5000/api/export?format=json" > jobs.json
```

---

## 6️⃣ Configuration

### Create Default Config
```bash
python scheduler.py
```
✅ Creates `scraper_config.json` with defaults

### Edit Configuration
```bash
# Edit in any text editor
notepad scraper_config.json

# Or use VS Code
code scraper_config.json
```

### View Current Config
```bash
curl http://localhost:5000/api/scheduler-status
```

---

## 7️⃣ Installation & Setup

### Install Dependencies
```bash
pip install flask flask-cors requests feedparser mysql-connector-python
```

### Copy Important Files from job_finder_trial
```bash
copy C:\Users\Lucky\Downloads\job_finder_trial\alerts.py C:\Users\Lucky\Downloads\job_portal\
copy C:\Users\Lucky\Downloads\job_finder_trial\diagnose.py C:\Users\Lucky\Downloads\job_portal\
copy C:\Users\Lucky\Downloads\job_finder_trial\remote_job_scraper.py C:\Users\Lucky\Downloads\job_portal\
```

### Verify MySQL Connection
```bash
mysql -h localhost -u root -paditya@2004
```

---

## 8️⃣ Database Management

### Clear All Jobs
```bash
curl -X DELETE http://localhost:5000/api/clear-jobs
```

### Backup Database
```bash
mysqldump -u root -paditya@2004 job_portal > job_portal_backup.sql
```

### Restore Database
```bash
mysql -u root -paditya@2004 job_portal < job_portal_backup.sql
```

---

## 9️⃣ Troubleshooting

### Check if Flask is Running
```bash
curl http://localhost:5000
```

### Check if MySQL is Running
```bash
mysql -u root -paditya@2004 -e "SELECT 1"
```

### Kill Flask Process (if stuck)
```bash
# Find process
tasklist | findstr python

# Kill by PID
taskkill /PID <PID> /F

# Or use name
taskkill /IM python.exe /F
```

### View Server Logs
```bash
# Check terminal output (tail -f for live logs on Linux/Mac)
# On Windows, keep terminal open or redirect to file:
python api.py > api.log 2>&1
```

### Test Scraper (specific)
```bash
python -c "import remote_job_scraper as rjs; print(rjs.scrape_remotive())"
```

---

## 🔟 Production Setup

### Run with Gunicorn (Production Server)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app
```

### Run Flask in Background (Windows)
```bash
start /B python api.py > server.log 2>&1
```

### Run Scheduler in Background (Windows)
```bash
start /B python scheduler.py --daemon > scheduler.log 2>&1
```

---

## 📋 Alert Configuration Cheat Sheet

### Enable Telegram
1. Message @BotFather
2. Create bot with `/newbot`
3. Get token
4. Message @userinfobot to get chat_id
5. Add to `scraper_config.json`:
```json
"alerts": {
  "enabled": true,
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  }
}
```

### Enable Email
1. Enable 2FA on Gmail
2. Get app password from https://myaccount.google.com/apppasswords
3. Add to `scraper_config.json`:
```json
"email": {
  "sender": "your-email@gmail.com",
  "password": "your-app-password",
  "recipient": "recipient@gmail.com"
}
```

### Enable Slack
1. Create incoming webhook: https://api.slack.com/messaging/webhooks
2. Copy webhook URL
3. Add to `scraper_config.json`:
```json
"slack": {
  "webhook_url": "https://hooks.slack.com/services/..."
}
```

---

## 🎯 Common Workflows

### Workflow: Quick Manual Check
```bash
# 1. Start server
python api.py

# 2. Open browser
# http://localhost:5000

# 3. Select sources, click fetch

# 4. Export CSV
# Click export button in UI
```

### Workflow: Scheduled Auto-Fetch
```bash
# 1. Edit config (optional)
# notepad scraper_config.json

# 2. Start scheduler
python scheduler.py --daemon

# 3. Keep running in background
# Fetches every 8 hours, sends alerts
```

### Workflow: Production Deployment
```bash
# 1. Install gunicorn
pip install gunicorn

# 2. Start API server
gunicorn -w 4 -b 0.0.0.0:5000 api:app

# 3. Start scheduler in separate terminal
python scheduler.py --daemon

# 4. Monitor with logs
tail -f server.log
tail -f scheduler.log
```

---

## 📊 Monitoring Commands

### Real-time Job Count
```bash
curl http://localhost:5000/api/db-info | grep total_jobs
```

### Monitor Scheduler
```bash
# Linux/Mac
tail -f scheduler.log

# Windows (PowerShell)
Get-Content -Path scheduler.log -Tail 10 -Wait
```

### Check CPU/Memory
```bash
# Windows
tasklist | findstr python

# Linux/Mac
ps aux | grep python
```

---

## 🆘 Emergency Commands

### Stop Everything
```bash
# Stop Flask
taskkill /IM python.exe /F

# Or Ctrl+C in terminal
```

### Restart Flask
```bash
python api.py
```

### Reset Database
```bash
# Clear all jobs
curl -X DELETE http://localhost:5000/api/clear-jobs

# Or manually
mysql -u root -paditya@2004 -e "DELETE FROM job_portal.jobs;"
```

### Reinstall from Scratch
```bash
# 1. Stop services
taskkill /IM python.exe /F

# 2. Backup data (optional)
mysqldump -u root -paditya@2004 job_portal > backup.sql

# 3. Reinstall requirements
pip install --upgrade flask flask-cors requests feedparser mysql-connector-python

# 4. Start fresh
python api.py
```

---

## 📱 Quick Access URLs

| URL | Purpose |
|-----|---------|
| http://localhost:5000 | Web UI |
| http://localhost:5000/api/sources | List sources |
| http://localhost:5000/api/jobs | Get jobs |
| http://localhost:5000/api/stats | Statistics |
| http://localhost:5000/api/db-info | Database info |
| http://localhost:5000/api/scheduler-status | Scheduler status |

---

## ✅ Pre-Flight Checklist

Before running:
- [ ] Python 3.7+ installed
- [ ] MySQL running
- [ ] Dependencies installed: `pip install flask flask-cors requests feedparser mysql-connector-python`
- [ ] MySQL credentials correct (root / aditya@2004)
- [ ] Port 5000 available (or change in api.py)
- [ ] Internet connection (for scraping)

---

**That's it! You're ready to go. 🚀**

Pick a command above and get started!
