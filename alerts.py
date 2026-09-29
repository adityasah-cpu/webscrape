"""
Alert integrations: Telegram, Email, Slack
Send notifications of new jobs matching filters.
"""

import os
import re
import html as html_escaper
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

logger = logging.getLogger(__name__)


def _safe_url(url):
    """Only allow http(s) URLs through to outbound messages/emails. Job data
    comes from scraped third-party sources, so a malicious or compromised
    listing could otherwise inject a javascript:/data: URI into an outbound
    notification."""
    url = str(url or "")
    if re.match(r"^https?://", url, re.IGNORECASE):
        return url
    return "#"


_MARKDOWN_SPECIAL_CHARS = re.compile(r"([_*\[\]`])")


def _escape_markdown(text):
    """Escape Telegram/Slack markdown special characters in untrusted job
    text so a crafted title/company can't break out of the surrounding
    formatting (e.g. unbalanced `*` closing bold early)."""
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", str(text or ""))


# ============ TELEGRAM ============

def send_telegram(bot_token, chat_id, message):
    """
    Send message via Telegram bot.
    
    Args:
        bot_token: From @BotFather on Telegram
        chat_id: Your chat ID (get from @userinfobot)
        message: Text to send (supports markdown)
    
    Returns:
        True if sent, False otherwise
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def format_jobs_telegram(jobs, title="🆕 New Jobs Found"):
    """Format jobs for Telegram message."""
    if not jobs:
        return f"{title}: None"
    
    msg = f"*{_escape_markdown(title)}* ({len(jobs)} new)\n\n"
    for j in jobs[:10]:  # Max 10 per message
        msg += f"*{_escape_markdown(j['title'])}* @ {_escape_markdown(j['company'])}\n"
        msg += f"🌍 {_escape_markdown(j.get('country', 'Unknown'))} | 💼 {_escape_markdown(j.get('work_type', 'Unknown'))}\n"
        msg += f"💰 {_escape_markdown(j.get('salary', 'Not listed'))} | 📅 {_escape_markdown(j.get('date', ''))}\n"
        msg += f"🔗 {_safe_url(j['url'])}\n\n"
    
    if len(jobs) > 10:
        msg += f"... and {len(jobs) - 10} more. Check the app for all."
    
    return msg


# ============ EMAIL ============

def send_email(sender_email, sender_password, recipient_email, subject, html_body):
    """
    Send email with job updates.
    
    Args:
        sender_email: Gmail/SMTP email (e.g., "your@gmail.com")
        sender_password: App password (NOT your regular password)
                         For Gmail: https://support.google.com/accounts/answer/185833
        recipient_email: Who to send to
        subject: Email subject
        html_body: HTML body of the email
    
    Returns:
        True if sent, False otherwise
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = recipient_email
        
        msg.attach(MIMEText(html_body, "html"))
        
        # Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False


def format_jobs_email(jobs, title="New Remote Jobs Found"):
    """Format jobs as HTML email."""
    if not jobs:
        return f"<p>No new jobs matching your filters.</p>"
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>{title} 🎉</h2>
        <p>Found <strong>{len(jobs)}</strong> new job(s) matching your profile.</p>
        <hr>
    """
    
    for j in jobs[:20]:
        esc = html_escaper.escape
        html += f"""
        <div style="border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
            <h3 style="margin-top: 0;">{esc(j['title'])}</h3>
            <p><strong>Company:</strong> {esc(j['company'])}</p>
            <p><strong>Location:</strong> {esc(j.get('location', 'Not specified'))} ({esc(j.get('country', 'Unknown'))})</p>
            <p><strong>Work Type:</strong> {esc(j.get('work_type', 'Unknown'))} | <strong>Type:</strong> {esc(j.get('job_type', 'Unknown'))}</p>
            <p><strong>Salary:</strong> {esc(j.get('salary', 'Not listed'))}</p>
            <p><strong>Posted:</strong> {esc(j.get('date', 'Unknown'))}</p>
            <p><strong>Source:</strong> {esc(j.get('source', 'Unknown'))}</p>
            <p><a href="{esc(_safe_url(j['url']))}" style="background-color: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 3px;">Apply Now →</a></p>
        </div>
        """
    
    if len(jobs) > 20:
        html += f"<p><em>... and {len(jobs) - 20} more. Check the app for all jobs.</em></p>"
    
    html += """
    <hr>
    <p style="color: #666; font-size: 12px;">
        This is an automated alert from Job Finder. 
        <a href="https://github.com/yourusername/job-finder">Manage your settings</a>
    </p>
    </body>
    </html>
    """
    return html


# ============ SLACK ============

def send_slack(webhook_url, message):
    """
    Send message via Slack webhook.

    Args:
        webhook_url: From Slack incoming webhook
                     https://api.slack.com/messaging/webhooks
        message: Text or blocks (dict)

    Returns:
        True if sent, False otherwise
    """
    # webhook_url is caller-supplied (ultimately from the /api/test-alert
    # request body) with no other validation upstream. Without this check,
    # this function is a generic SSRF primitive: it would POST an
    # attacker-controlled JSON body to any URL the caller names.
    if not re.match(r"^https://hooks\.slack\.com/", webhook_url or "", re.IGNORECASE):
        logger.error("Slack error: webhook_url must be a https://hooks.slack.com/ URL")
        return False
    try:
        data = {"text": message} if isinstance(message, str) else message
        r = requests.post(webhook_url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Slack error: {e}")
        return False


def format_jobs_slack(jobs, title="🆕 New Jobs Found"):
    """Format jobs for Slack blocks."""
    if not jobs:
        return {"text": f"{title}: No new jobs"}
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}*\n{len(jobs)} new job(s)"
            }
        },
        {"type": "divider"}
    ]
    
    for j in jobs[:10]:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"""*{_escape_markdown(j['title'])}* @ {_escape_markdown(j['company'])}
🌍 {_escape_markdown(j.get('country', 'Unknown'))} | 💼 {_escape_markdown(j.get('work_type', 'Unknown'))}
💰 {_escape_markdown(j.get('salary', 'Not listed'))} | 📅 {_escape_markdown(j.get('date', ''))}"""
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Apply"},
                "url": _safe_url(j['url'])
            }
        })
    
    if len(jobs) > 10:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"... and {len(jobs) - 10} more. Check the app!"
            }
        })
    
    return {"blocks": blocks}


# ============ MAIN ALERT FUNCTION ============

def send_alert(jobs, alert_config):
    """
    Send alert via configured channels.
    
    Args:
        jobs: List of job dicts
        alert_config: Dict with keys:
            - "telegram": {"bot_token": "...", "chat_id": "..."}
            - "email": {"sender": "...", "password": "...", "recipient": "..."}
            - "slack": {"webhook_url": "..."}
    
    Example:
        config = {
            "telegram": {"bot_token": "123:ABC", "chat_id": "999"},
            "email": {"sender": "jobs@gmail.com", "password": "app-pwd", "recipient": "me@gmail.com"},
            "slack": {"webhook_url": "https://hooks.slack.com/..."}
        }
        send_alert(jobs, config)
    """
    if not jobs:
        logger.info("No jobs to alert on.")
        return
    
    results = {}
    
    # Telegram
    if "telegram" in alert_config:
        cfg = alert_config["telegram"]
        msg = format_jobs_telegram(jobs)
        sent = send_telegram(cfg["bot_token"], cfg["chat_id"], msg)
        results["telegram"] = "✅" if sent else "❌"
    
    # Email
    if "email" in alert_config:
        cfg = alert_config["email"]
        subject = f"🎉 Job Alert: {len(jobs)} new job(s) found"
        html = format_jobs_email(jobs)
        sent = send_email(cfg["sender"], cfg["password"], cfg["recipient"], subject, html)
        results["email"] = "✅" if sent else "❌"
    
    # Slack
    if "slack" in alert_config:
        cfg = alert_config["slack"]
        blocks = format_jobs_slack(jobs)
        sent = send_slack(cfg["webhook_url"], blocks)
        results["slack"] = "✅" if sent else "❌"
    
    logger.info(f"Alerts sent: {results}")
    return results


if __name__ == "__main__":
    # Test with dummy config
    import json
    
    config_file = "alert_config.json"
    if os.path.exists(config_file):
        with open(config_file) as f:
            config = json.load(f)
        
        test_jobs = [
            {
                "title": "Python Developer",
                "company": "TechCorp",
                "country": "India",
                "work_type": "Remote",
                "job_type": "Full-time",
                "salary": "50-70 LPA",
                "date": "2024-09-20",
                "source": "Internshala",
                "url": "https://example.com/job1"
            }
        ]
        send_alert(test_jobs, config)
    else:
        print(f"Create {config_file} with alert settings to test.")
