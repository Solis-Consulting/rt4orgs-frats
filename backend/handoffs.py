"""
Handoff event logging and Markov state management.

Provides canonical primitives for tracking ownership changes and resetting
Markov state when cards are reassigned or deleted.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import psycopg2


def resolve_current_rep(conn: Any, card_id: str) -> Optional[str]:
    """
    Get current rep owner from card_assignments (source of truth).
    
    Args:
        conn: Database connection
        card_id: Card ID to look up
        
    Returns:
        user_id of current rep owner, or None if not assigned
    """
    from backend.assignments import get_card_assignment
    assignment = get_card_assignment(conn, card_id)
    return assignment['user_id'] if assignment else None


def reset_markov_for_card(conn: Any, card_id: str, rep_user_id: Optional[str], reason: str, actor: str) -> None:
    """
    Reset Markov state for existing conversation row(s) tied to a card.
    
    Updates conversations WHERE card_id = card_id:
    - state = 'initial_outreach'
    - rep_user_id = rep_user_id
    - previous_state = NULL
    
    Does NOT create new rows, only updates existing ones.
    
    Args:
        conn: Database connection
        card_id: Card ID to reset conversations for
        rep_user_id: New rep user ID (can be None)
        reason: Reason for reset (for logging)
        actor: Who triggered the reset (admin/rep/system)
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversations
            SET state = 'initial_outreach',
                rep_user_id = %s,
                updated_at = NOW()
            WHERE card_id = %s
        """, (rep_user_id, card_id))
        
        rows_updated = cur.rowcount
        if rows_updated > 0:
            print(f"[HANDOFF] ✅ Reset Markov state for {rows_updated} conversation(s) - card_id={card_id}, reason={reason}, actor={actor}", flush=True)


def log_handoff(
    conn: Any,
    card_id: str,
    from_rep: Optional[str],
    to_rep: Optional[str],
    reason: str,
    state_before: Optional[str],
    state_after: Optional[str],
    assigned_by: str
) -> None:
    """
    Log a handoff event to handoff_events table with structured JSON logging.
    
    Args:
        conn: Database connection
        card_id: Card ID involved in handoff
        from_rep: Previous rep owner (None for new assignments)
        to_rep: New rep owner (None for deletions)
        reason: Reason for handoff (rep_reassign, card_deleted, blast_claim, runtime_mismatch)
        state_before: Markov state before handoff
        state_after: Markov state after handoff
        assigned_by: Who triggered the handoff (admin/rep/system)
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO handoff_events
            (card_id, from_rep, to_rep, reason, markov_state_before, markov_state_after, assigned_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (card_id, from_rep, to_rep, reason, state_before, state_after, assigned_by))
    
    # Human-readable log
    if reason == 'card_deleted':
        print(f"[HANDOFF] 🧹 Card deleted — cleared conversations + Markov state", flush=True)
        print(f"[HANDOFF]   card_id={card_id}, from_rep={from_rep}, state_before={state_before}", flush=True)
    elif reason == 'rep_reassign':
        print(f"[HANDOFF] 🔁 Rep reassignment — Markov RESET", flush=True)
        print(f"[HANDOFF]   card_id={card_id}, from_rep={from_rep}, to_rep={to_rep}", flush=True)
        print(f"[HANDOFF]   state_before={state_before}, state_after={state_after}", flush=True)
    elif reason == 'blast_claim':
        print(f"[HANDOFF] 🚀 Blast claim — rep ownership claimed", flush=True)
        print(f"[HANDOFF]   card_id={card_id}, from_rep={from_rep}, to_rep={to_rep}", flush=True)
        print(f"[HANDOFF]   state_before={state_before}, state_after={state_after}", flush=True)
    elif reason == 'runtime_mismatch':
        print(f"[HANDOFF] ⚠️ Runtime mismatch detected — resetting state", flush=True)
        print(f"[HANDOFF]   card_id={card_id}, from_rep={from_rep}, to_rep={to_rep}", flush=True)
        print(f"[HANDOFF]   state_before={state_before}, state_after={state_after}", flush=True)
    
    # Structured JSON log for analytics
    event_data = {
        'card_id': card_id,
        'from_rep': from_rep,
        'to_rep': to_rep,
        'reason': reason,
        'state_before': state_before,
        'state_after': state_after,
        'actor': assigned_by,
        'timestamp': datetime.utcnow().isoformat()
    }
    print(f"[HANDOFF_EVENT] {json.dumps(event_data)}", flush=True)


def get_handoff_history(conn: Any, card_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Query handoff events for a card, ordered by created_at DESC.
    
    Args:
        conn: Database connection
        card_id: Card ID to get history for
        limit: Maximum number of events to return
        
    Returns:
        List of handoff event dictionaries
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, card_id, from_rep, to_rep, reason, markov_state_before,
                   markov_state_after, assigned_by, conversation_id, created_at
            FROM handoff_events
            WHERE card_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (card_id, limit))
        
        rows = cur.fetchall()
        return [
            {
                'id': row[0],
                'card_id': row[1],
                'from_rep': row[2],
                'to_rep': row[3],
                'reason': row[4],
                'markov_state_before': row[5],
                'markov_state_after': row[6],
                'assigned_by': row[7],
                'conversation_id': row[8],
                'created_at': row[9].isoformat() if row[9] else None,
            }
            for row in rows
        ]


def get_conversation_state(conn: Any, card_id: str) -> Optional[str]:
    """
    Get current Markov state for a card's conversation (may return None if no conversation).
    
    Args:
        conn: Database connection
        card_id: Card ID to look up
        
    Returns:
        Current state string, or None if no conversation exists
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT state FROM conversations
            WHERE card_id = %s
            LIMIT 1
        """, (card_id,))
        row = cur.fetchone()
        return row[0] if row else None
