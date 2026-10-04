# Job Portal — Project Status Report
**Generated:** 2026-10-04
**Repo:** `adityasah-cpu/webscrape` (public) · **Branch:** `main` · **Latest commit:** `42160f3`

---

## 1. What this project is

A Flask + MySQL web app that scrapes job listings from 17 external job boards, classifies each one as **Fresher/Internship** or **Experienced**, tags it by tech domain (AI/ML, Data Analytics, Blockchain, AR/VR, Cybersecurity), and lets a candidate upload their résumé to get stored jobs ranked by relevance. The candidate picks "Fresher" or "Experienced" before uploading, and only jobs from the matching bucket are ranked. A single-page vanilla HTML/CSS/JS frontend talks to a REST API; there's an analytics dashboard, CSV/JSON export, and manual Telegram/Email/Slack alert testing.

**Résumé reading supports scanned documents.** If a PDF has no extractable text layer (a scanned/printed-to-PDF resume), or the candidate uploads a photo (`.jpg`/`.jpeg`/`.png`) of a paper resume, the system automatically falls back to OCR (EasyOCR + PyMuPDF) to read it — verified end-to-end against a real 11-year-experience resume reconstructed as a simulated scan.

---

## 2. Architecture

```
Browser (index.html, ~1,800 lines, no build step, no external JS libs)
    │  fetch() calls to same-origin REST API
    ▼
Flask API (api.py, ~1,250 lines)
    │
    ├── remote_job_scraper.py  →  17 scraper functions hitting external
    │                              job-board APIs/RSS feeds (Remotive,
    │                              RemoteOK, Himalayas, Jobicy,
    │                              WeWorkRemotely, Arbeitnow, Adzuna,
    │                              Internshala, Unstop, FirstNaukri,
    │                              AngelList, Dev.to, Upwork, Toptal,
    │                              Greenhouse, Lever, Ashby)
    │
    ├── alerts.py  →  Telegram / Email / Slack notification senders
    │                 (reachable via POST /api/test-alert, not yet
    │                 wired to fire automatically on new jobs)
    │
    └── MySQL (`job_portal` database, single `jobs` table)
```

**Storage:** MySQL only.
**Caching:** a 15-second in-memory TTL cache in front of `load_jobs_from_db()`, invalidated on every write.
**Matching engine:** scikit-learn `TfidfVectorizer` + cosine similarity, fit fresh per résumé upload against **title (double-weighted), company, category, job type, work type, location, domain tags, and full job description** (when the source provides one).
**OCR:** EasyOCR (PyTorch-based) with PyMuPDF rasterizing PDF pages at 200 DPI, lazy-loaded and cached as a singleton on first use (~2-30s depending on whether models are already cached), capped at the first 5 pages of a PDF.

---

## 3. Features that are implemented and working

| Feature | Status | Notes |
|---|---|---|
| Multi-source job scraping | ✅ Working | 17 scrapers, all selectable in the UI across 5 categories |
| Fresher vs. Experienced classification | ✅ Working | Keyword-based; every job lands in exactly one bucket. Candidate selects their level before upload, and matching only considers that bucket |
| Domain auto-tagging (5 categories) | ✅ Working | Word-boundary keyword matching |
| Résumé upload + job matching | ✅ Working | PDF (digital or scanned)/DOCX/TXT/JPG/JPEG/PNG, in-memory only (never written to disk), TF-IDF ranking against title + category + **full job description** |
| OCR fallback for scanned resumes | ✅ Working | Verified against a simulated scan of a real 11-year-experience resume: OCR correctly read all sections, matching correctly surfaced Business Operations/Project Manager roles from the experienced pool |
| Job descriptions scraped and stored | ✅ Working | 12 of 17 scrapers now capture full description text (where the source API provides one); truncated to 4,000 chars per job to bound DB row size and TF-IDF fit time |
| Analytics dashboard | ✅ Working | Summary cards, jobs-added timeline, domain/work-type/source/country/company breakdowns |
| CSV / JSON export | ✅ Working | Includes description column |
| Rate limiting | ✅ Working | Global 200/hr·50/min, stricter per-route limits on expensive/destructive endpoints |
| In-memory jobs cache | ✅ Working | 15s TTL, auto-invalidated on writes |
| Automated schema migration | ✅ Working | `init_db()` diffs actual columns/indexes/widths against expected and migrates automatically — verified live against the real database |

---

## 4. API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/sources` | List available scraper sources for the UI checkboxes |
| POST | `/api/fetch` | Scrape selected sources, classify fresher/experienced, upsert into MySQL |
| POST | `/api/match-resume` | Upload a résumé + experience level, get ranked job matches |
| GET | `/api/jobs` | Filtered/paginated job listing |
| GET | `/api/stats` | Aggregate counts (work type, country, category, source) |
| GET | `/api/analytics` | Dashboard data (time series, top-N breakdowns) |
| GET | `/api/export` | CSV or JSON export |
| GET | `/api/db-info` | Connection/health summary |
| DELETE | `/api/clear-jobs` | Wipe all stored jobs |
| POST | `/api/test-alert` | Send a test notification via configured channel |
| GET | `/api/cache-info` | In-memory cache status |
| DELETE | `/api/cache-clear` | Manually invalidate the cache |
| GET | `/api/scheduler-status` | Reports on an optional (currently unused) scheduler config file |
| GET | `/` | Serves the frontend |

Full request/response documentation: `API_DOCUMENTATION.md`. Résumé feature details: `RESUME_FEATURE_GUIDE.md`.

---

## 5. Testing & quality

- **144 automated tests, 85% coverage on `api.py`**, all passing (`pytest`)
- Tests are fully mocked at the database boundary — the suite never touches real MySQL data
- Coverage includes: fresher/domain detection, résumé text extraction (PDF/DOCX/TXT/image, including the OCR fallback branches), TF-IDF matching and ranking, all API endpoints, pagination edge cases, config validation, SSRF protection, security headers, and scraper-level description handling (HTML-stripping, truncation)
- Verified live against the real server + real MySQL data multiple times, not just mocked tests — most recently: full OCR → matching pipeline against a simulated scan of a real 11-year-experience resume, confirming correct text extraction and correct fresher/experienced-bucket filtering

---

## 6. Security posture

Went through five rounds of audit-and-fix (history in `SECURITY_AUDIT_2.md` through `SECURITY_AUDIT_5.md`, `COMPREHENSIVE_AUDIT_REPORT.md`). Current state:

**Fixed:**
- Credentials moved out of source code into `.env` (gitignored)
- A MySQL password that had been hardcoded in tracked files was scrubbed from *all* git history (`git-filter-repo`, force-pushed, independently re-verified against a fresh GitHub clone) and rotated
- XSS: all scraped/external data is HTML-escaped everywhere it's rendered
- SSRF: the Slack-webhook alert channel validates the URL is actually `hooks.slack.com` before any outbound request
- `/api/test-alert` rate-limited to 5/hour
- Flask debug mode defaults to `False`, reads from `.env`, warns on startup if enabled
- SQL identifiers (database name) validated against an allowlist
- `Content-Security-Policy`, `Permissions-Policy`, `X-Frame-Options`, `X-Content-Type-Options` headers present and verified to actually block an injected external script
- Dependency versions kept in sync with what's installed, scanned with `pip-audit` — zero known CVEs
- A live data-loss bug (jobs silently failing to insert due to too-narrow columns and missing indexes) found and fixed with defensive per-field truncation, verified across repeated re-fetches: 0 failures, 100% of jobs saved

**Known, accepted limitation (by design, not a bug):**
- **No authentication on any endpoint.** This is a local single-developer/academic project; every endpoint — including the destructive `DELETE /api/clear-jobs` — is reachable by anyone who can reach the port. Fine for `localhost`-only use; would need real auth (e.g. Flask-Login + per-user sessions) before being deployed publicly.

---

## 7. Notable bugs found and fixed along the way

1. **Every job insert was silently failing for a period of time** due to schema drift (`CREATE TABLE IF NOT EXISTS` never adding new columns to an already-existing table). Fixed with an automatic migration step in `init_db()`.
2. **Domain mistagging via substring matching** ("Retail Manager" tagged AI/ML because of the substring "ai"). Fixed with word-boundary regex matching.
3. **Pagination bug** — negative page numbers fed Python's negative-index slicing and returned the wrong jobs instead of an empty page.
4. **Column-width data loss** — real scraped data (multi-tag categories, multi-country postings) exceeded `VARCHAR` limits, silently losing rows on insert. Fixed with wider columns plus defensive application-layer truncation on every field, so no future oversized value from any source can lose a job again.
5. **Windows-specific crash on malformed epoch timestamps** (`OSError` from `datetime.fromtimestamp()`, not just `ValueError`/`TypeError`) — could take down an entire scraper batch over one bad timestamp. Fixed with broader exception handling.

---

## 8. What's NOT implemented / gaps

- **Not every scraper returns a job description.** 12 of 17 sources capture one; Unstop, AngelList (an already-flaky endpoint), and a few RSS-only feeds don't expose one in their list/search response, so jobs from those sources match on title/category/domain alone and will score lower/noisier than description-bearing jobs. This is a per-source API limitation, not something fixable in this codebase.
- **Alerts aren't automatic.** `alerts.py`'s senders work (tested via `POST /api/test-alert`) but nothing calls them automatically when new jobs are found during a fetch.
- **No scheduled/background fetching.** Jobs only get scraped when someone clicks "Fetch Jobs." There's an `/api/scheduler-status` endpoint reading an optional config file, but no actual background scheduler runs.
- **Dev server only.** `app.run()` is Werkzeug's development server — not meant for real deployment.
- **No authentication** (see §6).
- **In-memory-only caching and OCR reader state**, not distributed — fine for a single process, would need rework for multi-worker deployment (e.g. `gunicorn -w 4`), since each worker would load its own OCR model into memory.
- **TF-IDF matching has no persisted index** — refit on every résumé upload. Fine at current data volume; would need optimization past tens of thousands of jobs.
- **OCR adds real latency** (roughly 20-40 seconds per scanned resume on CPU) — acceptable for a one-off upload, but would need a background job queue if this were used at higher volume or needed to feel instant.

---

## 9. Suggested next steps, if continuing

Roughly in order of value-for-effort:

1. **Wire alerts to fire automatically** on new matching jobs after a fetch.
2. **A lightweight scheduler** (OS-level cron/Task Scheduler hitting `/api/fetch` periodically) so data doesn't go stale between manual fetches.
3. **Real authentication** before any deployment beyond localhost.
4. **A production WSGI server** (gunicorn/waitress) plus a persistent rate-limiter backend (Redis) if moving beyond single-process local use.
5. Everything else in §8 is lower priority — mostly matters only past local single-user use.

---

## 10. Quick reference

**Run it:** `python api.py` → http://localhost:5000
**Run tests:** `pytest` (or `pytest --cov=api --cov-report=term-missing` for coverage)
**Config:** `.env` (gitignored) — `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `FLASK_DEBUG`, `CORS_ORIGINS`, `MAX_RESUME_SIZE`, `MIN_RESUME_TEXT`, `OCR_MAX_PAGES`

**Key files:**
| File | Role |
|---|---|
| `api.py` | Flask backend — all routes, DB layer, matching/filtering/OCR logic |
| `index.html` | Entire frontend (HTML/CSS/JS, no build step) |
| `remote_job_scraper.py` | All 17 external job-board scraper functions |
| `alerts.py` | Telegram/Email/Slack notification senders |
| `tests/` | 144 pytest tests across 7 files |
| `API_DOCUMENTATION.md` | Full endpoint reference |
| `RESUME_FEATURE_GUIDE.md` | User-facing guide to the résumé-matching feature, including OCR |
