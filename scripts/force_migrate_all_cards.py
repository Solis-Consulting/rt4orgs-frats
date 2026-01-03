#!/usr/bin/env python3
"""
Force migration script - transforms ALL cards to 7-field format, regardless of current state.
This ensures all legacy fields are removed and cards are properly standardized.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv
from backend.cards import normalize_card

load_dotenv()

def get_conn():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)

def main():
    print("=" * 60)
    print("🔄 FORCE MIGRATION: Transform ALL cards to 7-field format")
    print("=" * 60)
    
    conn = get_conn()
    print("✅ Connected to database")
    
    # Fetch all person cards
    with conn.cursor() as cur:
        cur.execute("SELECT id, type, card_data FROM cards WHERE type = 'person'")
        cards = cur.fetchall()
    
    print(f"\n📥 Found {len(cards)} cards to migrate")
    
    migrated = 0
    errors = 0
    
    print("\n🔄 Migrating all cards (force mode)...")
    for idx, (card_id, card_type, card_data) in enumerate(cards):
        if not isinstance(card_data, dict):
            print(f"   ⚠️  Card {card_id}: Invalid card_data format, skipping")
            errors += 1
            continue
        
        try:
            # Always normalize, regardless of current state
            full_card = {
                "id": card_id,
                "type": "person",
                **card_data
            }
            
            normalized = normalize_card(full_card)
            
            # Extract just the card_data portion
            normalized_data = {
                k: v for k, v in normalized.items()
                if k not in ["id", "type", "sales_state", "owner", "vertical", "members", "contacts"]
            }
            
            # Update card in database
            with conn.cursor() as update_cur:
                update_cur.execute("""
                    UPDATE cards
                    SET card_data = %s::jsonb, updated_at = NOW()
                    WHERE id = %s
                """, (Json(normalized_data), card_id))
            
            migrated += 1
            
            # Show first few transformations
            if migrated <= 5:
                print(f"   ✅ {card_id}: {normalized_data.get('biz') or normalized_data.get('org', '?')} / {normalized_data.get('sector', '?')}")
            
            if (idx + 1) % 100 == 0:
                print(f"   ✅ Migrated {idx + 1}/{len(cards)} cards...")
        
        except Exception as e:
            print(f"   ❌ Error migrating card {card_id}: {e}")
            import traceback
            traceback.print_exc()
            errors += 1
    
    conn.commit()
    print(f"\n✅ Force migration complete!")
    print(f"   Migrated: {migrated}")
    print(f"   Errors: {errors}")
    
    conn.close()

if __name__ == "__main__":
    main()

