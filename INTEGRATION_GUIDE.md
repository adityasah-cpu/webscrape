# Job Portal - Complete Integration Guide

## Overview

This document explains the merged features from `job_finder_trial` and `job_portal`, and how to use them together for maximum effectiveness.

---

## 📁 File Integration Summary

| File | Source | Purpose | Status |
|------|--------|---------|--------|
| **api.py** | job_portal | Flask web API with MySQL | ✅ Enhanced |
| **mysql_db.py** | job_portal | MySQL database layer | ✅ New |
| **index.html** | job_portal | Corporate UI frontend | ✅ Active |
| **scheduler.py** | job_finder_trial | Automated job scraping | ✅ Merged & Enhanced |
| **alerts.py** | job_finder_trial | Telegram/Email/Slack | ✅ Merged |
| **diagnose.py** | job_finder_trial | Test scrapers | ✅ Merged |
| **remote_job_scraper.py** | job_finder_trial | Job scraping logic | ✅ Both use same |
| **scraper_config.json** | NEW | Configuration file | ✅ New |

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install flask flask-cors requests feedparser mysql-connector-python
```

### 2. Start Flask Server
```bash
cd C:\Users\Lucky\Downloads\job_portal
python api.py
```

### 3. Open Web Application
```
http://localhost:5000
```

---

## 🛠️ Three Ways to Fetch Jobs

### **Option 1: Web UI (Manual)**
1. Open http://localhost:5000
2. Select job sources from sidebar
3. Click "Fetch Jobs"
4. View results in real-time

### **Option 2: CLI One-Shot (Automated Once)**
```bash
python scheduler.py
```
- Fetches jobs once
- Stores in MySQL
- Applies filters from config
- Sends alerts if configured

### **Option 3: Continuous Daemon Mode**
```bash
python scheduler.py --daemon
```
- Runs every N hours (default: 8)
- Fetches and stores automatically
- Sends alerts for new jobs
- Press Ctrl+C to stop

### **Option 4: Cron/Task Scheduler (Always-On)**
```bash
python scheduler.py --cron
```
- Prints setup instructions
- Run at specific times via OS scheduler
- Best for production

---

## ⚙️ Configuration

### Config File: `scraper_config.json`

Create or edit this file to customize behavior:

```json
{
  "sources": ["remotive", "remoteok", "himalayas"],
  "filters": {
    "work_type": ["Remote", "Hybrid"],
    "countries": ["India"],
    "job_types": ["Full-time"],
    "keywords": ["python", "developer"]
  },
  "alerts": {
    "enabled": true,
    "telegram": {"bot_token": "...", "chat_id": "..."},
    "email": {"sender": "...", "password": "...", "recipient": "..."},
    "slack": {"webhook_url": "..."}
  },
  "schedule": {
    "interval_hours": 8,
    "send_alert_if_new": true,
    "alert_after_hours": 24
  }
}
```

### Key Settings

| Setting | Description | Example |
|---------|-------------|---------|
| **sources** | Which job boards to scrape | ["remotive", "remoteok"] |
| **work_type** | Only Remote/Hybrid/Onsite | ["Remote"] |
| **countries** | Filter by country | ["India", "USA"] |
| **keywords** | Only jobs matching these | ["python", "ml"] |
| **interval_hours** | Fetch frequency | 8 (every 8 hours) |
| **enabled** | Turn alerts on/off | true/false |

---

## 📬 Alerts & Notifications

### Enable Alerts

1. Configure channels in `scraper_config.json`
2. Set `"enabled": true`
3. Run scheduler

### Telegram Alerts
```json
"telegram": {
  "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
  "chat_id": "987654321"
}
```

**Setup:**
1. Message @BotFather on Telegram
2. Create bot with `/newbot`
3. Get bot token
4. Message @userinfobot to get your chat_id

### Email Alerts
```json
"email": {
  "sender": "your-email@gmail.com",
  "password": "app-specific-password",
  "recipient": "your-email@gmail.com"
}
```

**Setup (Gmail):**
1. Enable 2-factor authentication
2. Go to https://myaccount.google.com/apppasswords
3. Create app password for "Mail"
4. Use that password in config

### Slack Alerts
```json
"slack": {
  "webhook_url": "https://hooks.slack.com/services/T00000000/B00000000/XX"
}
```

**Setup:**
1. Go to https://api.slack.com/messaging/webhooks
2. Create Incoming Webhook
3. Copy webhook URL

### Test Alerts
```bash
# Test via API
curl -X POST http://localhost:5000/api/test-alert \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "telegram": {"bot_token": "...", "chat_id": "..."}
    }
  }'
```

---

## 🔍 Diagnostic Tools

### Test Individual Scrapers
```bash
python diagnose.py
```

Output:
```
✅ remotive: 20 jobs
✅ remoteok: 99 jobs
⚠️ internshala: 0 jobs (no data)
❌ adzuna: API key required
```

---

## 📊 Database Information

### View Database Stats
```bash
curl http://localhost:5000/api/db-info
```

Response:
```json
{
  "database": "MySQL",
  "status": "✓ Connected",
  "total_jobs": 1250,
  "statistics": {
    "by_work_type": {"Remote": 1100, "Hybrid": 150},
    "by_country": {"India": 800, "USA": 450},
    "by_source": {"remotive": 200, "remoteok": 300}
  },
  "last_fetch": "2024-09-21T15:30:00"
}
```

### Database Connection
```
Host: localhost
User: root
Password: aditya@2004
Database: job_portal
```

---

## 🌐 API Endpoints Reference

### Jobs
```
GET  /api/jobs?keyword=python&work_type=Remote&page=1&limit=20
GET  /api/stats
GET  /api/sources
POST /api/fetch (body: {"sources": ["remotive"]})
GET  /api/export?format=csv
DELETE /api/clear-jobs
```

### Database & Alerts
```
GET  /api/db-info
POST /api/test-alert (test notification config)
GET  /api/scheduler-status
```

---

## 📚 Usage Examples

### Example 1: Fetch Remote Jobs from India Only
```bash
curl -X POST http://localhost:5000/api/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["remotive", "remoteok", "himalayas"]
  }'
```

### Example 2: Search Specific Keywords
```bash
curl "http://localhost:5000/api/jobs?keyword=python%20developer&work_type=Remote"
```

### Example 3: Export All Jobs to CSV
```bash
curl "http://localhost:5000/api/export?format=csv" > jobs.csv
```

### Example 4: Get Statistics
```bash
curl http://localhost:5000/api/stats | python -m json.tool
```

---

## 🔄 Workflow Examples

### Workflow 1: Manual Daily Check
```
1. Open http://localhost:5000
2. Click "Fetch Jobs"
3. Browse results
4. Click "Export CSV"
```

### Workflow 2: Automatic Hourly Sync
```bash
# Run once to test
python scheduler.py

# Set up automated (every 8 hours)
python scheduler.py --daemon &

# Or setup cron job
python scheduler.py --cron
# Then add to crontab
```

### Workflow 3: Filtered Alerts
Edit `scraper_config.json`:
```json
{
  "sources": ["remoteok"],
  "filters": {
    "keywords": ["cybersecurity", "security engineer"],
    "countries": ["India"],
    "work_type": ["Remote"]
  },
  "alerts": {
    "enabled": true,
    "email": {
      "sender": "your@gmail.com",
      "password": "app-password",
      "recipient": "your@gmail.com"
    }
  },
  "schedule": {
    "interval_hours": 6
  }
}
```

Then:
```bash
python scheduler.py --daemon
# Runs every 6 hours, sends email for security jobs only
```

---

## 📈 Monitoring & Logging

### View Scheduler Logs
```bash
# If using daemon mode
tail -f scheduler.log

# Or run once to see output
python scheduler.py
```

### Database Query Examples
```bash
# Get MySQL shell
mysql -u root -p
# Enter password: aditya@2004

# View tables
USE job_portal;
SHOW TABLES;

# Count jobs
SELECT COUNT(*) FROM jobs;

# See latest jobs
SELECT title, company, date FROM jobs ORDER BY added_at DESC LIMIT 10;

# Jobs by country
SELECT country, COUNT(*) FROM jobs GROUP BY country;
```

---

## 🚨 Troubleshooting

### Flask server won't start
```bash
# Check if port 5000 is in use
netstat -ano | findstr :5000

# Use different port
# Edit api.py line 206: app.run(port=8000)
```

### MySQL connection error
```bash
# Check MySQL is running
# Verify credentials in mysql_db.py

# Test connection
mysql -h localhost -u root -paditya@2004
```

### Scrapers returning 0 jobs
```bash
# Test individual scrapers
python diagnose.py

# Some sites may have rate limits - wait and retry
```

### Alerts not sending
```bash
# Test alert config
curl -X POST http://localhost:5000/api/test-alert

# Check credentials in scraper_config.json
# Verify internet connection
```

---

## 📋 Files Checklist

| File | Present | Status |
|------|---------|--------|
| api.py | ✅ | Flask server |
| mysql_db.py | ✅ | MySQL database |
| index.html | ✅ | Web UI |
| scheduler.py | ✅ | Auto scheduler |
| alerts.py | ✅ | Notifications |
| diagnose.py | ✅ | Diagnostics |
| remote_job_scraper.py | ✅ | Scraper logic |
| scraper_config.json | ⚠️ | Create on first run |
| scraper_config_template.json | ✅ | Template |

---

## 🎯 Next Steps

1. **Start the server:** `python api.py`
2. **Open in browser:** http://localhost:5000
3. **Fetch some jobs** to test
4. **Configure alerts** (optional)
5. **Set up scheduler** for automation

---

## 🆘 Need Help?

1. Check CORPORATE_UI_SETUP.md for UI customization
2. Run `python diagnose.py` to test scrapers
3. Check logs with `tail -f scheduler.log`
4. Query database directly with mysql client

---

## 🎉 You're All Set!

Your Job Portal now has:
- ✅ Modern corporate web UI
- ✅ MySQL database persistence
- ✅ 12+ job source scrapers
- ✅ Automated scheduling
- ✅ Multi-channel alerts (Telegram, Email, Slack)
- ✅ Advanced filtering
- ✅ CSV export
- ✅ Diagnostic tools

**Happy job hunting! 🚀**
