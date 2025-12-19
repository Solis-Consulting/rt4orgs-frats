"""
Card management module for JSON-native CRM.
Handles validation, normalization, and storage of contact cards and entity cards.
"""

from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import Json


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text


def generate_card_id(card: Dict[str, Any]) -> str:
    """Auto-generate card ID if missing."""
    card_type = card.get("type", "person")
    name = card.get("name", "unknown")
    
    if card_type == "person":
        fraternity = card.get("fraternity", "")
        chapter = card.get("chapter", "")
        parts = [card_type, name]
        if fraternity:
            parts.append(fraternity)
        if chapter:
            parts.append(chapter)
    else:
        parts = [card_type, name]
    
    return "_".join(slugify(part) for part in parts if part)


def validate_card_schema(card: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate card schema per type.
    Returns (is_valid, error_message).
    """
    card_type = card.get("type")
    
    if not card_type:
        return False, "Missing required field: type"
    
    if card_type not in ["person", "fraternity", "team", "business"]:
        return False, f"Invalid type: {card_type}. Must be one of: person, fraternity, team, business"
    
    # Type-specific validation
    if card_type == "person":
        if not card.get("name"):
            return False, "Person card missing required field: name"
        if not card.get("phone"):
            return False, "Person card missing required field: phone"
    
    elif card_type == "fraternity":
        if not card.get("name"):
            return False, "Fraternity card missing required field: name"
        members = card.get("members", [])
        if not isinstance(members, list):
            return False, "Fraternity card 'members' must be an array"
    
    elif card_type == "team":
        if not card.get("name"):
            return False, "Team card missing required field: name"
        members = card.get("members", [])
        if not isinstance(members, list):
            return False, "Team card 'members' must be an array"
    
    elif card_type == "business":
        if not card.get("name"):
            return False, "Business card missing required field: name"
        contacts = card.get("contacts", [])
        if not isinstance(contacts, list):
            return False, "Business card 'contacts' must be an array"
    
    return True, None


def normalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize card: ensure id exists, clean up structure.
    Returns normalized card dict.
    """
    normalized = card.copy()
    
    # Ensure id exists
    if not normalized.get("id"):
        normalized["id"] = generate_card_id(normalized)
    
    # Ensure type is set
    if not normalized.get("type"):
        normalized["type"] = "person"
    
    # Ensure arrays exist for entity types
    if normalized["type"] == "fraternity" and "members" not in normalized:
        normalized["members"] = []
    if normalized["type"] == "team" and "members" not in normalized:
        normalized["members"] = []
    if normalized["type"] == "business" and "contacts" not in normalized:
        normalized["contacts"] = []
    
    # Ensure tags exist for person cards
    if normalized["type"] == "person" and "tags" not in normalized:
        normalized["tags"] = []
    
    # Ensure metadata exists for person cards
    if normalized["type"] == "person" and "metadata" not in normalized:
        normalized["metadata"] = {}
    
    return normalized


def resolve_card_references(
    conn: Any,
    card: Dict[str, Any]
) -> tuple[List[str], Optional[str]]:
    """
    Validate that referenced card IDs exist.
    Returns (missing_ids, error_message).
    """
    card_type = card.get("type")
    card_id = card.get("id")
    missing = []
    
    if card_type == "fraternity":
        members = card.get("members", [])
        if members:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(members))
                cur.execute(
                    f"SELECT id FROM cards WHERE id IN ({placeholders})",
                    tuple(members)
                )
                existing = {row[0] for row in cur.fetchall()}
                missing = [m for m in members if m not in existing]
    
    elif card_type == "team":
        members = card.get("members", [])
        if members:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(members))
                cur.execute(
                    f"SELECT id FROM cards WHERE id IN ({placeholders})",
                    tuple(members)
                )
                existing = {row[0] for row in cur.fetchall()}
                missing = [m for m in members if m not in existing]
    
    elif card_type == "business":
        contacts = card.get("contacts", [])
        if contacts:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(contacts))
                cur.execute(
                    f"SELECT id FROM cards WHERE id IN ({placeholders})",
                    tuple(contacts)
                )
                existing = {row[0] for row in cur.fetchall()}
                missing = [c for c in contacts if c not in existing]
    
    if missing:
        return missing, f"Referenced card IDs do not exist: {', '.join(missing)}"
    
    return [], None


def store_card(
    conn: Any,
    card: Dict[str, Any],
    allow_missing_references: bool = False
) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Store card in database.
    Returns (success, error_message, stored_card).
    """
    # Normalize card
    normalized = normalize_card(card)
    
    # Validate schema
    is_valid, error = validate_card_schema(normalized)
    if not is_valid:
        return False, error, None
    
    # Resolve references (unless we're allowing missing refs for initial upload)
    if not allow_missing_references:
        missing, ref_error = resolve_card_references(conn, normalized)
        if ref_error:
            return False, ref_error, None
    
    card_id = normalized["id"]
    card_type = normalized["type"]
    sales_state = normalized.get("sales_state", "cold")
    owner = normalized.get("owner")
    
    # Extract card_data (everything except id, type, sales_state, owner)
    card_data = {k: v for k, v in normalized.items() 
                  if k not in ["id", "type", "sales_state", "owner"]}
    
    try:
        with conn.cursor() as cur:
            # Check if upload_batch_id column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'cards' AND column_name = 'upload_batch_id'
            """)
            has_upload_batch_id = cur.fetchone() is not None
            
            if has_upload_batch_id:
                # Upsert card with upload_batch_id
                cur.execute("""
                    INSERT INTO cards (id, type, card_data, sales_state, owner, updated_at, upload_batch_id)
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        type = EXCLUDED.type,
                        card_data = EXCLUDED.card_data,
                        sales_state = EXCLUDED.sales_state,
                        owner = EXCLUDED.owner,
                        updated_at = EXCLUDED.updated_at,
                        upload_batch_id = COALESCE(EXCLUDED.upload_batch_id, cards.upload_batch_id)
                    RETURNING id, type, card_data, sales_state, owner, created_at, updated_at, upload_batch_id;
                """, (
                    card_id,
                    card_type,
                    Json(card_data),
                    sales_state,
                    owner,
                    datetime.utcnow(),
                    upload_batch_id
                ))
            else:
                # Fallback: upsert card without upload_batch_id (pre-migration)
                cur.execute("""
                    INSERT INTO cards (id, type, card_data, sales_state, owner, updated_at)
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        type = EXCLUDED.type,
                        card_data = EXCLUDED.card_data,
                        sales_state = EXCLUDED.sales_state,
                        owner = EXCLUDED.owner,
                        updated_at = EXCLUDED.updated_at
                    RETURNING id, type, card_data, sales_state, owner, created_at, updated_at;
                """, (
                    card_id,
                    card_type,
                    Json(card_data),
                    sales_state,
                    owner,
                    datetime.utcnow()
                ))
            
            row = cur.fetchone()
            if not row:
                return False, "Failed to store card", None
            
            # Store relationships
            store_relationships(conn, normalized)
            
            # Build stored card dict
            stored_card = {
                "id": row[0],
                "type": row[1],
                "card_data": row[2],
                "sales_state": row[3],
                "owner": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None,
            }
            
            # Add upload_batch_id if column exists
            if has_upload_batch_id and len(row) > 7:
                stored_card["upload_batch_id"] = row[7]
            
            return True, None, stored_card
            
    except psycopg2.IntegrityError as e:
        return False, f"Database integrity error: {str(e)}", None
    except Exception as e:
        return False, f"Error storing card: {str(e)}", None


def store_relationships(conn: Any, card: Dict[str, Any]) -> None:
    """Store card relationships in card_relationships table."""
    card_id = card.get("id")
    card_type = card.get("type")
    
    if not card_id:
        return
    
    with conn.cursor() as cur:
        # Delete existing relationships for this card as parent
        cur.execute(
            "DELETE FROM card_relationships WHERE parent_card_id = %s",
            (card_id,)
        )
        
        # Insert new relationships
        if card_type == "fraternity":
            members = card.get("members", [])
            for member_id in members:
                cur.execute("""
                    INSERT INTO card_relationships (parent_card_id, child_card_id, relationship_type)
                    VALUES (%s, %s, 'member')
                    ON CONFLICT (parent_card_id, child_card_id, relationship_type) DO NOTHING;
                """, (card_id, member_id))
        
        elif card_type == "team":
            members = card.get("members", [])
            for member_id in members:
                cur.execute("""
                    INSERT INTO card_relationships (parent_card_id, child_card_id, relationship_type)
                    VALUES (%s, %s, 'member')
                    ON CONFLICT (parent_card_id, child_card_id, relationship_type) DO NOTHING;
                """, (card_id, member_id))
        
        elif card_type == "business":
            contacts = card.get("contacts", [])
            for contact_id in contacts:
                cur.execute("""
                    INSERT INTO card_relationships (parent_card_id, child_card_id, relationship_type)
                    VALUES (%s, %s, 'contact')
                    ON CONFLICT (parent_card_id, child_card_id, relationship_type) DO NOTHING;
                """, (card_id, contact_id))


def get_card(conn: Any, card_id: str) -> Optional[Dict[str, Any]]:
    """Get a single card by ID."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, type, card_data, sales_state, owner, created_at, updated_at
            FROM cards
            WHERE id = %s;
        """, (card_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "type": row[1],
            "card_data": row[2],
            "sales_state": row[3],
            "owner": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "updated_at": row[6].isoformat() if row[6] else None,
        }


def delete_card(conn: Any, card_id: str, deleted_by: str) -> tuple[bool, Optional[str]]:
    """
    Delete a card and all associated data. Terminal cleanup event.
    
    Steps:
    1. Get current assignments and conversations for logging
    2. Get current Markov state before deletion
    3. Delete card_assignments (explicit, before card deletion)
    4. Delete card (cascades to conversations via FK)
    5. Log terminal event (NOT a handoff): to_rep=NULL indicates deletion
    
    Args:
        conn: Database connection
        card_id: Card ID to delete
        deleted_by: User/admin who triggered deletion
        
    Returns:
        (success: bool, error_message: Optional[str])
    """
    from backend.handoffs import get_conversation_state, log_handoff, resolve_current_rep
    
    try:
        with conn.cursor() as cur:
            # Step 1: Get current assignment and state for logging
            current_rep = resolve_current_rep(conn, card_id)
            state_before = get_conversation_state(conn, card_id)
            
            # Step 2: Delete card_assignments (explicit, before card deletion)
            cur.execute("""
                DELETE FROM card_assignments
                WHERE card_id = %s
            """, (card_id,))
            assignments_deleted = cur.rowcount
            
            # Step 3: Delete card (cascades to conversations via FK)
            cur.execute("""
                DELETE FROM cards
                WHERE id = %s
            """, (card_id,))
            
            if cur.rowcount == 0:
                return False, f"Card {card_id} not found"
            
            # Step 4: Log terminal event (NOT a handoff)
            # to_rep=NULL indicates deletion, not a handoff
            log_handoff(
                conn=conn,
                card_id=card_id,
                from_rep=current_rep,
                to_rep=None,  # NULL for terminal events
                reason='card_deleted',
                state_before=state_before,
                state_after=None,  # NULL for deletions
                assigned_by=deleted_by
            )
            
            print(f"[CARD_DELETE] ✅ Deleted card {card_id}", flush=True)
            print(f"[CARD_DELETE]   Removed {assignments_deleted} assignment(s)", flush=True)
            print(f"[CARD_DELETE]   Conversations cascaded via FK", flush=True)
            
            return True, None
            
    except psycopg2.Error as e:
        error_msg = f"Database error deleting card {card_id}: {str(e)}"
        print(f"[CARD_DELETE] ❌ {error_msg}", flush=True)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error deleting card {card_id}: {str(e)}"
        print(f"[CARD_DELETE] ❌ {error_msg}", flush=True)
        return False, error_msg


def get_card_relationships(conn: Any, card_id: str) -> List[Dict[str, Any]]:
    """Get all relationships for a card (both as parent and child)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                parent_card_id,
                child_card_id,
                relationship_type,
                created_at
            FROM card_relationships
            WHERE parent_card_id = %s OR child_card_id = %s
            ORDER BY created_at;
        """, (card_id, card_id))
        
        return [
            {
                "parent_card_id": row[0],
                "child_card_id": row[1],
                "relationship_type": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
            }
            for row in cur.fetchall()
        ]

