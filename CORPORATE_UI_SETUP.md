# 🏢 Corporate UI Setup Guide

## What You Get

A professional, enterprise-grade job discovery platform with:

✅ Modern dark sidebar navigation  
✅ Beautiful gradient stat cards  
✅ Responsive job cards with hover effects  
✅ Advanced filtering system  
✅ Real-time pagination  
✅ Export to CSV  
✅ Professional color scheme  
✅ Smooth animations & transitions  
✅ Mobile responsive design  

---

## Prerequisites

```bash
# Python 3.7+
python3 --version

# Flask & CORS
pip install flask flask-cors
```

---

## Quick Start

### Step 1: Copy Files to Your Project

```bash
cd ~/Desktop/Expts

# You should have:
# ✓ remote_job_scraper.py
# ✓ db.py
# ✓ api.py (new)
# ✓ index.html (new)
```

### Step 2: Install Flask

```bash
source venv/bin/activate
pip install flask flask-cors
```

### Step 3: Run the Server

```bash
cd ~/Desktop/Expts
source venv/bin/activate
python api.py
```

You'll see:
```
 * Running on http://localhost:5000
 * Press CTRL+C to quit
```

### Step 4: Open in Browser

```
http://localhost:5000
```

That's it! 🎉

---

## Features

### 📊 Dashboard Stats

Three beautiful gradient cards showing:
- **Remote Jobs** 📍
- **Hybrid Jobs** 🏢
- **Onsite Jobs** 🏪

Updates instantly when you fetch jobs.

### 🎯 Sidebar Navigation

**Clean source selection:**
- Remote Boards (5 sources)
- Freshers & Internships (2 sources)
- All Jobs (2 sources)

Each source shows job count badge.

### 🔍 Advanced Filtering

Filter by:
- **Keywords** — search title + company
- **Work Type** — Remote, Hybrid, Onsite
- **Country** — location-based search

Filters update in real-time.

### 💼 Job Cards

Each job displays:
- **Title & Company**
- **Work Type** (badge color-coded)
- **Location** 📍
- **Country** 🌍
- **Posted Date** 📅
- **Source** (which scraper found it)
- **Salary** 💰 (if available)
- **Apply Now** button (direct link)

Hover effects with smooth animations.

### 📄 Export

Download all jobs as CSV with one click:
```
📥 Export CSV
```

Opens in Excel, Google Sheets, etc.

### 📱 Pagination

View 10 jobs per page with numbered buttons.

---

## API Endpoints

The Flask backend provides:

```
GET  /api/sources          — List all job sources
POST /api/fetch            — Fetch jobs from selected sources
GET  /api/jobs             — Get filtered jobs
GET  /api/stats            — Get job statistics
GET  /api/export           — Export jobs (CSV or JSON)
GET  /                     — Serve corporate UI
```

### Example: Fetch Jobs

```bash
curl -X POST http://localhost:5000/api/fetch \
  -H "Content-Type: application/json" \
  -d '{"sources": ["remotive", "remoteok", "himalayas"]}'
```

Response:
```json
{
  "success": true,
  "jobs_count": 320,
  "status": {
    "remotive": {"success": true, "count": 20},
    "remoteok": {"success": true, "count": 100},
    "himalayas": {"success": true, "count": 200}
  },
  "stats": {
    "total": 320,
    "by_work_type": {
      "Remote": 300,
      "Hybrid": 20,
      "Onsite": 0
    },
    "by_country": {
      "Worldwide": 250,
      "India": 70
    }
  }
}
```

---

## Design System

### Colors

```css
Primary Blue:    #1e40af
Accent Blue:     #3b82f6
Dark BG:         #0f172a
Light BG:        #f8fafc
Success Green:   #10b981
Warning Amber:   #f59e0b
Error Red:       #ef4444
```

### Typography

- **Headers:** 28px, Bold
- **Titles:** 16px, Semi-bold
- **Body:** 14px, Regular
- **Labels:** 12px, Uppercase, Semi-bold

### Spacing

- **Sidebar:** 280px fixed
- **Padding:** 30px standard, 20px compact
- **Gap:** 20px between cards, 15px between items

---

## Customization

### Change Logo Text

Edit `index.html`:
```html
<div class="logo">
    <span class="logo-icon">🎯</span>
    <span>Your Company Name</span>
</div>
```

### Change Colors

Edit CSS variables in `<style>`:
```css
:root {
    --primary: #1e40af;      /* Change these */
    --secondary: #0f172a;
    --accent: #3b82f6;
    ...
}
```

### Change Card Layout

Edit `.job-card` CSS or modify the job card HTML in the `renderJobs()` function.

---

## Troubleshooting

### "Connection refused" error

**Problem:** Flask not running

**Solution:**
```bash
python api.py
# Check that it says "Running on http://localhost:5000"
```

### "No jobs found" after fetch

**Problem:** 
1. Didn't select any sources
2. Scrapers are rate-limited
3. Network issue

**Solution:**
```bash
python diagnose.py
# Use only ✅ working sources
```

### JSON API errors

**Problem:** CORS error when fetching

**Solution:** Make sure Flask is running with CORS enabled:
```python
from flask_cors import CORS
CORS(app)  # Already in api.py
```

### Styling looks broken

**Problem:** CSS not loading

**Solution:** Open browser DevTools (F12) and check Console for errors. Make sure `index.html` is in the same folder as `api.py`.

---

## Production Deployment

### Using Gunicorn (production server)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app
```

### Using Nginx (reverse proxy)

```nginx
server {
    listen 80;
    server_name jobs.example.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
    }
}
```

### Docker (optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install flask flask-cors requests feedparser
CMD ["python", "api.py"]
```

---

## Advanced Features

### Add More Statistics

In `api.py`, modify the `/api/stats` endpoint:
```python
@app.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify({
        "total": len(cache["jobs"]),
        "by_country": {...},
        "by_source": {...},
        "new_today": len([j for j in cache["jobs"] if is_today(j["date"])]),
        ...
    })
```

### Add Charts

In `index.html`, add Chart.js:
```html
<canvas id="statsChart"></canvas>
<script>
    new Chart(document.getElementById("statsChart"), {
        type: 'doughnut',
        data: {
            labels: ['Remote', 'Hybrid', 'Onsite'],
            datasets: [{
                data: [300, 20, 0],
                backgroundColor: ['#667eea', '#f093fb', '#4facfe']
            }]
        }
    });
</script>
```

### Add Authentication

```python
from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()

@auth.verify_password
def verify(username, password):
    return username == "admin" and password == "secret"

@app.route("/api/jobs", methods=["GET"])
@auth.login_required
def get_jobs():
    ...
```

---

## File Structure

```
~/Desktop/Expts/
├── venv/
├── remote_job_scraper.py    ← Job scrapers
├── db.py                    ← Database
├── api.py                   ← Flask API (NEW)
├── index.html               ← Corporate UI (NEW)
├── app.py                   ← Old Streamlit UI
├── scheduler.py
├── alerts.py
└── ...other files
```

---

## Keyboard Shortcuts

- **Ctrl+K:** Focus search (coming soon)
- **Ctrl+E:** Export jobs (coming soon)

---

## Support

If you encounter issues:

1. Check Flask is running: `python api.py`
2. Open browser DevTools (F12)
3. Check Console for errors
4. Run diagnostic: `python diagnose.py`

---

**You now have a production-ready corporate UI!** 🚀

Enjoy discovering amazing jobs with style! ✨
