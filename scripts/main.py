from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

import sys
from pathlib import Path

# Add backend to path for imports
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Local imports
from message_processor.utils import (
    load_leads,
    load_sales_history,
    find_matching_fraternity,
)
from message_processor.generate_message import generate_message
from blast import run_blast
from config import SERVER_HOST, SERVER_PORT

# Note: Twilio server should be run separately now (python backend/twilio_server.py)
# This script no longer starts the Twilio server in a thread

BASE_DIR = BACKEND_DIR
TEMPLATE_PATH = BASE_DIR / "templates" / "messages.txt"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------
# 1. Generate outbound messages (original run_batch)
# ------------------------------------------------------
def generate_all_messages() -> Dict[str, Any]:
    leads: List[Dict[str, Any]] = load_leads()
    if not leads:
        return {"error": "No leads found."}

    sales_history = load_sales_history()
    results: List[Dict[str, Any]] = []

    for contact in leads:
        purchased_example = find_matching_fraternity(contact, sales_history)

        message = generate_message(
            contact=contact,
            purchased_example=purchased_example,
            template_path=TEMPLATE_PATH,
        )

        name_safe = contact.get("name", "Unknown").replace(" ", "_")
        out_path = OUTPUT_DIR / f"{name_safe}.txt"
        out_path.write_text(message, encoding="utf-8")

        results.append(
            {
                "contact": contact,
                "message": message,
                "output_file": str(out_path),
            }
        )

    return {"count": len(results), "results": results}


# ------------------------------------------------------
# 2. Main execution entrypoint
# ------------------------------------------------------
def main():
    print("\n========================================")
    print("   RT4ORGS FULL OPERATIONS CONSOLE")
    print("========================================\n")

    # A) Generate all messages
    print("Generating all outbound messages...\n")
    result = generate_all_messages()
    print(f" → Generated messages for {result['count']} contacts.\n")

    # B) Optionally run the outbound blast engine
    do_blast = input("Run outbound blast now? (y/n): ").strip().lower()
    if do_blast == "y":
        run_blast()
    else:
        print("Skipping blast.\n")

    # C) Note about Twilio server
    print("\n" + "="*40)
    print("To start the Twilio webhook server, run:")
    print(f"  cd backend && python twilio_server.py")
    print("="*40 + "\n")


if __name__ == "__main__":
    main()
