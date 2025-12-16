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


def find_matching_fraternity(
    contact: Dict[str, Any],
    sales_history: Dict[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """
    Matching logic with fallback priority:
    1. Exact fraternity & chapter match
    2. Any record under the same fraternity
    3. SAE Nationals deal at Towson University
    4. First record in the entire sales_history (last fallback)
    
    Pure function: no side effects, returns matched deal or None.
    """
    fraternity = contact.get("fraternity", "").strip().upper()
    chapter = contact.get("chapter", "").strip()
    location_norm = (contact.get("location") or contact.get("institution") or chapter).strip().lower()

    # Normalize key for sales_history lookup
    deals_for_frat = sales_history.get(fraternity, [])

    # -------------------------------------------------------
    # 1) EXACT MATCH: fraternity + institution/chapter
    # -------------------------------------------------------
    if deals_for_frat:
        for deal in deals_for_frat:
            inst = (deal.get("institution") or deal.get("chapter") or "").lower()
            if inst == location_norm:
                return deal

    # -------------------------------------------------------
    # 2) ANY DEAL under same fraternity
    # -------------------------------------------------------
    if deals_for_frat:
        return deals_for_frat[0]

    # -------------------------------------------------------
    # 3) FALLBACK: SAE Nationals at Towson
    # -------------------------------------------------------
    sae = sales_history.get("SAE", [])
    for deal in sae:
        inst = (deal.get("institution") or "").lower()
        if "towson" in inst:
            return deal

    # -------------------------------------------------------
    # 4) FINAL FALLBACK: First deal in entire file
    # -------------------------------------------------------
    for _, deal_list in sales_history.items():
        if deal_list:
            return deal_list[0]

    return None
