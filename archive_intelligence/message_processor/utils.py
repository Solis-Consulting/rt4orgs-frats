from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

BASE_DIR = Path(__file__).resolve().parent.parent  # Go up to backend/
DATA_DIR = BASE_DIR / "data"
CONTACTS_DIR = BASE_DIR / "contacts"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

PathLike = Union[str, Path]


def ensure_parent_dir(path: PathLike) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: PathLike, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default if default is not None else {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: PathLike, data: Any) -> None:
    path = ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def safe_folder_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^\w\-.]", "", name)
    return name


def make_contact_event_folder(
    contact_name: str,
    base_dir: Optional[PathLike] = None,
    ts: Optional[str] = None,
) -> Path:
    if base_dir is None:
        base_dir = CONTACTS_DIR
    if ts is None:
        ts = timestamp()
    ts_safe = ts.replace(":", "-")
    folder_name = f"{safe_folder_name(contact_name)}_{ts_safe}"
    path = Path(base_dir) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


# ------------------------------------------------------------
# REQUIRED BY twilio_server.py
# (Alias wrapper – keeps backward compatibility)
# ------------------------------------------------------------
def create_new_event_folder(contact_name: str) -> Path:
    return make_contact_event_folder(contact_name)


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


# ------------------------------------------------------------
# PHONE LOOKUP
# ------------------------------------------------------------
def _normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) > 10:
        return digits[-10:]
    return digits


def lookup_contact_by_phone(
    leads: List[Dict[str, Any]],
    phone: str
) -> Dict[str, Any]:
    """
    Look up an existing contact by phone number (normalized).
    If not found, auto-create a minimal contact record.
    """
    target = _normalize_phone(phone)

    for row in leads:
        if _normalize_phone(str(row.get("phone", ""))) == target:
            return row

    contact: Dict[str, Any] = {
        "name": target,
        "role": "",
        "phone": phone,
        "email": "",
        "insta": "",
        "other_social": "",
        "fraternity": "",
        "chapter": "",
        "state": "initial_outreach",
    }
    leads.append(contact)
    return contact


# ------------------------------------------------------------
# LOAD LATEST MARKOV STATE
# ------------------------------------------------------------
def load_latest_event_state(contact_name: str) -> Dict[str, Any]:
    """
    Load the newest state.json for a given contact.
    Returns {} if none exist.
    """
    prefix = safe_folder_name(contact_name)

    if not CONTACTS_DIR.exists():
        return {}

    folders = [
        p for p in CONTACTS_DIR.iterdir()
        if p.is_dir() and p.name.startswith(prefix + "_")
    ]

    if not folders:
        return {}

    folders.sort(key=lambda p: p.name, reverse=True)
    latest = folders[0]

    state_file = latest / "state.json"
    if not state_file.exists():
        return {}

    return load_json(state_file, default={})


# ------------------------------------------------------------
# MATCHING + LOADING
# ------------------------------------------------------------
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
    """

    fraternity = contact.get("fraternity", "").strip().upper()
    chapter = contact.get("chapter", "").strip()
    location_norm = (contact.get("location") or contact.get("institution") or chapter).strip().lower()

    # Normalize key for sales_history lookup
    # Your keys appear uppercase (e.g., "SAE", "ATO", etc.)
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



def leads_path() -> Path:
    return DATA_DIR / "leads.json"


def sales_history_path() -> Path:
    return DATA_DIR / "sales_history.json"


def load_leads() -> List[Dict[str, Any]]:
    data = load_json(leads_path(), default=[])
    return data if isinstance(data, list) else []


def save_leads(leads: List[Dict[str, Any]]) -> None:
    save_json(leads_path(), leads)


def load_sales_history() -> Dict[str, List[Dict[str, Any]]]:
    data = load_json(sales_history_path(), default={})
    return data if isinstance(data, dict) else {}
