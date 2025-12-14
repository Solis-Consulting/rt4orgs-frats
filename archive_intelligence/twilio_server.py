from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pathlib import Path
from datetime import datetime
import json
import os

from message_processor.handler import handle_inbound
from message_processor.markov_chain import MarkovChain
from message_processor.utils import (
    load_leads,
    load_sales_history,
    find_matching_fraternity,
    lookup_contact_by_phone,
    load_latest_event_state,
)
from message_processor.generate_message import generate_message

BASE_DIR = Path(__file__).resolve().parent
CONTACTS_DIR = BASE_DIR / "contacts"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

markov = MarkovChain()


def ensure_contacts_dir():
    CONTACTS_DIR.mkdir(parents=True, exist_ok=True)


def twiml(message: str):
    """Generate TwiML XML response for Twilio"""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{message}</Message></Response>"
    )
    return xml


def append_link(text: str) -> str:
    return f"{text}\n\nLearn more: https://rt4orgs.com"


def load_all():
    """Load all contact folders and organize by base name"""
    ensure_contacts_dir()
    items = {}
    
    for folder in CONTACTS_DIR.iterdir():
        if not folder.is_dir():
            continue
        
        state_path = folder / "state.json"
        msg_path = folder / "message.txt"
        
        if not state_path.exists():
            continue
        
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            continue
        
        message = msg_path.read_text() if msg_path.exists() else ""
        
        # Extract base name (everything before the timestamp)
        # Example: "Cooper_Berry_2025-12-08T19-47-40" → "Cooper_Berry"
        parts = folder.name.split("_")
        # Find the part that looks like a timestamp (YYYY-MM-DDTHH-MM-SS)
        base_name_parts = []
        for i, part in enumerate(parts):
            if len(part) >= 10 and "T" in part and part.replace("T", "").replace("-", "").isdigit():
                break
            base_name_parts.append(part)
        
        base_name = "_".join(base_name_parts) if base_name_parts else folder.name.split("_")[0]
        
        if base_name not in items:
            items[base_name] = {
                "name": base_name,
                "folders": [],
                "latest_state": None,
            }
        
        items[base_name]["folders"].append({
            "folder": folder.name,
            "state": state,
            "message": message,
        })
        
        # Update latest_state to the most recent folder
        if items[base_name]["latest_state"] is None:
            items[base_name]["latest_state"] = state
        else:
            # Compare timestamps if available
            current_ts = state.get("last_updated", "")
            latest_ts = items[base_name]["latest_state"].get("last_updated", "")
            if current_ts > latest_ts:
                items[base_name]["latest_state"] = state
    
    return items


@app.post("/twilio")
async def twilio_webhook(request: Request):
    """Twilio webhook endpoint - receives inbound SMS and processes with full message pipeline"""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "").strip()

    # Load + lookup lead
    leads = load_leads()
    contact = lookup_contact_by_phone(leads, from_number)

    if contact is None:
        msg = (
            "Hey — this is rt4orgs.\n\n"
            "We couldn't match your number to any chapter contact. "
            "Reply with your name + fraternity if that's wrong."
        )
        return Response(content=twiml(append_link(msg)), media_type="application/xml")

    # Load previous state
    prev_state = load_latest_event_state(contact.get("name", ""))

    # fraternity example
    sales = load_sales_history()
    purchased_example = find_matching_fraternity(contact, sales)

    # 1) classify
    inbound = handle_inbound(
        contact=contact,
        incoming_text=body,
        prev_state=prev_state,
        purchased_example=purchased_example,
    )

    # 2) Markov state transition
    markov_result = markov.update_state(
        contact=contact,
        message=body,
        intent=inbound["intent"],
        purchased_example=purchased_example,
        history=inbound.get("history"),
    )

    # 3) Generate response **BY NEXT_STATE ONLY**
    reply_text = generate_message(
        contact=contact,
        purchased_example=purchased_example,
        intent=markov_result.get("intent"),
        next_state=markov_result.get("next_state"),
    )

    return Response(content=twiml(append_link(reply_text)), media_type="application/xml")


@app.post("/sms")
async def sms_webhook_legacy(request: Request):
    """Legacy Flask-compatible endpoint"""
    return await twilio_webhook(request)


@app.get("/all")
def get_all():
    """Get all leads organized by contact name"""
    return load_all()


@app.get("/lead/{name}")
def get_lead(name: str):
    """Get a specific lead by name"""
    all_items = load_all()
    lead = all_items.get(name)
    if not lead:
        return {"error": "not_found"}
    return lead


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("twilio_server:app", host="0.0.0.0", port=8000, reload=True)
