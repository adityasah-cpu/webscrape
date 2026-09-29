"""
Tests for module-load-time configuration validation in api.py. These spawn a
subprocess with a controlled environment rather than importing api.py in
this process, since DB_NAME/DB_PASSWORD are validated once at import time
(raising ValueError immediately) - by the time the shared api_module fixture
exists for the rest of the suite, that validation has already passed.
"""
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_import_with_env(extra_env):
    env = os.environ.copy()
    env.update({
        "DB_PASSWORD": "irrelevant-for-this-test",
        "DB_NAME": "job_portal",
    })
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", "import api"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


class TestDbNameValidation:
    def test_valid_db_name_imports_cleanly(self):
        result = _run_import_with_env({"DB_NAME": "job_portal"})
        assert result.returncode == 0, result.stderr

    def test_sql_injection_attempt_in_db_name_is_rejected(self):
        """Regression test: DB_NAME is interpolated directly into a
        CREATE DATABASE statement (identifiers can't use %s placeholders).
        A value like this must be rejected at startup, not reach the SQL."""
        result = _run_import_with_env({"DB_NAME": "job_portal; DROP TABLE users;--"})
        assert result.returncode != 0
        assert "DB_NAME must contain only letters, digits, and underscores" in result.stderr

    def test_backtick_in_db_name_is_rejected(self):
        result = _run_import_with_env({"DB_NAME": "job`portal"})
        assert result.returncode != 0

    def test_missing_db_password_is_rejected(self):
        env = os.environ.copy()
        env.pop("DB_PASSWORD", None)
        env["DB_NAME"] = "job_portal"
        env["DB_PASSWORD"] = ""
        result = subprocess.run(
            [sys.executable, "-c", "import api"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "DB_PASSWORD environment variable is required" in result.stderr
