"""
Tests for alerts.py: SSRF protection on the Slack webhook, URL-scheme
validation, and HTML/Markdown escaping of untrusted scraped job data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alerts


MALICIOUS_JOB = {
    "title": "<script>alert(1)</script>",
    "company": "Evil* Corp_[test]",
    "url": "javascript:alert(1)",
    "country": "India",
    "work_type": "Remote",
    "salary": "",
    "date": "",
    "source": "Test",
}


class TestSafeUrl:
    def test_allows_http(self):
        assert alerts._safe_url("http://example.com/job") == "http://example.com/job"

    def test_allows_https(self):
        assert alerts._safe_url("https://example.com/job") == "https://example.com/job"

    def test_rejects_javascript_scheme(self):
        assert alerts._safe_url("javascript:alert(1)") == "#"

    def test_rejects_data_scheme(self):
        assert alerts._safe_url("data:text/html,<script>alert(1)</script>") == "#"

    def test_handles_none_and_empty(self):
        assert alerts._safe_url(None) == "#"
        assert alerts._safe_url("") == "#"


class TestSendSlackSSRFProtection:
    def test_rejects_non_slack_webhook_url(self, mocker):
        """Regression test: send_slack used to POST to any caller-supplied
        URL with no validation - a live SSRF primitive reachable via
        POST /api/test-alert's alert_config.slack.webhook_url field."""
        post_spy = mocker.patch("alerts.requests.post")
        result = alerts.send_slack("http://169.254.169.254/latest/meta-data/", "hello")
        assert result is False
        post_spy.assert_not_called()

    def test_rejects_arbitrary_external_url(self, mocker):
        post_spy = mocker.patch("alerts.requests.post")
        result = alerts.send_slack("https://attacker.example.com/collect", "hello")
        assert result is False
        post_spy.assert_not_called()

    def test_allows_real_slack_webhook_url(self, mocker):
        mock_response = mocker.Mock(status_code=200)
        post_spy = mocker.patch("alerts.requests.post", return_value=mock_response)
        result = alerts.send_slack("https://hooks.slack.com/services/T000/B000/XXX", "hello")
        assert result is True
        post_spy.assert_called_once()

    def test_case_insensitive_scheme_check_still_rejects_non_slack_host(self, mocker):
        post_spy = mocker.patch("alerts.requests.post")
        result = alerts.send_slack("HTTPS://NOT-SLACK.COM/webhook", "hello")
        assert result is False
        post_spy.assert_not_called()


class TestOutputEscaping:
    def test_email_escapes_script_tag(self):
        html_out = alerts.format_jobs_email([MALICIOUS_JOB])
        assert "<script>alert(1)</script>" not in html_out
        assert "&lt;script&gt;" in html_out

    def test_email_blocks_javascript_url(self):
        html_out = alerts.format_jobs_email([MALICIOUS_JOB])
        assert 'href="javascript:alert(1)"' not in html_out
        assert 'href="#"' in html_out

    def test_telegram_escapes_markdown_special_chars(self):
        msg = alerts.format_jobs_telegram([MALICIOUS_JOB])
        # The raw unescaped company string must not appear verbatim
        assert "Evil* Corp_[test]" not in msg
        assert "javascript:alert(1)" not in msg

    def test_slack_escapes_markdown_and_blocks_bad_url(self):
        blocks = alerts.format_jobs_slack([MALICIOUS_JOB])
        text = blocks["blocks"][2]["text"]["text"]
        assert "Evil* Corp_[test]" not in text
        assert blocks["blocks"][2]["accessory"]["url"] == "#"
