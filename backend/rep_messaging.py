"""
Rep messaging system.
Handles sending messages from rep phone numbers and managing rep conversations.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import os
import psycopg2
from twilio.rest import Client

from backend.auth import get_user
from backend.cards import get_card


def send_rep_message(
    conn: Any,
    user_id: str,
    card_id: str,
    message: str,
) -> Dict[str, Any]:
    """
    Send SMS from system phone number to the card's phone number.
    Returns dict with result including twilio_sid.
    """
    # Get rep user info
    user = get_user(conn, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    # Get card to find phone number
    card = get_card(conn, card_id)
    if not card:
        raise ValueError(f"Card {card_id} not found")
    
    phone = card.get("card_data", {}).get("phone")
    if not phone:
        raise ValueError(f"Card {card_id} does not have a phone number")
    
    # Get Twilio credentials (use rep-specific or fall back to system)
    account_sid = user.get("twilio_account_sid")
    auth_token = user.get("twilio_auth_token")
    
    if not account_sid or not auth_token:
        # Fall back to system Twilio credentials
        import os
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials not configured for user or system")
    
    # Send SMS via Twilio with comprehensive logging
    import traceback
    
    print("=" * 80)
    print(f"[REP_MESSAGE] 🚀 SENDING REP MESSAGE")
    print("=" * 80)
    print(f"[REP_MESSAGE] Rep User ID: {user_id}")
    print(f"[REP_MESSAGE] Rep Username: {user.get('username')}")
    print(f"[REP_MESSAGE] Card ID: {card_id}")
    print(f"[REP_MESSAGE] To Phone: {phone}")
    print(f"[REP_MESSAGE] Message length: {len(message)} chars")
    print(f"[REP_MESSAGE] Using System Phone Number (via Messaging Service)")
    print(f"[REP_MESSAGE] Account SID: {account_sid[:10]}... (length: {len(account_sid)})" if account_sid else "[REP_MESSAGE] Account SID: None")
    print(f"[REP_MESSAGE] Auth Token: {auth_token[:15]}... (length: {len(auth_token)})" if auth_token else "[REP_MESSAGE] Auth Token: None")
    
    try:
        print(f"[REP_MESSAGE] Creating Twilio Client...")
        client = Client(account_sid, auth_token)
        print(f"[REP_MESSAGE] ✅ Twilio Client created")
        
        # 🔒 ENFORCE: Messaging Service takes precedence if set
        messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
        phone_number = os.getenv("TWILIO_PHONE_NUMBER")  # Fallback if Messaging Service not set
        
        use_messaging_service = bool(messaging_service_sid)
        
        if use_messaging_service:
            print(f"[REP_MESSAGE] ✅ TWILIO_MESSAGING_SERVICE_SID is set - using Messaging Service mode")
            if not phone_number:
                print(f"[REP_MESSAGE] ⚠️ TWILIO_PHONE_NUMBER not set (not required for Messaging Service)")
        else:
            if not phone_number:
                error_msg = "TWILIO_PHONE_NUMBER must be set in environment variables (required when Messaging Service not set)"
                print(f"[REP_MESSAGE] ❌ {error_msg}")
                raise ValueError(error_msg)
        
        # ENHANCED LOGGING: Log all parameters being sent to Twilio
        print("=" * 80)
        print(f"[REP_MESSAGE] 📤 PREPARING TWILIO API CALL")
        print("=" * 80)
        print(f"[REP_MESSAGE] Account SID: {account_sid[:10]}...{account_sid[-4:] if len(account_sid) > 14 else account_sid} (full length: {len(account_sid)})")
        print(f"[REP_MESSAGE] Auth Token: {auth_token[:10]}...{auth_token[-4:] if len(auth_token) > 14 else auth_token} (full length: {len(auth_token)})")
        print(f"[REP_MESSAGE] Phone Number: {phone_number}")
        # 🔒 ENFORCE: Messaging Service takes precedence if set
        messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
        use_messaging_service = bool(messaging_service_sid)
        send_mode = "MESSAGING_SERVICE" if use_messaging_service else "DIRECT_NUMBER"
        
        print(f"[REP_MESSAGE] 📡 Send Mode: {send_mode}")
        if use_messaging_service:
            print(f"[REP_MESSAGE] Using Messaging Service (TWILIO_MESSAGING_SERVICE_SID is set)")
        else:
            print(f"[REP_MESSAGE] Sending directly from phone number (Messaging Service not configured)")
        print(f"[REP_MESSAGE] Rep isolation maintained via card_assignments table")
        print("=" * 80)
        print(f"[REP_MESSAGE] 📋 EXACT PARAMETERS BEING SENT TO TWILIO:")
        if use_messaging_service:
            print(f"[REP_MESSAGE]   messaging_service_sid: {messaging_service_sid[:10]}...{messaging_service_sid[-4:]}")
            print(f"[REP_MESSAGE]   from_: NOT SET (using Messaging Service)")
        else:
            print(f"[REP_MESSAGE]   from_: {phone_number}")
            print(f"[REP_MESSAGE]   messaging_service_sid: NOT SET (using direct phone number)")
        print(f"[REP_MESSAGE]   to: {phone}")
        print(f"[REP_MESSAGE]   body: {message[:100]}{'...' if len(message) > 100 else ''}")
        print(f"[REP_MESSAGE]   body length: {len(message)} chars")
        print("=" * 80)
        
        # 🔒 PREPARE MESSAGE PARAMETERS: Use Messaging Service if available
        message_params = {
            "to": phone,
            "body": message
        }
        
        if use_messaging_service:
            message_params["messaging_service_sid"] = messaging_service_sid
            # CRITICAL: Do NOT set from_ when using Messaging Service
            assert "from_" not in message_params, "Cannot use from_ with Messaging Service"
        else:
            message_params["from_"] = phone_number
            # CRITICAL: Do NOT set messaging_service_sid when using direct phone
            assert "messaging_service_sid" not in message_params, "Cannot use messaging_service_sid with direct phone"
        
        print(f"[REP_MESSAGE] 🚀 Calling client.messages.create() NOW...")
        msg = client.messages.create(**message_params)
        print(f"[REP_MESSAGE] ✅ API call completed, processing response...")
        
        # ENHANCED LOGGING: Log comprehensive response details
        print("=" * 80)
        print(f"[REP_MESSAGE] ✅ TWILIO API RESPONSE RECEIVED")
        print("=" * 80)
        print(f"[REP_MESSAGE] Message SID: {msg.sid}")
        print(f"[REP_MESSAGE] Status: {msg.status} {'⚠️' if msg.status in ['failed', 'undelivered'] else '✅' if msg.status in ['sent', 'delivered', 'queued', 'accepted'] else ''}")
        print(f"[REP_MESSAGE] To: {msg.to}")
        print(f"[REP_MESSAGE] From (actual sender): {msg.from_}")
        print(f"[REP_MESSAGE] Account SID Used: {msg.account_sid}")
        actual_messaging_service = getattr(msg, 'messaging_service_sid', None)
        print(f"[REP_MESSAGE] Messaging Service SID: {actual_messaging_service or 'N/A'}")
        print(f"[REP_MESSAGE] 🔒 Send Mode Used: {send_mode}")
        if use_messaging_service and not actual_messaging_service:
            print(f"[REP_MESSAGE] ⚠️⚠️⚠️ WARNING: Expected Messaging Service but response shows N/A - check Twilio configuration!")
        elif not use_messaging_service and actual_messaging_service:
            print(f"[REP_MESSAGE] ⚠️⚠️⚠️ WARNING: Used direct phone but response shows Messaging Service - unexpected!")
        print(f"[REP_MESSAGE] Date Created: {msg.date_created}")
        print(f"[REP_MESSAGE] Date Sent: {msg.date_sent or 'Not sent yet'}")
        print(f"[REP_MESSAGE] Error Code: {msg.error_code or 'None (no error)'}")
        print(f"[REP_MESSAGE] Error Message: {msg.error_message or 'None (no error)'}")
        print(f"[REP_MESSAGE] Price: {msg.price or 'None'}")
        print(f"[REP_MESSAGE] Price Unit: {msg.price_unit or 'None'}")
        print(f"[REP_MESSAGE] URI: {msg.uri or 'None'}")
        print("=" * 80)
        
        # Enhanced status checking with actionable warnings
        if msg.status in ['failed', 'undelivered']:
            print("=" * 80)
            print(f"[REP_MESSAGE] ⚠️⚠️⚠️ MESSAGE DELIVERY FAILED ⚠️⚠️⚠️")
            print("=" * 80)
            print(f"[REP_MESSAGE] Status: {msg.status}")
            print(f"[REP_MESSAGE] Error Code: {msg.error_code}")
            print(f"[REP_MESSAGE] Error Message: {msg.error_message}")
            print(f"[REP_MESSAGE] This message was NOT delivered to the recipient.")
            print(f"[REP_MESSAGE] Check Twilio Console for more details: https://console.twilio.com/")
            print("=" * 80)
        elif msg.status in ['queued', 'accepted']:
            print(f"[REP_MESSAGE] ℹ️ Message accepted by Twilio, status: {msg.status}")
            print(f"[REP_MESSAGE] Message is queued for delivery. Check status later.")
        elif msg.status in ['sent', 'delivered']:
            print(f"[REP_MESSAGE] ✅ Message successfully {msg.status}")
        else:
            print(f"[REP_MESSAGE] ℹ️ Message status: {msg.status} (unusual status, monitor)")
        
        # Update conversation to rep mode (with card_id for proper linking)
        switch_conversation_to_rep(conn, phone, user_id, card_id=card_id)
        
        # Store message in conversation history
        add_message_to_history(
            conn,
            phone,
            direction="outbound",
            text=message,
            sender=f"rep:{user_id}",
            twilio_sid=msg.sid,
        )
        
        return {
            "ok": True,
            "twilio_sid": msg.sid,
            "status": msg.status,
            "phone": phone,
            "error_code": msg.error_code,
            "error_message": msg.error_message,
        }
    except Exception as e:
        print("=" * 80)
        print(f"[REP_MESSAGE] ❌ TWILIO API CALL FAILED")
        print("=" * 80)
        print(f"[REP_MESSAGE] Error Type: {type(e).__name__}")
        print(f"[REP_MESSAGE] Error Message: {str(e)}")
        print(f"[REP_MESSAGE] Traceback:")
        traceback.print_exc()
        print("=" * 80)
        raise


def switch_conversation_to_rep(
    conn: Any,
    phone: str,
    user_id: str,
    card_id: Optional[str] = None,
) -> bool:
    """
    Switch a conversation from AI mode to rep mode.
    If card_id is provided, ensures conversation is linked to that card.
    Rep isolation is maintained via card_assignments table, not phone numbers.
    """
    with conn.cursor() as cur:
        # Try to get card_id from existing conversation if not provided
        if not card_id:
            cur.execute("""
                SELECT card_id FROM conversations WHERE phone = %s LIMIT 1
            """, (phone,))
            row = cur.fetchone()
            if row and row[0]:
                card_id = row[0]
        
        # Update existing conversation
        # Note: rep_phone_number column kept for backward compatibility but not used
        cur.execute("""
            UPDATE conversations
            SET routing_mode = 'rep',
                rep_user_id = %s,
                card_id = COALESCE(%s, card_id),
                updated_at = NOW()
            WHERE phone = %s
        """, (user_id, card_id, phone))
        
        # If conversation doesn't exist, create it
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO conversations (
                    phone, card_id, routing_mode, rep_user_id,
                    state, owner, created_at, updated_at, history
                )
                VALUES (%s, %s, 'rep', %s, 'awaiting_response', %s, NOW(), NOW(), '[]'::jsonb)
                ON CONFLICT (phone) DO UPDATE SET
                    routing_mode = 'rep',
                    rep_user_id = EXCLUDED.rep_user_id,
                    card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                    updated_at = NOW()
            """, (phone, card_id, user_id, user_id))
        
        return True


def get_rep_conversations(conn: Any, user_id: str) -> List[Dict[str, Any]]:
    """
    Get all conversations for a rep.
    Includes:
    - Conversations where rep_user_id = user_id (rep mode)
    - Conversations for assigned cards (even if still in AI mode)
    """
    # Helper function to convert datetime to ISO string (defined outside loop)
    def to_iso(dt):
        if dt is None:
            return None
        if hasattr(dt, 'isoformat'):
            return dt.isoformat()
        return str(dt)
    
    with conn.cursor() as cur:
        # Get conversations where:
        # 1. rep_user_id = user_id (rep mode conversations)
        # 2. OR card_id is in rep's assigned cards (assigned cards, even if AI mode)
        cur.execute("""
            SELECT DISTINCT
                c.phone, c.card_id, c.state, c.routing_mode, c.rep_phone_number,
                c.last_outbound_at, c.last_inbound_at, c.created_at, c.updated_at,
                c.history,
                COALESCE(c.last_inbound_at, c.last_outbound_at, c.updated_at) as sort_date
            FROM conversations c
            LEFT JOIN card_assignments ca ON c.card_id = ca.card_id
            WHERE (
                c.rep_user_id = %s
                OR (c.card_id IS NOT NULL AND ca.user_id = %s)
            )
            ORDER BY sort_date DESC NULLS LAST
        """, (user_id, user_id))
        
        conversations = []
        for row in cur.fetchall():
            history = row[9] or []  # history is at index 9 (sort_date is at index 10, not used in Python)
            if isinstance(history, str):
                try:
                    history = json.loads(history)
                except:
                    history = []
            
            # Get unread count (messages after last outbound)
            unread_count = 0
            if history:
                last_outbound_idx = -1
                for i, msg in enumerate(reversed(history)):
                    if msg.get("direction") == "outbound":
                        last_outbound_idx = len(history) - 1 - i
                        break
                    
                if last_outbound_idx >= 0:
                    unread_count = len([m for m in history[last_outbound_idx+1:] if m.get("direction") == "inbound"])
                else:
                    unread_count = len([m for m in history if m.get("direction") == "inbound"])
            
            # Convert all datetime objects to ISO strings
            conversations.append({
                "phone": row[0],
                "card_id": row[1],
                "state": row[2],
                "routing_mode": row[3],
                "rep_phone_number": row[4],
                "last_outbound_at": to_iso(row[5]),
                "last_inbound_at": to_iso(row[6]),
                "created_at": to_iso(row[7]),
                "updated_at": to_iso(row[8]),
                "unread_count": unread_count,
            })
        
        return conversations


def get_conversation_messages(conn: Any, phone: str) -> List[Dict[str, Any]]:
    """Get full message history for a phone number."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT history
            FROM conversations
            WHERE phone = %s
        """, (phone,))
        
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        
        history = row[0]
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except:
                return []
        
        return history if isinstance(history, list) else []


def add_message_to_history(
    conn: Any,
    phone: str,
    direction: str,
    text: str,
    sender: str,
    twilio_sid: Optional[str] = None,
) -> None:
    """Add a message to conversation history."""
    with conn.cursor() as cur:
        # Get existing history
        cur.execute("""
            SELECT COALESCE(history::text, '[]') as history
            FROM conversations
            WHERE phone = %s
        """, (phone,))
        
        row = cur.fetchone()
        existing_history = []
        if row and row[0]:
            try:
                existing_history = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except:
                existing_history = []
        
        # Add new message
        new_message = {
            "direction": direction,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
            "sender": sender,
        }
        if twilio_sid:
            new_message["twilio_sid"] = twilio_sid
        
        updated_history = existing_history + [new_message]
        
        # Update conversation
        cur.execute("""
            UPDATE conversations
            SET history = %s::jsonb,
                updated_at = NOW(),
                last_outbound_at = CASE WHEN %s = 'outbound' THEN NOW() ELSE last_outbound_at END,
                last_inbound_at = CASE WHEN %s = 'inbound' THEN NOW() ELSE last_inbound_at END
            WHERE phone = %s
        """, (json.dumps(updated_history), direction, direction, phone))
