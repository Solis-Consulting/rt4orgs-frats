#!/usr/bin/env python3
"""
Migration script to link existing conversations.phone to cards.id.
Matches conversations to cards by phone number.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.utils import normalize_phone


def get_conn():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    return conn


def bridge_conversations_to_cards(dry_run: bool = True):
    """
    Link conversations.phone to cards.id by matching phone numbers.
    
    Args:
        dry_run: If True, only show what would be updated without making changes.
    """
    conn = get_conn()
    
    print("\n" + "="*60)
    print("Bridge Conversations to Cards")
    print("="*60 + "\n")
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    else:
        print("⚠️  LIVE MODE - Changes will be committed\n")
    
    # Check if card_id column exists
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'conversations' AND column_name = 'card_id';
        """)
        has_card_id_column = cur.fetchone() is not None
    
    # Get all conversations without card_id (or all if column doesn't exist)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if has_card_id_column:
            cur.execute("""
                SELECT phone, contact_id, owner, state
                FROM conversations
                WHERE card_id IS NULL
                ORDER BY last_outbound_at DESC NULLS LAST, last_inbound_at DESC NULLS LAST;
            """)
        else:
            print("⚠️  card_id column doesn't exist yet. Run the schema migration first:")
            print("   psql $DATABASE_URL -f backend/db/schema.sql\n")
            cur.execute("""
                SELECT phone, contact_id, owner, state
                FROM conversations
                ORDER BY last_outbound_at DESC NULLS LAST, last_inbound_at DESC NULLS LAST;
            """)
        conversations = cur.fetchall()
    
    print(f"Found {len(conversations)} conversations without card_id\n")
    
    if len(conversations) == 0:
        print("No conversations to bridge.\n")
        return
    
    # Get all person cards with phone numbers
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, card_data->>'phone' as phone
            FROM cards
            WHERE type = 'person' AND card_data->>'phone' IS NOT NULL;
        """)
        cards = cur.fetchall()
    
    # Build phone -> card_id mapping (normalized)
    phone_to_card = {}
    for card in cards:
        phone = card['phone']
        if phone:
            normalized = normalize_phone(phone)
            # Store all possible card IDs for this phone (in case of duplicates)
            if normalized not in phone_to_card:
                phone_to_card[normalized] = []
            phone_to_card[normalized].append(card['id'])
    
    print(f"Found {len(cards)} person cards with phone numbers\n")
    
    # Match conversations to cards
    matches = []
    no_matches = []
    multiple_matches = []
    
    for conv in conversations:
        phone = conv['phone']
        normalized_phone = normalize_phone(phone)
        
        matching_cards = phone_to_card.get(normalized_phone, [])
        
        if len(matching_cards) == 0:
            no_matches.append({
                'phone': phone,
                'normalized': normalized_phone,
                'contact_id': conv.get('contact_id'),
                'owner': conv.get('owner'),
                'state': conv.get('state'),
            })
        elif len(matching_cards) == 1:
            matches.append({
                'phone': phone,
                'normalized': normalized_phone,
                'card_id': matching_cards[0],
                'contact_id': conv.get('contact_id'),
                'owner': conv.get('owner'),
                'state': conv.get('state'),
            })
        else:
            multiple_matches.append({
                'phone': phone,
                'normalized': normalized_phone,
                'card_ids': matching_cards,
                'contact_id': conv.get('contact_id'),
                'owner': conv.get('owner'),
                'state': conv.get('state'),
            })
    
    # Print summary
    print("="*60)
    print("MATCHING SUMMARY")
    print("="*60)
    print(f"✓ Exact matches (1 card): {len(matches)}")
    print(f"✗ No matches: {len(no_matches)}")
    print(f"⚠ Multiple matches: {len(multiple_matches)}\n")
    
    # Show sample matches
    if matches:
        print("Sample exact matches:")
        for match in matches[:5]:
            print(f"  Phone: {match['phone']} → Card: {match['card_id']}")
        if len(matches) > 5:
            print(f"  ... and {len(matches) - 5} more\n")
    
    # Show sample no matches
    if no_matches:
        print("\nSample no matches (no card found):")
        for nm in no_matches[:5]:
            print(f"  Phone: {nm['phone']} (normalized: {nm['normalized']})")
        if len(no_matches) > 5:
            print(f"  ... and {len(no_matches) - 5} more\n")
    
    # Show multiple matches
    if multiple_matches:
        print("\nSample multiple matches (ambiguous):")
        for mm in multiple_matches[:3]:
            print(f"  Phone: {mm['phone']} → Cards: {', '.join(mm['card_ids'])}")
        if len(multiple_matches) > 3:
            print(f"  ... and {len(multiple_matches) - 3} more\n")
    
    # Update database if not dry run
    if not dry_run:
        if not has_card_id_column:
            print("\n❌ Cannot update: card_id column doesn't exist. Run schema migration first.\n")
            return
        
        print("\n" + "="*60)
        print("UPDATING DATABASE")
        print("="*60 + "\n")
        
        updated_count = 0
        
        with conn.cursor() as cur:
            for match in matches:
                cur.execute("""
                    UPDATE conversations
                    SET card_id = %s
                    WHERE phone = %s AND card_id IS NULL;
                """, (match['card_id'], match['phone']))
                updated_count += cur.rowcount
        
        print(f"✓ Updated {updated_count} conversations with card_id\n")
        
        if multiple_matches:
            print(f"⚠ Skipped {len(multiple_matches)} conversations with multiple card matches")
            print("  (manual review required)\n")
    
    print("="*60)
    print("Bridge complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Bridge conversations to cards by phone number")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually update the database (default is dry-run)"
    )
    
    args = parser.parse_args()
    
    try:
        bridge_conversations_to_cards(dry_run=not args.execute)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)

