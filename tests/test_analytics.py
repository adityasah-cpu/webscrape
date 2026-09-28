"""
Tests for the analytics dashboard: get_analytics() helper and the
GET /api/analytics endpoint. Uses the analytics_jobs fixture (controlled
added_at timestamps) for deterministic time-series assertions.
"""
import api as api_module


class TestGetAnalytics:
    def test_empty_jobs_returns_zeroed_shape(self, mocker):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=[])
        result = api_module.get_analytics()
        assert result["summary"]["total_jobs"] == 0
        assert result["jobs_over_time"] == []
        assert result["by_domain"] == {}

    def test_summary_counts(self, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        result = api_module.get_analytics(days=14)
        summary = result["summary"]
        assert summary["total_jobs"] == 4
        assert summary["added_today"] == 1
        assert summary["added_this_week"] == 3  # today, yesterday, 5 days ago
        assert summary["total_companies"] == 3  # Acme AI, ChainWorks, BrandCo
        assert summary["total_sources"] == 2  # Remotive, Himalayas

    def test_jobs_over_time_has_requested_number_of_days(self, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        result = api_module.get_analytics(days=14)
        assert len(result["jobs_over_time"]) == 14
        # Days are contiguous and sorted ascending
        dates = [d["date"] for d in result["jobs_over_time"]]
        assert dates == sorted(dates)

    def test_jobs_over_time_excludes_jobs_outside_window(self, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        result = api_module.get_analytics(days=14)
        total_in_window = sum(d["count"] for d in result["jobs_over_time"])
        # Only 3 of the 4 fixture jobs fall within the last 14 days
        assert total_in_window == 3

    def test_by_domain_counts_every_tag(self, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        result = api_module.get_analytics()
        assert result["by_domain"]["AIML"] == 1
        assert result["by_domain"]["Data Analytics"] == 1
        assert result["by_domain"]["Blockchain"] == 1
        assert result["by_domain"]["General"] == 1

    def test_top_sources_sorted_descending(self, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        result = api_module.get_analytics(top_n=10)
        top = result["top_sources"]
        assert top[0] == {"name": "Remotive", "count": 2}
        assert {"name": "Himalayas", "count": 2} in top

    def test_top_n_limits_results(self, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        result = api_module.get_analytics(top_n=1)
        assert len(result["top_sources"]) == 1
        assert len(result["top_companies"]) == 1


class TestAnalyticsEndpoint:
    def test_returns_success_and_expected_keys(self, client, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        res = client.get("/api/analytics")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert "summary" in body
        assert "jobs_over_time" in body
        assert "by_domain" in body
        assert "top_companies" in body

    def test_days_param_is_bounded(self, client, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        res = client.get("/api/analytics?days=9999")
        assert res.status_code == 200
        assert len(res.get_json()["jobs_over_time"]) == 90  # capped, not 9999

    def test_invalid_query_params_fall_back_to_defaults(self, client, mocker, analytics_jobs):
        mocker.patch.object(api_module, "load_jobs_from_db", return_value=analytics_jobs)
        res = client.get("/api/analytics?days=not-a-number")
        assert res.status_code == 200
        assert len(res.get_json()["jobs_over_time"]) == 14

    def test_error_does_not_leak_exception_text(self, client, mocker):
        mocker.patch.object(api_module, "load_jobs_from_db", side_effect=RuntimeError("db secret"))
        res = client.get("/api/analytics")
        assert res.status_code == 500
        body = res.get_json()
        assert body["success"] is False
        assert "db secret" not in body["error"]
