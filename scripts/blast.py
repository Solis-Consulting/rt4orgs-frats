#!/usr/bin/env python3
from __future__ import annotations

import time
import random
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from twilio.rest import Client
import requests

import sys

# #region agent log - Module load verification
_log_file = Path(__file__).resolve().parent.parent / ".cursor" / "debug.log"
def _debug_log(location, message, data=None, hypothesis_id=None):
    try:
        import json as _json
        from datetime import datetime
        payload = {
            "sessionId": "debug-session",
            "runId": "run1",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "hypothesisId": hypothesis_id
        }
        with open(_log_file, "a") as f:
            f.write(_json.dumps(payload) + "\n")
    except:
        pass

_debug_log(f"{__file__}:MODULE_LOAD", "🔥🔥🔥 NEW BLAST LOGIC LOADED 🔥🔥🔥", {"file": str(__file__), "resolved": str(Path(__file__).resolve())}, "C")
# #endregion

# Add archive_intelligence to path for imports
ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "archive_intelligence"
sys.path.insert(0, str(ARCHIVE_DIR))

from archive_intelligence.message_processor.utils import (
    load_leads,
    save_leads,
    load_sales_history,
    make_contact_event_folder,
    timestamp,
    ensure_parent_dir,
    save_json,
)
from archive_intelligence.message_processor.generate_message import generate_message

# Try to import config from multiple possible locations
try:
    from config import (
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
        TWILIO_PHONE_NUMBER,
        TWILIO_MESSAGING_SERVICE_SID,
    )
except ImportError:
    # Fallback: try importing from backend or root via env vars
    import os
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
    TWILIO_MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SERVICE_SID")

BASE_DIR = ARCHIVE_DIR
TEMPLATE_PATH = BASE_DIR / "templates" / "messages.txt"
# Contacts directory is in backend/, not archive_intelligence/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTACTS_DIR = PROJECT_ROOT / "backend" / "contacts"


def _contact_has_been_blasted(contact_name: str) -> bool:
    """
    Check if a contact has already received an outbound SMS blast.
    Only considers contacts 'blasted' if they have a state.json file
    with next_state == "initial_outreach" (indicating outbound was sent).
    """
    # #region agent log - Function entry
    _debug_log(f"{__file__}:47:ENTRY", "CHECKING BLAST STATE FOR", {"contact_name": contact_name, "contacts_dir": str(CONTACTS_DIR)}, "D")
    # #endregion
    
    # #region agent log - Directory check
    dir_exists = CONTACTS_DIR.exists()
    _debug_log(f"{__file__}:53:DIR_CHECK", "CONTACTS_DIR exists check", {"path": str(CONTACTS_DIR), "exists": dir_exists}, "D")
    # #endregion
    
    if not dir_exists:
        # #region agent log - Early return
        _debug_log(f"{__file__}:54:RETURN", "Returning False (dir not exists)", {"contact_name": contact_name}, "D")
        # #endregion
        return False

    prefix = contact_name.replace(" ", "_")
    # #region agent log - Before iteration
    _debug_log(f"{__file__}:57:PREFIX", "Contact prefix generated", {"contact_name": contact_name, "prefix": prefix}, "D")
    # #endregion
    
    folders_found = []
    for folder in CONTACTS_DIR.iterdir():
        if folder.is_dir() and folder.name.startswith(prefix):
            folders_found.append(str(folder))
            # #region agent log - Folder match
            _debug_log(f"{__file__}:58:FOLDER_MATCH", "Found matching folder", {"folder": folder.name, "prefix": prefix}, "B")
            # #endregion
            
            # Check if this folder has a state.json indicating outbound was sent
            state_file = folder / "state.json"
            state_file_exists = state_file.exists()
            
            # #region agent log - State file check
            _debug_log(f"{__file__}:60:STATE_FILE", "Checking state.json", {"folder": folder.name, "state_file_exists": state_file_exists}, "B")
            # #endregion
            
            if state_file_exists:
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    
                    # #region agent log - State content
                    next_state = state.get("next_state")
                    _debug_log(f"{__file__}:67:STATE_CONTENT", "Read state.json", {"folder": folder.name, "next_state": next_state, "full_state": state}, "B")
                    # #endregion
                    
                    # Only mark as blasted if it's an outbound event (initial_outreach)
                    if next_state == "initial_outreach":
                        # #region agent log - Blasted confirmed
                        _debug_log(f"{__file__}:70:RETURN", "Returning True (blasted)", {"contact_name": contact_name, "folder": folder.name, "next_state": next_state}, "B")
                        # #endregion
                        return True
                except (json.JSONDecodeError, IOError) as e:
                    # #region agent log - State read error
                    _debug_log(f"{__file__}:73:ERROR", "Error reading state.json", {"folder": folder.name, "error": str(e)}, "B")
                    # #endregion
                    # If we can't read the state file, skip this folder
                    continue
    
    # #region agent log - Final return
    _debug_log(f"{__file__}:77:RETURN", "Returning False (not blasted)", {"contact_name": contact_name, "folders_checked": folders_found}, "B")
    # #endregion
    return False


def find_unblasted_contacts(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # #region agent log - Find unblasted entry
    _debug_log(f"{__file__}:58:FIND_UNBLASTED_ENTRY", "find_unblasted_contacts called", {"leads_count": len(leads)}, "D")
    # #endregion
    
    unblasted = []
    for c in leads:
        contact_name = c.get("name", "")
        is_blasted = _contact_has_been_blasted(contact_name)
        # #region agent log - Contact check result
        _debug_log(f"{__file__}:65:CONTACT_CHECK", "Contact blast status", {"contact_name": contact_name, "is_blasted": is_blasted}, "D")
        # #endregion
        if not is_blasted:
            unblasted.append(c)
    
    # #region agent log - Find unblasted result
    _debug_log(f"{__file__}:70:FIND_UNBLASTED_RESULT", "find_unblasted_contacts result", {"total_leads": len(leads), "unblasted_count": len(unblasted)}, "D")
    # #endregion
    return unblasted


def send_sms(to_number: str, body: str, auth_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Send SMS via Twilio.
    
    Args:
        to_number: Recipient phone number
        body: Message body
        auth_token: Optional Twilio auth token (overrides TWILIO_AUTH_TOKEN env var)
    """
    # Use provided auth_token or fall back to environment variable
    # Only use auth_token if it's a non-empty string
    if auth_token and auth_token.strip():
        token_to_use = auth_token.strip()
        env_token_preview = (TWILIO_AUTH_TOKEN[:10] + "..." if TWILIO_AUTH_TOKEN and len(TWILIO_AUTH_TOKEN) > 10 else "not set") if TWILIO_AUTH_TOKEN else "not set"
        print(f"[SEND_SMS] ✅ Using PROVIDED auth token: {token_to_use[:10]}... (env var: {env_token_preview})")
    else:
        token_to_use = TWILIO_AUTH_TOKEN
        print(f"[SEND_SMS] ⚠️ Using environment variable TWILIO_AUTH_TOKEN (no token provided)")
    
    if not token_to_use:
        raise ValueError("Twilio auth token not provided and TWILIO_AUTH_TOKEN not set")
    
    client = Client(TWILIO_ACCOUNT_SID, token_to_use)
    if TWILIO_MESSAGING_SERVICE_SID:
        # Preferred: send via Messaging Service for A2P / compliance
        msg = client.messages.create(
            to=to_number,
            messaging_service_sid=TWILIO_MESSAGING_SERVICE_SID,
            body=body,
        )
    elif TWILIO_PHONE_NUMBER:
        # Fallback: direct From number if configured
        msg = client.messages.create(
            to=to_number,
            from_=TWILIO_PHONE_NUMBER,
            body=body,
        )
    else:
        raise ValueError(
            "Twilio configuration error: set TWILIO_MESSAGING_SERVICE_SID or TWILIO_PHONE_NUMBER"
        )
    return {"sid": msg.sid, "status": msg.status}


def write_initial_state(folder: Path, contact: Dict[str, Any], purchased_example: Dict[str, Any]):
    state_path = folder / "state.json"
    data = {
        "previous_state": None,
        "next_state": "initial_outreach",
        "intent": None,
        "message": None,
        "last_updated": timestamp(),
        "contact": contact,
        "purchased_example": purchased_example,
    }
    save_json(state_path, data)


def write_initial_message(folder: Path, message: str):
    msg_path = folder / "message.txt"
    ensure_parent_dir(msg_path)
    with msg_path.open("w", encoding="utf-8") as f:
        f.write(message)


def run_blast(
    limit: int = None,
    auto_confirm: bool = False,
    base_url: str = None,
    owner: str = "system",
    source_batch_id: str = None
) -> Dict[str, Any]:
    """
    Run outbound blast to unblasted contacts.
    
    Args:
        limit: Maximum number of messages to send (None = all)
        auto_confirm: If True, skip confirmation prompt (for API use)
        base_url: Base URL for /events/outbound endpoint (if None, skips API call)
        owner: Owner name for outbound events
        source_batch_id: Batch ID for tracking
    
    Returns:
        Dict with results: {
            "ok": bool,
            "sent": int,
            "skipped": int,
            "total_time": float,
            "messages_per_sec": float,
            "results": List[Dict]  # Individual message results
        }
    """
    if not auto_confirm:
        print("\n--- RT4ORGS OUTBOUND BLAST ENGINE ---\n")

    # #region agent log - Run blast entry
    _debug_log(f"{__file__}:RUN_BLAST_ENTRY", "run_blast function called", {"limit": limit, "auto_confirm": auto_confirm, "base_url": base_url}, "D")
    # #endregion
    
    leads = load_leads()
    # #region agent log - Leads loaded
    _debug_log(f"{__file__}:LEADS_LOADED", "Leads loaded from file", {"leads_count": len(leads), "sample_names": [l.get("name") for l in leads[:3]] if leads else []}, "D")
    # #endregion
    
    sales_history = load_sales_history()
    # #region agent log - Before find_unblasted
    _debug_log(f"{__file__}:BEFORE_FIND", "About to call find_unblasted_contacts", {"leads_count": len(leads)}, "D")
    # #endregion

    unblasted = find_unblasted_contacts(leads)
    # #region agent log - After find_unblasted
    _debug_log(f"{__file__}:AFTER_FIND", "After find_unblasted_contacts", {"unblasted_count": len(unblasted)}, "D")
    # #endregion

    if not unblasted:
        msg = "All contacts have already been blasted."
        if not auto_confirm:
            print(msg + "\n")
        return {
            "ok": False,
            "error": msg,
            "sent": 0,
            "skipped": 0,
            "total_time": 0.0,
            "messages_per_sec": 0.0,
            "results": []
        }

    # Apply limit if specified
    if limit and limit > 0:
        unblasted = unblasted[:limit]

    if not auto_confirm:
        print("These contacts have NOT been blasted yet:\n")
        for i, c in enumerate(unblasted, 1):
            print(f"{i}. {c.get('name')} ({c.get('phone')}) – {c.get('fraternity')} {c.get('chapter')}")
        print("\nTotal:", len(unblasted))

        choice = input("\nBlast these contacts now? (y/n): ").strip().lower()
        if choice != "y":
            msg = "Aborting. No messages sent."
            print(msg + "\n")
            return {
                "ok": False,
                "error": msg,
                "sent": 0,
                "skipped": 0,
                "total_time": 0.0,
                "messages_per_sec": 0.0,
                "results": []
            }

    if not auto_confirm:
        print("\n--- SENDING MESSAGES ---\n")

    TARGET_MSGS_PER_MIN = 100
    BASE_DELAY = 60 / TARGET_MSGS_PER_MIN

    sent_count = 0
    skipped_count = 0
    start_time = time.time()
    results = []

    # Generate batch ID if not provided
    if not source_batch_id:
        from datetime import datetime
        source_batch_id = f"blast_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for contact in unblasted:
        # 🚨 SKIP CONTACTS WITH NO PHONE NUMBER
        phone = contact.get("phone")
        if not phone or phone in ["", None]:
            skipped_count += 1
            result = {
                "contact": contact.get("name"),
                "phone": phone,
                "status": "skipped",
                "reason": "missing phone number"
            }
            results.append(result)
            if not auto_confirm:
                print(f"Skipping {contact.get('name')} — missing phone number.\n")
            continue

        purchased_example = next(
            (
                row for row in sales_history
                if isinstance(row, dict)
                and row.get("fraternity") == contact.get("fraternity")
            ),
            None
        )

        message = generate_message(contact, purchased_example, TEMPLATE_PATH)

        try:
            if not auto_confirm:
                print(f"Sending to {contact.get('name')} ({phone}):")
            sms_result = send_sms(phone, message)
            
            if not auto_confirm:
                print(" → Twilio SID:", sms_result["sid"], "| Status:", sms_result["status"])

            # Post to /events/outbound if base_url provided
            if base_url:
                try:
                    outbound_url = f"{base_url.rstrip('/')}/events/outbound"
                    requests.post(
                        outbound_url,
                        json={
                            "phone": phone,
                            "contact_id": contact.get("contact_id"),
                            "owner": owner,
                            "source_batch_id": source_batch_id
                        },
                        timeout=5
                    )
                except Exception as e:
                    # Log but don't fail the blast
                    if not auto_confirm:
                        print(f"  Warning: Failed to post to {outbound_url}: {e}")

            folder = make_contact_event_folder(contact.get("name", "Unknown"))
            write_initial_state(folder, contact, purchased_example)
            write_initial_message(folder, message)

            save_leads(leads)

            result = {
                "contact": contact.get("name"),
                "phone": phone,
                "status": "sent",
                "twilio_sid": sms_result["sid"],
                "twilio_status": sms_result["status"]
            }
            results.append(result)
            sent_count += 1

            jitter = random.uniform(-0.05, 0.05)
            delay = max(0.15, BASE_DELAY + jitter)
            time.sleep(delay)

        except Exception as e:
            skipped_count += 1
            result = {
                "contact": contact.get("name"),
                "phone": phone,
                "status": "error",
                "error": str(e)
            }
            results.append(result)
            if not auto_confirm:
                print(f"  Error: {e}")

    total_time = time.time() - start_time
    messages_per_sec = sent_count / total_time if total_time > 0 else 0.0

    if not auto_confirm:
        print(f"\n--- BLAST COMPLETE ---")
        print(f"Sent: {sent_count} messages in {total_time:.1f} seconds "
              f"({messages_per_sec:.1f} msg/sec)\n")

    return {
        "ok": True,
        "sent": sent_count,
        "skipped": skipped_count,
        "total_time": round(total_time, 2),
        "messages_per_sec": round(messages_per_sec, 2),
        "results": results
    }


if __name__ == "__main__":
    run_blast()
