"""
CGO Proposal Workflow - HubSpot + Claude integration.

Reimplements the CGO skill logic as executable Python for Slack-triggered runs.
Phases 1-4: HubSpot API (deal, companies, contacts, Fathom transcripts)
Phases 5-6: Claude API (recommendations, 90-day preview, executive summary)
Phases 7-8: Create quote + line items in HubSpot
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

# SKU to product mapping (from references/subproducts.md)
SERVICES = [
    {"sku": "CGO-MKTOPS", "name": "Marketing Operations Consulting", "price": 3000,
     "description": "Lead scoring, segmentation, campaign orchestration, ABM strategy"},
    {"sku": "CGO-SALESOPS", "name": "Sales Operations Consulting", "price": 3000,
     "description": "Sales enablement, pipeline optimization, lead scoring"},
    {"sku": "CGO-CRM", "name": "CRM Management", "price": 2000,
     "description": "Weekly hotfixes, data quality monitoring, ad-hoc reporting"},
    {"sku": "CGO-DATA", "name": "Ongoing Data Enrichment", "price": 1500,
     "description": "1 custom signal + ICP monthly enrichment"},
    {"sku": "CGO-EMAIL", "name": "Email Outreach Automation", "price": 1500,
     "description": "Cold email infrastructure and campaign execution"},
    {"sku": "CGO-LINKEDIN", "name": "LinkedIn Outreach Automation", "price": 1500,
     "description": "LinkedIn prospecting automation"},
    {"sku": "CGO-BUNDLE", "name": "CGO Bundle (Full)", "price": 12000,
     "description": "All services included"},
]

PAIN_POINT_MAP = {
    "CGO-CRM": ["hubspot underutilized", "crm", "data silo", "logging", "data quality", "duplicates",
                "messy data", "hubspot help", "custom properties", "reporting", "dashboards"],
    "CGO-MKTOPS": ["marketing automation", "lead scoring", "campaigns", "abm", "marketing attribution",
                   "visitor identification", "website traffic", "de-anonymize", "lead qualification", "mql", "nurture"],
    "CGO-SALESOPS": ["sales enablement", "pipeline", "sequences", "sales process", "forecasting",
                     "sales team", "quota", "opportunity", "deal velocity", "win rate", "sales handoff"],
    "CGO-DATA": ["data enrichment", "target market data", "contacts", "validation", "lead lists",
                 "icp data", "firmographic", "technographic", "buying signals", "intent data", "clay"],
    "CGO-EMAIL": ["email campaign", "cold email", "deliverability", "outreach", "email sequences",
                  "prospecting email", "spam", "email warmup", "open rates", "reply rates"],
    "CGO-LINKEDIN": ["linkedin campaign", "linkedin outreach", "social selling", "linkedin prospecting",
                     "connection requests", "inmail", "linkedin automation", "social"],
}


def parse_deal_url(url: str) -> Optional[tuple[str, str]]:
    """Extract PORTAL_ID and DEAL_ID from HubSpot deal URL."""
    # Format: https://app.hubspot.com/contacts/PORTAL_ID/record/0-3/DEAL_ID
    m = re.search(r"contacts/(\d+)/record/0-3/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _hubspot_get(api_key: str, path: str, params: dict | None = None) -> dict:
    """GET request to HubSpot API."""
    url = f"https://api.hubapi.com{path}"
    r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _hubspot_post(api_key: str, path: str, data: dict) -> dict:
    """POST request to HubSpot API."""
    url = f"https://api.hubapi.com{path}"
    r = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=data, timeout=30)
    r.raise_for_status()
    return r.json()


def _hubspot_put(api_key: str, path: str) -> None:
    """PUT request to HubSpot API (associations)."""
    url = f"https://api.hubapi.com{path}"
    r = requests.put(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    r.raise_for_status()


def fetch_deal(api_key: str, deal_id: str) -> dict:
    """Phase 2: Fetch deal with associations."""
    return _hubspot_get(api_key, f"/crm/v3/objects/deals/{deal_id}", {"associations": "contacts,companies"})


def fetch_companies(api_key: str, company_ids: list[str]) -> list[dict]:
    """Phase 3: Fetch companies."""
    companies = []
    props = "name,domain,industry,numberofemployees,address,city,state,zip,hs_logo_url"
    for cid in company_ids:
        try:
            data = _hubspot_get(api_key, f"/crm/v3/objects/companies/{cid}", {"properties": props})
            companies.append(data)
        except requests.HTTPError:
            pass
    return companies


def fetch_contacts(api_key: str, contact_ids: list[str]) -> list[dict]:
    """Phase 3: Fetch contacts."""
    contacts = []
    props = "firstname,lastname,email,jobtitle"
    for cid in contact_ids:
        try:
            data = _hubspot_get(api_key, f"/crm/v3/objects/contacts/{cid}", {"properties": props})
            contacts.append(data)
        except requests.HTTPError:
            pass
    return contacts


def fetch_fathom_transcripts(api_key: str, deal_id: str) -> list[str]:
    """Phase 4: Fetch Fathom AI summaries from meeting engagements."""
    transcripts = []
    try:
        assoc = _hubspot_get(api_key, f"/crm/v4/objects/deals/{deal_id}/associations/meetings")
        results = assoc.get("results", [])
    except requests.HTTPError:
        return transcripts

    props = "hs_meeting_title,hs_internal_meeting_notes,hs_meeting_body,hs_timestamp"
    for r in results:
        meeting_id = r.get("toObjectId")
        if not meeting_id:
            continue
        try:
            meeting = _hubspot_get(api_key, f"/crm/v3/objects/meetings/{meeting_id}", {"properties": props})
            notes = (meeting.get("properties") or {}).get("hs_internal_meeting_notes") or ""
            if "AI Meeting Summary" in notes or "Generated by Fathom" in notes:
                transcripts.append(notes)
        except requests.HTTPError:
            pass
    return transcripts


def fetch_products(api_key: str) -> dict[str, str]:
    """Get product IDs by SKU."""
    data = _hubspot_get(api_key, "/crm/v3/objects/products", {"limit": 100, "properties": "name,hs_sku"})
    sku_to_id: dict[str, str] = {}
    for p in data.get("results", []):
        sku = (p.get("properties") or {}).get("hs_sku")
        if sku:
            sku_to_id[sku] = p["id"]
    return sku_to_id


def _recommend_from_transcript(text: str) -> set[str]:
    """Score transcript against pain point indicators; return recommended SKUs."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for sku, indicators in PAIN_POINT_MAP.items():
        if sku == "CGO-BUNDLE":
            continue
        score = 0
        for ind in indicators:
            if ind in text_lower:
                score += 2
        if score >= 2:
            scores[sku] = score
    return set(scores.keys())


def recommend_services(transcripts: list[str]) -> tuple[list[dict], int]:
    """
    Phase 5: Analyze transcripts and recommend services.
    Returns (list of service dicts with name, price, description, justification), total_monthly.
    """
    all_skus: set[str] = set()
    for t in transcripts:
        all_skus |= _recommend_from_transcript(t)

    if len(all_skus) >= 4:
        return [s for s in SERVICES if s["sku"] == "CGO-BUNDLE"], 12000

    recommended = [s for s in SERVICES if s["sku"] in all_skus]
    total = sum(s["price"] for s in recommended)
    return recommended, total


def _call_claude(api_key: str, system: str, user: str, max_tokens: int = 4096) -> str:
    """Call Anthropic Claude API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    r = requests.post(url, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    blocks = data.get("content", [])
    text = ""
    for b in blocks:
        if b.get("type") == "text":
            text += b.get("text", "")
    return text.strip()


def generate_90_day_preview(anthropic_key: str, transcripts: list[str], company_name: str) -> str:
    """Phase 6: Generate First 90 Day Preview HTML via Claude."""
    transcript_text = "\n\n---\n\n".join(transcripts) if transcripts else "No discovery call transcripts available. Generate a general but professional 90-day preview."
    system = """You are a RevOps consultant. Generate a First 90 Day Preview as HTML for a CGO proposal.
Structure: 5-7 workstream sections. Each section has an h3 header and a ul with 4-7 detailed li items.
Reference specific tools, people, numbers from the transcript when possible. Be action-oriented.
Output ONLY valid HTML, no markdown code fences. Use <h3> and <ul><li>...</li></ul>."""
    user = f"Company: {company_name}\n\nTranscripts:\n{transcript_text[:15000]}"
    return _call_claude(anthropic_key, system, user)


def generate_executive_summary(anthropic_key: str, transcripts: list[str], company_name: str, services: list[dict], total: int) -> str:
    """Phase 7: Generate Executive Summary HTML for hs_comments."""
    transcript_text = "\n\n---\n\n".join(transcripts) if transcripts else "No discovery call data."
    services_text = "\n".join(f"- {s['name']} (${s['price']:,}/mo): {s['description']}" for s in services)
    system = """You are a RevOps consultant. Generate an Executive Summary as HTML for a CGO proposal.
Structure: <h3>Understanding Your Challenges</h3><p>...</p>
<h3>Our Recommendation</h3><p>Based on our discovery, we recommend:</p><ul><li><strong>Service Name</strong> - justification</li>...</ul>
<blockquote>With this engagement, you'll have a dedicated RevOps partner focused on one thing: helping you win more business, more often.</blockquote>
Be specific to the transcript. Professional, warm. Output ONLY valid HTML."""
    user = f"Company: {company_name}\nMonthly total: ${total:,}\n\nTranscripts:\n{transcript_text[:12000]}\n\nServices:\n{services_text}"
    return _call_claude(anthropic_key, system, user)


def create_quote_and_line_items(
    api_key: str,
    portal_id: str,
    deal_id: str,
    company_name: str,
    services: list[dict],
    executive_summary_html: str,
    ninety_day_preview_html: str,
) -> str:
    """
    Phase 8: Create quote, line items, associations.
    Returns quote URL.
    """
    sku_to_id = fetch_products(api_key)
    exp_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
    terms = """<ul><li><strong>Initial Term:</strong> 12 months from effective date</li>
<li><strong>Termination:</strong> 30 days written notice after initial term</li>
<li><strong>Payment:</strong> Net 15, monthly in advance</li>
<li><strong>Expenses:</strong> Pre-approved expenses billed at cost</li></ul>"""

    quote_data = {
        "properties": {
            "hs_title": f"CGO in a Box Proposal - {company_name}",
            "hs_expiration_date": exp_date,
            "hs_status": "DRAFT",
            "hs_language": "en",
            "hs_locale": "en-us",
            "hs_currency": "USD",
            "hs_comments": executive_summary_html,
            "cgo_90_day_preview": ninety_day_preview_html,
            "hs_terms": terms,
        },
        "associations": [{"to": {"id": deal_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 64}]}],
    }
    quote = _hubspot_post(api_key, "/crm/v3/objects/quotes", quote_data)
    quote_id = quote["id"]

    for svc in services:
        prod_id = sku_to_id.get(svc["sku"])
        if not prod_id:
            continue
        li_data = {
            "properties": {
                "hs_product_id": prod_id,
                "quantity": 1,
                "price": str(svc["price"]),
                "name": svc["name"],
                "description": svc.get("description", ""),
            },
        }
        line_item = _hubspot_post(api_key, "/crm/v3/objects/line_items", li_data)
        _hubspot_put(api_key, f"/crm/v3/objects/quotes/{quote_id}/associations/line_items/{line_item['id']}/67")

    return f"https://app.hubspot.com/contacts/{portal_id}/record/0-115/{quote_id}"


def run_workflow(deal_url: str) -> dict[str, Any]:
    """
    Run the full CGO proposal workflow.
    Returns dict with keys: success, message, quote_url (if success), error (if not).
    """
    api_key = os.environ.get("HUBSPOT_API_KEY")
    portal_id = os.environ.get("HUBSPOT_PORTAL_ID")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not portal_id:
        return {"success": False, "error": "HUBSPOT_API_KEY and HUBSPOT_PORTAL_ID must be set"}
    if not anthropic_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY must be set for AI generation"}

    parsed = parse_deal_url(deal_url)
    if not parsed:
        return {"success": False, "error": "Invalid HubSpot deal URL. Use: https://app.hubspot.com/contacts/PORTAL_ID/record/0-3/DEAL_ID"}
    url_portal, deal_id = parsed
    if url_portal != portal_id:
        return {"success": False, "error": f"Deal URL portal {url_portal} does not match configured HUBSPOT_PORTAL_ID {portal_id}"}

    try:
        deal_resp = fetch_deal(api_key, deal_id)
    except requests.HTTPError as e:
        return {"success": False, "error": f"HubSpot API error: {e}"}

    deal_props = deal_resp.get("properties", {})
    deal_name = deal_props.get("dealname", "Unknown Deal")
    associations = deal_resp.get("associations", {})
    company_ids = [r["id"] for r in associations.get("companies", {}).get("results", [])]
    contact_ids = [r["id"] for r in associations.get("contacts", {}).get("results", [])]

    companies = fetch_companies(api_key, company_ids)
    contacts = fetch_contacts(api_key, contact_ids)
    company_name = companies[0]["properties"]["name"] if companies else deal_name

    transcripts = fetch_fathom_transcripts(api_key, deal_id)
    if not transcripts:
        return {
            "success": False,
            "error": "No Fathom meeting summaries found for this deal. Please ensure discovery calls are recorded with Fathom and linked to the deal, or add discovery notes manually.",
        }

    services, total = recommend_services(transcripts)
    if not services:
        services, total = [SERVICES[0]], 3000

    try:
        exec_summary = generate_executive_summary(anthropic_key, transcripts, company_name, services, total)
        preview = generate_90_day_preview(anthropic_key, transcripts, company_name)
    except requests.HTTPError as e:
        return {"success": False, "error": f"Claude API error: {e}"}

    try:
        quote_url = create_quote_and_line_items(
            api_key, portal_id, deal_id, company_name, services,
            exec_summary, preview,
        )
    except requests.HTTPError as e:
        return {"success": False, "error": f"HubSpot error creating quote: {e}"}

    return {
        "success": True,
        "quote_url": quote_url,
        "company_name": company_name,
        "total_monthly": total,
        "services": [s["name"] for s in services],
    }
