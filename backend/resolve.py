"""
Target resolution engine for messaging.
Resolves target specs (contact, entity, query) to lists of contact cards.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import psycopg2
from backend.cards import get_card
from backend.query import build_list_query


def resolve_target(
    conn: Any,
    target: Dict[str, Any]
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Resolve target spec to list of contact cards.
    
    Supports:
    - {type: "contact", id: "..."} -> single contact
    - {type: "entity", entity_type: "fraternity", id: "..."} -> expand members
    - {type: "query", where: {...}} -> JSONB query filter
    
    Returns (contact_cards, error_message).
    """
    target_type = target.get("type")
    
    if target_type == "contact":
        card_id = target.get("id")
        if not card_id:
            return [], "Missing 'id' in contact target"
        
        card = get_card(conn, card_id)
        if not card:
            return [], f"Card not found: {card_id}"
        
        if card["type"] != "person":
            return [], f"Card {card_id} is not a person card"
        
        # Extract phone from card_data
        phone = card["card_data"].get("phone")
        if not phone:
            return [], f"Contact card {card_id} has no phone number"
        
        return [card], None
    
    elif target_type == "entity":
        entity_type = target.get("entity_type")
        entity_id = target.get("id")
        
        if not entity_id:
            return [], "Missing 'id' in entity target"
        
        if not entity_type:
            return [], "Missing 'entity_type' in entity target"
        
        entity_card = get_card(conn, entity_id)
        if not entity_card:
            return [], f"Entity card not found: {entity_id}"
        
        if entity_card["type"] != entity_type:
            return [], f"Card {entity_id} is not a {entity_type} card"
        
        # Get members/contacts based on entity type
        member_ids = []
        if entity_type == "fraternity":
            member_ids = entity_card["card_data"].get("members", [])
        elif entity_type == "team":
            member_ids = entity_card["card_data"].get("members", [])
        elif entity_type == "business":
            member_ids = entity_card["card_data"].get("contacts", [])
        else:
            return [], f"Unsupported entity_type: {entity_type}"
        
        if not member_ids:
            return [], f"Entity {entity_id} has no members/contacts"
        
        # Fetch all member/contact cards
        contact_cards = []
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(member_ids))
            cur.execute(f"""
                SELECT id, type, card_data, sales_state, owner, created_at, updated_at
                FROM cards
                WHERE id IN ({placeholders}) AND type = 'person';
            """, tuple(member_ids))
            
            for row in cur.fetchall():
                card = {
                    "id": row[0],
                    "type": row[1],
                    "card_data": row[2],
                    "sales_state": row[3],
                    "owner": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                    "updated_at": row[6].isoformat() if row[6] else None,
                }
                # Only include cards with phone numbers
                phone = card["card_data"].get("phone")
                if phone:
                    contact_cards.append(card)
        
        if not contact_cards:
            return [], f"Entity {entity_id} has no members/contacts with phone numbers"
        
        return contact_cards, None
    
    elif target_type == "query":
        where = target.get("where")
        if not where:
            return [], "Missing 'where' clause in query target"
        
        # Build query
        query, params = build_list_query(where=where)
        
        # Execute query
        contact_cards = []
        with conn.cursor() as cur:
            cur.execute(query, params)
            
            for row in cur.fetchall():
                card = {
                    "id": row[0],
                    "type": row[1],
                    "card_data": row[2],
                    "sales_state": row[3],
                    "owner": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                    "updated_at": row[6].isoformat() if row[6] else None,
                }
                # Only include person cards with phone numbers
                if card["type"] == "person":
                    phone = card["card_data"].get("phone")
                    if phone:
                        contact_cards.append(card)
        
        if not contact_cards:
            return [], "Query returned no contact cards with phone numbers"
        
        return contact_cards, None
    
    else:
        return [], f"Unsupported target type: {target_type}"


def extract_phones_from_cards(cards: List[Dict[str, Any]]) -> List[str]:
    """Extract phone numbers from contact cards."""
    phones = []
    for card in cards:
        phone = card["card_data"].get("phone")
        if phone:
            phones.append(phone)
    return phones

