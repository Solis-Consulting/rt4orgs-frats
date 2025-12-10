from __future__ import annotations

from typing import Dict, Any, Optional, List

from message_processor.classifier import classify_intent_semantic


def handle_inbound(
    contact: Dict[str, Any],
    incoming_text: str,
    prev_state: Optional[Dict[str, Any]] = None,
    purchased_example: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    MAIN ENTRYPOINT used by twilio_server.py.

    FIXED (FINAL VERSION):
    - Classifier now uses conversation history properly.
    - No state anchoring; history does not override classifier.
    - Markov sees evolving intent and transitions correctly.
    """

    # -------------------------
    # Load prior history
    # -------------------------
    history: List[str] = []

    if "history" in contact and isinstance(contact["history"], list):
        history = contact["history"]

    elif prev_state and "history" in prev_state:
        if isinstance(prev_state["history"], list):
            history = prev_state["history"]

    # -------------------------
    # Append new inbound message
    # -------------------------
    updated_history = history + [incoming_text]

    # -------------------------
    # CLASSIFY USING CONTEXT  (THIS IS THE CRITICAL FIX)
    # -------------------------
    intent = classify_intent_semantic(
        incoming_text,
        history=history   # <-- you forgot THIS
    )

    # -------------------------
    # Return bundle to twilio_server
    # -------------------------
    return {
        "intent": intent,
        "history": updated_history,
        "purchased_example": purchased_example,
    }
