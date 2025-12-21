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
from intelligence.utils import normalize_phone
from archive_intelligence.message_processor.generate_message import generate_message

# ALWAYS use environment variables - no config file fallbacks
# This ensures Railway deployment uses the correct variables
import os

BASE_DIR = ARCHIVE_DIR
TEMPLATE_PATH = BASE_DIR / "templates" / "messages.txt"
# Contacts directory is in backend/, not archive_intelligence/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTACTS_DIR = PROJECT_ROOT / "backend" / "contacts"

# 🔥 CRITICAL: Only normalize phone if Messaging Service is NOT configured
# If Messaging Service is set, phone number handling is completely disabled
_MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "")
_RAW_TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER", "")

if _MESSAGING_SERVICE_SID:
    # Messaging Service mode: Phone number normalization is NOT needed
    TWILIO_PHONE_E164 = ""
    print(f"[BLAST_MODULE] ✅ Messaging Service configured - phone number handling disabled", flush=True)
elif _RAW_TWILIO_PHONE:
    # Direct mode: Normalize phone to E.164 format
    TWILIO_PHONE_E164 = normalize_phone(_RAW_TWILIO_PHONE)
    # Validate normalized phone at module load
    if TWILIO_PHONE_E164 and not TWILIO_PHONE_E164.startswith("+"):
        raise RuntimeError(f"Invalid TWILIO_PHONE_NUMBER after normalization: {_RAW_TWILIO_PHONE} → {TWILIO_PHONE_E164} (must be E.164 format with + prefix)")
    # Log normalization result (one-time at module load)
    if _RAW_TWILIO_PHONE != TWILIO_PHONE_E164:
        print(f"[BLAST_MODULE] 📞 Normalized TWILIO_PHONE_NUMBER: {_RAW_TWILIO_PHONE} → {TWILIO_PHONE_E164}", flush=True)
    else:
        print(f"[BLAST_MODULE] 📞 TWILIO_PHONE_NUMBER already in E.164: {TWILIO_PHONE_E164}", flush=True)
else:
    TWILIO_PHONE_E164 = ""


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


def send_sms(to_number: str, body: str, force_direct: bool = False) -> Dict[str, Any]:
    """
    Send SMS via Twilio with comprehensive logging.
    Always uses system Twilio credentials from environment variables.
    
    Routing logic:
    - If TWILIO_MESSAGING_SERVICE_SID is set: Use Messaging Service (includes campaign/brand metadata)
    - Otherwise: Use direct phone number (TWILIO_PHONE_NUMBER)
    
    This ensures carriers see approved traffic with proper campaign context when available.
    
    Args:
        to_number: Recipient phone number
        body: Message body
        force_direct: DEPRECATED - ignored. Routing is determined by env vars.
    
    Returns:
        Dict with sid, status, and detailed response info
    
    Raises:
        RuntimeError: If message is sent with no sender (from_ is None)
    """
    import traceback
    import os
    from datetime import datetime
    
    print("=" * 80, flush=True)
    print(f"[SEND_SMS] 🚀 STARTING SMS SEND", flush=True)
    print("=" * 80, flush=True)
    print(f"[SEND_SMS] To: {to_number}", flush=True)
    print(f"[SEND_SMS] Body length: {len(body)} chars", flush=True)
    print(f"[SEND_SMS] Body preview: {body[:100]}...", flush=True)
    # Note: force_direct parameter is deprecated - routing determined by env vars
    
    # ALWAYS use environment variables - no parameters
    token_to_use = os.getenv("TWILIO_AUTH_TOKEN")
    sid_to_use = os.getenv("TWILIO_ACCOUNT_SID")
    messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
    
    # 🔥 CRITICAL: Determine mode FIRST - phone handling only happens in direct mode
    use_messaging_service = bool(messaging_service_sid)
    
    # ONLY access phone if Messaging Service is NOT configured
    phone_number_normalized = TWILIO_PHONE_E164 if not use_messaging_service else None
    
    # Validate immediately - fail fast with clear errors
    if not token_to_use:
        error_msg = "TWILIO_AUTH_TOKEN not set in environment variables"
        print(f"[SEND_SMS] ❌ ERROR: {error_msg}", flush=True)
        raise ValueError(error_msg)
    
    if not sid_to_use:
        error_msg = "TWILIO_ACCOUNT_SID not set in environment variables"
        print(f"[SEND_SMS] ❌ ERROR: {error_msg}", flush=True)
        raise ValueError(error_msg)
    
    # 🔒 ROUTING LOGIC: Use Messaging Service if available (has campaign/brand metadata)
    # Otherwise fall back to direct phone number
    # CRITICAL: These paths are MUTUALLY EXCLUSIVE - phone handling ONLY in direct mode
    if use_messaging_service:
        print(f"[SEND_SMS] ✅ Using Messaging Service (campaign metadata attached, NO from_ parameter)", flush=True)
        print(f"[SEND_SMS] Messaging Service SID: {messaging_service_sid[:10]}...{messaging_service_sid[-4:]} (length: {len(messaging_service_sid)})", flush=True)
        send_mode = "MESSAGING_SERVICE"
        # CRITICAL: Do NOT validate or access phone number when using Messaging Service
    else:
        print(f"[SEND_SMS] ✅ Using direct phone number (no Messaging Service configured)", flush=True)
        if not phone_number_normalized:
            error_msg = "TWILIO_PHONE_NUMBER not set in environment variables (REQUIRED when Messaging Service not available)"
            print(f"[SEND_SMS] ❌ ERROR: {error_msg}", flush=True)
            raise ValueError(error_msg)
        
        # Validate E.164 format
        if not phone_number_normalized.startswith("+"):
            error_msg = f"TWILIO_PHONE_NUMBER must be in E.164 format (got: {phone_number_normalized})"
            print(f"[SEND_SMS] ❌ ERROR: {error_msg}", flush=True)
            raise ValueError(error_msg)
        send_mode = "DIRECT_NUMBER"
    
    # Validate Account SID format
    if not sid_to_use.startswith('AC'):
        error_msg = f"Invalid Account SID format: must start with 'AC', got '{sid_to_use[:2]}...'"
        print(f"[SEND_SMS] ❌ ERROR: {error_msg}", flush=True)
        raise ValueError(error_msg)
    
    # Validate phone number format
    if not to_number:
        raise ValueError("Phone number is empty")
    if not to_number.startswith('+'):
        print(f"[SEND_SMS] ⚠️ WARNING: Phone number doesn't start with +: {to_number}", flush=True)
    
    print(f"[SEND_SMS] ✅ Using system Twilio credentials from environment variables", flush=True)
    print(f"[SEND_SMS] Account SID: {sid_to_use[:10]}...{sid_to_use[-4:]} (length: {len(sid_to_use)})", flush=True)
    print(f"[SEND_SMS] Auth Token: {token_to_use[:10]}...{token_to_use[-4:]} (length: {len(token_to_use)})", flush=True)
    print(f"[SEND_SMS] 📡 Send Mode: {send_mode}", flush=True)
    # CRITICAL: Only log phone-related info in direct mode
    if use_messaging_service:
        print(f"[SEND_SMS] Messaging Service SID: {messaging_service_sid[:10]}...{messaging_service_sid[-4:]} (length: {len(messaging_service_sid)})", flush=True)
        print(f"[SEND_SMS] ⚠️ Phone number handling DISABLED (Messaging Service mode)", flush=True)
    else:
        print(f"[SEND_SMS] Phone Number (E.164 normalized): {phone_number_normalized}", flush=True)
        print(f"[SEND_SMS] ✅ Using direct phone number (from_={phone_number_normalized})", flush=True)
    
    try:
        print(f"[SEND_SMS] Creating Twilio Client with Account SID: {sid_to_use[:10]}... and Token: {token_to_use[:15]}...", flush=True)
        client = Client(sid_to_use, token_to_use)
        print(f"[SEND_SMS] ✅ Twilio Client created")
        
        # 🔒 PREPARE MESSAGE PARAMETERS: Explicit branching - no ambiguity
        # CRITICAL: Never mix both - Twilio will reject if both are set
        # Use Messaging Service if available (preserves campaign/brand metadata for carriers)
        # Otherwise fall back to direct phone number
        if use_messaging_service:
            # Messaging Service mode: Includes campaign/brand metadata for carrier approval
            message_params = {
                "to": to_number,
                "body": body,
                "messaging_service_sid": messaging_service_sid
            }
            # CRITICAL: Do NOT set from_ when using Messaging Service
            assert "from_" not in message_params, "Cannot use from_ with Messaging Service"
        else:
            # Direct mode: Use from_ phone number (fallback when Messaging Service not configured)
            # 🔥 CRITICAL: Use normalized E.164 format (Twilio requires + prefix)
            message_params = {
                "to": to_number,
                "body": body,
                "from_": phone_number_normalized
            }
            # CRITICAL: Do NOT set messaging_service_sid when using direct phone
            assert "messaging_service_sid" not in message_params, "Cannot use messaging_service_sid with direct phone"
        
        # ENHANCED LOGGING: Log all parameters being sent to Twilio
        print("=" * 80, flush=True)
        print(f"[SEND_SMS] 📤 PREPARING TWILIO API CALL", flush=True)
        print("=" * 80, flush=True)
        print(f"[SEND_SMS] Account SID: {sid_to_use[:10]}...{sid_to_use[-4:]} (length: {len(sid_to_use)})", flush=True)
        print(f"[SEND_SMS] Auth Token: {token_to_use[:10]}...{token_to_use[-4:]} (length: {len(token_to_use)})", flush=True)
        print(f"[SEND_SMS] Send Mode: {send_mode}", flush=True)
        print("=" * 80, flush=True)
        print(f"[SEND_SMS] 📋 EXACT PARAMETERS BEING SENT TO TWILIO:", flush=True)
        if use_messaging_service:
            print(f"[SEND_SMS]   messaging_service_sid: {messaging_service_sid[:10]}...{messaging_service_sid[-4:]}", flush=True)
            print(f"[SEND_SMS]   from_: NOT SET (using Messaging Service)", flush=True)
        else:
            print(f"[SEND_SMS]   from_: {phone_number_normalized} (E.164 normalized)", flush=True)
            print(f"[SEND_SMS]   messaging_service_sid: NOT SET (using direct phone number)", flush=True)
        print(f"[SEND_SMS]   to: {message_params.get('to')}", flush=True)
        print(f"[SEND_SMS]   body: {message_params.get('body', '')[:100]}{'...' if len(message_params.get('body', '')) > 100 else ''}", flush=True)
        print(f"[SEND_SMS]   body length: {len(message_params.get('body', ''))} chars", flush=True)
        print("=" * 80, flush=True)
        
        # Make the API call
        print(f"[SEND_SMS] 🚀 Calling client.messages.create() NOW...", flush=True)
        print(f"[SEND_SMS] Request timestamp: {datetime.now().isoformat()}", flush=True)
        
        # 🔥 CRITICAL DEBUG: Log before Twilio API call
        print("=" * 80, flush=True)
        print(f"📤 [TWILIO_SEND] SEND ATTEMPT → to={to_number} from={message_params.get('from_', 'N/A')} body_len={len(body) if body else 'NONE'}", flush=True)
        print("=" * 80, flush=True)
        
        try:
            msg = client.messages.create(**message_params)
            print(f"[SEND_SMS] ✅ API call completed successfully", flush=True)
            
            # 🔥 CRITICAL DEBUG: Log after successful Twilio API call
            print("=" * 80, flush=True)
            print(f"✅ [TWILIO_SEND] SENT SID={msg.sid}", flush=True)
            print("=" * 80, flush=True)
        except Exception as api_error:
            print("=" * 80, flush=True)
            print(f"[SEND_SMS] ❌ TWILIO API CALL EXCEPTION", flush=True)
            print("=" * 80, flush=True)
            print(f"[SEND_SMS] Exception type: {type(api_error).__name__}", flush=True)
            print(f"[SEND_SMS] Exception message: {str(api_error)}", flush=True)
            print(f"[SEND_SMS] Full exception details:", flush=True)
            import traceback
            traceback.print_exc()
            print("=" * 80, flush=True)
            raise
        
        print(f"[SEND_SMS] ✅ API call completed, processing response...", flush=True)
        
        # 🔒 CRITICAL RUNTIME ASSERTION: Fail loud if message has no sender
        # This prevents silent "ghost messages" that are accepted but never sent
        if msg.from_ is None:
            error_msg = (
                f"FATAL: SMS sent with no sender. Message will never deliver.\n"
                f"Message SID: {msg.sid}\n"
                f"Status: {msg.status}\n"
                f"Send Mode Used: {send_mode}\n"
                f"This indicates the Messaging Service has no valid sender, or direct from_ was not set."
            )
            print("=" * 80, flush=True)
            print(f"[SEND_SMS] ❌❌❌ FATAL ERROR ❌❌❌", flush=True)
            print("=" * 80, flush=True)
            print(f"[SEND_SMS] {error_msg}", flush=True)
            print("=" * 80, flush=True)
            raise RuntimeError(error_msg)
        
        # ENHANCED LOGGING: Log comprehensive response details
        print("=" * 80, flush=True)
        print(f"[SEND_SMS] ✅ TWILIO API RESPONSE RECEIVED", flush=True)
        print("=" * 80, flush=True)
        print(f"[SEND_SMS] Response timestamp: {datetime.now().isoformat()}", flush=True)
        print(f"[SEND_SMS] Message SID: {msg.sid}", flush=True)
        print(f"[SEND_SMS] Status: {msg.status} {'⚠️' if msg.status in ['failed', 'undelivered'] else '✅' if msg.status in ['sent', 'delivered', 'queued', 'accepted'] else ''}", flush=True)
        print(f"[SEND_SMS] To: {msg.to}", flush=True)
        print(f"[SEND_SMS] From (actual sender): {msg.from_}", flush=True)
        print(f"[SEND_SMS] Account SID Used: {msg.account_sid}", flush=True)
        actual_messaging_service = getattr(msg, 'messaging_service_sid', None)
        print(f"[SEND_SMS] Messaging Service SID: {actual_messaging_service or 'None'}", flush=True)
        print(f"[SEND_SMS] 🔒 Send Mode Used: {send_mode}", flush=True)
        
        # Validate send mode matches expectations
        if use_messaging_service and not actual_messaging_service:
            print(f"[SEND_SMS] ⚠️⚠️⚠️ WARNING: Expected Messaging Service but response shows None - check Twilio configuration!", flush=True)
        elif not use_messaging_service and actual_messaging_service:
            print(f"[SEND_SMS] ⚠️⚠️⚠️ WARNING: Used direct phone but response shows Messaging Service - unexpected!", flush=True)
        
        # CRITICAL: Validate that message actually has a sender (should never be None after assertion above)
        if msg.from_ is None:
            print(f"[SEND_SMS] ❌❌❌ FATAL: from_ is None (should have been caught by assertion)", flush=True)
        else:
            print(f"[SEND_SMS] ✅ Sender confirmed: {msg.from_}", flush=True)
        
        print(f"[SEND_SMS] Date Created: {msg.date_created}", flush=True)
        print(f"[SEND_SMS] Date Sent: {msg.date_sent or 'Not sent yet'}", flush=True)
        
        # Additional validation: date_sent should exist for real sends
        if not msg.date_sent and msg.status in ['sent', 'delivered']:
            print(f"[SEND_SMS] ⚠️ WARNING: Status is '{msg.status}' but date_sent is None - message may not have actually sent", flush=True)
        print(f"[SEND_SMS] Date Updated: {msg.date_updated}", flush=True)
        print(f"[SEND_SMS] Error Code: {msg.error_code or 'None (no error)'}", flush=True)
        print(f"[SEND_SMS] Error Message: {msg.error_message or 'None (no error)'}", flush=True)
        print(f"[SEND_SMS] Price: {msg.price or 'None'}", flush=True)
        print(f"[SEND_SMS] Price Unit: {msg.price_unit or 'None'}", flush=True)
        print(f"[SEND_SMS] URI: {msg.uri or 'None'}", flush=True)
        
        # Log ALL available attributes for debugging
        print(f"[SEND_SMS] All response attributes:", flush=True)
        for attr in dir(msg):
            if not attr.startswith('_'):
                try:
                    value = getattr(msg, attr)
                    if not callable(value):
                        print(f"[SEND_SMS]   {attr}: {value}", flush=True)
                except:
                    pass
        
        # Log all available attributes for debugging
        print(f"[SEND_SMS] All response attributes: {dir(msg)}")
        try:
            print(f"[SEND_SMS] Direction: {getattr(msg, 'direction', 'N/A')}")
            print(f"[SEND_SMS] Num Segments: {getattr(msg, 'num_segments', 'N/A')}")
            print(f"[SEND_SMS] Num Media: {getattr(msg, 'num_media', 'N/A')}")
        except:
            pass
        print("=" * 80)
        
        # Enhanced status checking with actionable warnings
        if msg.status in ['failed', 'undelivered']:
            print("=" * 80)
            print(f"[SEND_SMS] ⚠️⚠️⚠️ MESSAGE DELIVERY FAILED ⚠️⚠️⚠️")
            print("=" * 80)
            print(f"[SEND_SMS] Status: {msg.status}")
            print(f"[SEND_SMS] Error Code: {msg.error_code}")
            print(f"[SEND_SMS] Error Message: {msg.error_message}")
            print(f"[SEND_SMS] This message was NOT delivered to the recipient.")
            print(f"[SEND_SMS] Check Twilio Console for more details: https://console.twilio.com/")
            print("=" * 80)
        elif msg.status in ['queued', 'accepted']:
            print(f"[SEND_SMS] ℹ️ Message accepted by Twilio, status: {msg.status}")
            print(f"[SEND_SMS] Message is queued for delivery. Check status later.")
        elif msg.status in ['sent', 'delivered']:
            print(f"[SEND_SMS] ✅ Message successfully {msg.status}")
        else:
            print(f"[SEND_SMS] ℹ️ Message status: {msg.status} (unusual status, monitor)")
        
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
