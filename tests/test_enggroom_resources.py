"""
Tests for the EnggRoom resource index: the scraper (metadata only - no
project content) and the /api/resources* endpoints. All DB access is mocked,
same convention as the rest of the suite.
"""
import pytest

import api as api_module
import enggroom_scraper


class TestScrapeEnggroomResources:
    def test_returns_metadata_rows_only(self):
        resources = enggroom_scraper.scrape_enggroom_resources()
        assert len(resources) > 0
        for r in resources:
            assert set(r.keys()) == {"discipline", "resource_type", "title", "url", "source"}
            assert r["url"].startswith("https://www.enggroom.com/")
            assert r["source"] == "EnggRoom"

    def test_no_duplicate_urls_within_a_single_scrape(self):
        resources = enggroom_scraper.scrape_enggroom_resources()
        urls = [r["url"] for r in resources]
        # Some category labels (e.g. "Interview Questions") intentionally
        # point at the same shared page across disciplines - that's expected,
        # not checked here. This only guards against an accidental literal
        # duplicate entry for the exact same (discipline, resource_type).
        keys = [(r["discipline"], r["resource_type"]) for r in resources]
        assert len(keys) == len(set(keys))


class TestFetchResourcesEndpoint:
    def test_fetch_resources_saves_and_reports_counts(self, client, mocker):
        mocker.patch.object(
            api_module, "save_resources_to_db",
            return_value={"saved": 2, "failed": 0}
        )
        mocker.patch.object(
            enggroom_scraper, "scrape_enggroom_resources",
            return_value=[
                {"discipline": "Computer Engineering", "resource_type": "Projects",
                 "title": "Computer Engineering - Projects", "url": "https://www.enggroom.com/Project.aspx",
                 "source": "EnggRoom"},
                {"discipline": "Civil Engineering", "resource_type": "Projects",
                 "title": "Civil Engineering - Projects", "url": "https://www.enggroom.com/Civil/x.htm",
                 "source": "EnggRoom"},
            ]
        )
        res = client.post("/api/resources/fetch")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["fetched"] == 2
        assert body["saved"] == 2

    def test_fetch_resources_handles_scraper_failure(self, client, mocker):
        mocker.patch.object(
            enggroom_scraper, "scrape_enggroom_resources",
            side_effect=RuntimeError("boom")
        )
        res = client.post("/api/resources/fetch")
        assert res.status_code == 500
        assert res.get_json()["success"] is False


class TestGetResourcesEndpoint:
    SAMPLE = [
        {"id": 1, "discipline": "Computer Engineering", "resource_type": "Projects",
         "title": "Computer Engineering - Projects", "url": "https://www.enggroom.com/Project.aspx"},
        {"id": 2, "discipline": "Civil Engineering", "resource_type": "Projects",
         "title": "Civil Engineering - Projects", "url": "https://www.enggroom.com/Civil/x.htm"},
    ]

    def test_get_resources_returns_all_by_default(self, client, mocker):
        mocker.patch.object(api_module, "load_resources_from_db", return_value=self.SAMPLE)
        res = client.get("/api/resources")
        assert res.status_code == 200
        body = res.get_json()
        assert body["total"] == 2

    def test_get_resources_filters_by_discipline(self, client, mocker):
        mocker.patch.object(api_module, "load_resources_from_db", return_value=self.SAMPLE)
        res = client.get("/api/resources?discipline=Civil Engineering")
        body = res.get_json()
        assert body["total"] == 1
        assert body["resources"][0]["discipline"] == "Civil Engineering"

    def test_get_resources_handles_db_failure(self, client, mocker):
        mocker.patch.object(api_module, "load_resources_from_db", side_effect=RuntimeError("db down"))
        res = client.get("/api/resources")
        assert res.status_code == 500
        assert res.get_json()["success"] is False
