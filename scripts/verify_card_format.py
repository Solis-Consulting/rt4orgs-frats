#!/usr/bin/env python3
"""
Verification script to check which cards are in the standardized 7-field format
and which still need migration.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import psycopg2
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)

def verify_cards():
    """Verify all cards and report their format status."""
    conn = get_conn()
    
    with conn.cursor() as cur:
        cur.execute("SELECT id, type, card_data FROM cards WHERE type = 'person'")
        cards = cur.fetchall()
    
    print("=" * 60)
    print("🔍 CARD FORMAT VERIFICATION")
    print("=" * 60)
    print(f"\nTotal cards: {len(cards)}\n")
    
    standardized = []
    needs_migration = []
    
    required_fields = ["ig", "sector", "name", "univ", "email", "phone"]
    
    for card_id, card_type, card_data in cards:
        if not isinstance(card_data, dict):
            needs_migration.append({
                "id": card_id,
                "reason": "Invalid card_data format"
            })
            continue
        
        # Check for 7-field format
        has_biz_org = ("biz" in card_data and card_data.get("biz")) or ("org" in card_data and card_data.get("org"))
        has_sector = "sector" in card_data and card_data.get("sector")
        has_all_fields = all(field in card_data for field in required_fields)
        
        if has_biz_org and has_sector and has_all_fields:
            standardized.append({
                "id": card_id,
                "biz_org": card_data.get("biz") or card_data.get("org", ""),
                "sector": card_data.get("sector", ""),
                "name": card_data.get("name", "")
            })
        else:
            missing = []
            if not has_biz_org:
                missing.append("biz/org")
            if not has_sector:
                missing.append("sector")
            for field in required_fields:
                if field not in card_data:
                    missing.append(field)
            
            needs_migration.append({
                "id": card_id,
                "reason": f"Missing: {', '.join(missing)}",
                "has_legacy_fields": any(field in card_data for field in ["fraternity", "chapter", "role", "metadata", "insta"])
            })
    
    print(f"✅ Standardized (7-field format): {len(standardized)}")
    if standardized:
        print("\n   Sample standardized cards:")
        for card in standardized[:5]:
            print(f"   - {card['id']}: {card['biz_org'].upper()} / {card['sector']} ({card['name']})")
    
    print(f"\n⚠️  Needs migration: {len(needs_migration)}")
    if needs_migration:
        print("\n   Cards needing migration:")
        for card in needs_migration[:10]:
            legacy_note = " [HAS LEGACY FIELDS]" if card.get("has_legacy_fields") else ""
            print(f"   - {card['id']}: {card['reason']}{legacy_note}")
        if len(needs_migration) > 10:
            print(f"   ... and {len(needs_migration) - 10} more")
    
    print("\n" + "=" * 60)
    if needs_migration:
        print("💡 Run migration: python3 scripts/migrate_to_7field_format.py --yes")
    else:
        print("✅ All cards are standardized!")
    print("=" * 60)
    
    conn.close()
    return len(needs_migration) == 0

if __name__ == "__main__":
    all_standardized = verify_cards()
    sys.exit(0 if all_standardized else 1)

