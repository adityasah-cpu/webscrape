# Code Audit — Job Portal ("Novagig" / Centurion)

**Audit date:** 27 Nov 2026
**Snapshot audited:** `338a1c6` — *security: Add @require_admin decorator to all sensitive admin endpoints*
**Stack:** Flask 3.1, MySQL (`mysql-connector-python`), vanilla HTML/CSS/JS, scikit-learn + EasyOCR + PyMuPDF + pdfminer for resume/ATS, 17 job scrapers.
**Method:** full read of all Python/JS/SQL/config files, route inventory, schema inspection, secret scan of git history, `pytest` (231 tests) and coverage run, targeted grep for security sinks.

> Note: `api.py` was modified and committed by another process *during* this audit (commit `338a1c6`). All findings below were re-checked against that commit. The earlier state had the admin decorator defined after its first use (an import-time `NameError`); that is fixed in `338a1c6`.

---

## 1. Scorecard

| Area | Grade | One-line verdict |
|---|---|---|
| Security | **D+** | Admin APIs just got protected, but the main API gate is disabled, stored XSS is reachable, and internals leak. |
| Correctness / features | **D** | Several shipped features cannot work (groups, student upload, admin groups, analytics, ATS endpoint unused). |
| Data layer / schema | **D+** | No canonical schema; new installs miss core tables; two endpoints reference columns that don't exist. |
| Frontend quality | **C−** | Works visually, but 33 `innerHTML` sinks with partial/no escaping, duplicated JS across 4 pages. |
| Tests / CI | **C−** | 231 tests but **18 fail**; 48% coverage; no CI, no lint/type checks; large untested admin surface. |
| Maintainability | **C−** | One 4,900-line `api.py`, dead routes/dead code, 3 duplicated source lists, tracked junk files. |
| Operations / deploy | **D** | Werkzeug dev server only, migrations are manual/invalid on MySQL, `.env` overrides real env, no README/CI/Dockerfile. |

**Overall: not production-ready in its current state.** The core job-fetch/search flow mostly works and has good defensive details (parameterized SQL, CSV-formula escaping, SSRF guard on Slack, lock-protected cache), but the app has a broken auth model, reachable XSS, and a set of features that are wired to the UI yet cannot succeed.

---

## 2. Executive summary (top 7)

1. **The API is fully public while the UI and tests assume a login gate.** `require_login()` returns `None` (`api.py:272`), and CSRF validation is commented out (`api.py:384`). Anonymous calls can trigger scrapes/ingestion, and ownership is `owner_email = NULL`, which never matches MySQL `= NULL` reads (see F1).
2. **Stored XSS is reachable.** `index.html` injects `job.url` and `job.salary` into HTML without escaping; `admin_dashboard.html` injects Google display names and student fields raw. CSP allows `'unsafe-inline'`, so injected event handlers execute.
3. **Schema drift makes several features impossible on a fresh install.** `init_db()` never creates `users`, `user_events`, `user_sessions`, `user_cv_uploads`, or `admin_access_logs`; `admin_students` is missing `email`, `year`, `domain_project`, `department`, yet the API reads/writes them.
4. **`load_dotenv(override=True)`** (`api.py:46`) makes a checked-in `.env` override real deployment environment variables. This is why the three config-validation tests fail — and it is dangerous in production.
5. **A cluster of dead/broken features**: group creation always 404s (`DOMAIN_PROJECTS = []`), "My Groups" never sends an email so is always empty, no frontend ever calls `/api/log-event` or `/api/ats-score`, so engagement and CV-upload analytics are permanently zero.
6. **Migrations are not runnable as written on MySQL** (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` are MariaDB syntax), and no canonical schema exists — `init_db` vs. two `.sql` files disagree.
7. **Test suite is red** (18 failed / 213 passed) and covers only 48% of statements; the entire admin CRUD surface is untested.

---

## 3. P0 — Critical

### F1. API authentication gate disabled; ownership model breaks for anonymous users
**Evidence**
- `api.py:264-274` — comments say every `/api/*` route is gated, but `require_login()` is a no-op returning `None`.
- `api.py:384-390` — the CSRF `before_request` hook is commented out ("API is public").
- `api.py:269` — `_AUTH_EXEMPT_ENDPOINTS` is now dead code.
- `api.py:550` — `current_user_email()` returns `None` without a session; every per-user table keyed on `owner_email` then uses `NULL`.
- `load_jobs_from_db` does `WHERE owner_email = %s` with `None` → MySQL `= NULL` never matches, so anonymous fetches are stored but never readable. `save_jobs_to_db` also inserts `owner_email = NULL`, and because `UNIQUE(owner_email, url)` treats NULLs as distinct, repeated anonymous fetches insert unbounded duplicates.
- The UI still redirects anonymous visitors to `/login` (`root()`), so the product behaviour and API behaviour contradict each other.
- `tests/test_auth.py` still asserts 401 for unauthenticated `/api/jobs` (2 gate tests fail).

**Impact**
- Unauthenticated users can consume expensive scrapers (`POST /api/fetch`, 17 sources, minutes of work), write rows, and grow the DB with NULL-owner duplicates.
- No cross-user data leak from the jobs table (NULL filter accidentally prevents it), but the security posture is inconsistent and fragile.
- The "fully public" decision (commit `eb9d920`) was not propagated to the UI, analytics, tests, or ownership logic.

**Fix (recommended)**
Restore the gate in `before_request` for `/api/*` with an explicit exempt set (`/api/auth/google`, `/api/auth/config`, `/api/auth/me`, `/api/health`, static), return JSON 401. Alternatively, if the app must be public, remove sessions/`owner_email` entirely and make the data model explicit — do not keep a NULL-owner shadow mode. Re-enable CSRF (or document SameSite-Lax as the control) and add an origin check for state changes. Delete `_AUTH_EXEMPT_ENDPOINTS` or use it.

---

### F2. Stored XSS via unescaped job/user data (multiple pages)
**Evidence**
- `index.html:283-300` and `index.html:599-610`: job cards are built with template literals; `${job.title}`, `${job.company}`, `${job.location}`, `${job.salary}`, and especially `href="${job.url}"` are inserted raw.
- `remote_job_scraper.py:253-286`: `title/company/location/description` go through `clean()` (which strips tags), but **`url` and `salary` are stored raw**. A third-party listing with `url = x" onmouseover="alert(1)` injects an event handler; `javascript:` URLs execute on click.
- `admin_dashboard.html:789-801`: `${user.name}`, `${user.email}`, `${user.registration_num}` raw. `user.name` comes from the Google profile of any allowed-domain user — a valid account can attack an admin.
- `admin_dashboard.html:902-924`: student rows (`campus`, `school`, `name`, `reg_no`, `domain`, …) raw, including `onclick="editStudent('${escapedRegNo}')"` which only escapes quotes.
- `domain-projects.html` and `list-opportunities.html` define `escapeHtml` and use it, which proves the pattern exists — it is simply missing in `index.html` and `admin_dashboard.html`.
- CSP (`api.py:151-173`) contains `script-src 'unsafe-inline'`, so injected `onerror`/`onmouseover` executes; `cdn.jsdelivr.net` is allowlisted but unused.

**Fix**
Add one shared `escapeHtml`/`escapeAttr` helper and use it for every interpolation; validate URLs with `new URL()` and allow only `http:`/`https:` before writing `href`. Better: build DOM nodes and assign `textContent`/`href` properties. Remove `unsafe-inline` from CSP after moving inline handlers to `addEventListener`, and drop the unused `cdn.jsdelivr.net` allowlist. Add a test fixture with hostile `title/company/url/salary`.

---

### F3. Database schema drift — fresh installs and several endpoints are broken
**Evidence**
- `init_db()` (`api.py:1313-1695`) creates: `jobs`, `resources`, `hackathons`, `domain_projects`, `student_groups`, `group_members`, `admin_students`, `admin_projects`. It **does not create** `users`, `user_events`, `user_sessions`, `user_cv_uploads`, `admin_access_logs` — all of which are queried by auth/analytics/admin code.
- `admin_students` DDL (`api.py:1631-1648`) has no `email`, `year`, `domain_project`, `department`. But:
  - `POST /api/students` inserts `year, email, domain_project` (`api.py:682`);
  - `bulk_upload_students` inserts the same (`api.py:864`);
  - `admin_get_groups` selects `ast.email, ast.department` (`api.py:1141-1147`) — `department` exists in no schema at all.
- `users.location` is hardcoded to `'Vizianagaram'` on sign-in (`api.py:319`), so location analytics are meaningless, while event logging writes `'Unknown'` because the session user has no `location`.
- `promote_admin` / `demote_admin` write `users.is_admin` (`api.py:4396, 4434`), but **nothing reads it** — authorization is `ALLOWED_ADMIN_EMAILS` only (`is_admin_user`). The promote/demote feature is therefore cosmetic/misleading.
- `init_db()` only runs under `if __name__ == "__main__"`; a WSGI deployment (`gunicorn api:app`) would never migrate.

**Impact**
- A new developer following the docstring (`python api.py`) gets "Database initialized successfully" but `users` and analytics tables don't exist: sign-in still "works" (DB error swallowed), admin dashboards fail, events are lost.
- Student add/edit/upload and admin groups fail with "Unknown column" on any DB built from `init_db`.
- Promoting an admin has no effect, so admins may think access was granted when it wasn't.

**Fix**
Create one canonical schema (SQL file + `init_db`), including all tables and columns, and run it in both dev and WSGI startup (or a migration tool). Add `email`, `year`, `domain_project`, `department` to `admin_students` (or stop referencing them). Make `is_admin_user` consult `users.is_admin` if DB-managed admins are intended, or delete promote/demote. Set user location from a real source, not a constant.

---

### F4. `.env` overrides the real environment (`load_dotenv(override=True)`)
**Evidence:** `api.py:46`.
**Impact:** A stale committed/local `.env` silently wins over container/CI/platform variables. This directly breaks the config-validation tests (`DB_NAME`/`DB_PASSWORD` are overwritten by `.env`), and can point production at the wrong DB. Also `.env.example` documents `ALLOWED_USER_DOMAINS`, but the code reads `ALLOWED_DOMAINS` (`api.py:101`) — copying the example silently falls back to the hardcoded list (which includes `thegttech.com`).
**Fix:** Use `load_dotenv(override=False)` (default), rename the example key to `ALLOWED_DOMAINS`, and document every variable the code reads (`ATS_API_TIMEOUT`, `OCR_MAX_PAGES`, `JOBS_CACHE_TTL_SECONDS`, `MAX_JOBS_FETCH`, Adzuna keys, `SESSION_COOKIE_SECURE`).

---

## 4. P1 — High

### F5. Features that cannot work as shipped
| Feature | Evidence | Why it fails |
|---|---|---|
| Create group | `api.py:4705` `DOMAIN_PROJECTS = []`; `api.py:4711` looks up `next(...)` in that empty list | Always returns 404 "Project not found". |
| My Groups | `api.py:4840` requires `?email=`; `domain-projects.html:905` calls `/api/my-groups` with no query | Always returns empty list. |
| Engagement analytics | No HTML calls `/api/log-event`; `log_user_event` skips without a session | Jobs viewed/clicked/applied are always 0. |
| CV/upload analytics | `log_cv_upload` is only called by `/api/ats-score` (`api.py:3395`); the frontend only calls `/api/match-resume` | `cv_uploaded` and CV counts are never set by the real upload flow. |
| ATS score UI | `/api/ats-score` is never called by any page | Local category analysis + external ATS endpoint are dead weight from the UI's perspective. |
| Resume matching ATS | `match_resume` builds `category_scores` by multiplying one score (`api.py:3335-3341`) | Presented as seven measured categories, but they are fabricated ratios — misleading. |
| Admin promote/demote | writes `users.is_admin`, never read | No access change. |

### F6. Migrations are invalid/unmaintainable on MySQL
- `migration_location_dashboard.sql` uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` — MariaDB-only syntax; MySQL 8 rejects them.
- Two migration files disagree (`user_cv_uploads.location` nullable vs NOT NULL), overlap index definitions, and neither is the source of truth used by `init_db`.
- `init_db` alters tables on every boot (locks on large `jobs` tables) and is skipped entirely under WSGI.

**Fix:** Adopt one versioned migration tool (Alembic/Flyway/Liquibase or plain numbered SQL), remove `IF NOT EXISTS` for MySQL, and add a startup schema check that fails loudly.

### F7. Shipped CSV templates are rejected by the upload validators
- `sample_students.csv` has no `Year`/`Domain Project` and includes `Rating`; the validator requires `Year`, `Domain Project` and rejects unknown columns (`api.py:795-824`).
- `sample_projects.csv` uses `Comments / Details` and has no `Rating`; validator requires `Comment(s)` + `Rating` (`api.py:1035-1063`).
- `group_bulk_upload_template.csv` has only 3 columns; validator requires `Student2/3/4` (`api.py:1154`).
- Uploads accept `.xlsx/.xls` but parse the stream as CSV (`api.py:771, 1009, 1150`) → decode/parse errors on Excel files.

**Impact:** The documented onboarding path fails immediately; admins see confusing errors. **Fix:** Regenerate templates from the validators, support real XLSX via `openpyxl`, and add one test per template.

### F8. Internal errors returned to clients
Roughly 21 responses include `str(e)` in JSON (e.g., `api.py:671, 699, 748, 862, 876, 908, 937, 986, 1098, 1123, 1278`). This exposes SQL errors, table/column names, and driver internals. **Fix:** log the exception, return a generic message + correlation ID; use the existing `_api_error` helper consistently.

### F9. Write-integrity problems
- `MYSQL_CONFIG` sets `autocommit=True` (`api.py:490`), so every row in the bulk loops commits individually; `conn.commit()` at the end is a no-op. A failed row leaves partial data and there is no rollback.
- `UNIQUE(owner_email, url)` does not dedupe rows where `owner_email IS NULL` (anonymous fetch path).
- `save_jobs_to_db` catches per-row errors and returns a count, but the caller's `inserted` still reports `len(jobs)` (`api.py:3177`), so the API response overstates success.
- `save_jobs_to_db` leaks the cursor/connection if an unexpected exception occurs outside the per-row loop.

**Fix:** disable autocommit for batch operations, wrap in one transaction with rollback, make `owner_email` `NOT NULL` (or use a sentinel), report `saved` accurately, and use context managers / `finally` for connections.

### F10. `/api/fetch` is a long, blocking, unauthenticated job
- Up to 17 scrapers run sequentially with `time.sleep(1-2)` per page (`remote_job_scraper.py`); one request can take minutes. It is rate-limited to 5/min/IP but runs in the Flask worker thread.
- No `ProxyFix`/trusted-proxy handling, so behind a reverse proxy every user shares the proxy IP for rate limiting.
- The dev server (`app.run(..., threaded=True)`) is the only entry point; `requirements.txt` has no WSGI server (gunicorn/waitress).
- No retry/backoff on scraper HTTP calls; failures are per-source but logged only to stdout.

**Fix:** restore auth, move scraping to a background worker/queue, add a per-source timeout budget, deploy behind gunicorn/waitress with `ProxyFix` and shared rate-limit storage (Redis), and expose job status.

---

## 5. P2 — Medium

### Security hardening
- **Session**: `SESSION_COOKIE_SECURE` defaults to `False` (`api.py:86`); ensure `True` in prod (`.env.production` does). No HSTS header. Logout only pops `user` (`api.py:418`); a stolen cookie stays valid for the 7-day lifetime. Consider server-side session revocation.
- **Google sign-in**: `verify_oauth2_token` does not check `email_verified`. Add it. Consider `hd`/domain normalization and lowercase comparison (currently `email_domain` is lowercased but the email itself is not normalized).
- **CSRF**: token code exists but is disabled and exempts many prefixes anyway (`api.py:365-381`). Relying on `SameSite=Lax` is acceptable only if every state change is POST/PUT/DELETE and the app is never embedded; add `Origin` checks as defense-in-depth.
- **CORS**: `cors_origins` is split without trimming (`api.py:61`), so `"https://a, https://b"` produces a broken second origin; `methods` omits `PUT`/`PATCH` even though the app uses PUT. Not exploitable same-origin, but config is wrong.
- **Headers**: `X-XSS-Protection` is obsolete; CSP allows `'unsafe-inline'` and unused `cdn.jsdelivr.net`; add `Strict-Transport-Security` when HTTPS, and consider `Cross-Origin-Opener-Policy`.
- **PII in logs**: INFO logs include user emails and filenames; debug logs would include resume text. Set log level via env and scrub PII.
- **ATS privacy**: `/api/ats-score` forwards the full resume text to `qwen.cutm.ac.in` (`api.py:2622-2626`) and persists filename/size (`log_cv_upload`), while the docstring says nothing is persisted. Add consent/notice, redact, or keep it local.
- **Rate limiting**: `storage_uri="memory://"` (`api.py:113`) is per-process and resets on restart; use Redis in production. Unauthorized requests bypass `@limiter` when `@require_admin` is the outer decorator.
- **Alerts**: `/api/test-alert` lets a caller supply SMTP credentials and recipient → the server can be used to send arbitrary mail via Gmail; Telegram token is interpolated into a URL. Both are rate-limited but should require auth/ownership.
- **File uploads**: `MAX_CONTENT_LENGTH` is the resume cap (5 MB) applied globally (`api.py:430`); bulk uploads inherit it and get a resume-specific error message. No per-type magic-byte check; `.xlsx` accepted but not parsed.
- **Template injection in `showMessage`**: `domain-projects.html:945` assigns `element.innerHTML = message`; server errors/user strings flow into it. Escape or use `textContent`.

### Performance / reliability
- `_jobs_cache` is per-user and never evicted except on write — unbounded memory as user count grows.
- Every `/api/jobs`/`/api/stats`/analytics call loads up to 5,000 rows and parses JSON domains; `get_statistics` re-fetches through the cache, but `/api/fetch` calls `get_statistics` immediately after saving.
- Resume matching fits a TF-IDF vocabulary over up to 5,000 documents per request (CPU-heavy, 10/min/IP). If the resume is all stopwords, `TfidfVectorizer` can raise "empty vocabulary" → 500.
- EasyOCR loads a ~30 s model lazily inside a request; the singleton is not protected during `readtext` (EasyOCR may not be thread-safe). First OCR upload blocks a worker.
- A new MySQL connection per request (no pooling). Consider `mysql.connector.pooling`.
- Admin dashboards load full tables with no pagination (`/api/students`, `/api/projects`, `/api/admin/users`).
- `get_admin_users` joins `users` to `user_events`; if the events table is missing (fresh install) the whole dashboard 500s.

### Correctness details
- `ALLOWED_DOMAINS[0]` is used to synthesize student emails (`api.py:679, 861`), so email domain depends on env ordering; frontend hardcodes `centurionuniv.edu.in` (`admin_dashboard.html:945`) — three possible answers.
- `root()` and `index()` are both registered for `/` (`api.py:590, 3739`); the first wins, so `index()` is dead code and confusingly bypasses the login redirect.
- `/api/sources/status` hardcodes 11 "non-working" sources; `/api/sources` and `index.html` maintain a third, independent source list. They will drift.
- `/api/scheduler-status` reads `scraper_config.json` from CWD and returns its contents (file doesn't exist; no scheduler is implemented).
- `/api/export` is GET-only and `/api/clear-jobs` DELETE-only, while `ENDPOINT_STATUS_REPORT.txt` documents POST for both — stale documentation.
- `fetch_jobs` returns `"inserted": len(jobs)` regardless of `save_result["saved"]` (`api.py:3177`).
- `dedupe` keys on title+company (+location), so identical titles at the same company in different cities can still collapse for remote roles; minor.
- `is_fresher_job` substring matching ("graduate", "college") will classify senior roles containing "graduate" as fresher; heuristic-only.
- `/api/opportunities` is a hardcoded list in code (`api.py:4524-4675`) with 2026 dates — no maintenance path.

---

## 6. P3 — Maintainability & repo hygiene

- **Monolith:** `api.py` is 4,887 lines / ~20k words, mixing auth, scraping orchestration, resume parsing, SQL migrations, admin analytics, and static-file serving. Split into `blueprints/` (auth, jobs, resume, admin, groups) + `services/` (db, schema, scrapers) + `config.py`.
- **Dead code:** `require_login` (no-op), `_AUTH_EXEMPT_ENDPOINTS`, `validate_csrf_token` + disabled hook, `index()` duplicate route, `/api/ats-score` path, `admin_access_logs` (never written), `users.is_admin` (never read), `_AUTH_EXEMPT...`, `get_csrf_token` (token never validated).
- **Duplication:** source lists in three places; ATS category math duplicated in two branches of `match_resume`; bulk-upload parsing duplicated three times (student/project/group) with slightly different rules; `escapeHtml` duplicated in two pages.
- **No canonical schema** (see F3/F6); no README/architecture doc; `USER_GUIDE.html` is the only documentation.
- **Tracked junk (48 tracked files):** `.playwright-mcp/` screenshots + YAML, `server.pid`, `server_output.txt`, `logo_dataurl.txt` (526 KB embedded image), `test_new_features.py` (ad-hoc, outside `tests/`), `.env.production` (should be `*.example`). `.env` is correctly untracked and no secrets were found in git history, but logs/`.coverage` are present in the working tree.
- **Missing infra:** no `.github/workflows`, no Dockerfile, no `wsgi.py`/gunicorn/waitress config, no lint/format/type config (ruff/black/mypy), no pre-commit, no dependency lock/hashes.
- **`.gitignore` gaps:** add `.env.*` (except examples), `.playwright-mcp/`, `*.pid`, `server_output.txt`, `.coverage`, `pytest_*.txt`.
- **Frontend duplication:** four standalone HTML files with copy-pasted CSS/JS and inconsistent `credentials` usage; extract shared JS/CSS or adopt a small build step.
- **Accessibility/UX:** emoji-only labels, `alert()` flows, no loading/empty error states on admin failures, hardcoded `??` placeholders in `index.html:110,281`.

---

## 7. Tests & quality gates (measured)

```
231 collected
213 passed
 18 failed
Coverage: 48% total
  api.py                  52% (2268 stmts, 1087 missed)
  remote_job_scraper.py   29% (591 stmts, 419 missed)
  alerts.py               48%
  hackathon_scraper.py   100%
  enggroom_scraper.py    100%
```

Failure groups:
| # | Tests | Cause | Verdict |
|---|---|---|---|
| 3 | `test_auth.py` (unauthenticated gate, frontend route, valid-token session) | Gate disabled / `/` redirects to `/login` | **Stale tests or intentionally reverted feature — decide and align** |
| 3 | `test_config_validation.py` | `load_dotenv(override=True)` overwrites test env | **Real bug (F4)** |
| 2 | `test_init_db_*` | Code legitimately adds new indexes (`idx_category`, `idx_owner_category`) not in fixture | Stale tests |
| 10 | `test_resume_extraction.py::TestEvaluateAtsScore` | `evaluate_ats_score` now falls back instead of raising `ValueError` | Stale tests (behaviour changed deliberately) |

Notable gaps:
- **Zero tests** for `/api/students`, `/api/projects`, `/api/groups/*`, `/api/admin/*` (the entire admin CRUD surface touched by commit `338a1c6`).
- No tests for the CSV upload validators, sample templates, schema completeness (users/events tables), XSS escaping, or the auth gate after the revert.
- No CI; tests are only run manually. Add `pytest --cov --cov-fail-under=...` to CI, plus `ruff` and a `pip-audit`/`bandit` pass.
- `tests/conftest.py` mocks DB boundaries well; keep that pattern when adding admin tests.

---

## 8. What is already good (keep it)

- **SQL injection resistance:** all user-facing queries use `%s` parameters; identifiers in DDL are whitelisted, and `DB_NAME` is regex-validated before being interpolated (`api.py:503-505`).
- **Defensive DB layer:** `DatabaseUnavailableError` correctly distinguishes outage from "no rows"; health endpoint pings the DB; per-user cache is lock-protected and invalidated on writes.
- **CSV formula-injection guard** in both export (`_csv_safe`) and scraper CLI (`remote_job_scraper.py:1066-1075`).
- **SSRF guard** on Slack webhooks (`alerts.py:178-184`) and `_safe_url` for outbound email/Telegram links.
- **OCR decompression-bomb cap** (`MAX_OCR_IMAGE_PIXELS`) and per-page OCR limit.
- **Security headers** (CSP, frame deny, referrer policy, permissions policy) and a JSON error contract so the frontend never parses HTML errors.
- **Resume files are processed in memory**, never written to disk (aside from metadata logging).
- **Good test style** at the DB boundary: fixtures, mocked connectors, rate-limiter reset, deterministic job data.

---

## 9. Prioritised action plan

### Now (block release)
1. **Restore the API login gate** (`before_request`, exempt auth/health/static) or consciously redesign for public access; propagate the decision to tests, `ENDPOINT_STATUS_REPORT.txt`, and ownership. Make `owner_email NOT NULL` if sessions remain.
2. **Fix XSS**: add shared escaping, validate/auto-prefix URLs, switch `innerHTML` to DOM/textContent where practical, remove `unsafe-inline` from CSP after moving inline handlers.
3. **Unify the schema**: create `users`/`user_events`/`user_sessions`/`user_cv_uploads`/`admin_access_logs` in `init_db`; add missing `admin_students` columns (`email`, `year`, `domain_project`, `department`) or remove the reads; run schema init under WSGI too.
4. **`load_dotenv(override=False)`** and fix `.env.example` (`ALLOWED_DOMAINS`, empty `ATS_API_URL`).
5. **Get tests green**: update the 15 stale tests to current behaviour, fix the 3 config tests by fixing F4. Add admin endpoint tests (auth + happy path + 403).

### Next (1–2 weeks)
6. Fix the broken features list (F5): group creation against DB projects, `/api/my-groups` session-based, call `/api/log-event`/`log_cv_upload` from the real UI flow, decide whether `/api/ats-score` or `/api/match-resume` is the product path and delete the other.
7. Replace/repair migrations with one versioned schema; add a startup schema assertion.
8. Regenerate the three CSV templates; support real XLSX or reject it with a clear message.
9. Stop returning `str(e)`; add correlation IDs.
10. Fix batch write integrity (no autocommit, rollback, accurate counts).
11. Add pagination to admin lists; cap/cache eviction; DB connection pooling.

### Later (hardening & scale)
12. Move scraping to a background worker/queue; deploy with gunicorn/waitress + ProxyFix + Redis rate limits.
13. Add CI (pytest + coverage gate + ruff + bandit/pip-audit), pre-commit, Dockerfile, README.
14. Split `api.py` into blueprints/services; remove dead code and duplicated source lists; dedupe frontend JS.
15. Add PII policy for resumes/analytics (DPDP-style consent, retention, redaction), email-verified check, HSTS, server-side session revocation.
16. Remove tracked artifacts and update `.gitignore`.

---

## 10. Appendix — evidence index

| Concern | Location |
|---|---|
| Public API / dead gate | `api.py:264-274`, `api.py:384-390` |
| Dead CSRF | `api.py:365-381` |
| `load_dotenv(override=True)` | `api.py:46` |
| Domain config mismatch | `api.py:101`, `.env.example:29` |
| XSS sinks | `index.html:283-300,599-610`; `admin_dashboard.html:789-801,902-924`; `remote_job_scraper.py:280-285` |
| Missing tables | `api.py:1313-1695` (no `users`/events/sessions/CV DDL); queries at `3827, 3880, 3919, 4225` |
| `admin_students` drift | DDL `api.py:1631-1648` vs inserts `682, 864`; join `1141-1147` |
| Promote no-op | `api.py:4396/4434` vs `is_admin_user` `146-153` |
| Group creation dead | `api.py:4705, 4711-4727` |
| Broken My Groups | `api.py:4840`; `domain-projects.html:905` |
| Unused analytics | `api.py:4456` (`/api/log-event`), no HTML caller; `3840` `log_cv_upload` only at `3395` |
| ATS endpoint unused | `api.py:3373`; no HTML caller |
| Fabricated category scores | `api.py:3335-3341` |
| Migration syntax | `migration_location_dashboard.sql:63-90` |
| Template mismatch | `sample_students.csv`, `sample_projects.csv`, `group_bulk_upload_template.csv` vs `api.py:795-824, 1035-1063, 1154` |
| Error leakage | ~21 `str(e)` responses (e.g. `api.py:671, 748, 862, 986, 1123`) |
| Batch/autocommit | `api.py:490`, `1768-1812` |
| Duplicate `/` route | `api.py:590` vs `3739` |
| Tracked junk | `git ls-files`: `logo_dataurl.txt`, `server.pid`, `.playwright-mcp/*`, `server_output.txt`, `test_new_features.py` |
| Test failures | `tests/test_auth.py`, `tests/test_config_validation.py`, `tests/test_resume_extraction.py`, `tests/test_api_endpoints.py` |
