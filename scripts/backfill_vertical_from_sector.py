#!/usr/bin/env python3
"""
Backfill vertical field for existing cards that have sector but no vertical.
This script updates cards in the database to infer vertical from sector.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import psycopg2
from typing import Any, Dict
from dotenv import load_dotenv
from backend.cards import sector_to_vertical, store_card

load_dotenv()

def get_conn():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    return conn

def main():
    """Main backfill function."""
    print("=" * 60)
    print("🔄 BACKFILL: Infer vertical from sector for existing cards")
    print("=" * 60)
    
    try:
        conn = get_conn()
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 1
    
    updated_count = 0
    skipped_count = 0
    errors_count = 0
    
    try:
        with conn.cursor() as cur:
            # Find cards with sector but no vertical (or empty vertical)
            cur.execute("""
                SELECT id, type, card_data, sales_state, owner
                FROM cards
                WHERE type = 'person'
                AND card_data->>'sector' IS NOT NULL
                AND card_data->>'sector' != ''
                AND (
                    card_data->>'vertical' IS NULL
                    OR card_data->>'vertical' = ''
                )
            """)
            cards_to_update = cur.fetchall()
        
        print(f"\n📥 Found {len(cards_to_update)} cards with sector but no vertical")
        print("\n🔄 Backfilling vertical from sector...")
        
        for card_id, card_type, card_data, sales_state, owner in cards_to_update:
            if not isinstance(card_data, dict):
                skipped_count += 1
                continue
            
            sector = card_data.get("sector", "")
            biz_org = "biz" if card_data.get("biz") else ("org" if card_data.get("org") else None)
            
            if not sector or not biz_org:
                skipped_count += 1
                continue
            
            # Infer vertical from sector
            inferred_vertical = sector_to_vertical(sector, biz_org)
            
            if not inferred_vertical:
                # No mapping for this sector (e.g., Interest-Based, BIZ sectors)
                skipped_count += 1
                continue
            
            # Reconstruct full card
            full_card = {
                "id": card_id,
                "type": card_type,
                "sales_state": sales_state,
                "owner": owner,
                "vertical": inferred_vertical,  # Set the vertical
                **card_data  # Merge existing card_data
            }
            
            # Store updated card
            success, error_msg, stored_card = store_card(conn, full_card, allow_missing_references=True)
            
            if success:
                updated_count += 1
                name = card_data.get("name", card_id)
                print(f"   ✅ {name[:40]:40} | {sector:20} → {inferred_vertical}")
            else:
                errors_count += 1
                print(f"   ❌ Failed to update {card_id}: {error_msg}")
                
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        import traceback
        print(traceback.format_exc())
        errors_count += len(cards_to_update) - updated_count
    finally:
        conn.close()
    
    print("\n✅ Backfill complete!")
    print(f"   Updated: {updated_count}")
    print(f"   Skipped: {skipped_count} (no mapping or already set)")
    print(f"   Errors: {errors_count}")
    
    return 0 if errors_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

