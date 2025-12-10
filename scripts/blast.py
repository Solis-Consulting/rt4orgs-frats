#!/usr/bin/env python3
from __future__ import annotations

import time
import random
from pathlib import Path
from typing import List, Dict, Any

from twilio.rest import Client

import sys
from pathlib import Path

# Add backend to path for imports
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from message_processor.utils import (
    load_leads,
    save_leads,
    load_sales_history,
    make_contact_event_folder,
    timestamp,
    ensure_parent_dir,
    save_json,
)
from message_processor.generate_message import generate_message
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER

BASE_DIR = BACKEND_DIR
TEMPLATE_PATH = BASE_DIR / "templates" / "messages.txt"
CONTACTS_DIR = BASE_DIR / "contacts"


def _contact_has_been_blasted(contact_name: str) -> bool:
    if not CONTACTS_DIR.exists():
        return False

    prefix = contact_name.replace(" ", "_")
    for folder in CONTACTS_DIR.iterdir():
        if folder.is_dir() and folder.name.startswith(prefix):
            return True
    return False


def find_unblasted_contacts(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in leads if not _contact_has_been_blasted(c.get("name", ""))]


def send_sms(to_number: str, body: str) -> Dict[str, Any]:
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    msg = client.messages.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        body=body,
    )
    return {"sid": msg.sid, "status": msg.status}


def write_initial_state(folder: Path, contact: Dict[str, Any], purchased_example: Dict[str, Any]):
    state_path = folder / "state.json"
    data = {
        "previous_state": None,
        "next_state": "initial_outreach",
        "intent": None,
        "message": None,
        "last_updated": timestamp(),
        "contact": contact,
        "purchased_example": purchased_example,
    }
    save_json(state_path, data)


def write_initial_message(folder: Path, message: str):
    msg_path = folder / "message.txt"
    ensure_parent_dir(msg_path)
    with msg_path.open("w", encoding="utf-8") as f:
        f.write(message)


def run_blast():
    print("\n--- RT4ORGS OUTBOUND BLAST ENGINE ---\n")

    leads = load_leads()
    sales_history = load_sales_history()

    unblasted = find_unblasted_contacts(leads)

    if not unblasted:
        print("All contacts have already been blasted.\n")
        return

    print("These contacts have NOT been blasted yet:\n")
    for i, c in enumerate(unblasted, 1):
        print(f"{i}. {c.get('name')} ({c.get('phone')}) – {c.get('fraternity')} {c.get('chapter')}")
    print("\nTotal:", len(unblasted))

    choice = input("\nBlast ALL unblasted contacts now? (y/n): ").strip().lower()
    if choice != "y":
        print("Aborting. No messages sent.\n")
        return

    print("\n--- SENDING MESSAGES ---\n")

    TARGET_MSGS_PER_MIN = 100
    BASE_DELAY = 60 / TARGET_MSGS_PER_MIN

    sent_count = 0
    start_time = time.time()

    for contact in unblasted:

        # 🚨 SKIP CONTACTS WITH NO PHONE NUMBER
        phone = contact.get("phone")
        if not phone or phone in ["", None]:
            print(f"Skipping {contact.get('name')} — missing phone number.\n")
            continue

        purchased_example = next(
            (
                row for row in sales_history
                if isinstance(row, dict)
                and row.get("fraternity") == contact.get("fraternity")
            ),
            None
        )

        message = generate_message(contact, purchased_example, TEMPLATE_PATH)

        print(f"Sending to {contact.get('name')} ({phone}):")
        sms_result = send_sms(phone, message)
        print(" → Twilio SID:", sms_result["sid"], "| Status:", sms_result["status"])

        folder = make_contact_event_folder(contact.get("name", "Unknown"))
        write_initial_state(folder, contact, purchased_example)
        write_initial_message(folder, message)

        save_leads(leads)

        jitter = random.uniform(-0.05, 0.05)
        delay = max(0.15, BASE_DELAY + jitter)
        time.sleep(delay)

        sent_count += 1

    total_time = time.time() - start_time
    print(f"\n--- BLAST COMPLETE ---")
    print(f"Sent: {sent_count} messages in {total_time:.1f} seconds "
          f"({sent_count / total_time:.1f} msg/sec)\n")


if __name__ == "__main__":
    run_blast()
