from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to E.164 format (preserves + and country code).
    
    CRITICAL: This function preserves E.164 format (+1234567890) for consistency.
    All phone numbers should be stored and queried in E.164 format.
    """
    if not phone:
        return ""
    
    # Strip whitespace
    phone = phone.strip()
    
    # If already in E.164 format (starts with +), return as-is
    if phone.startswith("+"):
        # Ensure it's valid E.164 (digits after +)
        digits = "".join(ch for ch in phone[1:] if ch.isdigit())
        if digits:
            return "+" + digits
        return phone
    
    # If no +, extract digits and add +1 for US numbers
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return phone
    
    # If 10 digits, assume US and add +1
    if len(digits) == 10:
        return "+1" + digits
    
    # If 11 digits starting with 1, add +
    if len(digits) == 11 and digits[0] == "1":
        return "+" + digits
    
    # If already has country code (11+ digits), add +
    if len(digits) >= 11:
        return "+" + digits
    
    # Fallback: return with +1 prefix for US
    return "+1" + digits


def normalize_text(text: Optional[str]) -> str:
    """
    Normalize text: lowercase, strip, collapse whitespace.
    """
    if not text:
        return ""
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


def _get_deal_field(deal: Dict[str, Any], *field_names: str) -> str:
    """Get deal field value, trying multiple possible field name variations. Exported for use in blast.py."""
    """Get deal field value, trying multiple possible field name variations."""
    for field_name in field_names:
        value = deal.get(field_name) or deal.get(field_name.lower()) or deal.get(field_name.upper())
        if value:
            return str(value).strip()
    return ""


def _get_deal_abbreviation(deal: Dict[str, Any]) -> str:
    """Get fraternity abbreviation from deal - handles 'Abbreviation', 'fraternity', etc."""
    return _get_deal_field(deal, "Abbreviation", "abbreviation", "fraternity", "Fraternity").upper()


def _get_deal_institution(deal: Dict[str, Any]) -> str:
    """Get institution from deal."""
    return _get_deal_field(deal, "Institution", "institution").lower()


def _get_deal_chapter(deal: Dict[str, Any]) -> str:
    """Get chapter from deal."""
    return _get_deal_field(deal, "Chapter", "chapter").lower()


def _get_deal_names_given(deal: Dict[str, Any]) -> int:
    """Get names given from deal - handles 'Names given', 'names_given', etc."""
    value = deal.get("Names given") or deal.get("names given") or deal.get("names_given") or deal.get("Names Given")
    if value:
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
    return 0


def _normalize_institution_name(inst: str) -> str:
    """
    Normalize institution name for matching.
    Handles common variations like "UNC Chapel Hill" vs "University of North Carolina at Chapel Hill"
    """
    if not inst:
        return ""
    inst = inst.lower().strip()
    # Remove common prefixes/suffixes that might vary
    inst = inst.replace("university of ", "")
    inst = inst.replace("university ", "")
    inst = inst.replace(" at ", " ")
    # Normalize whitespace
    inst = normalize_text(inst)
    return inst


def _normalize_fraternity_key(key: str) -> str:
    """
    Normalize fraternity key for case-insensitive matching.
    Converts to uppercase for consistent matching.
    """
    return key.strip().upper() if key else ""


def _find_case_insensitive_key(d: Dict[str, Any], target_key: str) -> Optional[str]:
    """
    Find a key in a dictionary case-insensitively.
    Returns the actual key if found, None otherwise.
    """
    target_normalized = _normalize_fraternity_key(target_key)
    for key in d.keys():
        if _normalize_fraternity_key(key) == target_normalized:
            return key
    return None


def _extract_fraternity_from_card(card_data: Dict[str, Any]) -> str:
    """
    Extract fraternity information from multiple card fields.
    
    Checks fields in priority order:
    1. 'fraternity' field (direct)
    2. 'organization' field
    3. 'chapter' field (may contain fraternity name)
    4. 'name' field (may contain fraternity abbreviation)
    5. 'notes' or 'description' fields (may mention fraternity)
    6. 'tags' or 'labels' fields
    
    Returns the first non-empty fraternity value found, or empty string.
    """
    if not card_data:
        return ""
    
    # Priority 1: Direct fraternity field
    frat = card_data.get("fraternity") or card_data.get("Fraternity") or card_data.get("FRATERNITY")
    if frat and str(frat).strip():
        return str(frat).strip()
    
    # Priority 2: Organization field
    org = card_data.get("organization") or card_data.get("Organization") or card_data.get("org")
    if org and str(org).strip():
        return str(org).strip()
    
    # Priority 3: Chapter field (may contain full fraternity name)
    chapter = card_data.get("chapter") or card_data.get("Chapter")
    if chapter and str(chapter).strip():
        # Check if chapter contains a fraternity name (e.g., "Tau Kappa Epsilon - Colorado")
        chapter_str = str(chapter).strip()
        # Common fraternity patterns in chapter names
        frat_patterns = [
            "tau kappa epsilon", "tke",
            "beta upsilon chi", "byx",
            "sigma alpha epsilon", "sae",
            "phi gamma delta", "fiji",
            "sigma nu", "snu",
            "alpha tau omega", "ato",
            "delta chi", "dx",
            "kappa sigma", "ks",
            "pi kappa alpha", "pike",
            "phi delta theta", "phidelt"
        ]
        chapter_lower = chapter_str.lower()
        for pattern in frat_patterns:
            if pattern in chapter_lower:
                # Extract abbreviation if present, or return the pattern
                if "tke" in chapter_lower or "tau kappa epsilon" in chapter_lower:
                    return "TKE"
                elif "byx" in chapter_lower or "beta upsilon chi" in chapter_lower:
                    return "BYX"
                elif "sae" in chapter_lower or "sigma alpha epsilon" in chapter_lower:
                    return "SAE"
                elif "fiji" in chapter_lower or "phi gamma delta" in chapter_lower:
                    return "FIJI"
                elif "snu" in chapter_lower or "sigma nu" in chapter_lower:
                    return "SNU"
                elif "ato" in chapter_lower or "alpha tau omega" in chapter_lower:
                    return "ATO"
                elif "dx" in chapter_lower or "delta chi" in chapter_lower:
                    return "DX"
                elif "ks" in chapter_lower or "kappa sigma" in chapter_lower:
                    return "KS"
                elif "pike" in chapter_lower or "pi kappa alpha" in chapter_lower:
                    return "PIKE"
                elif "phidelt" in chapter_lower or "phi delta theta" in chapter_lower:
                    return "PhiDelt"
        # If no pattern match, return chapter as-is (might be fraternity name)
        return chapter_str
    
    # Priority 4: Name field (may contain fraternity abbreviation)
    name = card_data.get("name") or card_data.get("Name")
    if name:
        name_str = str(name).strip()
        # Check for common fraternity abbreviations in name
        # Look for patterns like "John Doe - TKE" or "TKE Chapter"
        name_upper = name_str.upper()
        known_abbrevs = ["TKE", "BYX", "SAE", "FIJI", "SNU", "ATO", "DX", "KS", "PIKE", "PHIDELT"]
        for abbrev in known_abbrevs:
            if abbrev in name_upper:
                return abbrev
    
    # Priority 5: Notes/Description fields (search for fraternity mentions)
    notes = card_data.get("notes") or card_data.get("Notes") or card_data.get("description") or card_data.get("Description")
    if notes:
        notes_str = str(notes).strip()
        notes_lower = notes_str.lower()
        # Check for fraternity patterns in notes
        frat_patterns = {
            "tke": "TKE", "tau kappa epsilon": "TKE",
            "byx": "BYX", "beta upsilon chi": "BYX",
            "sae": "SAE", "sigma alpha epsilon": "SAE",
            "fiji": "FIJI", "phi gamma delta": "FIJI",
            "snu": "SNU", "sigma nu": "SNU",
            "ato": "ATO", "alpha tau omega": "ATO",
            "dx": "DX", "delta chi": "DX",
            "ks": "KS", "kappa sigma": "KS",
            "pike": "PIKE", "pi kappa alpha": "PIKE",
            "phidelt": "PhiDelt", "phi delta theta": "PhiDelt"
        }
        for pattern, abbrev in frat_patterns.items():
            if pattern in notes_lower:
                return abbrev
    
    # Priority 6: Tags/Labels fields
    tags = card_data.get("tags") or card_data.get("Tags") or card_data.get("labels") or card_data.get("Labels")
    if tags:
        if isinstance(tags, list):
            for tag in tags:
                tag_str = str(tag).strip().upper()
                known_abbrevs = ["TKE", "BYX", "SAE", "FIJI", "SNU", "ATO", "DX", "KS", "PIKE", "PHIDELT"]
                if tag_str in known_abbrevs:
                    return tag_str
        elif isinstance(tags, str):
            tags_upper = str(tags).upper()
            known_abbrevs = ["TKE", "BYX", "SAE", "FIJI", "SNU", "ATO", "DX", "KS", "PIKE", "PHIDELT"]
            for abbrev in known_abbrevs:
                if abbrev in tags_upper:
                    return abbrev
    
    return ""


def find_matching_fraternity(
    contact: Dict[str, Any],
    sales_history: Dict[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """
    Relational proof-point selector with matching hierarchy:
    1. Same fraternity + same institution (best)
    2. Same fraternity, different school
    3. Same school, different fraternity (RELATIONAL MATCH)
    4. Fallback: TKE at University of Colorado Boulder (708 names)
    5. Final fallback: Highest names given deal
    
    Pure function: no side effects, returns matched deal or None.
    
    Now extracts fraternity from multiple card fields if 'fraternity' field is empty.
    """
    # Extract fraternity from multiple card fields (expanded scope)
    target_frat = _extract_fraternity_from_card(contact)
    target_frat_normalized = _normalize_fraternity_key(target_frat)
    
    # Log extraction details for debugging
    if target_frat:
        print(f"[MATCH] ✅ Extracted fraternity from card: '{target_frat}' (normalized: '{target_frat_normalized}')", flush=True)
    else:
        print(f"[MATCH] ⚠️ No fraternity found in card fields - will use fallback matching", flush=True)
        # Show what fields were checked for debugging
        checked_fields = ['fraternity', 'organization', 'chapter', 'name', 'notes', 'description', 'tags', 'labels']
        available_fields = [k for k in contact.keys() if k.lower() in [f.lower() for f in checked_fields]]
        if available_fields:
            print(f"[MATCH]   Card has these relevant fields: {available_fields}", flush=True)
    
    # Also extract institution from multiple fields
    target_inst_raw = (
        contact.get("institution") or 
        contact.get("Institution") or
        contact.get("location") or 
        contact.get("Location") or
        contact.get("university") or
        contact.get("University") or
        contact.get("school") or
        contact.get("School") or
        ""
    ).strip()
    target_inst = _normalize_institution_name(target_inst_raw)
    
    # Debug logging
    print(
        f"[MATCH] Target: fraternity='{target_frat}' (normalized: '{target_frat_normalized}') institution='{target_inst_raw}' (normalized: '{target_inst}')",
        flush=True,
    )
    
    # Collect all deals and match by abbreviation
    all_deals: List[Dict[str, Any]] = []
    available_frat_keys = []
    for frat_key, deal_list in sales_history.items():
        available_frat_keys.append(frat_key)
        if isinstance(deal_list, list):
            all_deals.extend(deal_list)
    
    print(f"[MATCH] Total deals in sales history: {len(all_deals)}", flush=True)
    print(f"[MATCH] Available fraternity keys: {available_frat_keys}", flush=True)
    
    # Normalize: also handle direct fraternity key matches (case-insensitive)
    # First try exact key match (case-insensitive)
    actual_key = _find_case_insensitive_key(sales_history, target_frat)
    if actual_key:
        deals_for_frat = sales_history.get(actual_key, [])
        if isinstance(deals_for_frat, list) and deals_for_frat:
            print(f"[MATCH] Found {len(deals_for_frat)} deals for fraternity key '{actual_key}' (matched '{target_frat}')", flush=True)
        else:
            deals_for_frat = []
    else:
        deals_for_frat = []
    
    # If no direct key match, try to find deals by abbreviation matching
    if not deals_for_frat:
        deals_for_frat = [
            deal for deal in all_deals
            if _normalize_fraternity_key(_get_deal_abbreviation(deal)) == target_frat_normalized
        ]
        if deals_for_frat:
            print(f"[MATCH] Found {len(deals_for_frat)} deals by abbreviation matching for '{target_frat}' (normalized: '{target_frat_normalized}')", flush=True)
        else:
            print(f"[MATCH] No deals found for fraternity '{target_frat}' (normalized: '{target_frat_normalized}')", flush=True)
    
    # -------------------------------------------------------
    # 1) PRIMARY MATCH: Same fraternity + same institution
    # -------------------------------------------------------
    if deals_for_frat and target_inst:
        matches = []
        for deal in deals_for_frat:
            deal_inst = _normalize_institution_name(_get_deal_institution(deal))
            if deal_inst == target_inst:
                matches.append(deal)
        if matches:
            # If multiple, pick highest Names Given
            matches.sort(key=_get_deal_names_given, reverse=True)
            matched = matches[0]
            print(
                f"[MATCH] ✅ PRIMARY MATCH: {_get_deal_abbreviation(matched)} at {_get_deal_institution(matched)} "
                f"({_get_deal_names_given(matched)} names)",
                flush=True,
            )
            return matched
    
    # -------------------------------------------------------
    # 2) SECONDARY MATCH: Same fraternity, different school
    # -------------------------------------------------------
    if deals_for_frat:
        # Sort by Names Given (highest first), or most recent
        sorted_deals = sorted(
            deals_for_frat,
            key=lambda d: (_get_deal_names_given(d),),
            reverse=True
        )
        matched = sorted_deals[0]
        print(
            f"[MATCH] ✅ SECONDARY MATCH: {_get_deal_abbreviation(matched)} at {_get_deal_institution(matched)} "
            f"({_get_deal_names_given(matched)} names) - same fraternity, different school",
            flush=True,
        )
        return matched
    
    # -------------------------------------------------------
    # 3) TERTIARY MATCH: Same institution, different fraternity (RELATIONAL)
    # -------------------------------------------------------
    if target_inst:
        inst_matches = []
        for deal in all_deals:
            deal_inst = _normalize_institution_name(_get_deal_institution(deal))
            if deal_inst == target_inst:
                inst_matches.append(deal)
        if inst_matches:
            inst_matches.sort(key=_get_deal_names_given, reverse=True)
            matched = inst_matches[0]
            print(
                f"[MATCH] ✅ TERTIARY MATCH (RELATIONAL): {_get_deal_abbreviation(matched)} at {_get_deal_institution(matched)} "
                f"({_get_deal_names_given(matched)} names) - same institution, different fraternity",
                flush=True,
            )
            return matched
        else:
            print(f"[MATCH] No deals found for institution '{target_inst}' (normalized from '{target_inst_raw}')", flush=True)
    
    # -------------------------------------------------------
    # 4) FALLBACK: TKE at University of Colorado Boulder (708 names)
    # -------------------------------------------------------
    for deal in all_deals:
        abbrev = _normalize_fraternity_key(_get_deal_abbreviation(deal))
        inst = _normalize_institution_name(_get_deal_institution(deal))
        if abbrev == "TKE" and "colorado boulder" in inst:
            print(
                f"[MATCH] ✅ FALLBACK MATCH: TKE at Colorado Boulder ({_get_deal_names_given(deal)} names)",
                flush=True,
            )
            return deal
    
    # If TKE Boulder not found, try any TKE deal
    tke_deals = [deal for deal in all_deals if _normalize_fraternity_key(_get_deal_abbreviation(deal)) == "TKE"]
    if tke_deals:
        tke_deals.sort(key=_get_deal_names_given, reverse=True)
        matched = tke_deals[0]
        print(
            f"[MATCH] ✅ FALLBACK MATCH: TKE at {_get_deal_institution(matched)} ({_get_deal_names_given(matched)} names)",
            flush=True,
        )
        return matched
    
    # -------------------------------------------------------
    # 5) FINAL FALLBACK: Highest names given deal
    # -------------------------------------------------------
    if all_deals:
        all_deals.sort(key=_get_deal_names_given, reverse=True)
        matched = all_deals[0]
        print(
            f"[MATCH] ✅ FINAL FALLBACK: {_get_deal_abbreviation(matched)} at {_get_deal_institution(matched)} "
            f"({_get_deal_names_given(matched)} names) - highest names given",
            flush=True,
        )
        return matched
    
    print("[MATCH] ❌ No match found - no deals available", flush=True)
    return None
