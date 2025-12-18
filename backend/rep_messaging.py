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
    Send SMS from rep's phone number to the card's phone number.
    Returns dict with result including twilio_sid.
    """
    # Get rep user info
    user = get_user(conn, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    if not user.get("twilio_phone_number"):
        raise ValueError(f"User {user_id} does not have a Twilio phone number configured")
    
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
    print(f"[REP_MESSAGE] Rep Twilio Phone: {user['twilio_phone_number']}")
    print(f"[REP_MESSAGE] Account SID: {account_sid[:10]}... (length: {len(account_sid)})" if account_sid else "[REP_MESSAGE] Account SID: None")
    print(f"[REP_MESSAGE] Auth Token: {auth_token[:15]}... (length: {len(auth_token)})" if auth_token else "[REP_MESSAGE] Auth Token: None")
    
    try:
        print(f"[REP_MESSAGE] Creating Twilio Client...")
        client = Client(account_sid, auth_token)
        print(f"[REP_MESSAGE] ✅ Twilio Client created")
        
        # Use rep's phone directly as "from" - this guarantees the message comes from their number
        # All reps use same Account SID (AC...) for auth, but different phone numbers as "from"
        rep_phone = user["twilio_phone_number"]
        if not rep_phone:
            error_msg = f"User {user_id} does not have a Twilio phone number configured"
            print(f"[REP_MESSAGE] ❌ {error_msg}")
            raise ValueError(error_msg)
        
        print(f"[REP_MESSAGE] Using Rep Phone as From: {rep_phone}")
        print(f"[REP_MESSAGE] Using System Account SID: {account_sid[:10]}... (same for all reps)")
        print(f"[REP_MESSAGE] Calling client.messages.create() with:")
        print(f"[REP_MESSAGE]   to: {phone}")
        print(f"[REP_MESSAGE]   from_: {rep_phone}")
        print(f"[REP_MESSAGE]   body length: {len(message)}")
        print(f"[REP_MESSAGE] Note: Message will come from rep's specific phone number")
        msg = client.messages.create(
            to=phone,
            from_=rep_phone,
            body=message
        )
        
        # Log comprehensive response
        print("=" * 80)
        print(f"[REP_MESSAGE] ✅ TWILIO API CALL SUCCESSFUL")
        print("=" * 80)
        print(f"[REP_MESSAGE] Message SID: {msg.sid}")
        print(f"[REP_MESSAGE] Status: {msg.status}")
        print(f"[REP_MESSAGE] To: {msg.to}")
        print(f"[REP_MESSAGE] From: {msg.from_}")
        print(f"[REP_MESSAGE] Date Created: {msg.date_created}")
        print(f"[REP_MESSAGE] Date Sent: {msg.date_sent}")
        print(f"[REP_MESSAGE] Error Code: {msg.error_code or 'None'}")
        print(f"[REP_MESSAGE] Error Message: {msg.error_message or 'None'}")
        print(f"[REP_MESSAGE] Price: {msg.price or 'None'}")
        print(f"[REP_MESSAGE] Price Unit: {msg.price_unit or 'None'}")
        print(f"[REP_MESSAGE] URI: {msg.uri or 'None'}")
        print("=" * 80)
        
        # Check for error status
        if msg.status in ['failed', 'undelivered']:
            print(f"[REP_MESSAGE] ⚠️ WARNING: Message status is '{msg.status}'")
            print(f"[REP_MESSAGE] Error Code: {msg.error_code}")
            print(f"[REP_MESSAGE] Error Message: {msg.error_message}")
        
        # Update conversation to rep mode (with card_id for proper linking)
        switch_conversation_to_rep(conn, phone, user_id, user["twilio_phone_number"], card_id=card_id)
        
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
    rep_phone_number: str,
    card_id: Optional[str] = None,
) -> bool:
    """
    Switch a conversation from AI mode to rep mode.
    If card_id is provided, ensures conversation is linked to that card.
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
        cur.execute("""
            UPDATE conversations
            SET routing_mode = 'rep',
                rep_user_id = %s,
                rep_phone_number = %s,
                card_id = COALESCE(%s, card_id),
                updated_at = NOW()
            WHERE phone = %s
        """, (user_id, rep_phone_number, card_id, phone))
        
        # If conversation doesn't exist, create it
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO conversations (
                    phone, card_id, routing_mode, rep_user_id, rep_phone_number,
                    state, owner, created_at, updated_at, history
                )
                VALUES (%s, %s, 'rep', %s, %s, 'awaiting_response', %s, NOW(), NOW(), '[]'::jsonb)
                ON CONFLICT (phone) DO UPDATE SET
                    routing_mode = 'rep',
                    rep_user_id = EXCLUDED.rep_user_id,
                    rep_phone_number = EXCLUDED.rep_phone_number,
                    card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                    updated_at = NOW()
            """, (phone, card_id, user_id, rep_phone_number, user_id))
        
        return True


def get_rep_conversations(conn: Any, user_id: str) -> List[Dict[str, Any]]:
    """
    Get all conversations for a rep.
    Includes:
    - Conversations where rep_user_id = user_id (rep mode)
    - Conversations for assigned cards (even if still in AI mode)
    """
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
            history = row[10] or []  # history is at index 10 (sort_date is at index 11, not used in Python)
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
            
            # Convert datetime objects to ISO format strings for JSON serialization
            def to_iso(dt):
                return dt.isoformat() if dt else None
            
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
