from __future__ import annotations

from typing import Any, Dict, Optional

# Root state
ROOT_STATE = "initial_outreach"

# Full SubTAM State Tree
CONVERSATION_TREE: Dict[str, list[str]] = {
    "initial_outreach": [
        "interest",
        "question",
        "pricing",
        "objection",
        "demo",
        "link_click",
        "purchase",
        "followup_24hr",
        "followup_10day",
        "dead",
    ],

    "interest": [
        "light_interest",
        "strong_interest",
        "confused_interest",
        "want_proof",
        "want_numbers",
    ],

    "question": [
        "pricing_question",
        "deliverable_question",
        "timeline_question",
        "data_source_question",
        "accuracy_question",
        "volume_question",
        "refund_question",
        "custom_request_question",
    ],

    "pricing": [
        "asks_for_price",
        "negotiates_price",
        "bulk_price_question",
        "confused_about_tiers",
    ],

    "objection": [
        "price_too_high",
        "no_time",
        "not_interested",
        "already_have_list",
        "send_info_only",
        "who_are_you",
        "sketchy_vibes",
        "long_delay",
    ],

    "demo": [
        "asks_for_example_list",
        "asks_for_specific_name",
        "wants_chapter_preview",
        "asks_for_pdf",
    ],

    "link_click": [
        "clicked_purchase_link",
        "clicked_example_link",
        "clicked_site",
    ],

    "purchase": [
        "confirmed_payment",
        "sent_venmo",
        "waiting_on_exec_board",
        "wants_invoice",
    ],

    "followup_24hr": [],
    "followup_10day": [],
    "dead": [],
}


def normalize_state(state: Optional[str]) -> str:
    """
    Normalize a state string to a valid state.
    Returns ROOT_STATE if state is invalid or None.
    """
    if not state:
        return ROOT_STATE
    if state == "initial_message_sent":
        return ROOT_STATE
    if state not in CONVERSATION_TREE:
        return ROOT_STATE
    return state


def transition(current_state: str, intent: Dict[str, Any]) -> str:
    """
    Compute the next state given the current state and intent.
    
    FIXED VERSION:
    - followup_24hr and followup_10day are NO LONGER terminal
    - Only "dead" is terminal
    - Re-engagement allowed from ANY state
    - Intent-driven state transitions favored (subcategory > category > fallback)
    
    Args:
        current_state: Current conversation state
        intent: Dict with 'category' and/or 'subcategory' keys
        
    Returns:
        Next state string
    """
    category = intent.get("category")
    sub = intent.get("subcategory")

    if current_state == "dead":
        return "dead"

    # 🎯 Re-engagement override: treat followups like root
    if current_state in ("followup_24hr", "followup_10day"):
        if category:
            # Prefer subcategory ALWAYS
            if sub:
                return sub
            return category

    # 🎯 Normal in-tree transitions
    if category:
        children = CONVERSATION_TREE.get(current_state, [])

        # If category is a valid child
        if category in children:
            # Prefer sub
            sub_children = CONVERSATION_TREE.get(category, [])
            if sub in sub_children:
                return sub
            return category

    # 🎯 Allow jumping back to root-level branches
    root_children = CONVERSATION_TREE.get(ROOT_STATE, [])
    if category in root_children:
        # again prefer sub
        sub_children = CONVERSATION_TREE.get(category, [])
        if sub in sub_children:
            return sub
        return category

    # 🚨 FINAL OVERRIDE:
    # If LLM confidently identified category/subcategory,
    # ALWAYS prefer sub → category → current
    if sub:
        return sub
    if category:
        return category

    # No update → stay
    return current_state
