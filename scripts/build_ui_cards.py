#!/usr/bin/env python3
import json
import re
from pathlib import Path

LEADS_PATH = Path("/Users/alanelrod/Desktop/rt4orgs-frats-v4/leads.json")
OUTPUT_PATH = Path("/Users/alanelrod/Desktop/rt4orgs-frats-v4/output/ui_cards.json")

def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def main():
    print("Loading leads.json...")
    leads = json.loads(LEADS_PATH.read_text())

    cards = []
    skipped = 0

    for lead in leads:
        name = (lead.get("name") or "").strip()
        phone = (lead.get("phone") or "").strip()

        if not name or not phone:
            skipped += 1
            continue

        fraternity = lead.get("fraternity", "")
        chapter = lead.get("chapter", "")

        card_id = slugify("_".join(filter(None, [name, fraternity, chapter])))

        card_data = {
            k: v for k, v in lead.items()
            if k not in {"name", "phone"}
        }

        cards.append({
            "id": card_id,
            "type": "person",
            "name": name,
            "phone": phone,
            "card_data": card_data
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cards, indent=2))

    print(f"Built {len(cards)} UI cards")
    print(f"Skipped {skipped}")
    print(f"Wrote → {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
