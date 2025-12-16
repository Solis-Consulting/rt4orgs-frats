"""
Blast bridge module.

Runs outbound blasts for a specific set of card IDs by:
- Resolving cards from the database
- Generating personalized messages using existing templates
- Sending SMS via Twilio
- Recording conversations in the conversations table
- Recording a blast_runs summary row
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from datetime import datetime
from pathlib import Path

import psycopg2

from scripts.blast import send_sms, write_initial_state, write_initial_message  # reuse existing engine pieces

# Reuse archive_intelligence message utilities
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "archive_intelligence"
sys.path.insert(0, str(ARCHIVE_DIR))

from archive_intelligence.message_processor.utils import (  # type: ignore
    load_sales_history,
    make_contact_event_folder,
)
from archive_intelligence.message_processor.generate_message import generate_message  # type: ignore


def _fetch_cards_by_ids(conn: Any, card_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch person cards by IDs from cards table."""
    if not card_ids:
        return []

    with conn.cursor() as cur:
        placeholders = ",".join(["%s"] * len(card_ids))
        cur.execute(
            f"""
            SELECT id, type, card_data, sales_state, owner
            FROM cards
            WHERE id IN ({placeholders})
            """,
            tuple(card_ids),
        )

        rows = cur.fetchall()

    cards: List[Dict[str, Any]] = []
    for row in rows:
        card_data = row[2]
        # card_data is JSONB; ensure dict
        if isinstance(card_data, str):
            import json as _json

            try:
                card_data = _json.loads(card_data)
            except Exception:
                pass

        cards.append(
            {
                "id": row[0],
                "type": row[1],
                "card_data": card_data,
                "sales_state": row[3],
                "owner": row[4],
            }
        )

    # Only keep person cards with phone numbers
    person_cards: List[Dict[str, Any]] = []
    for card in cards:
        if card["type"] != "person":
            continue
        phone = (card["card_data"] or {}).get("phone")
        if not phone:
            continue
        person_cards.append(card)

    return person_cards


def _insert_blast_run_row(
    conn: Any,
    blast_id: str,
    owner: str,
    source: str,
    limit_count: int,
    total_targets: int,
    sent_count: int,
    status: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blast_runs (
                id,
                created_at,
                owner,
                source,
                limit_count,
                total_targets,
                sent_count,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                owner = EXCLUDED.owner,
                source = EXCLUDED.source,
                limit_count = EXCLUDED.limit_count,
                total_targets = EXCLUDED.total_targets,
                sent_count = EXCLUDED.sent_count,
                status = EXCLUDED.status
            """,
            (
                blast_id,
                datetime.utcnow(),
                owner,
                source,
                limit_count,
                total_targets,
                sent_count,
                status,
            ),
        )


def run_blast_for_cards(
    conn: Any,
    card_ids: List[str],
    limit: int | None,
    owner: str,
    source: str,
) -> Dict[str, Any]:
    """
    Run outbound blast for a specific set of card IDs.

    - Resolves cards to people with phone numbers
    - Generates messages using archive_intelligence templates
    - Sends via Twilio (using scripts.blast.send_sms)
    - Records conversations and blast_run summary
    """
    if not card_ids:
        return {
            "ok": False,
            "error": "No card_ids provided",
            "sent": 0,
            "skipped": 0,
            "results": [],
        }

    # Fetch cards from DB
    cards = _fetch_cards_by_ids(conn, card_ids)
    if not cards:
        return {
            "ok": False,
            "error": "No matching person cards with phone numbers found for given card_ids",
            "sent": 0,
            "skipped": 0,
            "results": [],
        }

    # Apply limit at card level if provided
    if limit and limit > 0:
        cards = cards[:limit]

    sales_history = load_sales_history()

    # Generate a blast_run ID
    blast_id = f"cards_ui_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    sent_count = 0
    skipped_count = 0
    results: List[Dict[str, Any]] = []

    for card in cards:
        card_id = card["id"]
        data = card["card_data"] or {}
        phone = data.get("phone")

        if not phone:
            skipped_count += 1
            results.append(
                {
                    "card_id": card_id,
                    "phone": None,
                    "status": "skipped",
                    "reason": "missing phone number",
                }
            )
            continue

        # Find a purchased_example by fraternity, if available
        fraternity = data.get("fraternity")
        purchased_example = None
        if fraternity and isinstance(sales_history, list):
            for row in sales_history:
                if isinstance(row, dict) and row.get("fraternity") == fraternity:
                    purchased_example = row
                    break

        # Generate message text
        message = generate_message(data, purchased_example, ARCHIVE_DIR / "templates" / "messages.txt")

        try:
            sms_result = send_sms(phone, message)

            # Create legacy contact event folder for archive_intelligence compatibility
            folder = make_contact_event_folder(data.get("name") or card_id)
            write_initial_state(folder, data, purchased_example or {})
            write_initial_message(folder, message)

            # Record conversation row directly into conversations table
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversations
                    (phone, contact_id, card_id, owner, state, source_batch_id, last_outbound_at)
                    VALUES (%s, %s, %s, %s, 'awaiting_response', %s, %s)
                    ON CONFLICT (phone)
                    DO UPDATE SET
                      last_outbound_at = EXCLUDED.last_outbound_at,
                      owner = EXCLUDED.owner,
                      state = 'awaiting_response',
                      source_batch_id = EXCLUDED.source_batch_id,
                      card_id = COALESCE(EXCLUDED.card_id, conversations.card_id);
                    """,
                    (
                        phone,
                        card_id,  # contact_id
                        card_id,
                        owner,
                        blast_id,
                        datetime.utcnow(),
                    ),
                )

            sent_count += 1
            results.append(
                {
                    "card_id": card_id,
                    "phone": phone,
                    "status": "sent",
                    "twilio_sid": sms_result.get("sid"),
                    "twilio_status": sms_result.get("status"),
                }
            )
        except Exception as e:
            skipped_count += 1
            results.append(
                {
                    "card_id": card_id,
                    "phone": phone,
                    "status": "error",
                    "error": str(e),
                }
            )

    # Write blast_run summary row
    try:
        _insert_blast_run_row(
            conn=conn,
            blast_id=blast_id,
            owner=owner,
            source=source,
            limit_count=limit or 0,
            total_targets=len(cards),
            sent_count=sent_count,
            status="completed",
        )
    except psycopg2.Error:
        # Don't fail entire response on logging issues
        pass

    # Note: HTTP 200 + ok=True means "blast attempt completed",
    # even if some or all contacts were skipped; per-Card status is in results.
    return {
        "ok": True,
        "blast_run_id": blast_id,
        "sent": sent_count,
        "skipped": skipped_count,
        "results": results,
    }

