#!/usr/bin/env python3

import os, json, re
from pathlib import Path

CONTACTS_DIR = Path(__file__).resolve().parent.parent / "backend" / "contacts"

# Extract base name by removing timestamp suffix
# Example: "Cooper_Berry_2025-12-08T19-47-40" → "Cooper_Berry"
NAME_PATTERN = re.compile(r"^(.*)_\d{4}-\d{2}-\d{2}T")

def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def extract_base_name(folder_name):
    m = NAME_PATTERN.match(folder_name)
    return m.group(1) if m else folder_name

def main():
    replies = {}  # base_name → list of (folder_path, state, message, timestamp)

    # Iterate through all timestamped folders
    for folder in CONTACTS_DIR.iterdir():
        if not folder.is_dir():
            continue

        base_name = extract_base_name(folder.name)

        state_file = folder / "state.json"
        message_file = folder / "message.txt"

        if not state_file.exists() or not message_file.exists():
            continue

        state_json = load_json(state_file)
        next_state = state_json.get("next_state", "unknown")
        timestamp = state_json.get("last_updated", "unknown")

        with open(message_file, "r") as f:
            message = f.read().strip()

        if base_name not in replies:
            replies[base_name] = []

        replies[base_name].append({
            "folder": folder.name,
            "state": next_state,
            "message": message,
            "timestamp": timestamp
        })

    # Now filter only contacts with ≥ 2 replies
    multi_contacts = {k: v for k, v in replies.items() if len(v) >= 2}

    # Organize by state
    grouped = {}  # state → list of (base_name, last_message)
    for base_name, msgs in multi_contacts.items():
        # sort by timestamp to get most recent
        msgs_sorted = sorted(msgs, key=lambda x: x["timestamp"])
        latest = msgs_sorted[-1]
        state = latest["state"]

        if state not in grouped:
            grouped[state] = []

        grouped[state].append((base_name, latest["message"]))

    # Pretty terminal output
    print("\n===== ACTIVE MULTI-REPLY CONTACTS =====")

    for state, items in grouped.items():
        print(f"\n── {state.upper()} ({len(items)})")
        for name, msg in items:
            short = msg.replace("\n", " ")[:120]
            print(f"   • {name}: {short}")

    print("\n========================================\n")
    print(f"Total multi-reply contacts: {sum(len(v) for v in grouped.values())}")

if __name__ == "__main__":
    main()
