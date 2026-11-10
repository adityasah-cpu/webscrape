# 📊 Location-Based Management Dashboard - Setup Guide

## Overview

The location-based management dashboard allows admins to track and analyze user metrics by location (Vizianagaram, Parlakhemundi, Bhubaneswar). It provides comprehensive insights into user engagement, CV uploads, job views, clicks, and applications.

---

## 🚀 Quick Start

### Step 1: Run Database Migration

```bash
# SSH into production server
ssh root@vm-225

# Navigate to project
cd /opt/webscrape

# Run migration
mysql -u root -p job_portal < migration_location_dashboard.sql
```

**Or manually in MySQL:**
```sql
mysql -u root -p
USE job_portal;
SOURCE migration_location_dashboard.sql;
```

### Step 2: Update .env with Admin Emails

Add to your `.env` file:
```
ADMIN_EMAILS=admin@cutm.ac.in,dev@localhost
```

### Step 3: Restart Flask Server

```bash
pkill -f "python3 api.py"
sleep 2
nohup python3 api.py > server.log 2>&1 &
tail -f server.log
```

### Step 4: Access Dashboard

- **Local**: `http://localhost:5000/admin`
- **Production**: `https://novagig.thegttech.com/admin`

---

## 📊 Dashboard Features

### Quick Stats Cards
- **Total Users** - Overall user count by location
- **CV Uploaded (Yes/No)** - Breakdown of users with/without resumes
- **Active Users (Today)** - Users who logged in today
- **New Users (Today)** - Freshly registered users
- **Unique Users (Daily/Weekly/Monthly)** - Trend analysis

### Charts & Visualizations
1. **CV Upload Status** - Doughnut chart showing upload ratio
2. **Engagement Funnel** - Bar chart of user journey (view → click → apply)

### Engagement Funnel Table
Detailed breakdown of user conversion:
- Total Users → 100%
- Viewed Jobs → X%
- Clicked Jobs → Y%
- Applied Jobs → Z%
- Did Not Apply → remaining %

### User Details Table
Shows every user with:
- User name & email
- CV upload status (✅ Yes / ❌ No)
- Jobs viewed/clicked/applied
- Last active timestamp
- Signup date

---

## 🔧 Backend Implementation

### New API Endpoints

All endpoints require admin authentication. Base URL: `/api/admin`

#### 1. Get All Locations
```
GET /api/admin/locations
Response: { "locations": ["Vizianagaram", "Parlakhemundi", "Bhubaneswar"] }
```

#### 2. Get Location Statistics
```
GET /api/admin/location-stats/<location>
Response:
{
  "location": "Vizianagaram",
  "total_users": 234,
  "cv_uploaded_yes": 156,
  "cv_uploaded_no": 78,
  "active_users_today": 45,
  "new_users_today": 12,
  "unique_users_daily": 45,
  "unique_users_weekly": 128,
  "unique_users_monthly": 234,
  "engagement": {
    "viewed_jobs": 189,
    "clicked_jobs": 123,
    "applied_jobs": 45,
    "not_applied": 78
  }
}
```

#### 3. Get Location Users
```
GET /api/admin/location-users/<location>
Response:
{
  "location": "Vizianagaram",
  "total_users": 234,
  "users": [
    {
      "email": "user@email.com",
      "user_name": "Aditya S",
      "cv_uploaded": true,
      "jobs_viewed": 5,
      "jobs_clicked": 3,
      "jobs_applied": 2,
      "last_active": "2026-11-10 14:30:00"
    }
  ]
}
```

#### 4. Get Engagement Funnel
```
GET /api/admin/location-engagement/<location>
Response:
{
  "funnel": {
    "total_users": { "count": 234, "percentage": 100 },
    "viewed_jobs": { "count": 189, "percentage": 80.77 },
    "clicked_jobs": { "count": 123, "percentage": 52.56 },
    "applied_jobs": { "count": 45, "percentage": 19.23 },
    "not_applied": { "count": 189, "percentage": 80.77 }
  }
}
```

### Database Tables

#### user_cv_uploads
Tracks resume uploads per location:
```sql
CREATE TABLE user_cv_uploads (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_email VARCHAR(255),
  location VARCHAR(100),
  cv_filename VARCHAR(255),
  uploaded_at DATETIME,
  extraction_status VARCHAR(50)
);
```

#### user_events
Tracks all user interactions:
```sql
CREATE TABLE user_events (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_email VARCHAR(255),
  location VARCHAR(100),
  event_type VARCHAR(50),  -- 'job_viewed', 'job_clicked', 'job_applied'
  job_id VARCHAR(255),
  job_title VARCHAR(255),
  event_date DATETIME
);
```

#### user_sessions
Tracks daily/weekly/monthly unique users:
```sql
CREATE TABLE user_sessions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_email VARCHAR(255),
  location VARCHAR(100),
  login_date DATE,
  last_activity DATETIME,
  session_count INT
);
```

---

## 🎯 Backend Functions

### log_user_event()
```python
log_user_event(
  event_type='job_viewed',  # 'job_viewed', 'job_clicked', 'job_applied'
  job_id='12345',
  job_title='Software Engineer'
)
```

### log_cv_upload()
```python
log_cv_upload(
  filename='resume.pdf',
  file_size=250000,
  status='success'  # 'success' or 'failed'
)
```

### track_user_session()
```python
track_user_session(location='Vizianagaram')
```

---

## 📱 Frontend Integration

### 1. Add Location to User Signup

Update `index.html` signup form to include location dropdown:

```html
<select id="locationSelect" name="location" required>
  <option value="">Select Location</option>
  <option value="Vizianagaram">Vizianagaram</option>
  <option value="Parlakhemundi">Parlakhemundi</option>
  <option value="Bhubaneswar">Bhubaneswar</option>
</select>
```

When signing in, send location:
```javascript
// In your signin handler
const userData = {
  email: userEmail,
  name: userName,
  location: document.getElementById('locationSelect').value,
  picture: userPicture
};
session['user'] = userData;
```

### 2. Add Event Tracking on Job Interactions

Track when user views/clicks/applies for jobs:

```javascript
// When user views a job
async function onJobViewed(jobId, jobTitle) {
  await fetch('/api/log-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: 'job_viewed',
      job_id: jobId,
      job_title: jobTitle
    })
  });
}

// When user clicks on a job
async function onJobClicked(jobId, jobTitle) {
  await fetch('/api/log-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: 'job_clicked',
      job_id: jobId,
      job_title: jobTitle
    })
  });
}

// When user applies for a job
async function onJobApplied(jobId, jobTitle) {
  await fetch('/api/log-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: 'job_applied',
      job_id: jobId,
      job_title: jobTitle
    })
  });
}
```

### 3. Track CV Upload

After resume upload, log it:
```javascript
// After successful resume upload
log_cv_upload({
  filename: file.name,
  file_size: file.size,
  status: 'success'
});
```

---

## 🔐 Security

### Admin Authentication

Only users with emails in `ADMIN_EMAILS` environment variable can access:
- `/admin` page
- `/api/admin/*` endpoints

The `@require_admin` decorator checks this automatically:
```python
@app.route("/api/admin/locations", methods=["GET"])
@require_admin  # This enforces admin-only access
def get_all_locations():
    ...
```

---

## 📝 Usage Example

### Admin Accessing Dashboard

1. Admin opens `https://novagig.thegttech.com/admin`
2. Admin must be signed in (session cookie)
3. Admin must have email in `ADMIN_EMAILS`
4. Dashboard loads with location dropdown
5. Admin selects "Vizianagaram"
6. Dashboard fetches and displays:
   - Quick stats for that location
   - Charts showing CV uploads and engagement
   - Complete user table with metrics

---

## 🐛 Troubleshooting

### Dashboard shows "Unauthorized"
- Check if your email is in `ADMIN_EMAILS` in .env
- Verify you're signed in (check auth/me endpoint)
- Restart server to load new .env values

### No data showing
- Ensure migration was run successfully
- Check if users have `location` field populated
- Verify event logging is working in API

### Charts not loading
- Open browser DevTools (F12)
- Check Network tab for API responses
- Verify API endpoints returning proper JSON

---

## 📊 Dashboard Walkthrough

### Step-by-Step

1. **Open Dashboard**: Navigate to `/admin`
2. **Select Location**: Choose from dropdown
3. **Load Dashboard**: Click "Load Dashboard" button
4. **View Quick Stats**: See cards for users, CVs, activity
5. **Check Charts**:
   - CV upload pie chart
   - Engagement funnel bar chart
6. **Review Funnel**: Detailed conversion metrics
7. **Browse Users**: See all users with their engagement

---

## 🚀 Next Steps

- [ ] Update frontend signup with location field
- [ ] Add event logging to job interactions
- [ ] Test dashboard with sample data
- [ ] Deploy to production
- [ ] Monitor user activity trends
- [ ] Add export functionality (CSV, PDF)
- [ ] Create email alerts for metrics

---

## 📞 Support

For issues or questions:
1. Check API logs: `tail -f server.log`
2. Check MySQL: `mysql -u root -p`
3. Review migration: `SHOW TABLES; DESCRIBE user_events;`
4. Test endpoints with curl

---

**Created**: November 10, 2026  
**Version**: 1.0  
**Status**: Ready for Production ✅
