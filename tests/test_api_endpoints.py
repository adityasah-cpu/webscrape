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


def test_match_resume_no_jobs_in_db_returns_empty_matches(client, mocker):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])
    resume_text = b"Machine learning engineer with TensorFlow and PyTorch experience. " * 3
    data = {"resume": (io.BytesIO(resume_text), "resume.txt")}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["matches"] == []
    assert "message" in body


def test_match_resume_happy_path_ranks_relevant_job_first(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = (
        b"Machine learning engineer with deep learning, TensorFlow, PyTorch, "
        b"and artificial intelligence experience."
    )
    data = {"resume": (io.BytesIO(resume_text), "resume.txt")}
    res = client.post("/api/match-resume", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["total_jobs_considered"] == len(sample_jobs)
    assert body["matches"][0]["title"] == "Machine Learning Fresher"


def test_match_resume_top_n_is_capped_at_100(client, mocker, sample_jobs):
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=sample_jobs)
    resume_text = b"Machine learning engineer with TensorFlow experience. " * 3
    data = {"resume": (io.BytesIO(resume_text), "resume.txt")}
    res = client.post(
        "/api/match-resume?top_n=99999", data=data, content_type="multipart/form-data"
    )
    assert res.status_code == 200
    # sample_jobs only has 4 entries, so this proves no error/crash from the
    # oversized top_n rather than proving the exact cap (see test_helpers for
    # the direct bounds-checking behavior).
    assert len(res.get_json()["matches"]) == len(sample_jobs)


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
    save_mock = mocker.patch.object(api_module, "save_jobs_to_db", return_value=True)
    mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])

    res = client.post("/api/fetch", json={"sources": ["testsource"]})

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["jobs_count"] == 2  # both jobs scraped before fresher filtering
    assert body["total_stored"] == 1  # only the fresher job passes is_fresher_job
    assert body["status"]["testsource"]["success"] is True

    # Only the fresher job should have been handed to save_jobs_to_db
    saved_jobs = save_mock.call_args[0][0]
    assert len(saved_jobs) == 1
    assert saved_jobs[0]["title"] == "Fresher Backend Intern"
    assert saved_jobs[0]["domains"] == ["General"]  # detect_job_domain() applied


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
    mocker.patch.object(api_module, "save_jobs_to_db", return_value=True)
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


def test_init_db_adds_missing_columns_to_legacy_table(mocker):
    mock_conn_for_db_create = mocker.MagicMock()
    mock_conn_for_table = mocker.MagicMock()
    mocker.patch.object(api_module.mysql.connector, "connect", return_value=mock_conn_for_db_create)
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn_for_table)

    cursor = mock_conn_for_table.cursor.return_value
    cursor.fetchall.return_value = _old_schema_columns()

    result = api_module.init_db()

    assert result is True
    executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("ADD COLUMN start_date" in sql for sql in executed_sql)
    assert any("ADD COLUMN end_date" in sql for sql in executed_sql)
    assert any("ADD COLUMN domains" in sql for sql in executed_sql)


def test_init_db_skips_alter_when_schema_already_current(mocker):
    mock_conn_for_db_create = mocker.MagicMock()
    mock_conn_for_table = mocker.MagicMock()
    mocker.patch.object(api_module.mysql.connector, "connect", return_value=mock_conn_for_db_create)
    mocker.patch.object(api_module, "get_db_connection", return_value=mock_conn_for_table)

    cursor = mock_conn_for_table.cursor.return_value
    cursor.fetchall.return_value = _old_schema_columns() + [("start_date",), ("end_date",), ("domains",)]

    api_module.init_db()

    executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any("ADD COLUMN" in sql for sql in executed_sql)


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

    assert result is True
    spy.assert_called_once()
    mock_conn.cursor.return_value.execute.assert_called_once()
    query_used = mock_conn.cursor.return_value.execute.call_args[0][0]
    assert "domains = VALUES(domains)" in query_used  # regression: upsert must refresh domains


def test_save_jobs_to_db_returns_false_on_connection_failure(mocker):
    mocker.patch.object(api_module, "get_db_connection", return_value=None)
    assert api_module.save_jobs_to_db([{"url": "x"}]) is False
