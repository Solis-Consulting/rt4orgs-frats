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

# Valid sector categories
RT4ORGS_SECTORS = {
    "Greek Life",
    "Faith-Based",
    "Cultural Identity",
    "Honors Academic",
    "Professional Career",
    "Club Sports",
    "Student Government",
    "Arts Performance",
    "Interest-Based"  # Treat as "unclassified/needs review"
}

RT4BIZ_SECTORS = {
    "Housing",
    "Fitness",
    "Salons"
}

ALL_VALID_SECTORS = RT4ORGS_SECTORS | RT4BIZ_SECTORS


def classify_card_deterministic(card: Dict[str, Any], respect_existing: bool = True) -> tuple[str, str]:
    """
    Rule-first deterministic classification with clear precedence.
    Returns (biz_org, sector) tuple.
    
    Precedence order (FIRST MATCH WINS):
    1. Locked classification (if respect_existing=True and classification_locked=True)
    2. Explicit structural indicators (fraternity)
    3. Explicit sector already set (respect user/previous classification)
    4. Hard keyword rules (deterministic)
    5. Default fallback (Interest-Based = unclassified)
    
    This is NOT fuzzy-first. Rules are authoritative.
    
    Args:
        card: Card dictionary
        respect_existing: If True, respect existing sector/biz_org if already set and valid
    """
    # PRECEDENCE 1: Locked classification (highest priority - user override)
    if respect_existing and card.get("classification_locked"):
        existing_sector = card.get("sector", "")
        existing_biz = card.get("biz")
        existing_org = card.get("org")
        if existing_sector and existing_sector in ALL_VALID_SECTORS:
            if existing_biz:
                return ("biz", existing_sector)
            elif existing_org:
                return ("org", existing_sector)
            # Determine from sector
            if existing_sector in RT4BIZ_SECTORS:
                return ("biz", existing_sector)
            else:
                return ("org", existing_sector)
    
    card_lower = {}
    for k, v in card.items():
        if isinstance(v, str):
            card_lower[k] = v.lower()
        else:
            card_lower[k] = str(v).lower() if v else ""
    
    name = card_lower.get("name", "")
    org = card_lower.get("org", "")
    combined_text = f"{name} {org}".strip()
    
    # PRECEDENCE 2: Explicit structural indicators (fraternity field)
    if "fraternity" in card and card.get("fraternity"):
        return ("org", "Greek Life")
    
    # PRECEDENCE 3: Explicit sector already set (respect user/previous classification)
    # Only respect if it's not "Interest-Based" (which means unclassified)
    if respect_existing and "sector" in card and card.get("sector"):
        sector = card.get("sector")
        if sector in ALL_VALID_SECTORS and sector != "Interest-Based":
            # Sector is set and valid - determine biz/org from sector
            if sector in RT4BIZ_SECTORS:
                return ("biz", sector)
            elif sector in RT4ORGS_SECTORS:
                return ("org", sector)
    
    # PRECEDENCE 3: Explicit biz/org field
    if "biz" in card and card.get("biz"):
        # If biz is set but no sector, try to determine sector from name
        if any(kw in combined_text for kw in ["apartment", "housing", "residential", "leasing"]):
            return ("biz", "Housing")
        elif any(kw in combined_text for kw in ["gym", "fitness", "sportsplex", "athletic", "workout", "training"]):
            return ("biz", "Fitness")
        elif any(kw in combined_text for kw in ["salon", "spa", "aesthetics", "beauty", "hair", "nail", "wax", "waxing", "med spa", "medical spa", "clinic", "dermatology", "skincare"]):
            return ("biz", "Salons")
        else:
            return ("biz", "Fitness")  # Default biz sector
    
    if "org" in card and card.get("org"):
        # If org is set but no sector, try to determine from name
        if any(kw in combined_text for kw in ["faith", "church", "religious", "ministry", "campus", "christian", "catholic", "baptist"]):
            return ("org", "Faith-Based")
        elif any(kw in combined_text for kw in ["athletic", "sports", "club", "league", "team"]):
            return ("org", "Club Sports")
        else:
            return ("org", "Interest-Based")  # Unclassified org
    
    # PRECEDENCE 4: Hard keyword rules (deterministic, not fuzzy)
    # BIZ rules (check first - businesses are more specific)
    if any(kw in combined_text for kw in ["apartment", "housing", "residential", "leasing", "rental"]):
        return ("biz", "Housing")
    
    if any(kw in combined_text for kw in ["gym", "fitness", "sportsplex", "athletic center", "athletics center", "workout", "training", "crossfit", "yoga studio", "fitness center"]):
        return ("biz", "Fitness")
    
    if any(kw in combined_text for kw in ["salon", "spa", "aesthetics", "beauty", "hair", "nail", "barber", "cosmetic", "wax", "waxing", "med spa", "medical spa", "clinic", "dermatology", "skincare", "facial", "massage", "wellness center"]):
        return ("biz", "Salons")
    
    # ORG rules
    if any(kw in combined_text for kw in ["faith", "church", "religious", "ministry", "campus", "christian", "catholic", "baptist", "worship"]):
        return ("org", "Faith-Based")
    
    if any(kw in combined_text for kw in ["athletic", "sports club", "sports team", "athletics", "club sports", "intramural", "tennis club", "golf club", "swim club", "soccer club", "basketball club"]):
        return ("org", "Club Sports")
    
    if any(kw in combined_text for kw in ["student government", "sg", "asb", "student council"]):
        return ("org", "Student Government")
    
    if any(kw in combined_text for kw in ["honors", "honor society", "academic", "scholarship"]):
        return ("org", "Honors Academic")
    
    if any(kw in combined_text for kw in ["cultural", "heritage", "ethnic", "diversity"]):
        return ("org", "Cultural Identity")
    
    if any(kw in combined_text for kw in ["arts", "theater", "drama", "music", "performance", "band", "choir"]):
        return ("org", "Arts Performance")
    
    if any(kw in combined_text for kw in ["professional", "career", "business", "networking", "alumni"]):
        return ("org", "Professional Career")
    
    # PRECEDENCE 5: Default fallback (treat as unclassified)
    # Interest-Based means "needs review", not a real classification
    return ("org", "Interest-Based")


def analyze_batch_context(cards: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Analyze a batch of cards to determine dominant sector pattern.
    Returns context info if clear pattern exists (>50% threshold).
    
    Returns:
        {
            "dominant_sector": "Salons",
            "dominant_biz_org": "biz",
            "sector_distribution": {"Salons": 8, "Interest-Based": 2},
            "confidence": 0.8
        }
        or None if no clear pattern
    """
    if not cards or len(cards) < 2:
        return None
    
    sector_counts = {}
    biz_org_counts = {"biz": 0, "org": 0}
    total_classified = 0
    
    for card in cards:
        # Handle both card dicts with card_data and direct card_data dicts
        if isinstance(card, dict) and "card_data" in card:
            card_data = card.get("card_data", {})
        else:
            card_data = card
        
        if not isinstance(card_data, dict):
            continue
        
        sector = card_data.get("sector", "")
        biz_org = "biz" if card_data.get("biz") else ("org" if card_data.get("org") else None)
        
        if sector and sector != "Interest-Based":
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            total_classified += 1
            if biz_org:
                biz_org_counts[biz_org] = biz_org_counts.get(biz_org, 0) + 1
    
    if total_classified == 0:
        return None
    
    # Find dominant sector (must be >50% of classified cards)
    threshold = max(2, total_classified * 0.5)  # At least 50% or 2 cards minimum
    dominant_sector = None
    dominant_count = 0
    
    for sector, count in sector_counts.items():
        if count > dominant_count and count >= threshold:
            dominant_sector = sector
            dominant_count = count
    
    if not dominant_sector:
        return None
    
    # Determine dominant biz/org
    dominant_biz_org = None
    if dominant_sector in RT4BIZ_SECTORS:
        dominant_biz_org = "biz"
    elif dominant_sector in RT4ORGS_SECTORS:
        dominant_biz_org = "org"
    
    confidence = dominant_count / total_classified if total_classified > 0 else 0
    
    return {
        "dominant_sector": dominant_sector,
        "dominant_biz_org": dominant_biz_org,
        "sector_distribution": sector_counts,
        "confidence": confidence,
        "total_cards": len(cards),
        "classified_cards": total_classified
    }


def classify_with_batch_context(card: Dict[str, Any], batch_context: Optional[Dict[str, Any]] = None) -> tuple[str, str]:
    """
    Classify card with optional batch context hints.
    If card is Interest-Based and batch has dominant sector, use batch context as hint.
    
    Args:
        card: Card dictionary
        batch_context: Result from analyze_batch_context() or None
    
    Returns:
        (biz_org, sector) tuple
    """
    # First, try normal classification
    biz_org, sector = classify_card_deterministic(card, respect_existing=True)
    
    # If classified as Interest-Based and we have batch context, try to improve
    if sector == "Interest-Based" and batch_context:
        dominant_sector = batch_context.get("dominant_sector")
        dominant_biz_org = batch_context.get("dominant_biz_org")
        confidence = batch_context.get("confidence", 0)
        
        # Only use batch context if confidence is high (>60%)
        if dominant_sector and dominant_biz_org and confidence > 0.6:
            # Re-check with batch context as hint
            # Look for any keywords that might match the dominant sector
            card_lower = {}
            for k, v in card.items():
                if isinstance(v, str):
                    card_lower[k] = v.lower()
                else:
                    card_lower[k] = str(v).lower() if v else ""
            
            name = card_lower.get("name", "")
            org = card_lower.get("org", "")
            combined_text = f"{name} {org}".strip()
            
            # If dominant sector is Salons, check for salon-related keywords we might have missed
            if dominant_sector == "Salons":
                salon_keywords = ["wax", "waxing", "clinic", "med", "spa", "aesthetic", "beauty", "skin", "facial", "massage", "glow"]
                if any(kw in combined_text for kw in salon_keywords):
                    return (dominant_biz_org, dominant_sector)
            
            # If dominant sector is Fitness, check for fitness-related keywords
            elif dominant_sector == "Fitness":
                fitness_keywords = ["athletic", "sport", "gym", "fitness", "workout", "training", "center"]
                if any(kw in combined_text for kw in fitness_keywords):
                    return (dominant_biz_org, dominant_sector)
            
            # If dominant sector is Housing, check for housing-related keywords
            elif dominant_sector == "Housing":
                housing_keywords = ["apartment", "housing", "residential", "leasing", "rental"]
                if any(kw in combined_text for kw in housing_keywords):
                    return (dominant_biz_org, dominant_sector)
            
            # For other sectors, if batch context is very strong (>80%), use it
            if confidence > 0.8:
                # Only if card doesn't have strong conflicting signals
                # Check if name contains words that clearly indicate different sector
                conflicting_keywords = {
                    "Salons": ["gym", "fitness", "apartment", "housing"],
                    "Fitness": ["salon", "spa", "apartment", "housing"],
                    "Housing": ["gym", "fitness", "salon", "spa"]
                }
                
                conflicting = conflicting_keywords.get(dominant_sector, [])
                has_conflict = any(kw in combined_text for kw in conflicting)
                
                if not has_conflict:
                    return (dominant_biz_org, dominant_sector)
    
    return (biz_org, sector)

# Vertical type definitions
VERTICAL_TYPES = {
    "frats": {
        "name": "Fraternities",
        "required_fields": ["name", "phone"],
        "optional_fields": ["tags", "metadata", "email", "role", "chapter", "fraternity", "program", "university"],
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
    org = card.get("org", "")
    
    parts = [card_type, name]
    if org:
        parts.append(org)
    
    return "_".join(slugify(part) for part in parts if part)


def validate_card_schema(card: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate card schema - allows 7 standard fields: ig, biz/org, sector, name, univ, email, phone
    Also accepts legacy fields during migration (role, chapter, fraternity, metadata, tags, insta, other_social, etc.)
    Returns (is_valid, error_message).
    """
    card_type = card.get("type")
    
    if not card_type:
        return False, "Missing required field: type"
    
    if card_type not in ["person", "fraternity", "team", "business"]:
        return False, f"Invalid type: {card_type}. Must be one of: person, fraternity, team, business"
    
    # Standard 7 fields that are allowed
    standard_fields = {"ig", "biz", "org", "sector", "name", "univ", "email", "phone"}
    # Legacy fields that are accepted but will be normalized (for migration compatibility)
    legacy_fields = {
        "role", "tags", "chapter", "fraternity", "metadata", "insta", "other_social",
        "university", "school", "organization", "organization_name", "group", "team",
        "instagram", "phone_number", "contact_name", "faith_group", "program", "department"
    }
    # System fields that are allowed (not part of card_data)
    system_fields = {"id", "type", "sales_state", "owner", "vertical"}
    # Entity-specific fields
    entity_fields = {"members", "contacts"}
    
    # Check that only standard fields, legacy fields, system fields, and entity fields are present
    invalid_fields = []
    for field in card.keys():
        if field not in standard_fields and field not in legacy_fields and field not in system_fields and field not in entity_fields:
            invalid_fields.append(field)
    
    if invalid_fields:
        return False, f"Card contains invalid fields: {', '.join(invalid_fields)}. Standard fields are: ig, biz/org, sector, name, univ, email, phone"
    
    # Validate biz/org field if present (must be "biz" or "org")
    biz_org = card.get("biz") or card.get("org")
    if biz_org and biz_org not in ["biz", "org"]:
        return False, f"Invalid biz/org value: {biz_org}. Must be 'biz' or 'org'"
    
    # Validate sector if present (must be one of the valid sectors)
    sector = card.get("sector")
    if sector and sector not in ALL_VALID_SECTORS:
        return False, f"Invalid sector: {sector}. Must be one of: {', '.join(sorted(ALL_VALID_SECTORS))}"
    
    # All fields are optional (can be empty strings), but validate that name exists for person cards
    if card_type == "person":
        if "name" not in card:
            return False, "Person card missing required field: name"
    
    # For entity types, validate structure
    elif card_type == "fraternity":
        if "name" not in card:
            return False, "Fraternity card missing required field: name"
        members = card.get("members", [])
        if not isinstance(members, list):
            return False, "Fraternity card 'members' must be an array"
    
    elif card_type == "team":
        if "name" not in card:
            return False, "Team card missing required field: name"
        members = card.get("members", [])
        if not isinstance(members, list):
            return False, "Team card 'members' must be an array"
    
    elif card_type == "business":
        if "name" not in card:
            return False, "Business card missing required field: name"
        contacts = card.get("contacts", [])
        if not isinstance(contacts, list):
            return False, "Business card 'contacts' must be an array"
    
    return True, None


def normalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize card: ensure id exists, clean up structure, standardize to 7 fields.
    Returns normalized card dict with fields in order: ig, biz/org, sector, name, univ, email, phone
    
    Handles:
    - Legacy fraternity cards (with insta, fraternity, chapter, role, metadata, etc.)
    - Legacy faith cards
    - New scraped cards (with ig, org, name, univ, email, phone)
    """
    # System fields that should be preserved
    system_fields = ["id", "type", "sales_state", "owner", "vertical", "members", "contacts"]
    
    normalized = {}
    
    # Preserve system fields
    for sys_field in system_fields:
        if sys_field in card:
            normalized[sys_field] = card[sys_field]
    
    # Extract ig (field 1) - check multiple sources
    ig_value = ""
    if "ig" in card and card["ig"]:
        ig_value = str(card["ig"]).strip()
    elif "insta" in card and card["insta"]:
        ig_value = str(card["insta"]).strip()
    elif "instagram" in card and card["instagram"]:
        ig_value = str(card["instagram"]).strip()
    elif "metadata" in card and isinstance(card["metadata"], dict):
        metadata = card["metadata"]
        if "insta" in metadata and metadata["insta"]:
            ig_value = str(metadata["insta"]).strip()
    
    # Extract biz/org (field 2) and determine sector (field 3)
    # Use deterministic rule-first classification (NOT fuzzy NLP)
    biz_org_value, sector_value = classify_card_deterministic(card)
    
    # Extract name (field 4)
    name_value = ""
    if "name" in card and card["name"]:
        name_value = str(card["name"]).strip()
    elif "contact_name" in card and card["contact_name"]:
        name_value = str(card["contact_name"]).strip()
    
    # Extract univ (field 5)
    univ_value = ""
    if "univ" in card and card["univ"]:
        univ_value = str(card["univ"]).strip()
    elif "university" in card and card["university"]:
        univ_value = str(card["university"]).strip()
    elif "school" in card and card["school"]:
        univ_value = str(card["school"]).strip()
    
    # Extract email (field 6) - always include even if empty
    email_value = ""
    if "email" in card:
        email_value = str(card["email"]).strip() if card["email"] else ""
    
    # Extract phone (field 7)
    phone_value = ""
    if "phone" in card and card["phone"]:
        phone_value = str(card["phone"]).strip()
    elif "phone_number" in card and card["phone_number"]:
        phone_value = str(card["phone_number"]).strip()
    
    # Build normalized card with fields in exact order: ig, biz/org, sector, name, univ, email, phone
    # Note: Python dicts maintain insertion order (Python 3.7+)
    # IMPORTANT: Only include the 7 standard fields, remove all legacy fields
    normalized["ig"] = ig_value
    # Set either "biz" or "org" field (not both)
    if biz_org_value == "biz":
        normalized["biz"] = "biz"
    else:
        normalized["org"] = "org"
    normalized["sector"] = sector_value
    normalized["name"] = name_value
    normalized["univ"] = univ_value
    normalized["email"] = email_value
    normalized["phone"] = phone_value
    
    # Remove any legacy fields that might have been preserved
    legacy_fields_to_remove = ["role", "tags", "chapter", "fraternity", "metadata", "insta", "other_social", 
                               "instagram", "phone_number", "contact_name", "university", "school", 
                               "organization", "organization_name", "group", "team", "faith_group", 
                               "program", "department"]
    for legacy_field in legacy_fields_to_remove:
        normalized.pop(legacy_field, None)
    
    # Ensure type is set (default to person)
    if "type" not in normalized:
        normalized["type"] = card.get("type", "person")
    
    # Ensure id exists (after normalization so it uses correct fields)
    if not normalized.get("id"):
        normalized["id"] = generate_card_id(normalized)
    
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
    """Get a single card by ID. Normalizes card_data to ensure 7-field format."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, type, card_data, sales_state, owner, created_at, updated_at
            FROM cards
            WHERE id = %s;
        """, (card_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        # Normalize the card_data to ensure it's in 7-field format
        card_data = row[2] or {}
        if isinstance(card_data, dict):
            # Create full card dict for normalization
            full_card = {
                "id": row[0],
                "type": row[1],
                "sales_state": row[3],
                "owner": row[4],
                **card_data
            }
            normalized = normalize_card(full_card)
            # Extract just the card_data portion (exclude system fields)
            card_data = {
                k: v for k, v in normalized.items()
                if k not in ["id", "type", "sales_state", "owner", "vertical", "members", "contacts"]
            }
        
        return {
            "id": row[0],
            "type": row[1],
            "card_data": card_data,
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

