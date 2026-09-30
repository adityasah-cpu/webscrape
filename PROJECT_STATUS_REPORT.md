# Job Portal — Project Status Report
**Generated:** 2026-09-30
**Repo:** `adityasah-cpu/webscrape` (public) · **Branch:** `main` · **Latest commit:** `8ea0dfd`

---

## 1. What this project is

A Flask + MySQL web app that scrapes job listings from multiple external job boards, filters them down to **genuine fresher/internship roles only**, tags them by tech domain (AI/ML, Data Analytics, Blockchain, AR/VR, Cybersecurity), and lets a candidate upload their résumé to get the stored jobs ranked by relevance. A single-page vanilla HTML/CSS/JS frontend talks to a REST API; there's an analytics dashboard, CSV/JSON export, and (currently manual-only) Telegram/Email/Slack alert integrations.

**Live data right now:** 1,243 jobs stored, from 6 active sources, across 564 distinct companies.

---

## 2. Architecture

```
Browser (index.html, ~1,700 lines, no build step, no external JS libs)
    │  fetch() calls to same-origin REST API
    ▼
Flask API (api.py, ~1,125 lines)
    │
    ├── remote_job_scraper.py  →  16 scraper functions hitting external
    │                              job-board APIs/RSS feeds (Remotive,
    │                              RemoteOK, Himalayas, Internshala,
    │                              FirstNaukri, Arbeitnow, + 10 more not
    │                              yet exposed in the UI — see §6)
    │
    ├── alerts.py  →  Telegram / Email / Slack notification senders
    │                 (reachable via POST /api/test-alert, not yet
    │                 wired to fire automatically on new fresher jobs)
    │
    └── MySQL (`job_portal` database, single `jobs` table)
```

**Storage:** MySQL only (earlier PostgreSQL/Redis/SQLite experiments were removed as dead code — see §7).
**Caching:** a 15-second in-memory TTL cache in front of `load_jobs_from_db()`, invalidated on every write. Not Redis, not distributed — fine for a single-process local app.
**Matching engine:** scikit-learn `TfidfVectorizer` + cosine similarity, run fresh per resume upload (no persisted vector index — fine at current data volume, would need revisiting past ~10-20k jobs).

---

## 3. Features that are implemented and working

| Feature | Status | Notes |
|---|---|---|
| Multi-source job scraping | ✅ Working | 6 sources selectable in the UI; all verified fetching real data |
| Strict fresher/internship filter | ✅ Working | Rejects anything mentioning seniority/years-of-experience; only accepts explicit fresher/intern/graduate/trainee language. Deliberately favors precision over recall — a real job with neither signal gets excluded rather than guessed at |
| Domain auto-tagging (5 categories) | ✅ Working | Word-boundary keyword matching (fixed from an earlier substring-matching bug that mistagged "Retail"→AI/ML, "Car"→AR/VR) |
| Résumé upload + job matching | ✅ Working | PDF/DOCX/TXT, in-memory only (never written to disk), TF-IDF ranking, verified end-to-end with real resumes |
| Analytics dashboard | ✅ Working | Summary cards, jobs-added timeline, domain/work-type/source/country/company breakdowns — all CSS-rendered, no chart library dependency |
| CSV / JSON export | ✅ Working | |
| Pan-India filtering for onsite roles | ✅ Working | Remote jobs stay global; onsite jobs are filtered to Indian city/region keywords |
| Rate limiting | ✅ Working | Global 200/hr·50/min, with stricter per-route limits on expensive/destructive endpoints (fetch: 5/min, resume match: 10/min, clear-jobs: 3/min, test-alert: 5/hr) |
| In-memory jobs cache | ✅ Working | 15s TTL, auto-invalidated on writes |
| Automated schema migration | ✅ Working | `init_db()` detects and adds missing columns rather than silently failing inserts (this was a real, previously-undiscovered bug — see §7) |

---

## 4. API surface (14 endpoints)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/sources` | List available scraper sources for the UI checkboxes |
| POST | `/api/fetch` | Scrape selected sources, filter to freshers, upsert into MySQL |
| POST | `/api/match-resume` | Upload a résumé, get ranked job matches |
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

Full request/response documentation: `API_DOCUMENTATION.md`.

---

## 5. Testing & quality

- **105 automated tests, 84% coverage on `api.py`**, all passing (`pytest`)
- Tests are fully mocked at the database boundary — the suite never touches the real MySQL data, safe to run anytime
- Coverage includes: fresher/domain detection logic, résumé text extraction (PDF/DOCX/TXT), TF-IDF matching and ranking, all 14 API endpoints, pagination edge cases, config validation (rejects a malicious `DB_NAME` at startup), SSRF protection in the alert system, and security headers
- Verified live multiple times against the real server + real 1,243-row dataset (not just mocked tests) using Playwright for frontend checks

---

## 6. Security posture

Went through three rounds of audit-and-fix (full history in `SECURITY_AUDIT_2.md`, `SECURITY_AUDIT_3.md`, `COMPREHENSIVE_AUDIT_REPORT.md`). Current state:

**Fixed:**
- Credentials moved out of source code into `.env` (gitignored)
- The MySQL password that had been hardcoded in tracked files was scrubbed from *all* git history (`git-filter-repo`, force-pushed, independently verified against a fresh GitHub clone) and rotated
- XSS: all scraped/external data is HTML-escaped everywhere it's rendered (including a class-name injection spot that wasn't originally exploitable but was hardened anyway)
- SSRF: the Slack-webhook alert channel now validates the URL is actually `hooks.slack.com` before making any outbound request
- The alert-testing endpoint (`/api/test-alert`) is rate-limited to 5/hour — it previously had no meaningful limit and could be abused as a Gmail credential-testing oracle
- Flask debug mode now defaults to `False` (reads `FLASK_DEBUG` from `.env`, warns on startup if enabled)
- SQL identifiers (database name) validated against an allowlist before use in `CREATE DATABASE`
- Added `Content-Security-Policy` and `Permissions-Policy` headers (verified they block a real injected-external-script test while leaving the app's own inline code untouched)
- Dependency versions synced to what's actually installed (`requirements.txt` previously claimed Flask 2.3.3; the app has been running on 3.1.3 the whole time) and scanned with `pip-audit` — zero known CVEs in anything this project actually depends on
- 30+ stale/obsolete documentation and log files (Postgres/Redis migration notes, old audit logs) removed from the repo

**Known, accepted limitation (by design, not a bug):**
- **No authentication on any endpoint.** This is a local single-developer tool; every endpoint — including the destructive `DELETE /api/clear-jobs` — is reachable by anyone who can reach the port. Fine for `localhost`-only use; would need real auth before being deployed anywhere else.

---

## 7. Notable bugs found and fixed along the way

Worth knowing about since they affected data correctness, not just security:

1. **Every job insert was silently failing for a period of time.** The live `jobs` table had been created by an older schema version (before `start_date`/`end_date`/`domains` columns existed in the code). `CREATE TABLE IF NOT EXISTS` is a no-op on an already-existing table, so those three columns were never actually added — meaning every fetch reported "success" while persisting nothing new. Fixed with an automatic migration step in `init_db()` that diffs actual columns against expected ones.
2. **Domain mistagging via substring matching.** Short keywords like `ai`, `ml`, `ar`, `vr` were matched as raw substrings, so "Retail Manager" got tagged AI/ML and "Car Sales" got tagged AR/VR. Fixed with word-boundary regex matching; backfilled all 1,243 existing rows.
3. **Pagination bug.** `GET /api/jobs?page=-1` fed Python's negative-index list slicing and silently returned real, unrelated jobs instead of an empty page.

---

## 8. What's NOT implemented / gaps

- **Only 6 of ~16 coded scrapers are exposed in the UI.** `remote_job_scraper.py` has functions for Adzuna, AngelList, Dev.to, Upwork, Toptal, Greenhouse, Lever, Ashby, Unstop, Jobicy, and WeWorkRemotely, but `/api/sources` only lists Remotive/RemoteOK/Himalayas/Internshala/FirstNaukri/Arbeitnow. (Some of the un-exposed ones — Jobicy, WeWorkRemotely — already have data in the current DB from an earlier session, so the scrapers themselves work; they're just not currently selectable from the sidebar.)
- **Alerts aren't automatic.** `alerts.py`'s Telegram/Email/Slack senders exist and work (tested via `POST /api/test-alert`), but nothing currently calls them automatically when new fresher jobs are found during a fetch — a user would have to build that trigger themselves.
- **No scheduled/background fetching.** Jobs only get scraped when someone clicks "Fetch Jobs" in the UI. There's an `/api/scheduler-status` endpoint that reads an optional config file, but no actual background scheduler process runs.
- **Dev server only.** `app.run()` is Werkzeug's built-in development server — fine for local use, explicitly not meant for any real deployment (the startup banner says so).
- **No authentication** (see §6 — accepted limitation, not an oversight).
- **In-memory-only caching**, not distributed — irrelevant for single-process local use, would matter if ever scaled to multiple worker processes.
- **TF-IDF matching has no persisted index** — refit on every résumé upload. Fine at 1,243 jobs; would need caching/optimization if the dataset grew to tens of thousands.

---

## 9. Suggested next steps, if continuing

Roughly in order of value-for-effort:

1. **Expose the remaining scrapers in the UI** — the highest-leverage gap; the code already works, it's just a matter of adding checkboxes/categories to `index.html` and the `/api/sources` response.
2. **Wire alerts to fire automatically** on new fresher-job matches after a fetch, instead of only via manual test.
3. **A lightweight scheduler** (even just an OS-level cron/Task Scheduler entry hitting `/api/fetch` periodically) so job data doesn't go stale between manual fetches.
4. Everything else in §8 is lower priority — mostly matters only if this moves beyond local single-user use.

---

## 10. Quick reference

**Run it:** `python api.py` → http://localhost:5000
**Run tests:** `pytest` (or `pytest --cov=api --cov-report=term-missing` for coverage)
**Config:** `.env` (gitignored) — `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `FLASK_DEBUG`, `CORS_ORIGINS`, `MAX_RESUME_SIZE`, `MIN_RESUME_TEXT`

**Key files:**
| File | Role |
|---|---|
| `api.py` | Flask backend — all routes, DB layer, matching/filtering logic |
| `index.html` | Entire frontend (HTML/CSS/JS, no build step) |
| `remote_job_scraper.py` | All 16 external job-board scraper functions |
| `alerts.py` | Telegram/Email/Slack notification senders |
| `tests/` | 105 pytest tests across 6 files |
| `API_DOCUMENTATION.md` | Full endpoint reference |
| `RESUME_FEATURE_GUIDE.md` | User-facing guide to the résumé-matching feature |
| `SECURITY_AUDIT_2.md`, `SECURITY_AUDIT_3.md` | Full audit history and findings |
