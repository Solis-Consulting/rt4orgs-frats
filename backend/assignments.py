"""
Card assignment system for sales reps.
Handles assigning cards to reps and tracking assignment status.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import psycopg2
from datetime import datetime


def assign_card_to_rep(
    conn: Any,
    card_id: str,
    user_id: str,
    assigned_by: str,
    notes: Optional[str] = None,
) -> bool:
    """
    Assign a card to a rep. Returns True if successful.
    
    Source of truth: card_assignments is authoritative owner.
    If rep changes, resets Markov state and logs handoff event.
    """
    from backend.handoffs import (
        get_conversation_state,
        reset_markov_for_card,
        log_handoff
    )
    
    # Get current assignment from card_assignments (source of truth)
    current_assignment = get_card_assignment(conn, card_id)
    from_rep = current_assignment['user_id'] if current_assignment else None
    
    # Get current Markov state before reset (may be None if no conversation)
    state_before = get_conversation_state(conn, card_id)
    
    with conn.cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO card_assignments (card_id, user_id, assigned_by, notes, status)
                VALUES (%s, %s, %s, %s, 'assigned')
                ON CONFLICT (card_id, user_id) 
                DO UPDATE SET
                    assigned_by = EXCLUDED.assigned_by,
                    assigned_at = NOW(),
                    notes = COALESCE(EXCLUDED.notes, card_assignments.notes),
                    status = CASE 
                        WHEN card_assignments.status = 'closed' THEN 'closed'
                        WHEN card_assignments.status = 'lost' THEN 'lost'
                        ELSE 'assigned'
                    END
            """, (card_id, user_id, assigned_by, notes))
            
            # If rep changed, reset Markov and log handoff
            if from_rep and from_rep != user_id:
                reset_markov_for_card(conn, card_id, user_id, 'rep_reassign', assigned_by)
                log_handoff(
                    conn=conn,
                    card_id=card_id,
                    from_rep=from_rep,
                    to_rep=user_id,
                    reason='rep_reassign',
                    state_before=state_before,
                    state_after='initial_outreach',
                    assigned_by=assigned_by
                )
            
            return True
        except psycopg2.Error as e:
            print(f"[ASSIGNMENT] Error assigning card {card_id} to user {user_id}: {e}")
            return False


def get_rep_assigned_cards(
    conn: Any,
    user_id: str,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get all cards assigned to a rep, optionally filtered by status.
    
    SECURITY: This function ONLY returns cards that exist in card_assignments table.
    It uses an INNER JOIN, so unassigned cards are NEVER returned.
    """
    if not user_id:
        print(f"[ASSIGNMENTS] ERROR: get_rep_assigned_cards called with empty user_id!")
        return []
    
    print(f"[ASSIGNMENTS] get_rep_assigned_cards called for user_id={user_id}, status={status}")
    
    query = """
        SELECT 
            c.id, c.type, c.card_data, c.sales_state, c.owner, c.created_at, c.updated_at,
            c.upload_batch_id,
            ca.assigned_at, ca.status as assignment_status, ca.notes, ca.assigned_by
        FROM card_assignments ca
        INNER JOIN cards c ON ca.card_id = c.id
        WHERE ca.user_id = %s
    """
    params = [user_id]
    
    if status:
        query += " AND ca.status = %s"
        params.append(status)
    
    query += " ORDER BY ca.assigned_at DESC"
    
    print(f"[ASSIGNMENTS] Executing query: {query[:100]}... with params: {params}")
    
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        
        print(f"[ASSIGNMENTS] Query returned {len(rows)} rows for user_id={user_id}")
        
        cards = []
        for row in rows:
            card_data = row[2]
            if isinstance(card_data, str):
                import json
                try:
                    card_data = json.loads(card_data)
                except:
                    pass
            
            # Handle both old schema (no upload_batch_id) and new schema (with upload_batch_id)
            # Old: id, type, card_data, sales_state, owner, created_at, updated_at, assigned_at, status, notes, assigned_by (11 columns)
            # New: id, type, card_data, sales_state, owner, created_at, updated_at, upload_batch_id, assigned_at, status, notes, assigned_by (12 columns)
            has_upload_batch_id = len(row) >= 12
            
            card_obj = {
                "id": row[0],
                "type": row[1],
                "card_data": card_data,
                "sales_state": row[3],
                "owner": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None,
                "upload_batch_id": row[7] if has_upload_batch_id else None,
            }
            
            # Flatten card response to standard format
            from backend.cards import flatten_card_response
            flattened_card = flatten_card_response(card_obj)
            
            # Add assignment info
            flattened_card["assignment"] = {
                "assigned_at": (row[8] if has_upload_batch_id else row[7]).isoformat() if (row[8] if has_upload_batch_id else row[7]) else None,
                "status": row[9] if has_upload_batch_id else row[8],
                "notes": row[10] if has_upload_batch_id else row[9],
                "assigned_by": row[11] if has_upload_batch_id else row[10],
            }
            
            cards.append(flattened_card)
        
        print(f"[ASSIGNMENTS] Returning {len(cards)} cards for user_id={user_id}")
        return cards


def unassign_card(conn: Any, card_id: str, user_id: str) -> bool:
    """Unassign a card from a rep."""
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM card_assignments
            WHERE card_id = %s AND user_id = %s
        """, (card_id, user_id))
        
        return cur.rowcount > 0


def get_card_assignment(conn: Any, card_id: str) -> Optional[Dict[str, Any]]:
    """Get the assignment for a card (if any)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ca.card_id, ca.user_id, ca.assigned_at, ca.assigned_by,
                   ca.status, ca.notes, u.username
            FROM card_assignments ca
            JOIN users u ON ca.user_id = u.id
            WHERE ca.card_id = %s
            ORDER BY ca.assigned_at DESC
            LIMIT 1
        """, (card_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            "card_id": row[0],
            "user_id": row[1],
            "username": row[6],
            "assigned_at": row[2],
            "assigned_by": row[3],
            "status": row[4],
            "notes": row[5],
        }


# Export get_card_assignment for use in handoffs module
__all__ = [
    'assign_card_to_rep',
    'get_rep_assigned_cards',
    'unassign_card',
    'get_card_assignment',
    'update_assignment_status',
    'list_assignments',
]


def update_assignment_status(
    conn: Any,
    card_id: str,
    user_id: str,
    status: str,
    notes: Optional[str] = None,
) -> bool:
    """Update the status of a card assignment."""
    if status not in ('assigned', 'active', 'closed', 'lost'):
        return False
    
    with conn.cursor() as cur:
        if notes:
            cur.execute("""
                UPDATE card_assignments
                SET status = %s, notes = %s
                WHERE card_id = %s AND user_id = %s
            """, (status, notes, card_id, user_id))
        else:
            cur.execute("""
                UPDATE card_assignments
                SET status = %s
                WHERE card_id = %s AND user_id = %s
            """, (status, card_id, user_id))
        
        return cur.rowcount > 0


def list_assignments(
    conn: Any,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all assignments, optionally filtered by user or status."""
    query = """
        SELECT 
            ca.card_id, ca.user_id, ca.assigned_at, ca.assigned_by,
            ca.status, ca.notes,
            u.username,
            c.type, c.card_data, c.sales_state
        FROM card_assignments ca
        JOIN users u ON ca.user_id = u.id
        JOIN cards c ON ca.card_id = c.id
        WHERE 1=1
    """
    params = []
    
    if user_id:
        query += " AND ca.user_id = %s"
        params.append(user_id)
    
    if status:
        query += " AND ca.status = %s"
        params.append(status)
    
    query += " ORDER BY ca.assigned_at DESC"
    
    with conn.cursor() as cur:
        cur.execute(query, params)
        
        assignments = []
        for row in cur.fetchall():
            card_data = row[8]
            if isinstance(card_data, str):
                import json
                try:
                    card_data = json.loads(card_data)
                except:
                    pass
            
            assignments.append({
                "card_id": row[0],
                "user_id": row[1],
                "username": row[6],
                "assigned_at": row[2],
                "assigned_by": row[3],
                "status": row[4],
                "notes": row[5],
                "card": {
                    "type": row[7],
                    "card_data": card_data,
                    "sales_state": row[9],
                }
            })
        
        return assignments
