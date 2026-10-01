"""
Integration tests for Flask API endpoints, using Flask's test client.

All database access is mocked (load_jobs_from_db / save_jobs_to_db /
get_db_connection) so these tests never touch the real MySQL database -
safe to run on a machine that already has real scraped job data stored.
"""
import io
import json

import api as api_module
import remote_job_scraper as rjs


# ---------------- /api/sources ----------------

def test_get_sources_returns_expected_categories(client):
    res = client.get("/api/sources")
    assert res.status_code == 200
    data = res.get_json()
    assert "remote_boards" in data
    assert "freshers" in data
    assert any(s["id"] == "remotive" for s in data["remote_boards"])


# ---------------- /api/jobs ----------------

def test_get_jobs_returns_mysql_storage_label(client, mocker, sample_jobs):
    """Regression test: storage label previously said 'file-based' after the
    MySQL migration; must correctly report 'mysql'."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/jobs?limit=50")
    assert res.status_code == 200
    data = res.get_json()
    assert data["storage"] == "mysql"
    assert data["total"] == len(sample_jobs)


def test_get_jobs_filters_by_domain(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/jobs?domain=AIML&limit=50")
    data = res.get_json()
    assert all("AIML" in j["domains"] for j in data["jobs"])


def test_get_jobs_handles_db_failure_gracefully(client, mocker):
    mocker.patch.object(api_module, "load_jobs_from_db", side_effect=RuntimeError("boom"))
    res = client.get("/api/jobs")
    assert res.status_code == 500
    data = res.get_json()
    assert data["jobs"] == []
    # Must not leak the raw exception message to the client
    assert "boom" not in json.dumps(data)


def test_get_jobs_negative_page_does_not_return_unrelated_data(client, mocker, sample_jobs):
    """Regression test: page=-1 used to feed Python's negative-index list
    slicing and silently return real (wrong) jobs instead of an empty page."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/jobs?page=-1&limit=2")
    assert res.status_code == 200
    data = res.get_json()
    assert data["page"] == 1  # clamped to the minimum valid page
    assert data["jobs"] == sample_jobs[:2]  # same as an ordinary page=1 request


def test_get_jobs_non_numeric_page_falls_back_to_default(client, mocker, sample_jobs):
    """Regression test: a non-numeric page/limit used to raise an uncaught
    ValueError, turning a harmless malformed query into a 500."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/jobs?page=abc&limit=xyz")
    assert res.status_code == 200
    data = res.get_json()
    assert data["page"] == 1
    assert data["limit"] == 20


def test_get_jobs_limit_is_capped(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/jobs?limit=999999")
    assert res.status_code == 200
    assert res.get_json()["limit"] == 1000


# ---------------- /api/stats ----------------

def test_get_stats_returns_mysql_storage_label(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert data["storage"] == "mysql"
    assert data["total_jobs"] == len(sample_jobs)


# ---------------- /api/db-info ----------------

def test_db_info_does_not_lose_engine_label_to_duplicate_key(client, mocker, sample_jobs):
    """Regression test: db_info() used to have two "database" keys in the same
    dict literal, so "MySQL" silently got overwritten by the db name."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/db-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["database_engine"] == "MySQL"
    assert data["database"] == api_module.MYSQL_CONFIG["database"]


# ---------------- /api/cache-info & /api/cache-clear ----------------

def test_cache_info_reports_mysql_not_redis(client):
    res = client.get("/api/cache-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["storage"] == "mysql"
    assert "ttl_seconds" in data["cache"]


def test_cache_clear_invalidates_cache(client, mocker):
    spy = mocker.spy(api_module, "invalidate_jobs_cache")
    res = client.delete("/api/cache-clear")
    assert res.status_code == 200
    assert res.get_json()["success"] is True
    spy.assert_called_once()


# ---------------- /api/export ----------------

def test_export_csv(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/export?format=csv")
    assert res.status_code == 200
    assert b"Machine Learning Fresher" in res.data


def test_export_json(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/export?format=json")
    assert res.status_code == 200
    assert len(res.get_json()) == len(sample_jobs)


def test_export_unsupported_format_returns_400(client, mocker, sample_jobs):
    """Regression test: an unsupported format used to fall through silently
    with no response body/status instead of a clear error."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    res = client.get("/api/export?format=xml")
    assert res.status_code == 400


# ---------------- /api/clear-jobs ----------------

def test_clear_jobs_success_invalidates_cache(client, mocker):
    mock_conn = mocker.MagicMock()
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn)
    spy = mocker.spy(api_module, "invalidate_jobs_cache")

    res = client.delete("/api/clear-jobs")

    assert res.status_code == 200
    assert res.get_json()["success"] is True
    mock_conn.cursor.return_value.execute.assert_called_once_with("DELETE FROM jobs")
    spy.assert_called_once()


def test_clear_jobs_db_connection_failure(client, mocker):
    mocker.patch.object(api_module, "get_db_connection", return_value=None)
    res = client.delete("/api/clear-jobs")
    assert res.status_code == 500
    assert res.get_json()["success"] is False


# ---------------- /api/match-resume ----------------

def test_match_resume_no_file_field_returns_400(client):
    res = client.post("/api/match-resume", data={})
    assert res.status_code == 400
    assert "resume" in res.get_json()["error"]


def test_match_resume_empty_filename_returns_400(client):
    data = {"resume": (io.BytesIO(b""), "")}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 400


def test_match_resume_unsupported_extension_returns_400(client):
    data = {"resume": (io.BytesIO(b"some content"), "resume.doc")}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Unsupported file type" in res.get_json()["error"]


def test_match_resume_too_little_text_returns_422(client):
    data = {"resume": (io.BytesIO(b"hi"), "resume.txt")}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 422


def test_match_resume_missing_experience_level_returns_400(client, mocker, sample_jobs):
    """Regression test: the candidate must say whether they're a fresher or
    experienced - this determines which pool of stored jobs they get
    matched against."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = b"Machine learning engineer with TensorFlow experience. " * 3
    data = {"resume": (io.BytesIO(resume_text), "resume.txt")}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "experience_level" in res.get_json()["error"]


def test_match_resume_invalid_experience_level_returns_400(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = b"Machine learning engineer with TensorFlow experience. " * 3
    data = {"resume": (io.BytesIO(resume_text), "resume.txt"), "experience_level": "expert"}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 400


def test_match_resume_no_jobs_in_db_returns_empty_matches(client, mocker):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])
    resume_text = b"Machine learning engineer with TensorFlow and PyTorch experience. " * 3
    data = {"resume": (io.BytesIO(resume_text), "resume.txt"), "experience_level": "fresher"}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["matches"] == []
    assert "message" in body


def test_match_resume_fresher_mode_only_matches_against_fresher_jobs(client, mocker, sample_jobs):
    """sample_jobs has 2 fresher-classified jobs (Machine Learning Fresher,
    Data Analyst Intern) and 2 experienced-classified jobs (Senior
    Blockchain Engineer, Marketing Coordinator) - fresher mode must only
    rank/consider the fresher subset."""
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = (
        b"Machine learning engineer with deep learning, TensorFlow, PyTorch, "
        b"and artificial intelligence experience."
    )
    data = {
        "resume": (io.BytesIO(resume_text), "resume.txt"),
        "experience_level": "fresher",
    }
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["experience_level"] == "fresher"
    assert body["total_jobs_considered"] == 2
    assert body["matches"][0]["title"] == "Machine Learning Fresher"
    titles = [m["title"] for m in body["matches"]]
    assert "Senior Blockchain Engineer" not in titles
    assert "Marketing Coordinator" not in titles


def test_match_resume_experienced_mode_only_matches_against_experienced_jobs(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = b"Senior blockchain engineer with smart contract experience. " * 3
    data = {
        "resume": (io.BytesIO(resume_text), "resume.txt"),
        "experience_level": "experienced",
    }
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["experience_level"] == "experienced"
    assert body["total_jobs_considered"] == 2
    titles = [m["title"] for m in body["matches"]]
    assert "Machine Learning Fresher" not in titles
    assert "Data Analyst Intern" not in titles


def test_match_resume_top_n_is_capped_at_100(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = b"Machine learning engineer with TensorFlow experience. " * 3
    data = {"resume": (io.BytesIO(resume_text), "resume.txt"), "experience_level": "fresher"}
    res = client.post(
        "/api/match-resume?top_n=99999", data=data, content_type="multipart/form-data"
    )
    assert res.status_code == 200
    # sample_jobs only has 2 fresher-classified entries, so this proves no
    # error/crash from the oversized top_n rather than proving the exact
    # cap (see test_helpers for the direct bounds-checking behavior).
    assert len(res.get_json()["matches"]) == 2


# ---------------- / (index) ----------------

def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.content_type.startswith("text/html")


# ---------------- security headers ----------------

def test_security_headers_present_on_every_response(client):
    res = client.get("/api/sources")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"


def test_csp_header_blocks_external_resources_by_default(client):
    """Regression test: index.html has no external script/style/CDN
    dependencies, so CSP can (and should) default-deny external origins
    while still allowing the page's own inline script/style to run."""
    res = client.get("/api/sources")
    csp = res.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_permissions_policy_header_present(client):
    res = client.get("/api/sources")
    assert "geolocation=()" in res.headers.get("Permissions-Policy", "")


# ---------------- /api/fetch ----------------

def _make_fake_scraper(name, jobs):
    def _scraper():
        return jobs
    _scraper.__name__ = f"scrape_{name}"
    return _scraper


def test_fetch_jobs_scrapes_dedupes_filters_and_saves(client, mocker):
    fresher_job = {
        "source": "TestSource", "title": "Fresher Backend Intern", "company": "Acme",
        "work_type": "Remote", "country": "India", "location": "Remote",
        "job_type": "Internship", "category": "Engineering", "salary": "",
        "date": "2026-01-01", "start_date": "", "end_date": "",
        "url": "https://example.com/fresher-job",
    }
    senior_job = {
        "source": "TestSource", "title": "Senior Backend Engineer", "company": "Acme",
        "work_type": "Remote", "country": "India", "location": "Remote",
        "job_type": "Full-time", "category": "Engineering", "salary": "",
        "date": "2026-01-01", "start_date": "", "end_date": "",
        "url": "https://example.com/senior-job",
    }
    fake_scraper = _make_fake_scraper("testsource", [fresher_job, senior_job])

    mocker.patch.object(rjs, "SCRAPERS", [fake_scraper])
    mocker.patch.object(rjs, "dedupe", side_effect=lambda jobs: jobs)
    save_mock = mocker.patch.object(api_module, "save_jobs_to_db", return_value={"saved": 2, "failed": 0})
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])

    res = client.post("/api/fetch", json={"sources": ["testsource"]})

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["jobs_count"] == 2
    # Both fresher AND experienced jobs are now stored - the split happens
    # at query/match time, not by discarding one bucket at fetch time.
    assert body["total_stored"] == 2
    assert body["failed_to_store"] == 0
    assert body["fresher_count"] == 1
    assert body["experienced_count"] == 1
    assert body["status"]["testsource"]["success"] is True

    # Both jobs should have been handed to save_jobs_to_db, each tagged
    # with domains via detect_job_domain()
    saved_jobs = save_mock.call_args[0][0]
    assert len(saved_jobs) == 2
    titles = {j["title"] for j in saved_jobs}
    assert titles == {"Fresher Backend Intern", "Senior Backend Engineer"}
    assert all(j["domains"] == ["General"] for j in saved_jobs)


def test_fetch_jobs_continues_when_one_scraper_fails(client, mocker):
    working_job = {
        "source": "Good", "title": "Graduate Trainee", "company": "Acme",
        "work_type": "Remote", "country": "India", "location": "Remote",
        "job_type": "Full-time", "category": "Engineering", "salary": "",
        "date": "2026-01-01", "start_date": "", "end_date": "",
        "url": "https://example.com/graduate-job",
    }

    def broken_scraper():
        raise RuntimeError("upstream API down")
    broken_scraper.__name__ = "scrape_broken"

    good_scraper = _make_fake_scraper("good", [working_job])

    mocker.patch.object(rjs, "SCRAPERS", [good_scraper, broken_scraper])
    mocker.patch.object(rjs, "dedupe", side_effect=lambda jobs: jobs)
    mocker.patch.object(api_module, "save_jobs_to_db", return_value={"saved": 1, "failed": 0})
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])

    res = client.post("/api/fetch", json={"sources": ["good", "broken"]})

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["status"]["good"]["success"] is True
    assert body["status"]["broken"]["success"] is False


def test_fetch_jobs_unexpected_error_does_not_leak_exception_text(client, mocker):
    mocker.patch.object(rjs, "SCRAPERS", [])
    mocker.patch.object(api_module, "get_statistics", side_effect=RuntimeError("secret internal detail"))

    res = client.post("/api/fetch", json={"sources": []})

    assert res.status_code == 500
    assert "secret internal detail" not in json.dumps(res.get_json())


# ---------------- /api/test-alert ----------------

def test_test_alert_success(client, mocker):
    fake_alerts = mocker.Mock()
    fake_alerts.send_alert.return_value = {"telegram": "sent"}
    mocker.patch.dict("sys.modules", {"alerts": fake_alerts})

    res = client.post("/api/test-alert", json={"config": {"telegram": {"enabled": True}}})

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    fake_alerts.send_alert.assert_called_once()


def test_test_alert_failure_returns_safe_message(client, mocker):
    fake_alerts = mocker.Mock()
    fake_alerts.send_alert.side_effect = RuntimeError("bot token invalid")
    mocker.patch.dict("sys.modules", {"alerts": fake_alerts})

    res = client.post("/api/test-alert", json={"config": {}})

    assert res.status_code == 500
    assert "bot token invalid" not in json.dumps(res.get_json())


# ---------------- /api/scheduler-status ----------------

def test_scheduler_status_when_config_missing(client, mocker):
    mocker.patch.object(api_module.os.path, "exists", return_value=False)
    res = client.get("/api/scheduler-status")
    assert res.status_code == 200
    assert res.get_json()["status"] == "not configured"


# ---------------- init_db() schema migration ----------------
# Regression coverage for a real bug found in this codebase: the live jobs
# table had been created by an older schema (before start_date/end_date/
# domains existed), and CREATE TABLE IF NOT EXISTS is a no-op against an
# already-existing table - so those columns were silently never added, and
# every insert referencing them failed. init_db() must detect and ALTER TABLE
# to add any columns the code expects but the table is missing.

def _old_schema_columns():
    return [
        ("id",), ("url",), ("title",), ("company",), ("work_type",), ("country",),
        ("location",), ("job_type",), ("category",), ("salary",), ("date",),
        ("source",), ("added_at",),
    ]


def _make_schema_cursor(mocker, column_names, indexes, column_widths):
    """A mock cursor whose fetchall() return value depends on which of the
    three migration queries init_db() just ran (columns-exist check,
    SHOW INDEX, column-width check) - a single fixed fetchall() return
    value can't support all three since init_db() now runs all of them."""
    cursor = mocker.MagicMock()

    def fetchall_side_effect():
        sql = cursor.execute.call_args[0][0]
        if "CHARACTER_MAXIMUM_LENGTH" in sql:
            return list(column_widths.items())
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            return [(name,) for name in column_names]
        if "SHOW INDEX" in sql:
            # SHOW INDEX FROM jobs columns: Table, Non_unique, Key_name,
            # Seq_in_index, Column_name, ... - code reads row[2] (Key_name)
            return [(None, None, name, None, None) for name in indexes]
        return []

    cursor.fetchall.side_effect = fetchall_side_effect
    return cursor


def test_init_db_adds_missing_columns_to_legacy_table(mocker):
    mock_conn_for_db_create = mocker.MagicMock()
    mock_conn_for_table = mocker.MagicMock()
    mocker.patch.object(api_module.mysql.connector, "connect", return_value=mock_conn_for_db_create)
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn_for_table)

    cursor = _make_schema_cursor(
        mocker,
        column_names=[c[0] for c in _old_schema_columns()],
        indexes=["PRIMARY", "url"],  # idx_source/idx_work_type/idx_country missing
        column_widths={"category": 100, "country": 100, "location": 255},  # narrow, like the real legacy table
    )
    mock_conn_for_table.cursor.return_value = cursor

    result = api_module.init_db()

    assert result is True
    executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("ADD COLUMN start_date" in sql for sql in executed_sql)
    assert any("ADD COLUMN end_date" in sql for sql in executed_sql)
    assert any("ADD COLUMN domains" in sql for sql in executed_sql)
    assert any("MODIFY COLUMN category VARCHAR(500)" in sql for sql in executed_sql)
    assert any("MODIFY COLUMN country VARCHAR(500)" in sql for sql in executed_sql)
    assert any("MODIFY COLUMN location VARCHAR(500)" in sql for sql in executed_sql)
    assert any("ADD INDEX idx_source" in sql for sql in executed_sql)
    assert any("ADD INDEX idx_work_type" in sql for sql in executed_sql)
    assert any("ADD INDEX idx_country" in sql for sql in executed_sql)
    # country had no pre-existing index, so DROP INDEX must NOT be attempted
    assert not any("DROP INDEX idx_country" in sql for sql in executed_sql)


def test_init_db_drops_and_recreates_country_index_when_already_present(mocker):
    mock_conn_for_db_create = mocker.MagicMock()
    mock_conn_for_table = mocker.MagicMock()
    mocker.patch.object(api_module.mysql.connector, "connect", return_value=mock_conn_for_db_create)
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn_for_table)

    cursor = _make_schema_cursor(
        mocker,
        column_names=[c[0] for c in _old_schema_columns()] + ["start_date", "end_date", "domains"],
        indexes=["PRIMARY", "url", "idx_country"],
        column_widths={"category": 500, "country": 100, "location": 500},
    )
    mock_conn_for_table.cursor.return_value = cursor

    api_module.init_db()

    executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("DROP INDEX idx_country" in sql for sql in executed_sql)
    assert any("MODIFY COLUMN country VARCHAR(500)" in sql for sql in executed_sql)


def test_init_db_skips_alter_when_schema_already_current(mocker):
    mock_conn_for_db_create = mocker.MagicMock()
    mock_conn_for_table = mocker.MagicMock()
    mocker.patch.object(api_module.mysql.connector, "connect", return_value=mock_conn_for_db_create)
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn_for_table)

    cursor = _make_schema_cursor(
        mocker,
        column_names=[c[0] for c in _old_schema_columns()] + ["start_date", "end_date", "domains"],
        indexes=["PRIMARY", "url", "idx_source", "idx_work_type", "idx_country"],
        column_widths={"category": 500, "country": 500, "location": 500},
    )
    mock_conn_for_table.cursor.return_value = cursor

    api_module.init_db()

    executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any("ADD COLUMN" in sql for sql in executed_sql)
    assert not any("MODIFY COLUMN" in sql for sql in executed_sql)
    assert not any("ADD INDEX" in sql for sql in executed_sql)
    assert not any("DROP INDEX" in sql for sql in executed_sql)


# ---------------- DB helper functions (load_jobs_from_db / save_jobs_to_db) ----------------

def test_load_jobs_from_db_parses_domains_json(mocker):
    mock_conn = mocker.MagicMock()
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchall.return_value = [
        {"id": 1, "title": "Fresher Role", "domains": '["AIML", "Data Analytics"]'},
        {"id": 2, "title": "Broken domains field", "domains": "not-valid-json"},
    ]
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn)

    jobs = api_module.load_jobs_from_db(use_cache=False)

    assert jobs[0]["domains"] == ["AIML", "Data Analytics"]
    assert jobs[1]["domains"] == ["General"]  # malformed JSON falls back gracefully


def test_load_jobs_from_db_returns_empty_list_on_connection_failure(mocker):
    mocker.patch.object(api_module, "get_db_connection", return_value=None)
    assert api_module.load_jobs_from_db(use_cache=False) == []


def test_load_jobs_from_db_uses_cache_on_second_call(mocker):
    mock_conn = mocker.MagicMock()
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.fetchall.return_value = [{"id": 1, "title": "Cached job", "domains": None}]
    get_conn_mock = mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn)

    first = api_module.load_jobs_from_db()
    second = api_module.load_jobs_from_db()

    assert first == second
    get_conn_mock.assert_called_once()  # second call served from cache, no new DB hit


def test_save_jobs_to_db_invalidates_cache_and_upserts(mocker):
    mock_conn = mocker.MagicMock()
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn)
    spy = mocker.spy(api_module, "invalidate_jobs_cache")

    job = {
        "source": "Test", "title": "Fresher Role", "company": "Acme",
        "work_type": "Remote", "country": "India", "location": "Remote",
        "job_type": "Internship", "category": "Engineering", "salary": "",
        "date": "2026-01-01", "start_date": "", "end_date": "",
        "url": "https://example.com/x", "domains": ["General"],
    }
    result = api_module.save_jobs_to_db([job])

    assert result == {"saved": 1, "failed": 0}
    spy.assert_called_once()
    mock_conn.cursor.return_value.execute.assert_called_once()
    query_used = mock_conn.cursor.return_value.execute.call_args[0][0]
    assert "domains = VALUES(domains)" in query_used  # regression: upsert must refresh domains


def test_save_jobs_to_db_returns_failed_count_on_connection_failure(mocker):
    mocker.patch.object(api_module, "get_db_connection", return_value=None)
    result = api_module.save_jobs_to_db([{"url": "x"}])
    assert result == {"saved": 0, "failed": 1}


def test_save_jobs_to_db_counts_per_row_failures_separately_from_successes(mocker):
    """Regression test: save_jobs_to_db used to return a bare True/False for
    the whole batch, so /api/fetch's total_stored count (len(jobs)) didn't
    reflect actual persistence - a job that failed to insert (e.g. 'Data
    too long for column') silently vanished with no visible sign anywhere
    that it hadn't actually been saved."""
    mock_conn = mocker.MagicMock()
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn)
    # First insert succeeds, second raises a MySQL error (as a real
    # "Data too long for column" failure would)
    mock_conn.cursor.return_value.execute.side_effect = [None, api_module.Error("Data too long for column 'category'")]

    jobs = [
        {"source": "A", "title": "Job 1", "company": "Acme", "url": "https://example.com/1", "domains": ["General"]},
        {"source": "A", "title": "Job 2", "company": "Acme", "url": "https://example.com/2", "domains": ["General"]},
    ]
    result = api_module.save_jobs_to_db(jobs)
    assert result == {"saved": 1, "failed": 1}


def test_truncate_for_column_shortens_oversized_values():
    long_value = "x" * 1000
    assert len(api_module._truncate_for_column(long_value, "category")) == 500
    assert len(api_module._truncate_for_column(long_value, "title")) == 255
    assert api_module._truncate_for_column(None, "title") is None
    assert api_module._truncate_for_column("short", "title") == "short"


def test_save_jobs_to_db_truncates_oversized_fields_instead_of_losing_the_job(mocker):
    """Regression test: widening a column only moves the 'Data too long'
    failure to the next unusually long value - truncation at the
    application layer means no future oversized value in any field can
    silently lose a job again."""
    mock_conn = mocker.MagicMock()
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn)

    job = {
        "source": "Test", "title": "x" * 1000, "company": "Acme",
        "work_type": "Remote", "country": "y" * 1000, "location": "z" * 1000,
        "job_type": "Internship", "category": "c" * 1000, "salary": "",
        "date": "2026-01-01", "start_date": "", "end_date": "",
        "url": "https://example.com/x", "domains": ["General"],
    }
    result = api_module.save_jobs_to_db([job])

    assert result == {"saved": 1, "failed": 0}
    bound_params = mock_conn.cursor.return_value.execute.call_args[0][1]
    # title, country, location, category are params 1, 4, 5, 7 (0-indexed)
    assert len(bound_params[1]) == 255  # title
    assert len(bound_params[4]) == 500  # country
    assert len(bound_params[5]) == 500  # location
    assert len(bound_params[7]) == 500  # category
