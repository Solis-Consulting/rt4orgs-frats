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


def find_matching_fraternity(
    contact: Dict[str, Any],
    sales_history: Dict[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """
    Relational proof-point selector with matching hierarchy:
    1. Same fraternity + same institution (best)
    2. Same fraternity, different school
    3. Same school, different fraternity
    4. Fallback: TKE at University of Colorado Boulder (708 names)
    
    Pure function: no side effects, returns matched deal or None.
    """
    target_frat = contact.get("fraternity", "").strip().upper()
    target_inst = (contact.get("institution") or contact.get("location") or "").strip().lower()
    
    # Collect all deals and match by abbreviation
    all_deals: List[Dict[str, Any]] = []
    for frat_key, deal_list in sales_history.items():
        if isinstance(deal_list, list):
            all_deals.extend(deal_list)
    
    # Normalize: also handle direct fraternity key matches
    deals_for_frat = sales_history.get(target_frat, [])
    if isinstance(deals_for_frat, list) and deals_for_frat:
        pass  # Will use this below
    else:
        # Try to find deals by abbreviation matching
        deals_for_frat = [
            deal for deal in all_deals
            if _get_deal_abbreviation(deal) == target_frat
        ]
    
    # -------------------------------------------------------
    # 1) PRIMARY MATCH: Same fraternity + same institution
    # -------------------------------------------------------
    if deals_for_frat and target_inst:
        matches = [
            deal for deal in deals_for_frat
            if _get_deal_institution(deal) == target_inst
        ]
        if matches:
            # If multiple, pick highest Names Given
            matches.sort(key=_get_deal_names_given, reverse=True)
            return matches[0]
    
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
        return sorted_deals[0]
    
    # -------------------------------------------------------
    # 3) TERTIARY MATCH: Same institution, different fraternity
    # -------------------------------------------------------
    if target_inst:
        inst_matches = [
            deal for deal in all_deals
            if _get_deal_institution(deal) == target_inst
        ]
        if inst_matches:
            inst_matches.sort(key=_get_deal_names_given, reverse=True)
            return inst_matches[0]
    
    # -------------------------------------------------------
    # 4) FALLBACK: TKE at University of Colorado Boulder (708 names)
    # -------------------------------------------------------
    for deal in all_deals:
        abbrev = _get_deal_abbreviation(deal)
        inst = _get_deal_institution(deal)
        if abbrev == "TKE" and "colorado boulder" in inst:
            return deal
    
    # If TKE Boulder not found, try any TKE deal
    tke_deals = [deal for deal in all_deals if _get_deal_abbreviation(deal) == "TKE"]
    if tke_deals:
        tke_deals.sort(key=_get_deal_names_given, reverse=True)
        return tke_deals[0]
    
    # -------------------------------------------------------
    # 5) FINAL FALLBACK: Highest names given deal
    # -------------------------------------------------------
    if all_deals:
        all_deals.sort(key=_get_deal_names_given, reverse=True)
        return all_deals[0]
    
    return None
