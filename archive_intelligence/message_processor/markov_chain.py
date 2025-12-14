from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from message_processor.utils import (
    make_contact_event_folder,
    save_json,
    load_leads,
    save_leads,
    timestamp,
)

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


class MarkovChain:
    """
    FIXED VERSION:
    - followup_24hr and followup_10day are NO LONGER terminal
    - Only "dead" is terminal
    - Re-engagement allowed from ANY state
    - Intent-driven state transitions favored (subcategory > category > fallback)
    """

    def __init__(self) -> None:
        self.tree = CONVERSATION_TREE

    # -------------------------
    # Normalize
    # -------------------------

    def _normalize_state(self, state: Optional[str]) -> str:
        if not state:
            return ROOT_STATE
        if state == "initial_message_sent":
            return ROOT_STATE
        if state not in self.tree:
            return ROOT_STATE
        return state

    # -------------------------
    # Transition Logic (FIXED)
    # -------------------------

    def next_state(self, current_state: str, intent: Dict[str, Any]) -> str:
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
            children = self.tree.get(current_state, [])

            # If category is a valid child
            if category in children:
                # Prefer sub
                sub_children = self.tree.get(category, [])
                if sub in sub_children:
                    return sub
                return category

        # 🎯 Allow jumping back to root-level branches
        root_children = self.tree.get(ROOT_STATE, [])
        if category in root_children:
            # again prefer sub
            sub_children = self.tree.get(category, [])
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

    # -------------------------
    # Update + Log (stateless)
    # -------------------------

    def update_state(
        self,
        contact: Dict[str, Any],
        message: str,
        intent: Dict[str, Any],
        purchased_example: Optional[Dict[str, Any]] = None,
        history: Optional[list[str]] = None,
    ) -> Dict[str, Any]:

        now = timestamp()

        current_state = self._normalize_state(contact.get("state"))
        next_state = self.next_state(current_state, intent)

        # Update contact in memory
        contact["state"] = next_state
        contact["last_updated"] = now
        contact["last_intent"] = intent

        if "history" in contact:
            del contact["history"]

        # Create logging folder
        folder = make_contact_event_folder(contact.get("name", "Unknown"), ts=now)

        state_payload = {
            "previous_state": current_state,
            "next_state": next_state,
            "intent": intent,
            "message": message,
            "last_updated": now,
            "contact": contact,
            "purchased_example": purchased_example,
        }

        save_json(folder / "state.json", state_payload)

        with (folder / "message.txt").open("w", encoding="utf-8") as f:
            f.write(message or "")

        ## Persist to leads.json
        leads = load_leads()
        for row in leads:
            if (
                row.get("name") == contact.get("name")
                and row.get("fraternity") == contact.get("fraternity")
            ):
                row.update({
                    "state": next_state,
                    "last_updated": now,
                    "last_intent": intent,
                })
                if "history" in row:
                    del row["history"]

        save_leads(leads)

        return {
            "folder": str(folder),
            "next_state": next_state,
            "intent": intent,
        }
