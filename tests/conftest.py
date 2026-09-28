"""
Shared pytest fixtures for the Job Portal test suite.

Tests never touch the real MySQL database - all DB access (load_jobs_from_db,
save_jobs_to_db, get_db_connection) is mocked at the boundary. This keeps the
suite fast, deterministic, and safe to run against a machine that has real
scraped job data sitting in MySQL.
"""
import os
import sys

# Ensure the project root (parent of tests/) is importable as `api`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# api.py requires DB_PASSWORD to be set at import time (raises ValueError
# otherwise). Provide a dummy value here in case .env is missing in CI -
# no real connection is ever attempted in tests since DB functions are mocked.
os.environ.setdefault("DB_PASSWORD", "test-password-not-used")

import pytest
import api as api_module


@pytest.fixture
def app():
    """Flask app configured for testing (rate limiting disabled)."""
    api_module.app.config.update({
        "TESTING": True,
        "RATELIMIT_ENABLED": False,
    })
    yield api_module.app


@pytest.fixture
def client(app):
    """Flask test client for hitting API endpoints."""
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_jobs_cache():
    """Ensure the in-memory jobs cache never leaks state between tests."""
    api_module.invalidate_jobs_cache()
    yield
    api_module.invalidate_jobs_cache()


@pytest.fixture
def sample_jobs():
    """A small, varied pool of job dicts shaped like load_jobs_from_db() output."""
    return [
        {
            "id": 1,
            "source": "Remotive",
            "title": "Machine Learning Fresher",
            "company": "Acme AI",
            "work_type": "Remote",
            "country": "India",
            "location": "Remote",
            "job_type": "Full-time",
            "category": "AI/ML",
            "salary": "",
            "date": "2026-01-01",
            "start_date": "",
            "end_date": "",
            "url": "https://example.com/job/1",
            "domains": ["AIML"],
        },
        {
            "id": 2,
            "source": "FirstNaukri",
            "title": "Data Analyst Intern",
            "company": "DataCorp",
            "work_type": "Onsite",
            "country": "India",
            "location": "Bangalore, India",
            "job_type": "Internship",
            "category": "Data Analytics",
            "salary": "",
            "date": "2026-01-02",
            "start_date": "",
            "end_date": "",
            "url": "https://example.com/job/2",
            "domains": ["Data Analytics"],
        },
        {
            "id": 3,
            "source": "Arbeitnow",
            "title": "Senior Blockchain Engineer",
            "company": "ChainWorks",
            "work_type": "Onsite",
            "country": "Germany",
            "location": "Berlin",
            "job_type": "Full-time",
            "category": "Blockchain",
            "salary": "€90k",
            "date": "2026-01-03",
            "start_date": "",
            "end_date": "",
            "url": "https://example.com/job/3",
            "domains": ["Blockchain"],
        },
        {
            "id": 4,
            "source": "Himalayas",
            "title": "Marketing Coordinator",
            "company": "BrandCo",
            "work_type": "Remote",
            "country": "Worldwide",
            "location": "Worldwide",
            "job_type": "Full-time",
            "category": "Marketing",
            "salary": "",
            "date": "2026-01-04",
            "start_date": "",
            "end_date": "",
            "url": "https://example.com/job/4",
            "domains": ["General"],
        },
    ]
