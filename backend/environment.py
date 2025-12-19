"""
Environment Isolation Layer
Implements one conversation per (phone_number × rep × campaign)

Key invariant: Inbound messages route to the environment that last sent an outbound SMS.
"""

import hashlib
from typing import Optional, Dict, Any, Tuple
import psycopg2


def generate_environment_id(rep_id: Optional[str], campaign_id: Optional[str]) -> str:
    """
    Generate a deterministic environment_id from rep_id and campaign_id.
    
    Args:
        rep_id: Rep user ID (None = owner)
        campaign_id: Campaign identifier
        
    Returns:
        environment_id string (e.g., 'env_abc123...')
    """
    rep_key = rep_id if rep_id else 'owner'
    campaign_key = campaign_id if campaign_id else 'default'
    combined = f"{rep_key}_{campaign_key}"
    hash_val = hashlib.md5(combined.encode()).hexdigest()
    return f"env_{hash_val}"


def route_inbound_to_environment(
    conn: Any,
    phone_number: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Route inbound message to the environment that last sent an outbound SMS.
    
    Algorithm:
    1. Look up the most recent outbound with a message_sid for that phone number
    2. Extract environment_id, rep_id, campaign_id
    3. Return these values for conversation lookup
    
    Args:
        conn: Database connection
        phone_number: Normalized phone number
        
    Returns:
        Tuple of (environment_id, rep_id, campaign_id) or (None, None, None) if no prior outbound
    """
    with conn.cursor() as cur:
        # Check if message_events table exists
        try:
            cur.execute("""
                SELECT environment_id, rep_id, campaign_id
                FROM message_events
                WHERE phone_number = %s
                  AND direction = 'outbound'
                  AND message_sid IS NOT NULL
                ORDER BY sent_at DESC
                LIMIT 1
            """, (phone_number,))
            row = cur.fetchone()
            
            if row:
                environment_id = row[0]
                rep_id = row[1]
                campaign_id = row[2]
                print(f"[ENV_ROUTE] ✅ Found last outbound environment: env={environment_id}, rep={rep_id}, campaign={campaign_id}", flush=True)
                return environment_id, rep_id, campaign_id
            else:
                print(f"[ENV_ROUTE] ⚠️ No prior outbound found for phone: {phone_number}", flush=True)
                return None, None, None
        except psycopg2.ProgrammingError as e:
            # message_events table doesn't exist yet (pre-migration)
            if 'message_events' in str(e):
                print(f"[ENV_ROUTE] ⚠️ message_events table not found - using fallback routing", flush=True)
                # Fallback: try to infer from conversations table
                return _fallback_route_from_conversations(conn, phone_number)
            raise


def _fallback_route_from_conversations(
    conn: Any,
    phone_number: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fallback routing using conversations table (for backward compatibility).
    Only used if message_events table doesn't exist yet.
    """
    with conn.cursor() as cur:
        # Check if environment_id column exists
        try:
            cur.execute("""
                SELECT environment_id, rep_user_id
                FROM conversations
                WHERE phone = %s
                ORDER BY last_outbound_at DESC NULLS LAST
                LIMIT 1
            """, (phone_number,))
            row = cur.fetchone()
            
            if row:
                environment_id = row[0]
                rep_id = row[1]
                # Infer campaign_id from environment_id if possible
                campaign_id = None
                if environment_id:
                    # Try to extract from environment_id (format: env_hash(rep_campaign))
                    # For now, default to None - will be set on next outbound
                    pass
                print(f"[ENV_ROUTE] ✅ Fallback: Found conversation env={environment_id}, rep={rep_id}", flush=True)
                return environment_id, rep_id, campaign_id
        except psycopg2.ProgrammingError:
            # environment_id column doesn't exist yet
            pass
    
    return None, None, None


def get_or_create_environment(
    conn: Any,
    phone_number: str,
    rep_id: Optional[str],
    campaign_id: Optional[str],
    card_id: Optional[str] = None
) -> str:
    """
    Get existing environment_id or create a new one.
    
    If no prior outbound exists, create a new environment based on current rep_id and campaign_id.
    
    Args:
        conn: Database connection
        phone_number: Normalized phone number
        rep_id: Rep user ID (None = owner)
        campaign_id: Campaign identifier
        card_id: Optional card_id for inferring campaign if not provided
        
    Returns:
        environment_id string
    """
    # First, try to route to existing environment
    existing_env, existing_rep, existing_campaign = route_inbound_to_environment(conn, phone_number)
    
    if existing_env:
        print(f"[ENV_GET] ✅ Using existing environment: {existing_env}", flush=True)
        return existing_env
    
    # No prior outbound - create new environment
    # Infer campaign_id from card if not provided
    if not campaign_id and card_id:
        campaign_id = _infer_campaign_from_card(conn, card_id)
    
    environment_id = generate_environment_id(rep_id, campaign_id)
    print(f"[ENV_GET] ✅ Created new environment: {environment_id} (rep={rep_id}, campaign={campaign_id})", flush=True)
    return environment_id


def _infer_campaign_from_card(conn: Any, card_id: str) -> Optional[str]:
    """Infer campaign_id from card data (frat vs faith)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT card_data FROM cards WHERE id = %s LIMIT 1
        """, (card_id,))
        row = cur.fetchone()
        if row and row[0]:
            card_data = row[0] if isinstance(row[0], dict) else {}
            if card_data.get("fraternity"):
                return "frat_rt4orgs"
            elif card_data.get("faith_group"):
                return "faith_rt4orgs"
            elif card_data.get("role") == "Office":
                return "faith_rt4orgs"
    return "default_rt4orgs"


def store_message_event(
    conn: Any,
    phone_number: str,
    environment_id: str,
    direction: str,
    message_text: str,
    message_sid: Optional[str] = None,
    rep_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    state: Optional[str] = None,
    twilio_status: Optional[str] = None
) -> None:
    """
    Store a message event in message_events table.
    
    CRITICAL: Only rows with message_sid count as "sent".
    This distinguishes generated vs actually sent messages.
    
    Args:
        conn: Database connection
        phone_number: Normalized phone number
        environment_id: Environment identifier
        direction: 'inbound' or 'outbound'
        message_text: Message content
        message_sid: Twilio message SID (REQUIRED for outbound to count as "sent")
        rep_id: Rep user ID
        campaign_id: Campaign identifier
        state: Conversation state
        twilio_status: Twilio delivery status
    """
    with conn.cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO message_events
                (phone_number, environment_id, rep_id, campaign_id, message_sid, direction, 
                 sent_at, state, message_text, twilio_status)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
            """, (
                phone_number,
                environment_id,
                rep_id,
                campaign_id,
                message_sid,
                direction,
                state,
                message_text,
                twilio_status
            ))
            print(f"[ENV_STORE] ✅ Stored {direction} message event: env={environment_id}, sid={message_sid}", flush=True)
        except psycopg2.ProgrammingError as e:
            # message_events table doesn't exist yet (pre-migration)
            if 'message_events' in str(e):
                print(f"[ENV_STORE] ⚠️ message_events table not found - skipping event storage", flush=True)
            else:
                raise
