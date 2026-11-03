"""
Tests for the hackathon feature: the Devpost scraper and the
/api/hackathons* endpoints. All DB access and outbound HTTP calls are
mocked, same convention as the rest of the suite.
"""
import pytest

import api as api_module
import hackathon_scraper


class TestScrapeDevpostHackathons:
    def test_builds_expected_fields_from_api_response(self, mocker):
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "hackathons": [{
                "title": "<b>AI</b> Hackathon",
                "organization_name": "Acme Corp",
                "displayed_location": {"location": "Online"},
                "prize_amount": "$<span data-currency-value>10,000</span>",
                "themes": [{"name": "Machine Learning/AI"}, {"name": "Web"}],
                "registrations_count": 1234,
                "submission_period_dates": "Oct 01 - Nov 12, 2026",
                "time_left_to_submission": "9 days left",
                "url": "https://aihackathon.devpost.com/",
            }],
            "meta": {"total_count": 1, "per_page": 9},
        }
        mock_response.raise_for_status.return_value = None
        mocker.patch.object(hackathon_scraper.requests, "get", return_value=mock_response)

        result = hackathon_scraper.scrape_devpost_hackathons()
        assert len(result) == 1
        h = result[0]
        assert h["source"] == "Devpost"
        assert h["title"] == "AI Hackathon"  # HTML stripped
        assert h["organizer"] == "Acme Corp"
        assert h["location"] == "Online"
        assert h["prize_amount"] == "$10,000"  # HTML stripped
        assert h["themes"] == "Machine Learning/AI, Web"
        assert h["registrations_count"] == "1234"
        assert h["url"] == "https://aihackathon.devpost.com/"

    def test_stops_on_empty_batch(self, mocker):
        mock_response = mocker.Mock()
        mock_response.json.return_value = {"hackathons": [], "meta": {"total_count": 0}}
        mock_response.raise_for_status.return_value = None
        mock_get = mocker.patch.object(hackathon_scraper.requests, "get", return_value=mock_response)

        result = hackathon_scraper.scrape_devpost_hackathons()
        assert result == []
        mock_get.assert_called_once()  # didn't keep paging past an empty page

    def test_request_failure_returns_whatever_was_collected_so_far(self, mocker):
        mocker.patch.object(hackathon_scraper.requests, "get", side_effect=RuntimeError("network down"))
        result = hackathon_scraper.scrape_devpost_hackathons()
        assert result == []  # fails gracefully, no crash


class TestFetchHackathonsEndpoint:
    def test_fetch_hackathons_saves_and_reports_counts(self, client, mocker):
        mocker.patch.object(
            api_module, "save_hackathons_to_db",
            return_value={"saved": 2, "failed": 0}
        )
        mocker.patch.object(
            hackathon_scraper, "scrape_devpost_hackathons",
            return_value=[
                {"source": "Devpost", "title": "Hack A", "organizer": "Org A", "location": "Online",
                 "prize_amount": "$1,000", "themes": "AI", "registrations_count": "10",
                 "submission_dates": "Oct 1-5", "time_left": "2 days left", "url": "https://a.devpost.com"},
                {"source": "Devpost", "title": "Hack B", "organizer": "Org B", "location": "Online",
                 "prize_amount": "$2,000", "themes": "Web", "registrations_count": "20",
                 "submission_dates": "Oct 1-5", "time_left": "2 days left", "url": "https://b.devpost.com"},
            ]
        )
        res = client.post("/api/hackathons/fetch")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["fetched"] == 2
        assert body["saved"] == 2

    def test_fetch_hackathons_handles_scraper_failure(self, client, mocker):
        mocker.patch.object(
            hackathon_scraper, "scrape_devpost_hackathons",
            side_effect=RuntimeError("boom")
        )
        res = client.post("/api/hackathons/fetch")
        assert res.status_code == 500
        assert res.get_json()["success"] is False


class TestGetHackathonsEndpoint:
    def test_get_hackathons_returns_stored_list(self, client, mocker):
        mocker.patch.object(
            api_module, "load_hackathons_from_db",
            return_value=[{"id": 1, "title": "Hack A"}, {"id": 2, "title": "Hack B"}]
        )
        res = client.get("/api/hackathons")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["total"] == 2

    def test_get_hackathons_handles_db_failure(self, client, mocker):
        mocker.patch.object(api_module, "load_hackathons_from_db", side_effect=RuntimeError("db down"))
        res = client.get("/api/hackathons")
        assert res.status_code == 500
        assert res.get_json()["success"] is False
