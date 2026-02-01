"""
Flask app for Slack /cgo-proposal slash command.

Deploy to Railway, Render, Fly.io, or similar. For AWS Lambda, use the serverless
adapter (see README).
"""

import os

from flask import Flask, request, jsonify

from handler import handle_slash_command, parse_deal_url_from_text, parse_slack_form
from slack import verify_slack_request

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """Root route - confirms app is running."""
    return jsonify({
        "app": "CGO Proposal Slack",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "slash_command": "POST /slack/cgo-proposal",
        },
    }), 200


@app.route("/slack/cgo-proposal", methods=["POST"])
def slack_cgo_proposal():
    """Handle Slack slash command POST."""
    body = request.get_data()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_request(body, timestamp, signature):
        return jsonify({"error": "Invalid signature"}), 401

    params = parse_slack_form(body.decode("utf-8"))
    text = params.get("text", "")
    response_url = params.get("response_url", "")

    deal_url = parse_deal_url_from_text(text)
    user_id = params.get("user_id", "")

    response = handle_slash_command(
        deal_url=deal_url or "",
        response_url=response_url,
        user_id=user_id,
    )
    return jsonify(response), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check for load balancers."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
