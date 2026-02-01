# CGO Proposal Slack App

Run the CGO proposal workflow from Slack via `/cgo-proposal <deal-url>`.

## Prerequisites

- HubSpot Private App with required scopes (see `../setup/hubspot-setup.md`)
- Anthropic API key for Claude
- Slack workspace with admin access to create an app

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HUBSPOT_API_KEY` | Yes | HubSpot Private App access token |
| `HUBSPOT_PORTAL_ID` | Yes | HubSpot portal ID |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `SLACK_SIGNING_SECRET` | Yes | Slack app signing secret (verify requests) |
| `PORT` | No | Server port (default 5000) |

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. Name it (e.g. "CGO Proposal") and select your workspace
3. **Slash Commands** → Create New Command:
   - Command: `/cgo-proposal`
   - Request URL: `https://YOUR_DEPLOYMENT_URL/slack/cgo-proposal`
   - Short description: `Generate CGO proposal from HubSpot deal`
   - Usage hint: `https://app.hubspot.com/contacts/PORTAL_ID/record/0-3/DEAL_ID`
4. **OAuth & Permissions** → Bot Token Scopes (add if needed):
   - `chat:write` (post results to channel)
   - `chat:write.public` (if posting to public channels)
5. **Install App** to your workspace
6. Copy **Signing Secret** from Basic Information → App Credentials

## Local Development

```bash
cd cgo-proposal/slack-app
pip install -r requirements.txt
export HUBSPOT_API_KEY=...
export HUBSPOT_PORTAL_ID=...
export ANTHROPIC_API_KEY=...
export SLACK_SIGNING_SECRET=...
python app.py
```

Use [ngrok](https://ngrok.com) to expose localhost for the Slack Request URL:
```bash
ngrok http 5000
# Use https://YOUR_NGROK_URL/slack/cgo-proposal as Request URL
```

## Deployment

### Railway / Render / Fly.io

1. Connect your repo and set the root to `cgo-proposal/slack-app` (or set start command)
2. Set environment variables
3. Deploy — the app listens on `PORT` (Railway/Render set this automatically)
4. Update Slack slash command Request URL to your deployment URL

### Procfile (for Railway/Render)

```
web: python app.py
```

### AWS Lambda (optional)

For Lambda, use a framework like [Mangum](https://mangum.io/) or [AWS SAM](https://aws.amazon.com/serverless/sam/) to wrap the Flask app. The handler must:

1. Return 200 within 3 seconds (Slack timeout)
2. Invoke the workflow asynchronously (e.g. Step Functions, SQS, or Lambda async invocation)
3. Post the result to `response_url` when complete

## Usage

In Slack, type:

```
/cgo-proposal https://app.hubspot.com/contacts/21656838/record/0-3/12345678
```

The bot replies immediately with "Generating proposal..." then posts the quote URL when ready (~30–90 seconds).
