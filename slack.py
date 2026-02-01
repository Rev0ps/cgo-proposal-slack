"""
Slack utilities for posting CGO proposal results.
"""

import os
from typing import Any

import requests


def post_to_response_url(response_url: str, payload: dict) -> None:
    """
    Post a message to Slack's response_url (from slash command).
    Use this for the follow-up result after async processing.
    """
    requests.post(response_url, json=payload, timeout=10)


def post_success(response_url: str, result: dict[str, Any]) -> None:
    """Post success message with quote URL."""
    company = result.get("company_name", "Unknown")
    total = result.get("total_monthly", 0)
    quote_url = result.get("quote_url", "")
    services = result.get("services", [])
    services_text = "\n".join(f"• {s}" for s in services)
    payload = {
        "response_type": "in_channel",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*CGO Proposal created for {company}*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Monthly investment:* ${total:,}\n*Services:*\n{services_text}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"<{quote_url}|View quote in HubSpot>"}},
        ],
    }
    post_to_response_url(response_url, payload)


def post_error(response_url: str, error: str) -> None:
    """Post error message."""
    payload = {
        "response_type": "ephemeral",
        "text": f":x: CGO Proposal failed: {error}",
    }
    post_to_response_url(response_url, payload)


def post_ephemeral(response_url: str, text: str) -> None:
    """Post ephemeral (visible only to user) message."""
    payload = {"response_type": "ephemeral", "text": text}
    post_to_response_url(response_url, payload)


def verify_slack_request(body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify that a request came from Slack using the signing secret.
    See: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    import hmac
    import hashlib

    secret = os.environ.get("SLACK_SIGNING_SECRET")
    if not secret:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)
