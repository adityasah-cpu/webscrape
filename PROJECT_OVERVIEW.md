# Job Portal - Project Overview

**A Flask + MySQL web application that scrapes job listings from 17 working external job
boards (plus 3 honestly-stubbed sources with no public API), classifies each job as
Fresher/Internship or Experienced, tags them by tech domain, and lets candidates upload
a résumé (including scanned/photographed ones via OCR) to get TF-IDF-ranked job matches.**

---

## 🏗️ Architecture

```
Browser (index.html, ~1,930 lines, no build step, no external JS libs)
    │  fetch() calls to same-origin REST API
    ▼
Flask API (api.py, ~1,560 lines)
    │
    ├── remote_job_scraper.py  →  20 scraper functions: 17 hit real external
    │                              job-board APIs/RSS feeds, 3 (HackerRank,
    │                              GeeksforGeeks, Naipunyam) are honest no-ops
    │                              since those sites expose no public API
    │
    ├── enggroom_scraper.py    →  EnggRoom.com resource INDEX only (category/
    │                              link metadata, never the actual project
    │                              source code hosted there)
    │
    ├── alerts.py  →  Telegram / Email / Slack notification senders
    │                 (reachable via POST /api/test-alert, manual only)
    │
    └── MySQL (`job_portal` database: `jobs` table + `resources` table)
```

### Storage
- **MySQL only** — `job_portal` database, `jobs` table (job listings) + `resources` table (EnggRoom index)
- **Caching** — 15-second in-memory TTL cache in front of `load_jobs_from_db()`, auto-invalidated on every write
- **Matching engine** — scikit-learn `TfidfVectorizer` + cosine similarity, fit fresh per résumé upload against title (double-weighted) + company + category + job type + work type + location + domains + full job description

### OCR Pipeline
- **EasyOCR** (PyTorch-based) with PyMuPDF rasterizing PDF pages at 200 DPI
- Lazy-loaded, cached as a singleton on first use (model load ~2-30s depending on whether cached; actual OCR inference ~20-40s per resume on CPU regardless)
- Capped at the first 5 pages of a PDF (`OCR_MAX_PAGES`)
- Falls back to OCR automatically when pdfminer finds no text layer (scanned/photographed PDF)
- Direct image uploads (`.jpg`/`.jpeg`/`.png`) also route straight to OCR
- Guarded against decompression-bomb images (Pillow dimension check, 40MP cap) before any OCR work begins

---

## 📁 Complete File Structure

```
job_portal/
├── api.py                    # Flask backend — all routes, DB layer, matching/OCR/filtering logic
├── remote_job_scraper.py     # 17 real job-board scrapers + 3 honest no-op stubs
├── enggroom_scraper.py       # EnggRoom.com resource index scraper (metadata only)
├── alerts.py                 # Telegram / Email / Slack notification senders
├── index.html                # Entire frontend (HTML/CSS/JS, no build step), ~1,930 lines
├── .env                      # Environment variables (gitignored) — DB config, CORS, resume limits
├── requirements.txt          # Python dependencies
├── requirements-dev.txt      # Dev/test-only dependencies (pytest, pytest-cov, pytest-mock)
├── pytest.ini                # pytest configuration
├── PROJECT_OVERVIEW.md       # This file — full project handoff doc
├── PROJECT_STATUS_REPORT.md  # Earlier point-in-time status snapshot
├── COMPREHENSIVE_AUDIT_REPORT.md
├── API_DOCUMENTATION.md      # Full endpoint reference
├── RESUME_FEATURE_GUIDE.md   # User-facing guide to résumé-matching + OCR
├── SECURITY_AUDIT_2.md .. SECURITY_AUDIT_6.md  # Chronological audit history
├── server.log                # Application log file (local, not meaningful in git)
├── job_finder_complete.zip   # Older project archive — stale, safe to ignore/delete
├── tests/
│   ├── conftest.py                  # Shared pytest fixtures (mocks DB, sample_jobs fixture)
│   ├── test_helpers.py              # is_fresher_job, detect_job_domain, build_job_text,
│   │                                 score_job_match, extract_resume_keywords, filter_jobs
│   ├── test_api_endpoints.py        # Integration tests for every Flask route
│   ├── test_config_validation.py    # Module-load-time config validation tests
│   ├── test_enggroom_resources.py   # EnggRoom scraper + /api/resources* tests
│   ├── test_resume_extraction.py    # Resume text extraction + OCR-path unit tests
│   ├── test_scraper_helpers.py      # remote_job_scraper helpers (fmt_salary, epoch_to_date,
│   │                                 job() factory, dedupe, the 3 no-op stub scrapers)
│   └── test_analytics.py            # Analytics aggregation tests
└── (ignored) __pycache__/, .pytest_cache/, .coverage
```

---

## ✅ Done Features (Verified Working)

| Category | Feature | Status |
|---|---|---|
| **Scraping** | 17 real job-board scrapers (Remotive, RemoteOK, Himalayas, Jobicy, WeWorkRemotely, Arbeitnow, Adzuna, Internshala, Unstop, FirstNaukri, AngelList, Dev.to, Upwork, Toptal, Greenhouse, Lever, Ashby) | ✅ All working |
| **Honest stub sources** | HackerRank, GeeksforGeeks, Naipunyam — selectable in UI, return 0 jobs with a clear "no public API" note instead of being silently missing or faked | ✅ Working as designed |
| **Classification** | Fresher vs. Experienced, keyword-based | ✅ Every job lands in exactly one bucket |
| **Domain Tagging** | 5 categories: AIML, Data Analytics, Blockchain, AR/VR, Cybersecurity | ✅ Word-boundary regex (fixed from an earlier substring-match bug) |
| **Resume Upload + Matching** | PDF/DOCX/TXT/JPG/JPEG/PNG, in-memory only, never written to disk | ✅ Verified end-to-end with a real 11-year-experience resume |
| **OCR for Scanned Resumes** | Automatic fallback when no text layer found; verified against a simulated scan | ✅ Working |
| **Job-description matching** | 12 of 17 sources capture full job descriptions; matching uses them, not just titles | ✅ Verified: top match score rose after description data was populated |
| **Analytics Dashboard** | Summary cards, jobs-added timeline, domain/work-type/source/country/company breakdowns | ✅ Working |
| **CSV / JSON Export** | Both formats; CSV formula-injection protected (CWE-1236 fix) | ✅ Working |
| **EnggRoom Resource Index** | Category/resource-type/link metadata (not the underlying project content) | ✅ Working, stored in `resources` table |
| **Rate Limiting** | Global 200/hr · 50/min, stricter per-route limits on expensive/destructive endpoints | ✅ Working |
| **In-Memory Jobs Cache** | 15s TTL, auto-invalidated on writes | ✅ Working |
| **Schema Auto-Migration** | `init_db()` diffs actual columns/indexes/widths against expected and migrates | ✅ Verified live against the real database multiple times |
| **Security Headers** | CSP, X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Permissions-Policy | ✅ Present, verified to actually block an injected external script |
| **XSS Protection** | All scraped/external job data HTML-escaped everywhere rendered | ✅ Fixed and verified |
| **CSV Formula Injection Fix** | Job data from external boards is sanitized before CSV export | ✅ Fixed (Audit #6) |
| **OCR Memory-DoS Guard** | Pillow dimension check rejects oversized/decompression-bomb images before OCR | ✅ Fixed (Audit #6) |
| **413 Handling** | Oversized uploads return clean JSON, not a masked 500 or raw HTML error page | ✅ Fixed (Audit #6) |
| **Design-token Theme** | CampusOne-spec tokens (Inter font, color/spacing/radius/shadow/motion) applied; colored icon-badge stat cards; global `:focus-visible`; fixed low-contrast text | ✅ Applied |

### API Endpoints (All Working)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/sources` | List available scraper sources (incl. the 3 no-public-API ones) for UI checkboxes |
| POST | `/api/fetch` | Scrape selected sources, classify fresher/experienced, upsert into MySQL |
| POST | `/api/match-resume` | Upload résumé + experience level, get ranked job matches |
| GET | `/api/jobs` | Filtered/paginated job listing |
| GET | `/api/stats` | Aggregate counts (work type, country, category, source) |
| GET | `/api/analytics` | Dashboard data (time series, top-N breakdowns) |
| GET | `/api/export` | CSV (sanitized) or JSON export |
| GET | `/api/db-info` | Connection/health summary |
| DELETE | `/api/clear-jobs` | Wipe all stored jobs |
| POST | `/api/test-alert` | Send a test notification via configured channel |
| GET | `/api/cache-info` | In-memory cache status |
| DELETE | `/api/cache-clear` | Manually invalidate the cache |
| GET | `/api/scheduler-status` | Reports on an optional (unused) scheduler config file |
| POST | `/api/resources/fetch` | Pull the EnggRoom resource index (metadata only) |
| GET | `/api/resources` | List stored resource-index entries, optional `?discipline=` filter |
| GET | `/` | Serves the frontend |

### Testing
- **161 automated tests** across 8 test files, **all passing**
- **80% coverage** on `api.py` (`pytest --cov=api --cov-report=term-missing`)
- All tests mock DB access at the boundary — the suite never touches real MySQL data, safe to run anytime
- Coverage includes: fresher/domain detection, resume text extraction (PDF/DOCX/TXT/image, including both OCR fallback branches and OCR input validation), TF-IDF matching/ranking, every API endpoint, pagination edge cases, config validation, SSRF protection, security headers, CSV formula-injection neutralization, the three no-op stub scrapers, and the EnggRoom resource index

---

## ⏳ Pending / Known Limitations

### By Design (Not Bugs)
1. **No authentication** — local single-developer/academic project. Every endpoint, including destructive `DELETE /api/clear-jobs`, is reachable by anyone who can reach the port. Would need real auth (Flask-Login + sessions) before any public deployment.
2. **No automatic alerts** — `alerts.py` senders work (tested via `POST /api/test-alert`) but nothing calls them automatically when new matching jobs are found during a fetch.
3. **No scheduled/background fetching** — jobs only get scraped when someone clicks "Fetch Jobs." `/api/scheduler-status` reads an optional config file but there's no actual background scheduler process.
4. **Dev server only** — `app.run()` is Werkzeug's development server, not meant for real deployment (the startup banner says so).
5. **Not every scraper returns a description** — 12 of 17 real sources capture one; Unstop, AngelList (a flaky endpoint), and a couple of RSS-only feeds don't expose one, so jobs from those sources match on title/category/domain alone.
6. **HackerRank / GeeksforGeeks / Naipunyam intentionally return 0 jobs** — checked for a public API the same way every other source was; none exists (login-gated client-rendered pages, or no server-rendered data at all). Getting real data would require a headless browser driving an authenticated session — a ToS-violating approach for the login-gated two, not something this project does for any source.
7. **In-memory-only caching and OCR reader state** — fine for a single process; would need rework (e.g. Redis) for a multi-worker deployment, since each worker would otherwise load its own ~copy of the OCR model.
8. **`/api/test-alert` can be used as a credential-testing oracle** — accepts arbitrary email/Telegram/Slack config from the caller and reports back success/failure. Rate-limited to 5/hour (mitigates, doesn't eliminate). Same "no auth, local-use-only" risk profile as the rest of the API — documented in `SECURITY_AUDIT_6.md` rather than silently left unflagged.

### Technical Debt / Improvement Opportunities
1. Production WSGI server (gunicorn/waitress) instead of the Werkzeug dev server
2. Persistent rate-limiter backend (Redis) for multi-worker setups
3. Distributed job cache (Redis) across workers
4. Persisted TF-IDF index to avoid refitting on every résumé upload at larger data scale
5. Automatic alert triggering after a fetch finds new matching jobs
6. A lightweight scheduler (OS cron/Task Scheduler hitting `/api/fetch` periodically)
7. Real authentication before any deployment beyond localhost
8. OCR latency (~20-40s/resume on CPU) would need a background job queue at higher upload volume

---

## 🚀 How to Run

### Development
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env (gitignored — never commit this)
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=job_portal
FLASK_ENV=development
FLASK_DEBUG=False
CORS_ORIGINS=http://localhost:3000,http://localhost:5000
MAX_RESUME_SIZE=5242880
MIN_RESUME_TEXT=30
OCR_MAX_PAGES=5

# 3. Start the server (also auto-initializes/migrates the DB schema on startup)
python api.py

# 4. Open http://localhost:5000
```

### Running Tests
```bash
pytest                                        # run all 161 tests
pytest --cov=api --cov-report=term-missing    # with coverage report
```

### Notable gotcha
When `FLASK_DEBUG=True`, Werkzeug's auto-reloader has been observed to spuriously restart mid-request on this setup (unrelated file-change detection), killing long-running requests like OCR. Use `FLASK_DEBUG=False` when testing resume upload/OCR locally.

---

## 📊 Project Metrics

| Metric | Value |
|---|---|
| Lines of code | api.py 1,556 · remote_job_scraper.py 792 · enggroom_scraper.py 84 · alerts.py 315 · index.html 1,929 (~4,676 total) |
| Test count | 161 automated tests, all passing |
| Test coverage | 80% on `api.py` |
| Scraper count | 17 working job-board scrapers + 3 honest no-op stubs + 1 EnggRoom resource-index scraper |
| Job domains | 5 (AIML, Data Analytics, Blockchain, AR/VR, Cybersecurity) + General fallback |
| Resume file types | pdf, docx, txt, jpg, jpeg, png |
| OCR max pages | 5 (`OCR_MAX_PAGES`) |
| Max resume size | 5 MB (`MAX_RESUME_SIZE`) |
| Min resume text chars | 30 (`MIN_RESUME_TEXT`) |
| Cache TTL | 15 seconds |
| Rate limits | 200/hr · 50/min global; stricter per-route (fetch 5/min, resume match 10/min, clear-jobs 3/min, test-alert 5/hr) |
| Database | MySQL — `jobs` table + `resources` table |
| Frontend | Single-page vanilla HTML/CSS/JS, no build step, no external JS framework (Inter font loaded from Google Fonts) |

---

## 🔐 Security Status (Post-Audit #6)

### ✅ Fixed, chronologically (full detail in `SECURITY_AUDIT_2.md` → `SECURITY_AUDIT_6.md`)
- Credentials moved out of source into `.env` (gitignored)
- A hardcoded MySQL password was scrubbed from **all** git history (`git-filter-repo`, force-pushed, independently re-verified against a fresh clone) and rotated
- XSS: all scraped/external data HTML-escaped everywhere rendered, including a class-name injection spot
- SSRF: the Slack-webhook alert channel validates the URL is actually `hooks.slack.com` before any outbound request
- `/api/test-alert` rate-limited to 5/hour (was previously unbounded — a Gmail credential-testing oracle)
- Flask debug mode defaults to `False`, read from `.env`, warns on startup if enabled
- SQL identifiers (database name) validated against an allowlist before use in `CREATE DATABASE`
- CSP, Permissions-Policy, X-Frame-Options, X-Content-Type-Options headers present and verified to actually block an injected external `<script>` tag
- `pip-audit` against `requirements.txt`: zero known CVEs
- A live data-loss bug (jobs silently failing to insert on too-narrow columns + missing indexes) fixed with defensive per-field truncation — verified: 0 failures across repeated re-fetches after the fix
- **CSV/Formula Injection (CWE-1236)**: job titles/descriptions from external boards are sanitized before CSV export, in both `/api/export` and the standalone scraper CLI
- **OCR decompression-bomb guard**: resume images are dimension-checked via Pillow before any OCR work
- **413 masking bug**: Werkzeug's oversized-upload exception was being swallowed by routes' own broad `except Exception` and surfaced as a generic 500; fixed by re-raising `HTTPException` before the generic handler
- **`filter_jobs()` None-crash**: brought in line with the rest of the codebase's `(x.get(...) or '')` null-guard convention

### ⚠️ Known, Accepted Limitations (documented, not oversights)
- **No authentication** on any endpoint — local single-user project only
- **No HTTPS** — fine for localhost-only use
- **`/api/test-alert` credential-oracle risk** — rate-limited, not eliminated; same threat model as "no auth" generally
- **No CSRF protection** — by design for local, non-browser-session-based use

**Overall assessment:** solid for localhost/single-user/academic use; would need auth, HTTPS, and a production WSGI server before any real deployment.

---

## 👥 For Your Colleague

### Quick Start
1. `python api.py` → starts the Flask server at `http://localhost:5000` (also runs schema migration automatically)
2. Open `http://localhost:5000` in a browser
3. Pick job sources in the sidebar (5 categories, 20 checkboxes) → click "⚡ Fetch Jobs"
4. Upload a résumé (.pdf/.docx/.txt/.jpg/.jpeg/.png) via "📄 Upload Resume," selecting Fresher or Experienced first
5. Use the filter bar (Domain / Type / Region / Experience) to narrow the main job table
6. "⭐ Recommended for You" section shows ranked matches after a résumé upload

### Key Areas to Read First
- **`api.py`** — core logic: DB layer, matching, OCR, filtering, classification, all routes
- **`remote_job_scraper.py`** — all 20 scraper functions (17 real + 3 honest stubs); good place to understand how each source's data shape differs
- **`tests/`** — 161 tests are the best source of truth for expected behavior; start with `test_helpers.py` and `conftest.py`
- **`index.html`** — frontend; vanilla JS, no build step, every API call goes through `/api/*`
- **`.env`** — local config; never commit this file (it's gitignored)

### Common Debug Commands
```bash
python -c "from api import init_db; init_db()"   # check/repair DB schema
pytest                                            # run the test suite
curl http://localhost:5000/api/sources            # list scraper sources + status
curl http://localhost:5000/api/db-info             # DB connection + row counts
curl http://localhost:5000/api/cache-info           # in-memory cache status
```

### Recommended Reading Order
1. This file (`PROJECT_OVERVIEW.md`)
2. `API_DOCUMENTATION.md` — full endpoint request/response reference
3. `RESUME_FEATURE_GUIDE.md` — résumé matching + OCR, user-facing
4. `SECURITY_AUDIT_6.md` (and the earlier numbered audits for history)
5. `tests/conftest.py` → `tests/test_helpers.py` — how DB mocking works and the core business logic's expected behavior

---

*Document generated 2026-10-13, reflecting the repo as of commit `bb61793`. For anything newer, check `git log`.*
