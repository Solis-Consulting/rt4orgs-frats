from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to last 10 digits.
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) > 10:
        return digits[-10:]
    return digits


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
    """
    target_frat = contact.get("fraternity", "").strip()
    target_frat_normalized = _normalize_fraternity_key(target_frat)
    target_inst_raw = (contact.get("institution") or contact.get("location") or "").strip()
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
