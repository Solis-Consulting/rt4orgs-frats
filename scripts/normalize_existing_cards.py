#!/usr/bin/env python3
"""
Migration script to normalize existing cards in the database to the standardized format.
This updates all existing cards to use only the 6 standard fields: ig, org, name, univ, email, phone
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv
from backend.cards import normalize_card

load_dotenv()

def normalize_existing_cards():
    """Normalize all existing cards in the database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable is not set")
        return False
    
    print("🔌 Connecting to database...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    
    try:
        with conn.cursor() as cur:
            # Get all cards
            print("📋 Fetching all cards...")
            cur.execute("""
                SELECT id, type, card_data, sales_state, owner
                FROM cards
            """)
            rows = cur.fetchall()
            print(f"✅ Found {len(rows)} cards to normalize")
            
            updated_count = 0
            skipped_count = 0
            
            for row in rows:
                card_id = row[0]
                card_type = row[1]
                card_data = row[2]
                sales_state = row[3]
                owner = row[4]
                
                # Build card dict for normalization
                card = {
                    "id": card_id,
                    "type": card_type,
                    "sales_state": sales_state,
                    "owner": owner,
                }
                
                # Merge card_data into card dict
                if isinstance(card_data, dict):
                    card.update(card_data)
                elif isinstance(card_data, str):
                    import json
                    try:
                        card.update(json.loads(card_data))
                    except:
                        pass
                
                # Normalize the card
                normalized = normalize_card(card)
                
                # Extract card_data (everything except system fields)
                new_card_data = {k: v for k, v in normalized.items() 
                               if k not in ["id", "type", "sales_state", "owner", "vertical", "members", "contacts"]}
                
                # Update the card in the database
                try:
                    cur.execute("""
                        UPDATE cards
                        SET card_data = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (Json(new_card_data), card_id))
                    
                    updated_count += 1
                    if updated_count % 100 == 0:
                        print(f"  ✅ Normalized {updated_count} cards...")
                except Exception as e:
                    print(f"  ⚠️  Error updating card {card_id}: {e}")
                    skipped_count += 1
                    continue
        
        print(f"\n✅ Migration complete!")
        print(f"   Updated: {updated_count} cards")
        print(f"   Skipped: {skipped_count} cards")
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = normalize_existing_cards()
    sys.exit(0 if success else 1)

