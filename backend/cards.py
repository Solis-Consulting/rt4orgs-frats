"""
Card management module for JSON-native CRM.
Handles validation, normalization, and storage of contact cards and entity cards.
Supports vertical-based contact types with pitch templates.
"""

from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import Json

# Vertical type definitions
VERTICAL_TYPES = {
    "frats": {
        "name": "Fraternities",
        "required_fields": ["name", "role"],
        "optional_fields": ["tags", "metadata", "phone", "email", "chapter", "fraternity", "program", "university"],
        "pitch_template": "Hello {name}, we'd love to see how {fraternity} at {chapter} could engage with a FRESH PNM list.\nWe helped {purchased_chapter} at {purchased_institution} save DAYS of outreach. I'm David with RT4Orgs — https://rt4orgs.com"
    },
    "faith": {
        "name": "Faith / Religious Groups",
        "required_fields": ["name", "role", "faith_group", "university", "phone", "email"],
        "optional_fields": ["tags", "metadata"],
        "pitch_template": "Hello {name}, we help {faith_group} at {university} reach students likely to be receptive to faith-based community.\nOur lists allow your team to spend less time searching and more time welcoming, mentoring, and serving students.\nI'm Sarah with RT4Orgs — https://rt4orgs.com"
    },
    "academic": {
        "name": "Academic / Program-Specific",
        "required_fields": ["name", "role", "program", "department", "university", "phone", "email"],
        "optional_fields": ["tags", "metadata"],
        "pitch_template": "Hi {name}, we support {program} in {department} at {university} by providing a curated list of students already aligned with your program.\nThis helps your office save hours in outreach and focus on mentoring and advising.\nI'm Alex with RT4Orgs — https://rt4orgs.com"
    },
    "government": {
        "name": "Government / Student Government / Orgs",
        "required_fields": ["name", "role", "org", "university", "phone", "email"],
        "optional_fields": ["tags", "metadata"],
        "pitch_template": "Hello {name}, we help {org} at {university} streamline communication with student leaders and members.\nOur curated lists save your staff days of manual outreach, giving you more time for impactful student programming.\nI'm Jordan with RT4Orgs — https://rt4orgs.com"
    },
    "cultural": {
        "name": "Cultural / Faith-based Contacts",
        "required_fields": ["name", "role", "group", "university"],
        "optional_fields": ["email", "phone", "insta", "other_social", "tags", "metadata"],
        "pitch_template": "Hello {name}, we help {group} at {university} connect with students interested in cultural and faith-based communities.\nOur curated lists save your team time in outreach, allowing you to focus on building meaningful connections.\nI'm {rep_name} with RT4Orgs — https://rt4orgs.com"
    },
    "sports": {
        "name": "Sports / Club Contacts",
        "required_fields": ["name", "role", "team", "university"],
        "optional_fields": ["email", "phone", "insta", "other_social", "tags", "metadata"],
        "pitch_template": "Hello {name}, we help {team} at {university} streamline communication with athletes and club members.\nOur curated lists save your staff time in outreach, giving you more time for training and team building.\nI'm {rep_name} with RT4Orgs — https://rt4orgs.com"
    }
}


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text


def get_pitch_template(vertical: str) -> Optional[str]:
    """Get pitch template for a vertical type."""
    vertical_info = VERTICAL_TYPES.get(vertical)
    if vertical_info:
        return vertical_info.get("pitch_template")
    return None


def generate_pitch(card: Dict[str, Any], vertical: Optional[str] = None, 
                   additional_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Generate a personalized pitch from a card using the vertical's pitch template.
    
    Args:
        card: Contact card dictionary
        vertical: Vertical type (if not provided, will try to infer from card)
        additional_data: Additional data for placeholders (e.g., purchased_chapter, rep_name)
    
    Returns:
        Generated pitch text or None if template not found
    """
    # Determine vertical if not provided
    if not vertical:
        vertical = card.get("vertical")
    
    if not vertical or vertical not in VERTICAL_TYPES:
        return None
    
    template = get_pitch_template(vertical)
    if not template:
        return None
    
    # Merge card data with additional data
    data = card.copy()
    if additional_data:
        data.update(additional_data)
    
    # Map card fields to template placeholders
    # Handle different field name variations
    replacements = {}
    
    # Common fields
    replacements["{name}"] = data.get("name", data.get("contact_name", ""))
    replacements["{contact_name}"] = data.get("name", data.get("contact_name", ""))
    
    # Vertical-specific mappings
    if vertical == "frats":
        replacements["{fraternity}"] = data.get("fraternity", "")
        replacements["{chapter}"] = data.get("chapter", "")
        replacements["{purchased_chapter}"] = additional_data.get("purchased_chapter", "a chapter") if additional_data else "a chapter"
        replacements["{purchased_institution}"] = additional_data.get("purchased_institution", "a university") if additional_data else "a university"
    
    elif vertical == "faith":
        replacements["{faith_group}"] = data.get("faith_group", "")
        replacements["{university}"] = data.get("university", "")
    
    elif vertical == "academic":
        replacements["{program}"] = data.get("program", data.get("program_name", ""))
        replacements["{department}"] = data.get("department", data.get("department_name", ""))
        replacements["{university}"] = data.get("university", "")
    
    elif vertical == "government":
        replacements["{org}"] = data.get("org", data.get("organization_name", ""))
        replacements["{university}"] = data.get("university", "")
    
    elif vertical == "cultural":
        replacements["{group}"] = data.get("group", data.get("faith_group_or_org", ""))
        replacements["{university}"] = data.get("university", "")
        replacements["{rep_name}"] = additional_data.get("rep_name", "a team member") if additional_data else "a team member"
    
    elif vertical == "sports":
        replacements["{team}"] = data.get("team", data.get("team_or_club", ""))
        replacements["{university}"] = data.get("university", "")
        replacements["{rep_name}"] = additional_data.get("rep_name", "a team member") if additional_data else "a team member"
    
    # Replace placeholders in template
    pitch = template
    for placeholder, value in replacements.items():
        pitch = pitch.replace(placeholder, str(value))
    
    return pitch


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
    Validate card schema per type and vertical.
    Returns (is_valid, error_message).
    """
    card_type = card.get("type")
    vertical = card.get("vertical")
    
    # If vertical is present but type is missing, assume it's a person card
    # (normalize_card will set type to "person" but validation happens after normalization)
    if not card_type and vertical:
        card_type = "person"
    
    if not card_type:
        return False, "Missing required field: type"
    
    # Validate vertical-specific person cards
    # If vertical is present, treat as person card (type may be auto-set by normalization)
    if vertical and (card_type == "person" or not card_type):
        if vertical not in VERTICAL_TYPES:
            return False, f"Invalid vertical: {vertical}. Must be one of: {', '.join(VERTICAL_TYPES.keys())}"
        
        vertical_config = VERTICAL_TYPES[vertical]
        required_fields = vertical_config.get("required_fields", [])
        
        # Check required fields
        missing_fields = []
        for field in required_fields:
            # Handle field name variations
            if field == "contact_name":
                value = card.get("name") or card.get("contact_name")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("name/contact_name")
            elif field == "position" or field == "role":
                value = card.get("role") or card.get("position")
                # Role is required but can be empty string for frats
                if vertical == "frats":
                    # For frats, allow empty role (empty string is OK)
                    # Only fail if the field is completely missing (None)
                    # Check if either role or position exists in the card
                    has_role_field = "role" in card or "position" in card
                    if not has_role_field:
                        missing_fields.append("role/position")
                    # If we have the field but value is None (shouldn't happen, but be safe)
                    elif value is None and not has_role_field:
                        missing_fields.append("role/position")
                else:
                    if not value or (isinstance(value, str) and not value.strip()):
                        missing_fields.append("role/position")
            elif field == "phone_number":
                value = card.get("phone") or card.get("phone_number")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("phone/phone_number")
            elif field == "faith_group_or_org":
                value = card.get("group") or card.get("faith_group_or_org")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("group/faith_group_or_org")
            elif field == "team_or_club":
                value = card.get("team") or card.get("team_or_club")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("team/team_or_club")
            elif field == "program_name":
                value = card.get("program") or card.get("program_name")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("program/program_name")
            elif field == "department_name":
                value = card.get("department") or card.get("department_name")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("department/department_name")
            elif field == "organization_name":
                value = card.get("org") or card.get("organization_name")
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append("org/organization_name")
            elif field == "email":
                # Email validation - check if it's in required or optional
                value = card.get(field)
                # Email is optional for cultural/sports/frats, so skip if missing
                if vertical in ["cultural", "sports", "frats"]:
                    # For these verticals, email is optional (empty string is OK)
                    pass
                else:
                    # For other verticals, email is required
                    if not value or (isinstance(value, str) and not value.strip()):
                        missing_fields.append(field)
            elif field == "phone":
                # Phone validation - allow empty strings for frats
                value = card.get(field)
                if vertical in ["cultural", "sports", "frats"]:
                    # For these verticals, phone is optional (empty string is OK)
                    pass
                else:
                    # For other verticals, phone is required
                    if not value or (isinstance(value, str) and not value.strip()):
                        missing_fields.append(field)
            elif field == "chapter" or field == "fraternity":
                # Chapter and fraternity are optional for frats
                value = card.get(field)
                if vertical == "frats":
                    # Allow empty/missing for frats
                    pass
                else:
                    # For other verticals that require these, validate
                    if not value or (isinstance(value, str) and not value.strip()):
                        missing_fields.append(field)
            else:
                value = card.get(field)
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append(field)
        
        if missing_fields:
            return False, f"{vertical_config['name']} card missing required fields: {', '.join(missing_fields)}"
        
        return True, None
    
    # Legacy validation for non-vertical cards
    if card_type not in ["person", "fraternity", "team", "business"]:
        return False, f"Invalid type: {card_type}. Must be one of: person, fraternity, team, business"
    
    # Type-specific validation (legacy)
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
    Normalize card: ensure id exists, clean up structure, map field variations.
    Returns normalized card dict.
    """
    normalized = card.copy()
    
    # Normalize field name variations for vertical-based cards
    vertical = normalized.get("vertical")
    if vertical and normalized.get("type") == "person":
        # Map common field variations to standard names
        field_mappings = {
            "contact_name": "name",
            "position": "role",
            "phone_number": "phone",
            "faith_group_or_org": "group",
            "team_or_club": "team",
            "program_name": "program",
            "department_name": "department",
            "organization_name": "org"
        }
        
        for old_field, new_field in field_mappings.items():
            if old_field in normalized and new_field not in normalized:
                normalized[new_field] = normalized[old_field]
    
    # Ensure id exists
    if not normalized.get("id"):
        normalized["id"] = generate_card_id(normalized)
    
    # Ensure type is set - if vertical is present but type is missing, assume person
    if not normalized.get("type"):
        if normalized.get("vertical"):
            normalized["type"] = "person"
        else:
            normalized["type"] = "person"  # Default to person for backward compatibility
    
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
    
    # Ensure vertical is preserved
    if vertical:
        normalized["vertical"] = vertical
    
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
    allow_missing_references: bool = False,
    upload_batch_id: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Store card in database.
    Returns (success, error_message, stored_card).
    
    Args:
        conn: Database connection
        card: Card dictionary to store
        allow_missing_references: If True, allow cards with missing references (for initial upload)
        upload_batch_id: Optional batch ID to track which upload this card came from
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


def get_vertical_info(vertical: Optional[str] = None) -> Dict[str, Any]:
    """
    Get information about vertical types.
    
    Args:
        vertical: Specific vertical to get info for, or None for all verticals
    
    Returns:
        Dictionary with vertical information
    """
    if vertical:
        if vertical in VERTICAL_TYPES:
            return {
                "vertical": vertical,
                **VERTICAL_TYPES[vertical]
            }
        return {}
    
    return {
        "verticals": {
            k: {
                "name": v["name"],
                "required_fields": v["required_fields"],
                "optional_fields": v.get("optional_fields", [])
            }
            for k, v in VERTICAL_TYPES.items()
        }
    }

