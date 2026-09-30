# Job Portal API Documentation

Base URL (local development): `http://localhost:5000`

All endpoints are prefixed with `/api` except the root page (`/`). All responses are JSON unless noted otherwise (e.g. CSV export). Storage is MySQL; there is no authentication layer — this API is designed for local/single-user development use.

## Conventions

- **Rate limiting**: Global default is **200 requests/hour, 50/minute** per IP. Specific endpoints have tighter limits (noted per-endpoint below). Exceeding a limit returns:
  ```json
  { "success": false, "error": "Too many requests. Please slow down and try again shortly.", "retry_after": "5 per 1 minute" }
  ```
  with HTTP status `429`.
- **Error shape**: Most endpoints return `{"success": false, "error": "<message>"}` on failure. A few legacy endpoints (`/api/jobs`, `/api/stats`, `/api/export`, `/api/scheduler-status`) return `{"error": "<message>"}` without a `success` key — see each endpoint below.
- **Security headers**: Every response includes `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`.
- **CORS**: Restricted to origins listed in the `CORS_ORIGINS` environment variable (comma-separated), default `http://localhost:5000`.

---

## `GET /api/sources`

Returns the static list of job-board sources the scraper can pull from, grouped by category. All 17 scrapers in `remote_job_scraper.py` are exposed here (this used to be limited to 6).

**Response `200`:**
```json
{
  "remote_boards": [
    {"id": "remotive", "name": "Remotive", "status": "✅"},
    {"id": "remoteok", "name": "RemoteOK", "status": "✅"},
    {"id": "himalayas", "name": "Himalayas", "status": "✅"},
    {"id": "jobicy", "name": "Jobicy", "status": "✅"},
    {"id": "weworkremotely", "name": "WeWorkRemotely", "status": "✅"}
  ],
  "all_jobs": [
    {"id": "arbeitnow", "name": "Arbeitnow", "status": "✅"},
    {"id": "adzuna", "name": "Adzuna (India)", "status": "✅", "note": "Requires free ADZUNA_APP_ID/ADZUNA_APP_KEY in .env"}
  ],
  "freshers": [
    {"id": "internshala", "name": "Internshala", "status": "✅"},
    {"id": "unstop", "name": "Unstop", "status": "✅"},
    {"id": "firstnaukri", "name": "FirstNaukri", "status": "✅"},
    {"id": "angellist", "name": "AngelList/Wellfound", "status": "✅"}
  ],
  "developer_jobs": [
    {"id": "devto", "name": "Dev.to", "status": "✅"},
    {"id": "upwork", "name": "Upwork", "status": "✅"},
    {"id": "toptal", "name": "Toptal", "status": "✅"}
  ],
  "career_pages": [
    {"id": "greenhouse", "name": "Greenhouse", "status": "✅"},
    {"id": "lever", "name": "Lever", "status": "✅"},
    {"id": "ashby", "name": "Ashby", "status": "✅"}
  ]
}
```
`adzuna` covers India-wide remote/hybrid/onsite roles but needs free API keys from developer.adzuna.com — without them it returns an error status for that source (doesn't break the rest of the fetch).

---

## `POST /api/fetch`

**Rate limit: 5/minute.**

Scrapes jobs from the requested sources, deduplicates them, tags each with detected domains, and upserts **all of them** into MySQL — both fresher/internship and experienced roles. (Previously this endpoint discarded everything except fresher-classified jobs at fetch time; that filtering now happens at query/match time instead via `is_fresher_job()`/`is_experienced_job()`, so nothing scraped is thrown away.)

**Request body:**
```json
{ "sources": ["remotive", "internshala", "firstnaukri"] }
```
`sources` values must match an `id` from `GET /api/sources` (internally mapped to `remote_job_scraper.py` scraper function names). Unknown ids are silently ignored.

**Response `200`:**
```json
{
  "success": true,
  "jobs_count": 137,
  "inserted": 137,
  "skipped": 0,
  "total_stored": 137,
  "fresher_count": 22,
  "experienced_count": 115,
  "status": {
    "remotive": {"success": true, "count": 45},
    "internshala": {"success": false, "error": "Connection timeout"}
  },
  "stats": { "...": "see /api/stats shape" },
  "last_fetch": "2026-09-28T12:00:00.000000"
}
```
- `jobs_count` / `total_stored` — total unique jobs scraped and stored (equal to each other now that nothing gets discarded at fetch time).
- `fresher_count` / `experienced_count` — informational breakdown of how many of the stored jobs fall into each bucket (see `GET /api/jobs`'s `experience_level` param and `POST /api/match-resume` below for how to actually filter by this).
- `status` — per-source scrape outcome; a source failing (network error, etc.) does not fail the whole request — other sources still get processed and saved.

**Response `500`** on unexpected failure: `{"success": false, "error": "Failed to fetch jobs. Please try again."}` (the real exception is logged server-side, not exposed to the client).

---

## `POST /api/match-resume`

**Rate limit: 10/minute.**

Upload a resume file; the server extracts its text and ranks jobs currently in the database by relevance (TF-IDF + cosine similarity over each job's title/company/category/job_type/work_type/location/domains). **Nothing about the resume is persisted** — it's parsed in memory and discarded after the response is built.

The candidate pool is filtered to **either fresher/internship roles or experienced roles** before matching — the caller must say which via `experience_level`, since a fresher's resume shouldn't get ranked against senior roles and vice versa.

**Request:** `multipart/form-data` with:
| Field | Required | Description |
|---|---|---|
| `resume` | Yes | The file. Accepted extensions: `.pdf`, `.docx`, `.txt`. Max size 5 MB (`MAX_RESUME_SIZE` env var), enforced by Flask — an oversized upload gets rejected with `413` before the route body even runs. |
| `experience_level` | Yes | `"fresher"` or `"experienced"`. Can also be sent as a query param instead of a form field. Determines which bucket of stored jobs (via `is_fresher_job()`/`is_experienced_job()`) the resume gets matched against. |

Optional query param `top_n` (default `20`, max `100`) — how many ranked matches to return.

**Response `200` (success):**
```json
{
  "success": true,
  "matches": [
    { "id": 42, "title": "Data Scientist", "company": "Acme", "match_score": 84.2, "domains": ["AIML", "Data Analytics"], "...": "rest of job fields" }
  ],
  "total_jobs_considered": 615,
  "experience_level": "experienced",
  "resume_domains": ["AIML", "Data Analytics"],
  "resume_chars_extracted": 2143
}
```
`matches` is sorted descending by `match_score` (0–100). `total_jobs_considered` reflects only the filtered pool (e.g. only experienced-classified jobs), not the full database.

**Response `200` when no jobs exist in that bucket yet** (not an error — nothing to rank):
```json
{
  "success": true,
  "matches": [],
  "total_jobs_considered": 0,
  "experience_level": "fresher",
  "resume_domains": ["AIML"],
  "message": "No fresher jobs available yet. Fetch jobs first, then upload your resume."
}
```

**Error responses:**
| Status | Condition | Body |
|---|---|---|
| `400` | No `resume` field in the request | `{"success": false, "error": "No resume file provided (expected form field 'resume')"}` |
| `400` | Empty filename | `{"success": false, "error": "No file selected"}` |
| `400` | Unsupported extension (not pdf/docx/txt) | `{"success": false, "error": "Unsupported file type: .doc. Allowed: pdf, docx, txt"}` |
| `400` | Empty file body | `{"success": false, "error": "Uploaded file is empty"}` |
| `400` | Corrupt/unparseable PDF or DOCX | `{"success": false, "error": "Could not parse this file: <details>"}` |
| `400` | Missing or invalid `experience_level` | `{"success": false, "error": "experience_level is required and must be 'fresher' or 'experienced'"}` |
| `422` | Extracted text shorter than 30 chars (e.g. scanned/image-only PDF) | `{"success": false, "error": "Could not extract enough readable text..."}` |
| `413` | File exceeds `MAX_RESUME_SIZE` | Flask's default payload-too-large response |
| `429` | Rate limit exceeded | See [Conventions](#conventions) |

---

## `GET /api/jobs`

Filtered, paginated read of stored jobs.

**Query parameters** (all optional):
| Param | Type | Description |
|---|---|---|
| `keyword` | string | Case-insensitive substring match against `title` or `company` |
| `work_type` | string | Exact match: `Remote` / `Hybrid` / `Onsite`. When `Onsite`, results are further restricted to Pan-India locations only (matched against a curated list of Indian city/country keywords) |
| `country` | string | Exact match against `country` field |
| `job_type` | string | Exact match against `job_type` field (e.g. `Internship`, `Full-time`) |
| `sources` | string | Comma-separated list of source display names (e.g. `Remotive,Internshala`) |
| `domain` | string | One of `AIML`, `Data Analytics`, `Blockchain`, `AR VR`, `Cybersecurity`, or `All` |
| `experience_level` | string | `"fresher"` or `"experienced"` — filters using `is_fresher_job()`/`is_experienced_job()`. Omit for both. The old `?fresher=true` boolean param is still accepted as an alias for `experience_level=fresher`. |
| `page` | int | Default `1`, clamped to ≥1 |
| `limit` | int | Default `20` |

**Response `200`:**
```json
{
  "jobs": [ { "...": "job fields" } ],
  "total": 137,
  "page": 1,
  "pages": 7,
  "limit": 20,
  "from_cache": false,
  "storage": "mysql"
}
```

**Response `500`:** `{"jobs": [], "total": 0, "page": 1, "pages": 0, "error": "Failed to load jobs. Please try again."}` — note this endpoint does **not** use the `success` key convention.

---

## `GET /api/stats`

Aggregate counts over all stored jobs.

**Response `200`:**
```json
{
  "total_jobs": 1243,
  "by_work_type": {"Remote": 502, "Onsite": 727, "Hybrid": 14},
  "by_country": {"Germany": 383, "United States": 153, "...": "..."},
  "by_category": {"Engineering": 29, "...": "..."},
  "by_source": {"Arbeitnow": 767, "Himalayas": 178, "...": "..."},
  "from_cache": false,
  "storage": "mysql"
}
```

---

## `GET /api/analytics`

Aggregated data for the frontend analytics dashboard (summary counts, a jobs-added time series, domain/work-type distribution, and top sources/countries/companies). Built from `load_jobs_from_db()` in Python (benefits from the same in-memory cache as other endpoints — no extra DB queries).

**Query parameters** (all optional):
| Param | Type | Default | Bounds |
|---|---|---|---|
| `days` | int | `14` | clamped to `1`–`90` |
| `top_n` | int | `10` | clamped to `1`–`50` |

Invalid/non-numeric values silently fall back to the defaults rather than erroring.

**Response `200`:**
```json
{
  "success": true,
  "summary": {
    "total_jobs": 1243,
    "added_today": 0,
    "added_this_week": 1243,
    "total_companies": 564,
    "total_sources": 6
  },
  "jobs_over_time": [
    {"date": "2026-09-15", "count": 0},
    {"date": "2026-09-21", "count": 1243},
    "...": "one entry per day in the requested window, zero-filled for days with no inserts, sorted ascending"
  ],
  "by_domain": {"General": 1058, "AIML": 142, "Data Analytics": 30, "Cybersecurity": 15, "AR VR": 2, "Blockchain": 1},
  "by_work_type": {"Onsite": 727, "Remote": 502, "Hybrid": 14},
  "top_sources": [{"name": "Arbeitnow", "count": 767}, "...": "up to top_n entries, sorted descending"],
  "top_countries": [{"name": "Germany", "count": 383}, "..."],
  "top_companies": [{"name": "sumup", "count": 56}, "..."]
}
```

`added_today`/`added_this_week` are computed from each job's `added_at` timestamp (when it was inserted/last upserted), not from the job posting's own `date` field. A job counts toward `by_domain` once per tag if it matches multiple domains (same behavior as `detect_job_domain()`).

**Response `500`:** `{"success": false, "error": "Failed to load analytics. Please try again."}`

---

## `GET /api/export`

Export all stored jobs.

**Query parameters:**
| Param | Values | Default |
|---|---|---|
| `format` | `csv` \| `json` | `csv` |

**Response `200` (`format=csv`):** `Content-Type: text/csv`, `Content-Disposition: attachment; filename=jobs.csv`. Columns match `remote_job_scraper.FIELDS` (source, title, company, work_type, country, location, job_type, category, salary, date, start_date, end_date, url) — note `domains` is **not** included in the CSV export.

**Response `200` (`format=json`):** raw JSON array of job objects (includes `domains`).

**Response `400`** for any other `format` value: `{"error": "Unsupported export format: xml. Use 'csv' or 'json'."}`

---

## `GET /api/db-info`

Database connection/health summary.

**Response `200`:**
```json
{
  "database_engine": "MySQL",
  "status": "✓ Active",
  "total_jobs": 1243,
  "statistics": { "...": "same shape as /api/stats" },
  "host": "localhost",
  "database": "job_portal",
  "note": "Data stored in MySQL database."
}
```

---

## `DELETE /api/clear-jobs`

**Rate limit: 3/minute.** Deletes **all** rows from the `jobs` table. Irreversible — no confirmation step at the API level.

**Response `200`:** `{"success": true, "message": "All jobs cleared"}`
**Response `500`:** `{"success": false, "error": "Failed to clear jobs. Please try again."}` (or `"Database connection failed"` if MySQL is unreachable)

---

## `POST /api/test-alert`

Sends a test notification (Telegram/Email/Slack, depending on config) using the `alerts` module, against a hardcoded sample job.

**Request body:**
```json
{ "config": { "telegram": { "enabled": true, "bot_token": "...", "chat_id": "..." } } }
```

**Response `200`:** `{"success": true, "message": "Test alerts sent", "results": {"...": "per-channel outcome"}}`
**Response `500`:** `{"success": false, "error": "Failed to send test alert. Check your alert configuration."}`

---

## `GET /api/cache-info`

Reports on the in-memory jobs cache (a short-lived TTL cache in front of `load_jobs_from_db()`, **not** Redis — Redis is not used by this app).

**Response `200`:**
```json
{
  "cache": {
    "status": "active",
    "ttl_seconds": 15,
    "age_seconds": 3.2,
    "cached_jobs": 1243,
    "note": "In-memory cache for jobs table reads. Redis is not used."
  },
  "storage": "mysql"
}
```

---

## `DELETE /api/cache-clear`

Manually invalidates the in-memory jobs cache (forces the next `/api/jobs`/`/api/stats`/`/api/match-resume` call to re-read from MySQL). Does **not** delete any data.

**Response `200`:** `{"success": true, "message": "Jobs cache cleared"}`

---

## `GET /api/scheduler-status`

Reports whether a `scraper_config.json` file exists in the project root (used for an optional external scheduler, not implemented as a background process within this app).

**Response `200`:**
```json
{
  "status": "active",
  "config": { "...": "parsed contents of scraper_config.json, if present" },
  "config_file": "scraper_config.json",
  "note": "Storage: MySQL. Scheduler config (if any) is separate from the jobs database."
}
```
`status` is `"not configured"` and `config` is `{}` if the file doesn't exist.

---

## `GET /`

Serves the single-page frontend (`index.html`).

**Response `200`:** `Content-Type: text/html`
**Response `404`:** if `index.html` is missing from the project root.

---

## Fresher / Experienced Detection Logic

`is_fresher_job()` in `api.py` identifies genuine entry-level/internship postings:

1. **Reject** if the job's title/category/description contains any experience-requirement keyword (`senior`, `2+ years`, `5+ years`, `mid-level`, `staff engineer`, etc.).
2. **Accept** if it contains an explicit fresher/internship keyword (`fresher`, `intern`, `graduate`, `trainee`, `entry-level`, `campus`, etc.).
3. **Reject by default** otherwise — a job with neither signal is excluded (strict mode, favors precision over recall).

`is_experienced_job()` is simply `not is_fresher_job(job)` — every stored job lands in exactly one of the two buckets. A listing with no experience signal at all defaults to the *experienced* bucket, since that's the norm for real-world postings that don't explicitly call out "fresher."

Both functions are used at **query/match time** (`GET /api/jobs`'s `experience_level` param, `POST /api/match-resume`'s required `experience_level` field), not at fetch time — `POST /api/fetch` stores every scraped job regardless of experience level.

## Domain Detection Logic

Both stored jobs (`detect_job_domain()`) and uploaded resumes (`extract_resume_keywords()`) are tagged against the same keyword vocabulary (`DOMAIN_KEYWORDS` in `api.py`) covering **AIML**, **Data Analytics**, **Blockchain**, **AR VR**, and **Cybersecurity**, falling back to **General** if nothing matches. Matching uses word-boundary regex (not raw substring matching), so short keywords like `ai`/`ml`/`ar`/`vr` only match as whole words — e.g. "Retail Manager" does **not** get tagged `AIML` just because it contains the letters "ai".
