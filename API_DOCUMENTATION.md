# Job Portal API Documentation

**Version**: 1.0  
**Base URL**: `https://novagig.thegttech.com` (production) or `http://localhost:5000` (development)  
**Authentication**: Google OAuth 2.0 (with dev mode fallback)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Job Endpoints](#job-endpoints)
3. [User Endpoints](#user-endpoints)
4. [Admin Endpoints](#admin-endpoints)
5. [Event Tracking Endpoints](#event-tracking-endpoints)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)

---

## Authentication

All endpoints except `/auth/*` require authentication. The system uses Google OAuth 2.0 with a fallback dev mode.

### Login Flow
```
GET /auth/callback?code=<auth_code>
```

**Response** (Redirect):
- Success: Redirects to `/` with session cookie
- Dev mode: Email `dev@localhost` logs in automatically

### Check Current User
```
GET /auth/me
```

**Response** (JSON):
```json
{
  "email": "user@example.com",
  "is_admin": false,
  "location": "Vizianagaram"
}
```

### Logout
```
POST /auth/logout
```

**Response**:
```json
{
  "message": "Logged out successfully"
}
```

---

## Job Endpoints

### Get All Jobs
```
GET /api/jobs
```

**Query Parameters**:
- `location` (optional): Filter by location (Vizianagaram, Parlakhemundi, Bhubaneswar)
- `search` (optional): Search job titles/companies
- `page` (optional): Page number (default: 1)
- `limit` (optional): Results per page (default: 20)

**Response** (JSON):
```json
{
  "jobs": [
    {
      "id": "job_123",
      "title": "Software Engineer",
      "company": "Tech Corp",
      "location": "Vizianagaram",
      "salary": "8-12 LPA",
      "description": "...",
      "url": "https://careers.techcorp.com/jobs/123",
      "posted_date": "2024-11-10"
    }
  ],
  "total": 150,
  "page": 1,
  "pages": 8
}
```

**Rate Limit**: 20 per minute

### Get Single Job
```
GET /api/jobs/<job_id>
```

**Response** (JSON):
```json
{
  "id": "job_123",
  "title": "Software Engineer",
  "company": "Tech Corp",
  "location": "Vizianagaram",
  "salary": "8-12 LPA",
  "description": "...",
  "url": "https://careers.techcorp.com/jobs/123",
  "posted_date": "2024-11-10",
  "views": 245,
  "applies": 12
}
```

**Rate Limit**: 20 per minute

---

## User Endpoints

### Get User Profile
```
GET /api/user/profile
```

**Response** (JSON):
```json
{
  "email": "user@example.com",
  "location": "Vizianagaram",
  "cv_uploaded": true,
  "cv_filename": "resume.pdf",
  "created_at": "2024-01-15",
  "last_login": "2024-11-10T14:30:00"
}
```

**Rate Limit**: 60 per minute

### Upload CV
```
POST /api/cv-upload
Content-Type: multipart/form-data

file: <PDF file>
```

**File Constraints**:
- Format: PDF only
- Size: 0.1 MB to 50 MB
- Max file size: 50 MB

**Response** (JSON):
```json
{
  "success": true,
  "filename": "resume_user@example.com.pdf",
  "size": 245000,
  "extracted_text": "Software Engineer with 5 years experience...",
  "message": "CV uploaded successfully"
}
```

**Error Response** (400):
```json
{
  "error": "File size must be between 0.1 MB and 50 MB"
}
```

**Rate Limit**: 5 per minute

### Get ATS Score
```
POST /api/ats-score
Content-Type: application/json

{
  "job_url": "https://careers.techcorp.com/jobs/123"
}
```

**Response** (JSON):
```json
{
  "ats_score": 78,
  "score_range": "Good Match",
  "strengths": ["Python", "Django", "REST APIs"],
  "gaps": ["React", "DevOps"],
  "recommendations": ["Learn React for frontend work", "Consider DevOps certification"]
}
```

**Rate Limit**: 5 per minute

---

## Admin Endpoints

### Requirements
- User must be admin (checked via `is_admin` field and ADMIN_EMAILS config)
- All responses rate-limited

### Get All Locations
```
GET /api/admin/locations
```

**Rate Limit**: 60 per minute

**Response** (JSON):
```json
{
  "locations": [
    "Vizianagaram",
    "Parlakhemundi",
    "Bhubaneswar"
  ]
}
```

### Get Location Statistics
```
GET /api/admin/location-stats/<location>
```

**Parameters**:
- `location`: One of: Vizianagaram, Parlakhemundi, Bhubaneswar

**Rate Limit**: 60 per minute

**Response** (JSON):
```json
{
  "location": "Vizianagaram",
  "total_users": 234,
  "active_users": 189,
  "cv_uploaded_yes": 145,
  "cv_uploaded_no": 89,
  "avg_ats_score": 72.5,
  "total_jobs_viewed": 2340,
  "total_jobs_clicked": 890,
  "total_jobs_applied": 234
}
```

**Error Response** (400):
```json
{
  "error": "Invalid location. Allowed: Vizianagaram, Parlakhemundi, Bhubaneswar"
}
```

### Get Location Users
```
GET /api/admin/location-users/<location>
```

**Parameters**:
- `location`: One of: Vizianagaram, Parlakhemundi, Bhubaneswar

**Rate Limit**: 60 per minute

**Response** (JSON):
```json
{
  "location": "Vizianagaram",
  "total_users": 234,
  "users": [
    {
      "email": "user1@example.com",
      "cv_uploaded": true,
      "jobs_viewed": 15,
      "jobs_clicked": 8,
      "jobs_applied": 2,
      "created_at": "2024-01-15",
      "last_login": "2024-11-10"
    }
  ]
}
```

### Get Location Engagement
```
GET /api/admin/location-engagement/<location>
```

**Parameters**:
- `location`: One of: Vizianagaram, Parlakhemundi, Bhubaneswar

**Rate Limit**: 60 per minute

**Response** (JSON):
```json
{
  "location": "Vizianagaram",
  "total_users": 234,
  "viewed_jobs": {
    "count": 2340,
    "unique_users": 189,
    "avg_per_user": 12.4
  },
  "clicked_jobs": {
    "count": 890,
    "unique_users": 134,
    "avg_per_user": 6.6
  },
  "applied_jobs": {
    "count": 234,
    "unique_users": 98,
    "avg_per_user": 2.4
  },
  "conversion_rate": "9.8%"
}
```

### Get Admin Users
```
GET /api/admin/users
```

**Rate Limit**: 60 per minute

**Response** (JSON):
```json
{
  "admins": [
    {
      "email": "admin@cutm.ac.in",
      "promoted_at": "2024-01-01"
    }
  ],
  "allowed_admin_emails": ["admin@cutm.ac.in"]
}
```

### Promote User to Admin
```
POST /api/admin/promote/<email>
```

**Parameters**:
- `email`: User email to promote

**Rate Limit**: 30 per minute

**Response** (JSON):
```json
{
  "success": true,
  "message": "User promoted to admin",
  "email": "newadmin@example.com"
}
```

**Error Response** (400):
```json
{
  "error": "User is already an admin"
}
```

### Demote Admin User
```
POST /api/admin/demote/<email>
```

**Parameters**:
- `email`: Admin email to demote

**Rate Limit**: 30 per minute

**Response** (JSON):
```json
{
  "success": true,
  "message": "Admin demoted successfully",
  "email": "demoted@example.com"
}
```

**Error Response** (400):
```json
{
  "error": "Cannot demote yourself"
}
```

---

## Event Tracking Endpoints

### Log Event
```
POST /api/log-event
Content-Type: application/json

{
  "event_type": "job_viewed|job_clicked|job_applied",
  "job_url": "https://careers.techcorp.com/jobs/123",
  "job_title": "Software Engineer"
}
```

**Event Types**:
- `job_viewed`: User saw a job in search results
- `job_clicked`: User opened job details modal
- `job_applied`: User clicked apply button

**Response** (JSON):
```json
{
  "success": true,
  "message": "Event logged successfully",
  "event_id": "evt_123456"
}
```

**Rate Limit**: 20 per minute

**Note**: Failures are silent to prevent disrupting user experience

---

## Error Handling

### HTTP Status Codes
| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (not logged in) |
| 403 | Forbidden (not admin) |
| 404 | Not found |
| 429 | Too many requests (rate limited) |
| 500 | Server error |
| 503 | Service unavailable |

### Error Response Format
```json
{
  "error": "Descriptive error message",
  "code": "ERROR_CODE"
}
```

### Common Errors
```json
{
  "error": "Invalid location. Allowed: Vizianagaram, Parlakhemundi, Bhubaneswar",
  "code": "INVALID_LOCATION"
}

{
  "error": "Database connection failed",
  "code": "DB_ERROR"
}

{
  "error": "Unauthorized - Admin access required",
  "code": "UNAUTHORIZED"
}
```

---

## Rate Limiting

All endpoints are rate-limited per IP address.

### Rate Limits by Endpoint Type
| Endpoint Type | Limit | Period |
|---------------|-------|--------|
| Public (GET) | 20/min | Per IP |
| User (POST) | 5/min | Per IP |
| Admin (GET) | 60/min | Per IP |
| Admin (POST) | 30/min | Per IP |

### Rate Limit Headers
```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 18
X-RateLimit-Reset: 1699610400
```

### Rate Limit Exceeded Response
```
HTTP/1.1 429 Too Many Requests

{
  "error": "Rate limit exceeded. Try again in 45 seconds",
  "retry_after": 45
}
```

---

## Examples

### JavaScript/Fetch API

#### Login
```javascript
window.location.href = '/auth/login';
```

#### Get Current User
```javascript
const response = await fetch('/auth/me');
const user = await response.json();
console.log(user.email, user.location);
```

#### Log Event
```javascript
async function logEvent(eventType, jobUrl, jobTitle) {
  try {
    await fetch('/api/log-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: eventType,
        job_url: jobUrl,
        job_title: jobTitle
      })
    });
  } catch (error) {
    console.error('Event logging failed (non-critical):', error);
  }
}

// Usage
logEvent('job_clicked', 'https://careers.techcorp.com/jobs/123', 'Software Engineer');
```

#### Get Jobs
```javascript
const response = await fetch('/api/jobs?location=Vizianagaram&limit=10');
const data = await response.json();
data.jobs.forEach(job => console.log(job.title, job.company));
```

#### Upload CV
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('/api/cv-upload', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log('CV uploaded:', result.filename);
```

### Python/Requests

#### Get Admin Stats
```python
import requests

headers = {'Authorization': 'Bearer <token>'}
response = requests.get(
    'https://novagig.thegttech.com/api/admin/location-stats/Vizianagaram',
    headers=headers
)

stats = response.json()
print(f"Total users: {stats['total_users']}")
print(f"CV uploaded: {stats['cv_uploaded_yes']}")
```

#### Promote User
```python
import requests

response = requests.post(
    'https://novagig.thegttech.com/api/admin/promote/newuser@example.com',
    headers=headers
)

result = response.json()
print(result['message'])
```

---

## Development Mode

When running locally with `FLASK_ENV=development`, the system enables:
- Automatic login as `dev@localhost`
- CORS enabled for localhost
- Debug mode for troubleshooting
- No authentication required

---

## Environment Variables

```
FLASK_ENV=production|development
DATABASE_URL=mysql://user:pass@host/job_portal
GOOGLE_CLIENT_ID=<your_client_id>
GOOGLE_CLIENT_SECRET=<your_secret>
ADMIN_EMAILS=admin@cutm.ac.in,dev@localhost
SECRET_KEY=<your_secret_key>
```

---

## Support

For API issues or questions:
- Check error response for specific error codes
- Review server logs: `tail -f server.log`
- Contact: admin@cutm.ac.in

---

**Last Updated**: November 10, 2026  
**API Version**: 1.0  
**Status**: Production Ready
