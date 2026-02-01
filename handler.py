"""
HTTP handler for Slack slash command /cgo-proposal.

Uses async pattern: return 200 immediately, run workflow in background,
then post result to response_url.
"""

import os
import threading
from typing import Optional

from slack import post_error, post_ephemeral, post_success, verify_slack_request
from workflow import run_workflow


def handle_slash_command(
    deal_url: Optional[str],
    response_url: str,
    user_id: str,
) -> dict:
    """
    Handle slash command: validate input, return immediate response dict for Slack.
    Spawns background thread to run workflow and post result.
    """
    deal_url = (deal_url or "").strip()
    if not response_url:
        return {"response_type": "ephemeral", "text": "Missing response_url. This endpoint must be called from Slack."}
    if not deal_url:
        return {"response_type": "ephemeral", "text": "Usage: /cgo-proposal <HubSpot deal URL>\nExample: /cgo-proposal https://app.hubspot.com/contacts/21656838/record/0-3/12345"}

    def run_and_post():
        result = run_workflow(deal_url)
        if result.get("success"):
            post_success(response_url, result)
        else:
            post_error(response_url, result.get("error", "Unknown error"))

    thread = threading.Thread(target=run_and_post)
    thread.daemon = True
    thread.start()

    return {
        "response_type": "ephemeral",
        "text": "Generating CGO proposal... I'll post the quote link here when it's ready (usually 30–90 seconds).",
    }


def parse_slack_form(body: str) -> dict:
    """Parse Slack form-urlencoded body."""
    from urllib.parse import unquote_plus
    params: dict[str, str] = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = unquote_plus(v)
    return params


def parse_deal_url_from_text(text: str) -> Optional[str]:
    """Extract HubSpot deal URL from slash command text (may contain extra text)."""
    import re
    m = re.search(r"https://app\.hubspot\.com/contacts/\d+/record/0-3/\d+", text)
    return m.group(0) if m else (text.strip() if text.strip() else None)
