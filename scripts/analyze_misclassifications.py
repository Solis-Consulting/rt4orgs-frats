#!/usr/bin/env python3
"""
Analysis script to find misclassified cards, especially those in Interest-Based
that should be re-classified based on batch context.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import psycopg2
from typing import Dict, Any, List
from dotenv import load_dotenv
from backend.cards import analyze_batch_context, classify_with_batch_context, classify_card_deterministic

load_dotenv()

def get_conn():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)

def analyze_misclassifications():
    """Analyze cards for misclassifications, especially Interest-Based ones."""
    conn = get_conn()
    
    print("=" * 60)
    print("🔍 MISCLASSIFICATION ANALYSIS")
    print("=" * 60)
    
    # Get all Interest-Based cards
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, type, card_data, upload_batch_id
            FROM cards
            WHERE type = 'person' 
            AND card_data->>'sector' = 'Interest-Based'
            ORDER BY upload_batch_id, created_at
        """)
        interest_based_cards = cur.fetchall()
    
    print(f"\n📊 Found {len(interest_based_cards)} cards classified as Interest-Based")
    
    if len(interest_based_cards) == 0:
        print("✅ No Interest-Based cards found - all cards are properly classified!")
        conn.close()
        return
    
    # Group by upload batch
    batches = {}
    for card_id, card_type, card_data, upload_batch_id in interest_based_cards:
        batch_id = upload_batch_id or "no_batch"
        if batch_id not in batches:
            batches[batch_id] = []
        batches[batch_id].append({
            "id": card_id,
            "type": card_type,
            "card_data": card_data,
            "upload_batch_id": upload_batch_id
        })
    
    print(f"\n📦 Grouped into {len(batches)} batch(es)")
    
    # Analyze each batch
    suggestions = []
    
    for batch_id, cards in batches.items():
        print(f"\n{'=' * 60}")
        print(f"📦 Batch: {batch_id}")
        print(f"   Cards: {len(cards)}")
        
        # Get all cards in this batch (not just Interest-Based)
        with conn.cursor() as cur:
            if batch_id == "no_batch":
                # For cards without batch_id, try to find by created_at proximity
                if cards:
                    first_card = cards[0]
                    cur.execute("""
                        SELECT id, type, card_data, upload_batch_id
                        FROM cards
                        WHERE type = 'person'
                        AND created_at >= (
                            SELECT created_at - INTERVAL '10 seconds'
                            FROM cards
                            WHERE id = %s
                        )
                        AND created_at <= (
                            SELECT created_at + INTERVAL '10 seconds'
                            FROM cards
                            WHERE id = %s
                        )
                        ORDER BY created_at
                    """, (first_card["id"], first_card["id"]))
            else:
                cur.execute("""
                    SELECT id, type, card_data, upload_batch_id
                    FROM cards
                    WHERE type = 'person' AND upload_batch_id = %s
                    ORDER BY created_at
                """, (batch_id,))
            
            all_batch_cards = []
            for row in cur.fetchall():
                all_batch_cards.append({
                    "id": row[0],
                    "type": row[1],
                    "card_data": row[2] or {},
                    "upload_batch_id": row[3]
                })
        
        # Analyze batch context
        batch_context = analyze_batch_context(all_batch_cards)
        
        if batch_context:
            print(f"   ✅ Clear pattern detected:")
            print(f"      Dominant sector: {batch_context['dominant_sector']} ({batch_context['dominant_biz_org']})")
            print(f"      Confidence: {batch_context['confidence']:.1%}")
            print(f"      Distribution: {batch_context['sector_distribution']}")
            
            # Suggest re-classifications for Interest-Based cards
            for card in cards:
                card_data = card["card_data"] or {}
                name = card_data.get("name", card["id"])
                
                # Re-classify with batch context
                full_card = {
                    "id": card["id"],
                    "type": "person",
                    **card_data
                }
                new_biz_org, new_sector = classify_with_batch_context(full_card, batch_context)
                
                if new_sector != "Interest-Based":
                    suggestions.append({
                        "card_id": card["id"],
                        "name": name,
                        "current": "Interest-Based",
                        "suggested": new_sector,
                        "biz_org": new_biz_org,
                        "batch_id": batch_id,
                        "confidence": batch_context["confidence"]
                    })
                    print(f"      💡 {name[:40]:40} → {new_biz_org.upper()} / {new_sector}")
        else:
            print(f"   ⚠️  No clear pattern in batch")
            
            # Still try to improve individual cards
            for card in cards:
                card_data = card["card_data"] or {}
                name = card_data.get("name", card["id"])
                
                full_card = {
                    "id": card["id"],
                    "type": "person",
                    **card_data
                }
                new_biz_org, new_sector = classify_card_deterministic(full_card, respect_existing=False)
                
                if new_sector != "Interest-Based":
                    suggestions.append({
                        "card_id": card["id"],
                        "name": name,
                        "current": "Interest-Based",
                        "suggested": new_sector,
                        "biz_org": new_biz_org,
                        "batch_id": batch_id,
                        "confidence": 0.5  # Lower confidence without batch context
                    })
                    print(f"      💡 {name[:40]:40} → {new_biz_org.upper()} / {new_sector} (individual)")
    
    # Summary
    print(f"\n{'=' * 60}")
    print(f"📋 SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total Interest-Based cards: {len(interest_based_cards)}")
    print(f"Suggested re-classifications: {len(suggestions)}")
    
    if suggestions:
        print(f"\n💡 Suggested re-classifications:")
        for sug in suggestions[:20]:  # Show first 20
            print(f"   {sug['name'][:40]:40} → {sug['biz_org'].upper():3} / {sug['suggested']:20} (confidence: {sug['confidence']:.1%})")
        
        if len(suggestions) > 20:
            print(f"   ... and {len(suggestions) - 20} more")
        
        print(f"\n💡 To apply these suggestions, run:")
        print(f"   python3 scripts/apply_reclassifications.py")
    
    conn.close()
    return suggestions

if __name__ == "__main__":
    analyze_misclassifications()

