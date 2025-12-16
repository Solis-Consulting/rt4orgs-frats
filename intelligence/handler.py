from __future__ import annotations

from typing import Any, Dict, List, Optional

from intelligence.markov import normalize_state, transition, ROOT_STATE


def handle_inbound(
    conversation_row: Dict[str, Any],
    inbound_text: str,
    intent: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Pure function handler for inbound messages.
    
    Computes the next state based on current state and intent.
    No side effects, no DB calls, no filesystem I/O.
    
    Args:
        conversation_row: Dict containing conversation data including:
            - state: current state (optional, defaults to ROOT_STATE)
            - history: list of previous messages (optional)
        inbound_text: The incoming message text
        intent: Dict with 'category' and/or 'subcategory' keys
        
    Returns:
        Dict with:
            - next_state: The computed next state
            - intent: The intent that was passed in
            - updated_history: History with inbound_text appended
    """
    # Get current state, defaulting to ROOT_STATE
    current_state = normalize_state(conversation_row.get("state"))
    
    # Get history, defaulting to empty list
    history: List[str] = []
    if "history" in conversation_row and isinstance(conversation_row["history"], list):
        history = conversation_row["history"]
    
    # Append new inbound message to history
    updated_history = history + [inbound_text]
    
    # Compute next state using Markov transition
    next_state = transition(current_state, intent)
    
    return {
        "next_state": next_state,
        "intent": intent,
        "updated_history": updated_history,
        "previous_state": current_state,
    }
