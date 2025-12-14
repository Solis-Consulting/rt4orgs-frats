# semantic_classifier.py

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict, Any
from message_processor.subtam_descriptions import SUBTAM_DESCRIPTIONS


# ---------- Load embedding model ----------
model = SentenceTransformer("all-MiniLM-L6-v2")

# ---------- Pre-compute state embeddings ----------
STATE_EMBEDDINGS = {
    state: model.encode(description)
    for state, description in SUBTAM_DESCRIPTIONS.items()
}


def cosine_similarity(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def state_to_category(state: str) -> str:
    """
    Convert a substate name like 'light_interest' → 'interest'.
    """
    return state.split("_")[0] if "_" in state else state


def classify_intent_semantic(message: str, history: List[str] | None = None) -> Dict[str, Any]:
    """
    Classify inbound message → nearest SubTAM node via embeddings.
    Uses entire conversation history as context.
    """
    if history is None:
        history = []

    # Combine context into one input string
    text = " | ".join(history + [message])
    query_embed = model.encode(text)

    best_state = None
    best_score = -1.0

    # Find nearest SubTAM node
    for state, embed in STATE_EMBEDDINGS.items():
        score = cosine_similarity(query_embed, embed)
        if score > best_score:
            best_score = score
            best_state = state

    category = state_to_category(best_state)

    return {
        "category": category,
        "subcategory": best_state,
        "confidence": best_score,
    }
