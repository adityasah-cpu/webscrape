"""
Tests for the pure helper functions in remote_job_scraper.py. This module
previously had zero dedicated test coverage - only exercised indirectly via
mocked SCRAPERS/dedupe in test_api_endpoints.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import remote_job_scraper as rjs


class TestFmtSalary:
    def test_formats_a_range(self):
        assert rjs.fmt_salary(50000, 70000) == "50,000-70,000"

    def test_single_value_when_equal(self):
        assert rjs.fmt_salary(50000, 50000) == "50,000"

    def test_includes_currency(self):
        assert rjs.fmt_salary(50000, 70000, "$") == "50,000-70,000 $"

    def test_none_values_return_empty_string(self):
        assert rjs.fmt_salary(None, None) == ""

    def test_malformed_string_falls_back_to_valid_value(self):
        assert rjs.fmt_salary("not-a-number", 60000) == "60,000"

    def test_infinity_does_not_crash(self):
        """Regression test: int(float('inf')) raises OverflowError, which
        the old except (TypeError, ValueError) clause didn't catch - a
        third-party API returning a sentinel/unbounded value like this
        used to crash the entire scraper's per-job loop, losing every
        other job in that batch."""
        assert rjs.fmt_salary(float("inf"), 60000) == "60,000"
        assert rjs.fmt_salary(float("-inf"), float("inf")) == ""

    def test_nan_does_not_crash(self):
        assert rjs.fmt_salary(float("nan"), 60000) == "60,000"


class TestEpochToDate:
    def test_converts_seconds_epoch(self):
        assert rjs.epoch_to_date(1700000000) == "2023-11-14"

    def test_converts_milliseconds_epoch(self):
        assert rjs.epoch_to_date(1700000000000) == "2023-11-14"

    def test_none_returns_empty_string(self):
        assert rjs.epoch_to_date(None) == ""

    def test_non_numeric_string_returns_empty_string(self):
        assert rjs.epoch_to_date("not-a-timestamp") == ""

    def test_out_of_range_negative_epoch_does_not_crash(self):
        """Regression test: datetime.fromtimestamp() raises OSError (not
        ValueError/TypeError) for out-of-range epoch values on Windows -
        the old except clause let this propagate uncaught, silently
        dropping every job in the batch a single bad timestamp appeared in
        (e.g. via Lever's createdAt, Himalayas' pubDate, Arbeitnow's
        created_at)."""
        assert rjs.epoch_to_date(-999999999999) == ""

    def test_absurdly_large_positive_epoch_does_not_crash(self):
        assert rjs.epoch_to_date(99999999999999999) == ""


class TestJobFactory:
    def test_builds_expected_fields(self):
        j = rjs.job("TestSource", "Software Engineer", "Acme Corp", work_type="Remote")
        assert j["source"] == "TestSource"
        assert j["title"] == "Software Engineer"
        assert j["company"] == "Acme Corp"
        assert j["work_type"] == "Remote"

    def test_strips_html_from_title_and_company(self):
        j = rjs.job("Test", "<b>Engineer</b>", "<i>Acme</i>")
        assert j["title"] == "Engineer"
        assert j["company"] == "Acme"

    def test_missing_fields_default_sensibly(self):
        j = rjs.job("Test", "Engineer", "Acme")
        assert j["job_type"] == "Unspecified"
        assert j["url"] == ""
        assert j["description"] == ""

    def test_description_html_stripped(self):
        j = rjs.job("Test", "Engineer", "Acme", description="<p>Build <b>APIs</b> with Python</p>")
        assert j["description"] == "Build APIs with Python"

    def test_description_truncated_to_max_length(self):
        long_text = "x" * (rjs.MAX_DESCRIPTION_CHARS + 500)
        j = rjs.job("Test", "Engineer", "Acme", description=long_text)
        assert len(j["description"]) == rjs.MAX_DESCRIPTION_CHARS


class TestNoPublicApiScrapers:
    """HackerRank, GeeksforGeeks, and Naipunyam have no public job-listing
    API (login-gated or JS-rendered with no server-side data). These
    scrapers exist so the sources are honestly selectable in the UI, but
    must always return an empty list rather than fabricating data."""

    def test_hackerrank_returns_empty(self):
        assert rjs.scrape_hackerrank() == []

    def test_geeksforgeeks_returns_empty(self):
        assert rjs.scrape_geeksforgeeks() == []

    def test_naipunyam_returns_empty(self):
        assert rjs.scrape_naipunyam() == []

    def test_all_three_are_registered_in_scrapers_list(self):
        names = {s.__name__ for s in rjs.SCRAPERS}
        assert {"scrape_hackerrank", "scrape_geeksforgeeks", "scrape_naipunyam"} <= names


class TestDedupe:
    def test_removes_exact_duplicates(self):
        jobs = [
            rjs.job("A", "Engineer", "Acme", work_type="Remote"),
            rjs.job("A", "Engineer", "Acme", work_type="Remote"),
        ]
        assert len(rjs.dedupe(jobs)) == 1

    def test_keeps_same_role_at_different_onsite_locations(self):
        jobs = [
            rjs.job("A", "Engineer", "Acme", work_type="Onsite", location="Bangalore"),
            rjs.job("A", "Engineer", "Acme", work_type="Onsite", location="Delhi"),
        ]
        assert len(rjs.dedupe(jobs)) == 2

    def test_drops_jobs_with_no_title(self):
        jobs = [rjs.job("A", "", "Acme")]
        assert rjs.dedupe(jobs) == []
