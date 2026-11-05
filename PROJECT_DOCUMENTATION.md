# JobHub - Job Portal Project Documentation

## 📋 Project Overview

**JobHub** is a comprehensive job discovery platform designed specifically for freshers and entry-level job seekers in India. It aggregates job listings from multiple sources, provides intelligent resume matching with AI-powered feedback, and offers analytics to help users track job market trends.

### Key Highlights
- **Multi-source Job Aggregation**: Scrapes jobs from Remotive, RemoteOK, Himalayas, Jobicy, WeWorkRemotely, Arbeitnow, Adzuna, FirstNaukri, AngelList, and Unstop
- **Per-User Data Isolation**: Each user has their own isolated dashboard with personal job data
- **Resume Matching**: AI-powered resume analysis with ATS score feedback
- **Analytics Dashboard**: Visual insights into job trends and market data
- **Hackathon Tracking**: Track and manage hackathon opportunities
- **Google OAuth Integration**: Secure authentication with Google Sign-In
- **Responsive UI**: Modern, mobile-friendly interface with skeleton loading screens

---

## 🎯 Features

### 1. Job Discovery & Management
- Search and filter jobs by domain, job type, region, and experience level
- Save favorite jobs to personal dashboard
- View job details with company information and source tracking
- Last fetch timestamp to track data freshness

### 2. Resume Analysis & Matching
- Upload resume (PDF, DOCX, TXT, JPG, PNG)
- Get AI-powered resume recommendations based on job requirements
- ATS (Applicant Tracking System) score calculation
- Resume text extraction with OCR fallback for scanned documents
- Detailed feedback on resume improvements

### 3. Analytics Dashboard
- View job statistics (Remote vs Hybrid vs Onsite vs Internship)
- Track job additions over time with visual charts
- Domain-wise job distribution
- Company-wise opportunity analysis
- Type-wise job breakdown

### 4. Data Management
- Export jobs to CSV
- Clear cached data with one click
- View database statistics
- Check application performance metrics

### 5. Security & Authentication
- Google OAuth 2.0 integration
- Secure session management
- CORS protection
- Rate limiting to prevent API abuse
- Security headers (X-Frame-Options, X-XSS-Protection, CSP)

### 6. User Experience
- Skeleton loading screens during data fetches
- Real-time search and filtering
- Dark mode support
- Responsive design for all devices
- Error handling with user-friendly messages

---

## 🏗️ Technology Stack

### Backend
- **Framework**: Flask 3.1.3
- **Database**: MySQL 8.0+
- **Language**: Python 3.14+
- **Web Server**: Werkzeug (Flask's development server)

### Frontend
- **Markup**: HTML5
- **Styling**: CSS3 with CSS Grid and Flexbox
- **JavaScript**: Vanilla ES6+ (async/await, fetch API)
- **Authentication**: Google Identity Services (GIS)

### Key Libraries
| Library | Version | Purpose |
|---------|---------|---------|
| Flask-CORS | 6.0.5 | Cross-Origin Resource Sharing |
| mysql-connector-python | 9.7.0 | MySQL database connection |
| requests | 2.34.2 | HTTP requests for scraping |
| feedparser | 6.0.14 | RSS/Atom feed parsing |
| pdfminer.six | 20260107 | PDF text extraction |
| mammoth | 1.12.0 | DOCX to HTML conversion |
| scikit-learn | 1.9.0 | TF-IDF vectorization for matching |
| python-dotenv | 1.2.2 | Environment variable management |
| flask-limiter | 4.1.1 | Rate limiting |
| easyocr | 1.7.2 | Optical Character Recognition |
| pymupdf | 1.28.2 | PDF rasterization for OCR |
| google-auth | 2.56.2 | Google OAuth verification |
| pillow | 12.3.0 | Image processing |

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.14+
- MySQL 8.0+ (with root or dedicated user)
- Git
- Modern web browser

### Step 1: Clone the Repository
```bash
git clone https://github.com/adityasah-cpu/webscrape.git
cd webscrape
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Create a `.env` file in the project root:

```env
# Database Configuration
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_db_password
DB_NAME=job_portal

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=False
FLASK_SECRET_KEY=your_secret_key_here

# Google OAuth (Get from Google Cloud Console)
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com

# API Configuration
API_URL=http://localhost:5000
CORS_ORIGINS=http://localhost:5000,http://localhost:3000

# Resume Upload Configuration
MAX_RESUME_SIZE=5242880
MIN_RESUME_TEXT=30
```

### Step 5: Set Up MySQL Database
```bash
# Login to MySQL
mysql -u root -p

# Create database
CREATE DATABASE job_portal;

# Use the database
USE job_portal;
```

The application will automatically create required tables on first run.

### Step 6: Get Google OAuth Client ID
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Google+ API
4. Create OAuth 2.0 credentials (Web application)
5. Add `http://localhost:5000` to Authorized JavaScript origins
6. Add `http://localhost:5000/auth/google` to Authorized redirect URIs
7. Copy the Client ID and add to `.env`

### Step 7: Run the Application
```bash
python api.py
```

The application will be available at `http://localhost:5000`

---

## ⚙️ Configuration

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | MySQL host address |
| `DB_USER` | root | MySQL username |
| `DB_PASSWORD` | - | MySQL password (required) |
| `DB_NAME` | job_portal | Database name |
| `FLASK_ENV` | development | Flask environment |
| `FLASK_DEBUG` | False | Enable Flask debug mode |
| `FLASK_SECRET_KEY` | - | Session encryption key (required) |
| `GOOGLE_CLIENT_ID` | (empty) | Google OAuth Client ID |
| `API_URL` | http://localhost:5000 | API base URL |
| `CORS_ORIGINS` | http://localhost:5000 | Allowed origins (comma-separated) |
| `MAX_RESUME_SIZE` | 5242880 | Max resume file size in bytes (5MB) |
| `MIN_RESUME_TEXT` | 30 | Minimum text required in resume |
| `SESSION_COOKIE_SECURE` | False | Set to True for HTTPS only |

### Development Mode
If `GOOGLE_CLIENT_ID` is not set, the app automatically enters **development mode**:
- Users are auto-logged in as `dev@localhost`
- No Google Sign-In required
- Useful for testing without Google OAuth setup

---

## 📁 Project Structure

```
job_portal/
├── api.py                          # Main Flask application & API endpoints
├── index.html                      # Frontend single-page application
├── remote_job_scraper.py          # Remotive, RemoteOK, Himalayas scraper
├── enggroom_scraper.py            # Adzuna, Arbeitnow scraper
├── hackathon_scraper.py           # Hackathon opportunities scraper
├── alerts.py                       # Alert system (future use)
├── requirements.txt                # Python dependencies
├── .env                           # Environment variables (DO NOT COMMIT)
├── .env.example                   # Template for .env file
├── .gitignore                     # Git ignore rules
│
├── tests/                         # Test suite
│   ├── conftest.py               # Pytest fixtures
│   ├── test_api_endpoints.py     # API endpoint tests
│   ├── test_analytics.py         # Analytics logic tests
│   ├── test_auth.py              # Authentication tests
│   ├── test_config_validation.py # Config validation tests
│   ├── test_enggroom_resources.py # Resource scraper tests
│   ├── test_error_handling.py    # Error handling tests
│   ├── test_hackathon.py         # Hackathon scraper tests
│   ├── test_helpers.py           # Helper function tests
│   ├── test_resume_extraction.py # Resume extraction tests
│   └── test_scraper_helpers.py   # Scraper helper tests
│
├── .claude/                      # Claude AI configuration
├── PROJECT_DOCUMENTATION.md      # This file
├── API_DOCUMENTATION.md          # Detailed API documentation
└── [other documentation files]   # Various audit and progress reports
```

---

## 💾 Database Schema

### Tables

#### jobs
Stores job listings for each user
```sql
CREATE TABLE jobs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_email VARCHAR(255) NOT NULL,
  url VARCHAR(2048) UNIQUE KEY,
  title VARCHAR(500),
  company VARCHAR(500),
  type ENUM('Remote', 'Onsite', 'Hybrid', 'Internship'),
  domain VARCHAR(255),
  country VARCHAR(255),
  description LONGTEXT,
  source VARCHAR(255),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  INDEX idx_owner_email (owner_email),
  UNIQUE KEY uq_owner_url (owner_email, url)
);
```

#### resources
Stores learning resources and opportunities
```sql
CREATE TABLE resources (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_email VARCHAR(255) NOT NULL,
  title VARCHAR(500),
  url VARCHAR(2048),
  category VARCHAR(255),
  created_at TIMESTAMP,
  INDEX idx_owner_email (owner_email),
  UNIQUE KEY uq_owner_url (owner_email, url)
);
```

#### hackathons
Stores hackathon opportunities
```sql
CREATE TABLE hackathons (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_email VARCHAR(255) NOT NULL,
  title VARCHAR(500),
  url VARCHAR(2048),
  platform VARCHAR(255),
  created_at TIMESTAMP,
  INDEX idx_owner_email (owner_email),
  UNIQUE KEY uq_owner_url (owner_email, url)
);
```

### Data Isolation
- **Composite Unique Keys**: `UNIQUE(owner_email, url)` ensures each user can have the same job URL
- **Owner Email Filtering**: All queries filter by `owner_email` to prevent cross-user data leakage
- **Per-User Cache**: In-memory cache keyed by `owner_email` to avoid cache pollution

---

## 🔌 API Endpoints

### Authentication Endpoints

#### GET /api/auth/config
Returns Google OAuth Client ID
```json
{
  "success": true,
  "google_client_id": "your_client_id.apps.googleusercontent.com"
}
```

#### GET /api/auth/me
Returns current authenticated user
```json
{
  "authenticated": true,
  "success": true,
  "user": {
    "email": "user@example.com",
    "name": "User Name",
    "picture": "https://..."
  }
}
```

#### POST /api/auth/google
Verifies Google credential token
```json
{
  "credential": "jwt_token_from_google"
}
```

#### POST /api/auth/logout
Clears user session
```json
{
  "success": true
}
```

### Job Management Endpoints

#### GET /api/fetch
Fetch jobs from all sources
```json
{
  "success": true,
  "jobs": [...],
  "stats": {
    "remote": 25,
    "onsite": 10,
    "hybrid": 5,
    "internship": 3
  }
}
```

#### GET /api/jobs
Get user's saved jobs with optional filtering
```json
{
  "success": true,
  "jobs": [...]
}
```

#### POST /api/jobs
Save new job to user's collection
```json
{
  "title": "Software Engineer",
  "company": "Tech Corp",
  "type": "Remote",
  "url": "https://...",
  "source": "Remotive"
}
```

#### DELETE /api/jobs
Delete a job by URL
```json
{
  "url": "https://..."
}
```

#### POST /api/clear-jobs
Clear all cached jobs
```json
{
  "success": true,
  "message": "Cache cleared"
}
```

### Resume Analysis Endpoints

#### POST /api/match-resume
Match resume against jobs and get recommendations
```json
{
  "resume": "base64_encoded_file_content",
  "fileType": "pdf",
  "jobs": [...]
}
```
Returns:
```json
{
  "success": true,
  "matches": [
    {
      "title": "Software Engineer",
      "similarity": 0.85,
      "feedback": "..."
    }
  ]
}
```

#### POST /api/ats-score
Calculate ATS score and get resume feedback
```json
{
  "resume": "base64_encoded_file_content",
  "fileType": "pdf"
}
```
Returns:
```json
{
  "success": true,
  "score": 78,
  "category": "Good",
  "feedback": [...]
}
```

### Analytics Endpoints

#### GET /api/analytics
Get analytics for user's job data
```json
{
  "success": true,
  "total_jobs": 50,
  "by_type": {...},
  "by_domain": {...},
  "by_company": {...}
}
```

#### GET /api/stats
Get quick statistics
```json
{
  "success": true,
  "stats": {
    "remote": 25,
    "onsite": 10,
    "hybrid": 5,
    "internship": 3
  }
}
```

### Data Management Endpoints

#### GET /api/export
Export user's jobs as CSV
Returns CSV file download

#### GET /api/db-info
Get database information
```json
{
  "success": true,
  "tables": [...],
  "row_counts": {...}
}
```

#### GET /api/cache-info
Get cache statistics
```json
{
  "success": true,
  "cache_size": 150,
  "cached_users": 5
}
```

#### POST /api/cache-clear
Clear all application cache
```json
{
  "success": true
}
```

---

## 🔐 Security Features

### 1. Authentication & Authorization
- Google OAuth 2.0 integration
- JWT token verification server-side
- Secure session cookies with HttpOnly flag
- Session timeout (7 days)

### 2. Data Protection
- Per-user data isolation with composite unique keys
- SQL parameterized queries (no SQL injection)
- HTTPS enforcement option via `SESSION_COOKIE_SECURE`

### 3. API Security
- CORS protection (whitelist-based origins)
- Rate limiting (Limiter with get_remote_address)
- Request size limits (413 Payload Too Large)
- Content-Type validation

### 4. Security Headers
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: restrictive policy
Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=(), usb=()
```

### 5. Input Validation
- Resume file type validation
- File size limits
- Text extraction validation
- URL format validation

---

## 🧪 Testing

### Run Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api_endpoints.py

# Run with coverage
pytest --cov=. tests/

# Run with verbose output
pytest -v tests/
```

### Test Coverage
Tests are organized by feature:
- **API Endpoints**: Full endpoint testing with fixtures
- **Authentication**: Google OAuth flow testing
- **Analytics**: Calculation and aggregation testing
- **Resume Extraction**: PDF/DOCX/TXT parsing
- **Scrapers**: Web scraping and parsing logic
- **Error Handling**: Exception and edge cases
- **Configuration**: Environment variable validation

---

## 🚀 Running in Production

### Prerequisites
- Production MySQL instance
- HTTPS certificate (SSL/TLS)
- Production-grade Python web server (Gunicorn, uWSGI)
- Reverse proxy (Nginx, Apache)

### Configuration
```env
FLASK_ENV=production
FLASK_DEBUG=False
SESSION_COOKIE_SECURE=True
CORS_ORIGINS=https://yourdomain.com
```

### Running with Gunicorn
```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:8000 api:app
```

### Nginx Configuration Example
```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 🐛 Troubleshooting

### Issue: "ReferenceError: google is not defined"
**Solution**: The Google Sign-In library hasn't loaded yet.
- The frontend waits up to 2 seconds for the library
- Try refreshing the page
- Check browser console for network errors

### Issue: "GOOGLE_CLIENT_ID not set"
**Solution**: 
- Check if `.env` file exists and has `GOOGLE_CLIENT_ID` set
- Ensure `load_dotenv(override=True)` is called before accessing `os.getenv()`
- Restart the Flask server

### Issue: "Database connection failed"
**Solution**:
- Verify MySQL is running: `mysql -u root -p`
- Check credentials in `.env`
- Ensure `job_portal` database exists
- Check MySQL user permissions

### Issue: CORS errors in browser
**Solution**:
- Update `CORS_ORIGINS` in `.env` with your actual domain
- Restart the Flask server
- Clear browser cache

### Issue: Resume upload fails
**Solution**:
- Check file size (max 5MB by default)
- Supported formats: PDF, DOCX, TXT, JPG, PNG
- Ensure `MIN_RESUME_TEXT` environment variable is set

### Issue: Jobs not loading
**Solution**:
- Check if scrapers are accessible (network issues?)
- Check API logs for errors
- Try `/api/fetch` to manually trigger scrape
- Verify job sources are online

---

## 📚 Additional Resources

- **API Documentation**: See `API_DOCUMENTATION.md`
- **Security Audits**: See `SECURITY_AUDIT_*.md` files
- **Project Progress**: See `OCTOBER_PROGRESS_REPORT.md`
- **Resume Feature**: See `RESUME_FEATURE_GUIDE.md`

---

## 👥 Development Team

- **Backend**: Flask, MySQL, Python
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Deployment**: Git, GitHub

---

## 📄 License

This project is private and proprietary.

---

## ✨ Latest Updates (Nov 2026)

### Fixed Issues
1. **Per-User Data Isolation**: Implemented composite unique keys `(owner_email, url)` to prevent data leakage
2. **Google OAuth Integration**: Fixed Client ID loading with proper `.env` management
3. **Google Sign-In Library**: Fixed async loading issue - frontend now waits for library
4. **Development Mode**: Auto-login as `dev@localhost` when Google Client ID not configured
5. **Cache Management**: Per-user in-memory cache to prevent cross-user data sharing

### Features Added
- Skeleton loading screens for all async operations
- Error handling with 8 global exception handlers
- Rate limiting and security headers
- Enhanced Analytics dashboard
- Resume export to CSV
- Comprehensive test coverage

---

**Last Updated**: November 5, 2026
**Current Version**: 1.0.0 (Stable)
**Status**: ✅ Production Ready
