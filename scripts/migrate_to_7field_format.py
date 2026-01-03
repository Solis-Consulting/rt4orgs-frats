#!/usr/bin/env python3
"""
Migration script to transform existing cards to the new 7-field format:
ig, biz/org, sector, name, univ, email, phone

Handles:
- Legacy fraternity cards (with role, chapter, fraternity, metadata, etc.)
- Legacy faith group cards
- New scraped cards (already closer to format)
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import sys
import psycopg2
from psycopg2.extras import Json
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from backend.cards import normalize_card, ALL_VALID_SECTORS

load_dotenv()

# Check for --yes flag to skip confirmation
SKIP_CONFIRMATION = "--yes" in sys.argv or os.getenv("MIGRATE_YES", "").lower() == "true"

def get_conn():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)

def analyze_cards(conn) -> Dict[str, int]:
    """Analyze existing cards to categorize them."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, type, card_data FROM cards WHERE type = 'person'")
        cards = cur.fetchall()
    
    categories = {
        "legacy_fraternity": 0,
        "legacy_faith": 0,
        "already_standardized": 0,
        "needs_migration": 0
    }
    
    for card_id, card_type, card_data in cards:
        if not isinstance(card_data, dict):
            categories["needs_migration"] += 1
            continue
        
        # Check if already in 7-field format (has sector and biz/org)
        has_sector = "sector" in card_data and card_data.get("sector")
        has_biz_org = ("biz" in card_data and card_data.get("biz")) or ("org" in card_data and card_data.get("org"))
        
        if has_sector and has_biz_org:
            categories["already_standardized"] += 1
            continue
        
        # Check for legacy fraternity indicators (fraternity, chapter, role, metadata, insta)
        legacy_fraternity_fields = ["fraternity", "chapter", "role", "metadata", "insta", "other_social", "tags"]
        has_legacy_fraternity = any(field in card_data for field in legacy_fraternity_fields)
        
        if has_legacy_fraternity:
            categories["legacy_fraternity"] += 1
        # Check for legacy faith indicators
        elif any(keyword in str(card_data.get("name", "")).lower() + " " + str(card_data.get("org", "")).lower()
                 for keyword in ["faith", "church", "religious", "ministry", "campus", "christian", "catholic", "baptist"]):
            categories["legacy_faith"] += 1
        else:
            # Needs migration but unclear category
            categories["needs_migration"] += 1
    
    return categories

def migrate_card(card_data: Dict[str, Any], card_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Migrate a single card to 7-field format.
    Returns (normalized_card, transformation_log)
    """
    original = card_data.copy()
    
    # Use normalize_card to transform
    # We need to merge card_data with system fields for normalization
    full_card = {
        "id": card_id,
        "type": "person",
        **card_data
    }
    
    normalized = normalize_card(full_card)
    
    # Extract just the card_data portion (exclude system fields)
    normalized_data = {
        k: v for k, v in normalized.items()
        if k not in ["id", "type", "sales_state", "owner", "vertical", "members", "contacts"]
    }
    
    # Log what was transformed
    transformation_log = {
        "card_id": card_id,
        "fields_before": list(original.keys()),
        "fields_after": list(normalized_data.keys()),
        "discarded_fields": [k for k in original.keys() if k not in normalized_data and k not in ["id", "type"]],
        "sector": normalized_data.get("sector", ""),
        "biz_org": normalized_data.get("biz") or normalized_data.get("org", "")
    }
    
    return normalized_data, transformation_log

def main():
    """Main migration function."""
    print("=" * 60)
    print("🔄 MIGRATION: Transform cards to 7-field format")
    print("=" * 60)
    
    try:
        conn = get_conn()
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 1
    
    # Analyze existing cards
    print("\n📊 Analyzing existing cards...")
    categories = analyze_cards(conn)
    total = sum(categories.values())
    print(f"   Total cards: {total}")
    print(f"   Legacy fraternity: {categories['legacy_fraternity']}")
    print(f"   Legacy faith: {categories['legacy_faith']}")
    print(f"   Already standardized: {categories['already_standardized']}")
    print(f"   Needs migration: {categories['needs_migration']}")
    
    # Confirm before proceeding (unless --yes flag is set)
    if not SKIP_CONFIRMATION:
        response = input("\n⚠️  This will update all cards in the database. Continue? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Migration cancelled")
            return 0
    else:
        print("\n⚠️  Running migration with --yes flag (skipping confirmation)")
    
    # Fetch all person cards
    print("\n📥 Fetching all person cards...")
    with conn.cursor() as cur:
        cur.execute("SELECT id, type, card_data FROM cards WHERE type = 'person'")
        cards = cur.fetchall()
    
    print(f"   Found {len(cards)} cards to migrate")
    
    # Migrate each card
    migrated = 0
    skipped = 0
    errors = 0
    transformation_logs = []
    
    print("\n🔄 Migrating cards...")
    for idx, (card_id, card_type, card_data) in enumerate(cards):
        if not isinstance(card_data, dict):
            print(f"   ⚠️  Card {card_id}: Invalid card_data format, skipping")
            errors += 1
            continue
        
        # Check if already standardized (has sector and biz/org)
        has_sector = "sector" in card_data and card_data.get("sector")
        has_biz_org = ("biz" in card_data and card_data.get("biz")) or ("org" in card_data and card_data.get("org"))
        
        if has_sector and has_biz_org:
            # Already in 7-field format, but verify it has all 7 fields
            required_fields = ["ig", "sector", "name", "univ", "email", "phone"]
            has_all_fields = all(field in card_data for field in required_fields)
            if has_all_fields:
                skipped += 1
                if (idx + 1) % 100 == 0:
                    print(f"   ⏭️  Skipped {idx + 1}/{len(cards)} (already standardized)...")
                continue
        
        try:
            normalized_data, log = migrate_card(card_data, card_id)
            transformation_logs.append(log)
            
            # Update card in database
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE cards
                    SET card_data = %s::jsonb, updated_at = NOW()
                    WHERE id = %s
                """, (Json(normalized_data), card_id))
            
            migrated += 1
            if (idx + 1) % 100 == 0:
                print(f"   ✅ Migrated {idx + 1}/{len(cards)} cards...")
        
        except Exception as e:
            print(f"   ❌ Error migrating card {card_id}: {e}")
            import traceback
            traceback.print_exc()
            errors += 1
    
    # Commit changes
    conn.commit()
    print(f"\n✅ Migration complete!")
    print(f"   Migrated: {migrated}")
    print(f"   Skipped (already standardized): {skipped}")
    print(f"   Errors: {errors}")
    
    # Show sample transformations
    print("\n📋 Sample transformations:")
    for log in transformation_logs[:5]:
        print(f"\n   Card: {log['card_id']}")
        print(f"   Sector: {log['sector']}, Type: {log['biz_org']}")
        print(f"   Discarded fields: {', '.join(log['discarded_fields']) if log['discarded_fields'] else 'none'}")
    
    # Verify migration
    print("\n🔍 Verifying migration...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM cards 
            WHERE type = 'person' 
            AND card_data ? 'sector'
        """)
        count_with_sector = cur.fetchone()[0]
        print(f"   Cards with 'sector' field: {count_with_sector}/{total}")
        
        cur.execute("""
            SELECT COUNT(*) FROM cards 
            WHERE type = 'person' 
            AND (card_data ? 'biz' OR card_data ? 'org')
        """)
        count_with_biz_org = cur.fetchone()[0]
        print(f"   Cards with 'biz' or 'org' field: {count_with_biz_org}/{total}")
    
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())

