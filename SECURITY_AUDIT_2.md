# Security & Code Audit #2 — Full Codebase
**Date:** 2026-09-28
**Scope:** Every file in the repository, not just the active app (api.py/index.html/remote_job_scraper.py) — including the dead/legacy files left over from earlier development (mysql_db.py, postgres_db.py, redis_cache.py, db.py, audit.py, audit_v2.py, diagnose.py, scheduler.py, test_import.py).

---

## 🔴 CRITICAL — Fix Immediately

### 1. Real MySQL password is live on GitHub right now
**Files:** `mysql_db.py:15`, `audit.py:470` (both currently tracked and pushed to `origin/main`)

```python
# mysql_db.py
'password': '<REDACTED-real-password-was-here>',
```
```python
# audit.py
print("   • Run: mysql -u root -p<REDACTED-real-password-was-here>\n")
```

Phase 1 of the earlier audit moved the password out of `api.py` into `.env` — but these two **dead, unused files were never touched** and still hardcode the exact same real password. They are tracked in git and were pushed in the most recent commit (`HEAD`), so **the password is exposed in the current state of the public repo, not just its history.**

On top of that, it's *also* baked into git history regardless:
```
$ git log --all --oneline -S "<REDACTED-real-password-was-here>" -- api.py mysql_db.py
9cc6dca Phase 1: Critical Security & Error Handling Fixes
74a01dd Add resume upload and job matching feature
c8039f5 first commit
```
Removing it from the current files does not remove it from history — anyone can `git log -p` or browse old commits on GitHub to recover it.

**Action items (in order):**
1. **Rotate the MySQL `root` password now**, independent of anything else — treat it as compromised the moment it touched a pushed commit.
2. Delete or redact the password from `mysql_db.py` and `audit.py` (see Finding #6 — these files are dead code anyway; deleting them is the cleanest fix).
3. If the GitHub repo is public, the history itself should be scrubbed (`git filter-repo` / BFG Repo-Cleaner) or the repo should be considered burned and history rewritten — but **this only matters after the password is already rotated**, since scrubbing history doesn't un-expose a password that's already been visible.

---

## 🟠 HIGH

### 2. SSRF via `/api/test-alert`'s Slack webhook field
**File:** `alerts.py:139-157`, reachable from `api.py:966` (`POST /api/test-alert`)

```python
def send_slack(webhook_url, message):
    data = {"text": message} if isinstance(message, str) else message
    r = requests.post(webhook_url, json=data, timeout=10)
```

`webhook_url` comes straight from the caller's JSON body (`alert_config["slack"]["webhook_url"]`) with **zero validation** that it's actually a Slack URL. Anyone who can reach this endpoint can make the server issue an arbitrary outbound POST request with a JSON body they control — the textbook definition of SSRF. On a machine with cloud metadata endpoints, internal services, or other localhost-bound apps reachable from the Flask process, this can be used to probe/attack internal infrastructure through the server as a proxy.

**Fix:** validate `webhook_url` starts with `https://hooks.slack.com/` before calling `requests.post`, and reject anything else with a 400.

### 3. `/api/test-alert` doubles as a free Gmail-credential-testing oracle
**File:** `alerts.py:61-92`, same endpoint as above

```python
def send_email(sender_email, sender_password, recipient_email, subject, html_body):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
        server.login(sender_email, sender_password)
```

The endpoint has no authentication and only the global rate limit (200/hour, 50/min per IP — no per-route limit, unlike `/api/fetch` and `/api/match-resume`). It accepts an arbitrary `email`/`password` pair from the request body and reports back whether the SMTP login succeeded (`results["email"] = "✅"` or `"❌"`). That's a working oracle for testing stolen Gmail app-password lists against Google's servers, laundered through your server's IP.

**Fix:** at minimum, add a per-route rate limit (e.g. 3/hour) matching or stricter than `/api/clear-jobs`; ideally require the caller to already have a stored/authenticated alert config rather than accepting raw credentials per-request.

### 4. Flask debug mode is enabled
**File:** `api.py:1075`

```python
app.run(debug=True, port=5000)
```

Werkzeug's debugger, when an unhandled exception occurs, serves an **interactive Python console in the browser** — attacker-controlled arbitrary code execution if that page is ever reached from outside localhost. Current real-world exposure is limited (no `host=` override means Flask binds to `127.0.0.1` only), but this is exactly the kind of setting that "temporarily" ships to a real deployment. Every route currently has its own broad `try/except`, which limits how often the debugger would actually trigger — but anything happening outside those blocks (Werkzeug/Flask internals, the `@app.after_request` hook, `flask-limiter` internals) is still exposed.

**Fix:** gate `debug` on an environment variable (`FLASK_DEBUG` is already defined in `.env` but never read by `api.py` — wire it up: `app.run(debug=os.getenv("FLASK_DEBUG", "False") == "True", port=5000)`), and default to `False`.

---

## 🟡 MEDIUM

### 5. Unescaped, externally-sourced job data injected into outbound emails/Telegram messages
**File:** `alerts.py:95-134` (`format_jobs_email`), `41-56` (`format_jobs_telegram`)

```python
html += f"""
    <h3 style="margin-top: 0;">{j['title']}</h3>
    ...
    <p><a href="{j['url']}" ...>Apply Now →</a></p>
"""
```

`j['title']`, `j['company']`, `j['url']`, etc. come from **scraped third-party job boards** — untrusted external input, same category as the frontend XSS bug already fixed elsewhere in this codebase. Here they're interpolated directly into an HTML email body with no escaping. A malicious or compromised job listing could break the email's layout, inject a deceptive link (`href="javascript:..."` or a phishing URL disguised as the "Apply Now" button), or otherwise manipulate the outbound message. Lower severity than a browser-rendered XSS (most mail clients sandbox scripts), but it's the same missing-output-encoding root cause that was fixed in `index.html`, just in a different sink that got missed.

**Fix:** HTML-escape (`html.escape()`) every job field before interpolating into `format_jobs_email`'s template; validate `j['url']` starts with `http://`/`https://` before using it as an `href`.

### 6. Dead legacy files: duplicate insecure patterns, no longer needed, actively confusing
**Files:** `mysql_db.py`, `postgres_db.py`, `redis_cache.py`, `db.py`, `audit.py`, `audit_v2.py`, `diagnose.py`, `scheduler.py`, `test_import.py`

None of these are imported by `api.py` (verified — only `remote_job_scraper` at module level and `alerts` lazily). They're leftovers from earlier development iterations (SQLite → MySQL → Postgres → Redis experiments) that never got cleaned up. Besides the critical password leak in two of them (Finding #1), `db.py` also has its own bug:

```python
# db.py:94-100 — get_new_jobs()
c.execute(f"""
    SELECT j.* FROM jobs j
    ...
    WHERE j.added_at >= datetime('now', '-{hours} hours')
""")
```
`hours` is f-string-interpolated directly into the SQL instead of parameterized (every other query in the same file correctly uses `?` placeholders) — a SQL injection pattern, currently unreachable since nothing calls this function, but it's a landmine if anyone ever wires `db.py` back in.

**Fix:** delete these 9 files (or move them to a `legacy/` folder clearly marked as unused, with credentials stripped either way). They add attack surface, confuse anyone reading the repo about what's actually live, and — as this audit shows — silently rot out of sync with fixes applied to the real code.

### 7. `CREATE DATABASE` uses unparameterized identifier interpolation
**File:** `api.py:140`

```python
cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']}")
```

`MYSQL_CONFIG['database']` comes from `os.getenv('DB_NAME', 'job_portal')` — not directly user-facing, so actual exploitability requires control over the server's environment already (a high bar). Still a bad pattern: SQL identifiers can't be parameterized with `%s` placeholders in the connector API, but should at minimum be validated against an allowlist pattern before interpolation.

**Fix:**
```python
db_name = MYSQL_CONFIG['database']
if not re.match(r'^[A-Za-z0-9_]+$', db_name):
    raise ValueError(f"Invalid database name: {db_name!r}")
cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
```

### 8. `requirements.txt` doesn't match what's actually installed/tested — anywhere
Checked every pin against the real environment:

| Package | Pinned | Actually installed |
|---|---|---|
| Flask | 2.3.3 | **3.1.3** |
| flask-cors | 4.0.0 | **6.0.5** |
| mysql-connector-python | 8.1.0 | **9.7.0** |
| mammoth | 0.4.21 | **1.12.0** |
| scikit-learn | 1.3.1 | **1.9.0** |
| pdfminer.six | 20221105 | **20260107** |
| requests | 2.31.0 | 2.34.2 |
| feedparser | 6.0.10 | 6.0.14 |
| python-dotenv | 1.0.0 | 1.2.2 |
| flask-limiter | 4.1.1 | 4.1.1 ✓ |

Every pin except `flask-limiter` is wrong, several by a major version (Flask 2→3 alone has real breaking changes). A fresh `pip install -r requirements.txt` would **not** reproduce the environment this whole audit was actually verified against — anyone setting the project up from scratch could hit real incompatibilities.

**Fix:** regenerate from the real environment: `pip freeze | grep -iE "flask|mysql-connector|requests|feedparser|pdfminer|mammoth|scikit-learn|dotenv|limiter"` and replace the file's pins with those exact versions.

---

## 🟢 LOW

### 9. No scheme validation before `window.open(job.url)`
**File:** `index.html`, `applyJob()`

`job.url` is scraped external data, opened directly with no check that it's `http(s)://`. Modern browsers largely block `javascript:` URIs passed to `window.open` already, but it costs nothing to validate the scheme server- or client-side as defense in depth, especially since the same untrusted-URL problem exists in `alerts.py` (Finding #5).

### 10. No authentication on any endpoint
The entire API — including the destructive `DELETE /api/clear-jobs` and the SSRF-capable `/api/test-alert` — is reachable by anyone who can reach the port, no login/API key of any kind. This is *by design* for a local single-developer tool (documented as such in `API_DOCUMENTATION.md`), so it's not a "bug," but it's worth stating explicitly: if this app is ever deployed anywhere beyond `localhost` (a shared dev server, a Docker container with a published port, a tunnel like ngrok), every finding in this report becomes immediately exploitable by anyone on the network. Worth a one-line warning in the README if this project's scope ever grows.

### 11. Hardcoded frontend API base URL
**File:** `index.html`, `const API = "http://localhost:5000/api"`

Breaks if the page is ever served from a different host/port (reverse proxy, tunnel, different dev port). Low impact today; would matter if deployment scope changes. Could derive from `window.location.origin` instead.

---

## Summary

| Severity | Count | Items |
|---|---|---|
| 🔴 Critical | 1 | Real DB password live in tracked files + history |
| 🟠 High | 3 | SSRF via Slack webhook, credential-oracle via email test, debug mode on |
| 🟡 Medium | 4 | Unescaped data in outbound alerts, 9 dead files (one with its own SQLi), unparameterized DB-name SQL, requirements.txt drift |
| 🟢 Low | 3 | No URL scheme check on window.open, no-auth-by-design (documented risk), hardcoded frontend API URL |

**Recommended order of fixes:**
1. Rotate the MySQL password (do this right now, independent of any code change)
2. Delete the 9 dead legacy files (kills Finding #1's live exposure, #6, and its embedded SQLi in one move)
3. Lock down `/api/test-alert` (validate Slack URL, rate-limit it) — Findings #2, #3
4. Turn off debug mode by default — Finding #4
5. Escape job data in `alerts.py`'s HTML/Telegram formatters — Finding #5
6. Regenerate `requirements.txt` from the real environment — Finding #8
7. Everything else (#7, #9, #11) is cheap cleanup, do whenever convenient
