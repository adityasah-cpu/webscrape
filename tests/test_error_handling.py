"""
Failure-mode regression tests.

The app previously collapsed every failure into either "200 with empty data"
or an HTML error page:
  - a database outage looked exactly like "this user has no jobs"
  - /api/db-info reported "✓ Active" while MySQL was unreachable
  - /api/export returned an empty CSV with 200
  - unknown API routes returned HTML, which breaks the frontend's res.json()

These tests pin the behaviours that make failures visible and machine
readable: JSON error bodies, 503 for database outages, 404/405 JSON, and
the unauthenticated /api/health probe.
"""
import api as api_module
import remote_job_scraper as rjs


# ---------------- /api/health ----------------

class TestHealthEndpoint:
    def test_health_is_reachable_without_a_session(self, anonymous_client, mocker):
        mocker.patch.object(api_module, "_ping_db", return_value=True)
        res = anonymous_client.get("/api/health")
        assert res.status_code == 200

    def test_health_ok_when_database_answers(self, anonymous_client, mocker):
        mocker.patch.object(api_module, "_ping_db", return_value=True)
        body = anonymous_client.get("/api/health").get_json()
        assert body["status"] == "ok"
        assert body["database"] == "up"

    def test_health_reports_degraded_and_503_when_database_is_down(self, anonymous_client, mocker):
        mocker.patch.object(api_module, "_ping_db", return_value=False)
        res = anonymous_client.get("/api/health")
        assert res.status_code == 503
        body = res.get_json()
        assert body["status"] == "degraded"
        assert body["database"] == "down"


# ---------------- JSON error contract ----------------

class TestJsonErrorContract:
    def test_unknown_api_route_returns_json_404(self, client):
        res = client.get("/api/does-not-exist")
        assert res.status_code == 404
        assert res.content_type.startswith("application/json")
        assert res.get_json()["success"] is False

    def test_wrong_method_returns_json_405(self, client):
        res = client.post("/api/sources")
        assert res.status_code == 405
        assert res.content_type.startswith("application/json")
        assert res.get_json()["success"] is False

    def test_unhandled_exception_returns_json_500(self, client, mocker):
        """cache_info() has no try/except of its own, so this exercises the
        app-wide handler rather than a route-local one."""
        mocker.patch.object(api_module, "current_user_email", side_effect=RuntimeError("boom"))
        res = client.get("/api/cache-info")
        assert res.status_code == 500
        assert res.content_type.startswith("application/json")
        body = res.get_json()
        assert body["success"] is False
        assert "boom" not in body["error"]  # no internal detail leaked


# ---------------- database outage = 503, never empty 200 ----------------

class TestDatabaseOutage:
    def test_jobs_returns_503_when_database_is_unavailable(self, client, mocker):
        mocker.patch.object(
            api_module, "load_jobs_from_db",
            side_effect=api_module.DatabaseUnavailableError("connection refused"),
        )
        res = client.get("/api/jobs")
        assert res.status_code == 503
        body = res.get_json()
        assert body["success"] is False
        assert "unavailable" in body["error"].lower()

    def test_stats_returns_503_when_database_is_unavailable(self, client, mocker):
        mocker.patch.object(
            api_module, "load_jobs_from_db",
            side_effect=api_module.DatabaseUnavailableError("offline"),
        )
        assert client.get("/api/stats").status_code == 503

    def test_analytics_returns_503_when_database_is_unavailable(self, client, mocker):
        mocker.patch.object(
            api_module, "load_jobs_from_db",
            side_effect=api_module.DatabaseUnavailableError("offline"),
        )
        assert client.get("/api/analytics").status_code == 503

    def test_export_does_not_return_an_empty_file_on_outage(self, client, mocker):
        mocker.patch.object(
            api_module, "load_jobs_from_db",
            side_effect=api_module.DatabaseUnavailableError("offline"),
        )
        res = client.get("/api/export?format=csv")
        assert res.status_code == 503
        assert res.content_type.startswith("application/json")

    def test_db_info_returns_503_when_ping_fails(self, client, mocker):
        mocker.patch.object(api_module, "_ping_db", return_value=False)
        res = client.get("/api/db-info")
        assert res.status_code == 503
        body = res.get_json()
        assert body["success"] is False
        assert body["status"] == "✗ Unreachable"

    def test_resources_returns_503_when_database_is_unavailable(self, client, mocker):
        mocker.patch.object(
            api_module, "load_resources_from_db",
            side_effect=api_module.DatabaseUnavailableError("offline"),
        )
        assert client.get("/api/resources").status_code == 503

    def test_hackathons_returns_503_when_database_is_unavailable(self, client, mocker):
        mocker.patch.object(
            api_module, "load_hackathons_from_db",
            side_effect=api_module.DatabaseUnavailableError("offline"),
        )
        assert client.get("/api/hackathons").status_code == 503

    def test_fetch_returns_503_when_nothing_could_be_stored(self, client, mocker):
        job = {"title": "Graduate Trainee", "company": "Acme", "url": "https://example.com/g"}

        def fake_scraper():
            return [job]
        fake_scraper.__name__ = "scrape_fake"

        mocker.patch.object(rjs, "SCRAPERS", [fake_scraper])
        mocker.patch.object(rjs, "dedupe", side_effect=lambda jobs: jobs)
        mocker.patch.object(api_module, "save_jobs_to_db", return_value={"saved": 0, "failed": 1})

        res = client.post("/api/fetch", json={"sources": ["fake"]})
        assert res.status_code == 503


# ---------------- request validation ----------------

class TestRequestValidation:
    def test_fetch_without_json_body_returns_400_not_500(self, client):
        res = client.post("/api/fetch")
        assert res.status_code == 400
        assert res.get_json()["success"] is False

    def test_fetch_with_json_but_no_sources_key_returns_400(self, client):
        res = client.post("/api/fetch", json={"unexpected": "shape"})
        assert res.status_code == 400


# ---------------- scraper timeouts ----------------

class TestScraperTimeouts:
    def test_weworkremotely_fetches_via_requests_with_timeout(self, mocker):
        """feedparser.parse(url) has no timeout; the scraper must download
        the feed through requests (TIMEOUT) and only parse the bytes."""
        response = mocker.MagicMock()
        response.content = b"<rss><channel></channel></rss>"
        get_mock = mocker.patch.object(rjs.requests, "get", return_value=response)

        assert rjs.scrape_weworkremotely() == []
        assert get_mock.call_args.kwargs["timeout"] == rjs.TIMEOUT

    def test_firstnaukri_fetches_via_requests_with_timeout(self, mocker):
        response = mocker.MagicMock()
        response.content = b"<rss><channel></channel></rss>"
        get_mock = mocker.patch.object(rjs.requests, "get", return_value=response)

        assert rjs.scrape_firstnaukri() == []
        assert get_mock.call_args.kwargs["timeout"] == rjs.TIMEOUT

    def test_upwork_fetches_via_requests_with_timeout(self, mocker):
        response = mocker.MagicMock()
        response.content = b"<rss><channel></channel></rss>"
        get_mock = mocker.patch.object(rjs.requests, "get", return_value=response)

        assert rjs.scrape_upwork() == []
        assert get_mock.call_args.kwargs["timeout"] == rjs.TIMEOUT
