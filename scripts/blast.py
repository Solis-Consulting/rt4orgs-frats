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


def send_sms(to_number: str, body: str, auth_token: Optional[str] = None, account_sid: Optional[str] = None, rep_phone_number: Optional[str] = None) -> Dict[str, Any]:
    """
    Send SMS via Twilio with comprehensive logging.
    
    Args:
        to_number: Recipient phone number
        body: Message body
        auth_token: Optional Twilio auth token (overrides TWILIO_AUTH_TOKEN env var)
    
    Returns:
        Dict with sid, status, and detailed response info
    """
    import traceback
    
    print("=" * 80)
    print(f"[SEND_SMS] 🚀 STARTING SMS SEND")
    print("=" * 80)
    print(f"[SEND_SMS] To: {to_number}")
    print(f"[SEND_SMS] Body length: {len(body)} chars")
    print(f"[SEND_SMS] Body preview: {body[:100]}...")
    
    # Use provided auth_token or fall back to environment variable
    if auth_token and auth_token.strip():
        token_to_use = auth_token.strip()
        token_source = "PROVIDED"
        if TWILIO_AUTH_TOKEN and token_to_use != TWILIO_AUTH_TOKEN:
            print(f"[SEND_SMS] ✅ Using PROVIDED auth token (DIFFERENT from env var)")
            print(f"[SEND_SMS]   Provided: {token_to_use[:15]}... (length: {len(token_to_use)})")
            print(f"[SEND_SMS]   Env var:  {TWILIO_AUTH_TOKEN[:15]}... (length: {len(TWILIO_AUTH_TOKEN)})")
        else:
            print(f"[SEND_SMS] ✅ Using PROVIDED auth token (same as env var)")
            print(f"[SEND_SMS]   Token: {token_to_use[:15]}... (length: {len(token_to_use)})")
    else:
        token_to_use = TWILIO_AUTH_TOKEN
        token_source = "ENV_VAR"
        if not token_to_use:
            print(f"[SEND_SMS] ❌ ERROR: No auth token provided and TWILIO_AUTH_TOKEN not set")
            raise ValueError("Twilio auth token not provided and TWILIO_AUTH_TOKEN not set")
        else:
            print(f"[SEND_SMS] ⚠️ Using environment variable TWILIO_AUTH_TOKEN")
            print(f"[SEND_SMS]   Token: {token_to_use[:15]}... (length: {len(token_to_use)})")
    
    if not token_to_use:
        raise ValueError("Twilio auth token not provided and TWILIO_AUTH_TOKEN not set")
    
    # Validate phone number format
    if not to_number:
        raise ValueError("Phone number is empty")
    if not to_number.startswith('+'):
        print(f"[SEND_SMS] ⚠️ WARNING: Phone number doesn't start with +: {to_number}")
    
    # Determine which Account SID to use (provided or env var)
    sid_to_use = account_sid if account_sid else TWILIO_ACCOUNT_SID
    if account_sid:
        sid_source = "PROVIDED"
        # Validate Account SID format (must start with AC)
        if not account_sid.startswith('AC'):
            print(f"[SEND_SMS] ❌ ERROR: Invalid Account SID format: {account_sid[:20]}...")
            print(f"[SEND_SMS] Account SIDs must start with 'AC', but got '{account_sid[:2]}'")
            print(f"[SEND_SMS] This looks like a Phone Number SID (PN) or other SID type.")
            print(f"[SEND_SMS] Please use the Account SID (starts with AC) for authentication.")
            raise ValueError(f"Invalid Account SID format: Account SIDs must start with 'AC', but got '{account_sid[:2]}...' (this looks like a {account_sid[:2]} SID, not an Account SID)")
        print(f"[SEND_SMS] ✅ Using PROVIDED Account SID: {account_sid[:10]}... (length: {len(account_sid)})")
    else:
        sid_source = "ENV_VAR"
        if not TWILIO_ACCOUNT_SID:
            print(f"[SEND_SMS] ❌ ERROR: No account SID provided and TWILIO_ACCOUNT_SID not set")
            raise ValueError("Twilio account SID not provided and TWILIO_ACCOUNT_SID not set")
        else:
            # Validate env var Account SID format
            if not TWILIO_ACCOUNT_SID.startswith('AC'):
                print(f"[SEND_SMS] ❌ ERROR: Invalid Account SID in environment variable: {TWILIO_ACCOUNT_SID[:20]}...")
                print(f"[SEND_SMS] Account SIDs must start with 'AC'")
                raise ValueError(f"Invalid Account SID in environment: must start with 'AC'")
            print(f"[SEND_SMS] ⚠️ Using environment variable TWILIO_ACCOUNT_SID")
    
    # Log which account and token are being used
    account_sid_preview = sid_to_use[:10] + "..." if sid_to_use and len(sid_to_use) > 10 else str(sid_to_use)
    print(f"[SEND_SMS] Account SID: {account_sid_preview}")
    print(f"[SEND_SMS] Account SID Source: {sid_source}")
    print(f"[SEND_SMS] Auth Token Source: {token_source}")
    print(f"[SEND_SMS] Messaging Service SID: {TWILIO_MESSAGING_SERVICE_SID or 'NOT SET'} (REQUIRED - from env var)")
    if rep_phone_number:
        print(f"[SEND_SMS] Rep Phone Number: {rep_phone_number} (should be added to Messaging Service in Twilio)")
    print(f"[SEND_SMS] Note: All messages use Messaging Service for traceability and A2P compliance")
    
    try:
        print(f"[SEND_SMS] Creating Twilio Client with Account SID: {sid_to_use[:10]}... and Token: {token_to_use[:15]}...")
        client = Client(sid_to_use, token_to_use)
        print(f"[SEND_SMS] ✅ Twilio Client created")
        
        # Prepare message parameters
        message_params = {
            "to": to_number,
            "body": body
        }
        
        # Always use Messaging Service for traceability and A2P compliance
        # The rep's phone number should be in the Messaging Service sender pool
        # Enable "Sticky Sender" in Twilio console to ensure same sender for each recipient
        if not TWILIO_MESSAGING_SERVICE_SID:
            error_msg = "TWILIO_MESSAGING_SERVICE_SID must be set in environment variables"
            print(f"[SEND_SMS] ❌ {error_msg}")
            raise ValueError(error_msg)
        
        # Use Messaging Service (rep's phone should be in sender pool, Sticky Sender enabled)
        message_params["messaging_service_sid"] = TWILIO_MESSAGING_SERVICE_SID
        print(f"[SEND_SMS] Using Messaging Service: {TWILIO_MESSAGING_SERVICE_SID}")
        print(f"[SEND_SMS] Using System Account SID: {sid_to_use[:10]}... (same for all reps)")
        if rep_phone_number:
            # Use both messaging_service_sid AND from for deterministic rep identity
            # This is the maximum-power configuration Twilio allows
            message_params["from"] = rep_phone_number
            print(f"[SEND_SMS] Rep Phone: {rep_phone_number} (must be attached to Messaging Service)")
            print(f"[SEND_SMS] Using MAXIMUM-POWER config: messaging_service_sid + from=rep_phone")
            print(f"[SEND_SMS] This ensures deterministic rep identity while maintaining compliance")
        else:
            print(f"[SEND_SMS] No rep phone provided - using Messaging Service only")
            print(f"[SEND_SMS] Note: Enable 'Sticky Sender' in Twilio Messaging Service settings")
        print(f"[SEND_SMS] All messages are traceable through Messaging Service logs")
        
        print(f"[SEND_SMS] Calling client.messages.create() with params:")
        print(f"[SEND_SMS]   to: {message_params.get('to')}")
        if 'from' in message_params:
            print(f"[SEND_SMS]   from: {message_params.get('from')}")
        print(f"[SEND_SMS]   messaging_service_sid: {message_params.get('messaging_service_sid')}")
        print(f"[SEND_SMS]   body length: {len(message_params.get('body', ''))}")
        
        # Make the API call
        msg = client.messages.create(**message_params)
        
        # Log comprehensive response details
        print("=" * 80)
        print(f"[SEND_SMS] ✅ TWILIO API CALL SUCCESSFUL")
        print("=" * 80)
        print(f"[SEND_SMS] Message SID: {msg.sid}")
        print(f"[SEND_SMS] Status: {msg.status}")
        print(f"[SEND_SMS] To: {msg.to}")
        print(f"[SEND_SMS] From: {msg.from_}")
        print(f"[SEND_SMS] Date Created: {msg.date_created}")
        print(f"[SEND_SMS] Date Sent: {msg.date_sent}")
        print(f"[SEND_SMS] Date Updated: {msg.date_updated}")
        print(f"[SEND_SMS] Error Code: {msg.error_code or 'None'}")
        print(f"[SEND_SMS] Error Message: {msg.error_message or 'None'}")
        print(f"[SEND_SMS] Price: {msg.price or 'None'}")
        print(f"[SEND_SMS] Price Unit: {msg.price_unit or 'None'}")
        print(f"[SEND_SMS] URI: {msg.uri or 'None'}")
        print(f"[SEND_SMS] Account SID Used: {msg.account_sid}")
        print(f"[SEND_SMS] Messaging Service SID: {getattr(msg, 'messaging_service_sid', 'N/A')}")
        print("=" * 80)
        
        # Check for error status
        if msg.status in ['failed', 'undelivered']:
            print(f"[SEND_SMS] ⚠️ WARNING: Message status is '{msg.status}'")
            print(f"[SEND_SMS] Error Code: {msg.error_code}")
            print(f"[SEND_SMS] Error Message: {msg.error_message}")
        
        return {
            "sid": msg.sid,
            "status": msg.status,
            "to": msg.to,
            "from": msg.from_,
            "date_created": str(msg.date_created) if msg.date_created else None,
            "date_sent": str(msg.date_sent) if msg.date_sent else None,
            "error_code": msg.error_code,
            "error_message": msg.error_message,
            "price": str(msg.price) if msg.price else None,
            "price_unit": msg.price_unit,
        }
        
    except Exception as e:
        print("=" * 80)
        print(f"[SEND_SMS] ❌ TWILIO API CALL FAILED")
        print("=" * 80)
        print(f"[SEND_SMS] Error Type: {type(e).__name__}")
        print(f"[SEND_SMS] Error Message: {str(e)}")
        print(f"[SEND_SMS] Traceback:")
        traceback.print_exc()
        print("=" * 80)
        raise


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
