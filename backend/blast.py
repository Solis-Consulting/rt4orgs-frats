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

from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime
from pathlib import Path
import json

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
from intelligence.utils import (
    find_matching_fraternity,
    _get_deal_names_given,
    _get_deal_chapter,
    _get_deal_institution,
    _get_deal_field,
    _normalize_fraternity_key,
    normalize_phone,
)


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
            # Normalize phone to E.164 format for consistency
            phone = normalize_phone(phone)
            # Update card_data with normalized phone
            if isinstance(card["card_data"], dict):
                card["card_data"]["phone"] = phone
            person_cards.append(card)

    return person_cards


def _substitute_template(template: str, data: Dict[str, Any], purchased_example: Dict[str, Any] | None) -> str:
    """
    Substitute placeholders in template string with values from card data and purchased example.
    Supports all vertical types (frats, faith, academic, government, cultural, sports).
    
    Supported placeholders:
    - {name} or {contact_name} - from data.get("name")
    - {role} or {position} - from data.get("role")
    - {fraternity} - from data.get("fraternity") (frats)
    - {chapter} - from data.get("chapter") (frats)
    - {faith_group} - from data.get("faith_group") (faith)
    - {group} or {faith_group_or_org} - from data.get("group") (cultural)
    - {team} or {team_or_club} - from data.get("team") (sports)
    - {org} or {organization_name} - from data.get("org") (government)
    - {program} or {program_name} - from data.get("program") (academic)
    - {department} or {department_name} - from data.get("department") (academic)
    - {university} - from data.get("university")
    - {purchased_names} or {names_given} - from purchased_example (names given)
    - {purchased_chapter} or {matched_chapter} - from purchased_example (chapter)
    - {purchased_institution} or {matched_institution} - from purchased_example (institution)
    
    Falls back to empty string if placeholder value is missing.
    """
    print(f"[SUBSTITUTE] Starting template substitution", flush=True)
    print(f"[SUBSTITUTE] Template: {template[:100]}...", flush=True)
    print(f"[SUBSTITUTE] Purchased example is None: {purchased_example is None}", flush=True)
    
    # Extract values from card data - support all vertical types
    name = data.get("name") or data.get("contact_name") or ""
    role = data.get("role") or data.get("position") or ""
    fraternity = data.get("fraternity") or ""
    chapter = data.get("chapter") or ""
    faith_group = data.get("faith_group") or ""
    group = data.get("group") or data.get("faith_group_or_org") or ""
    team = data.get("team") or data.get("team_or_club") or ""
    org = data.get("org") or data.get("organization_name") or ""
    program = data.get("program") or data.get("program_name") or ""
    department = data.get("department") or data.get("department_name") or ""
    university = data.get("university") or ""
    print(f"[SUBSTITUTE] Card data - name: '{name}', role: '{role}', fraternity: '{fraternity}', chapter: '{chapter}', faith_group: '{faith_group}', group: '{group}', team: '{team}', org: '{org}', program: '{program}', department: '{department}', university: '{university}'", flush=True)
    
    # Extract values from purchased example (deal)
    purchased_names = ""
    purchased_chapter = ""
    purchased_institution = ""
    
    if purchased_example:
        print(f"[SUBSTITUTE] Purchased example keys: {list(purchased_example.keys())}", flush=True)
        print(f"[SUBSTITUTE] Purchased example: {purchased_example}", flush=True)
        
        names_given = _get_deal_names_given(purchased_example)
        purchased_names = str(names_given) if names_given > 0 else ""
        purchased_chapter = _get_deal_chapter(purchased_example)
        purchased_institution = _get_deal_institution(purchased_example)
        
        print(f"[SUBSTITUTE] Extracted values:", flush=True)
        print(f"[SUBSTITUTE]   purchased_names: '{purchased_names}'", flush=True)
        print(f"[SUBSTITUTE]   purchased_chapter: '{purchased_chapter}'", flush=True)
        print(f"[SUBSTITUTE]   purchased_institution: '{purchased_institution}'", flush=True)
    else:
        print(f"[SUBSTITUTE] ⚠️ No purchased_example provided - placeholders will be empty", flush=True)
    
    # Perform substitution using .format() with safe defaults
    # Support both naming conventions for backward compatibility
    # Include all vertical-specific fields
    try:
        result = template.format(
            name=name,
            contact_name=name,  # Alias for backward compatibility
            role=role,
            position=role,  # Alias for backward compatibility
            fraternity=fraternity,
            chapter=chapter,
            faith_group=faith_group,
            group=group,
            faith_group_or_org=group,  # Alias for backward compatibility
            team=team,
            team_or_club=team,  # Alias for backward compatibility
            org=org,
            organization_name=org,  # Alias for backward compatibility
            program=program,
            program_name=program,  # Alias for backward compatibility
            department=department,
            department_name=department,  # Alias for backward compatibility
            university=university,
            purchased_names=purchased_names,
            names_given=purchased_names,  # Alias for backward compatibility
            purchased_chapter=purchased_chapter,
            matched_chapter=purchased_chapter,  # Alias for backward compatibility
            purchased_institution=purchased_institution,
            matched_institution=purchased_institution,  # Alias for backward compatibility
        )
        print(f"[SUBSTITUTE] ✅ Substitution successful using .format()", flush=True)
        print(f"[SUBSTITUTE] Result: {result[:200]}...", flush=True)
        return result
    except KeyError as e:
        # If template has unknown placeholders, log and continue with what we have
        print(f"[SUBSTITUTE] ⚠️ Template substitution warning: unknown placeholder {e}", flush=True)
        # Fallback: use replace for known placeholders (all vertical types)
        result = template
        result = result.replace("{name}", name)
        result = result.replace("{contact_name}", name)
        result = result.replace("{role}", role)
        result = result.replace("{position}", role)
        result = result.replace("{fraternity}", fraternity)
        result = result.replace("{chapter}", chapter)
        result = result.replace("{faith_group}", faith_group)
        result = result.replace("{group}", group)
        result = result.replace("{faith_group_or_org}", group)
        result = result.replace("{team}", team)
        result = result.replace("{team_or_club}", team)
        result = result.replace("{org}", org)
        result = result.replace("{organization_name}", org)
        result = result.replace("{program}", program)
        result = result.replace("{program_name}", program)
        result = result.replace("{department}", department)
        result = result.replace("{department_name}", department)
        result = result.replace("{university}", university)
        result = result.replace("{purchased_names}", purchased_names)
        result = result.replace("{names_given}", purchased_names)
        result = result.replace("{purchased_chapter}", purchased_chapter)
        result = result.replace("{matched_chapter}", purchased_chapter)
        result = result.replace("{purchased_institution}", purchased_institution)
        result = result.replace("{matched_institution}", purchased_institution)
        print(f"[SUBSTITUTE] ✅ Substitution completed using .replace() fallback", flush=True)
        print(f"[SUBSTITUTE] Result: {result[:200]}...", flush=True)
        return result
    except Exception as e:
        print(f"[SUBSTITUTE] ❌ Template substitution error: {e}", flush=True)
        print(f"[SUBSTITUTE] Error type: {type(e).__name__}", flush=True)
        # Return template as-is if substitution fails completely
        return template


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
    limit: Optional[int],
    owner: str,
    source: str,
    rep_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run outbound blast for a specific set of card IDs.

    - Resolves cards to people with phone numbers
    - Generates messages using archive_intelligence templates
    - Sends via Twilio (using scripts.blast.send_sms)
    - Records conversations and blast_run summary
    - All messages sent from system phone number (919) 443-6288 via Messaging Service
    - Always uses system Twilio credentials from environment variables
    
    Args:
        conn: Database connection
        card_ids: List of card IDs to blast
        limit: Optional limit on number of cards
        owner: Owner identifier
        source: Source identifier (e.g., "rep_ui", "owner_ui")
        rep_user_id: Optional rep user ID (for conversation tracking)
    """
    # 🔥 BLAST MODE - Explicitly mark this as outbound-only, no inbound logic applies
    # This ensures no reply suppression, state checks, or Markov transition logic interferes
    is_blast_mode = True
    is_inbound = False
    
    # 8️⃣ Inside run_blast_for_cards (first line)
    logger.error(f"[BLAST_RUN] 🚀 STARTING BLAST: cards={len(card_ids)} rep={rep_user_id}")
    
    # High-level run visibility with detailed logging
    print("=" * 80, flush=True)
    print(f"[BLAST_RUN] 🚀 STARTING BLAST (BLAST MODE - NO INBOUND LOGIC)", flush=True)
    print("=" * 80, flush=True)
    print(f"[BLAST_RUN] ⚠️ BLAST MODE: is_blast_mode={is_blast_mode}, is_inbound={is_inbound}", flush=True)
    print(f"[BLAST_RUN] ⚠️ BLAST MODE: All reply suppression, state checks, and Markov transition logic DISABLED", flush=True)
    print(f"[BLAST_RUN] Card IDs: {card_ids} (count: {len(card_ids)})", flush=True)
    print(f"[BLAST_RUN] Limit: {limit}", flush=True)
    print(f"[BLAST_RUN] Owner: {owner}", flush=True)
    print(f"[BLAST_RUN] Source: {source}", flush=True)
    print(f"[BLAST_RUN] Rep User ID: {rep_user_id}", flush=True)
    print(f"[BLAST_RUN] Using System Phone Number (919) 443-6288 via Messaging Service", flush=True)
    print(f"[BLAST_RUN] Using System Twilio Credentials (from environment variables)", flush=True)
    print("=" * 80, flush=True)
    
    # 🔧 POLICY A: Blast-claim logic - whoever blasts LAST owns the automation
    # If rep_user_id is set, ensure card is assigned to that rep
    # If rep_user_id is NULL (owner blast), clear rep assignment to claim ownership
    from backend.handoffs import resolve_current_rep
    from backend.assignments import assign_card_to_rep, unassign_card
    
    for card_id in card_ids:
        current_rep = resolve_current_rep(conn, card_id)
        
        if rep_user_id:
            # Rep is blasting - claim ownership
            if current_rep != rep_user_id:
                print(f"[BLAST_RUN] 🔄 Blast claim (rep): card {card_id} currently assigned to {current_rep}, claiming for {rep_user_id}", flush=True)
                assign_card_to_rep(conn, card_id, rep_user_id, rep_user_id, notes="Blast claim - ownership transferred via blast")
                print(f"[BLAST_RUN] ✅ Card {card_id} reassigned to {rep_user_id} via blast claim", flush=True)
        else:
            # Owner is blasting - claim ownership by clearing ALL rep assignments (unconditional)
            # POLICY A: Owner blast = hard reclaim - delete ALL assignments for this card
            print(f"[BLAST_RUN] 🔄 Blast claim (owner): clearing ALL assignments for card {card_id}", flush=True)
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM card_assignments
                    WHERE card_id = %s
                """, (card_id,))
                deleted_count = cur.rowcount
                if deleted_count > 0:
                    print(f"[BLAST_RUN] ✅ Card {card_id} - deleted {deleted_count} assignment(s) - owner now owns via blast claim", flush=True)
                else:
                    print(f"[BLAST_RUN] ✅ Card {card_id} - no assignments to delete (already owner-owned)", flush=True)

    if not card_ids:
        return {
            "ok": False,
            "error": "No card_ids provided",
            "sent": 0,
            "skipped": 0,
            "results": [],
        }

    # Fetch cards from DB
    print(f"[BLAST_RUN] Fetching {len(card_ids)} cards from database...", flush=True)
    cards = _fetch_cards_by_ids(conn, card_ids)
    print(f"[BLAST_RUN] Found {len(cards)} person cards with phone numbers", flush=True)
    if not cards:
        print(f"[BLAST_RUN] ❌ No matching person cards with phone numbers found", flush=True)
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
    
    # Log sales history loading
    print(f"[BLAST] Sales history loaded: {len(sales_history)} fraternity keys", flush=True)
    if sales_history:
        total_deals = sum(len(deals) if isinstance(deals, list) else 0 for deals in sales_history.values())
        print(f"[BLAST] Total deals in sales history: {total_deals}", flush=True)
        print(f"[BLAST] Available fraternity keys: {list(sales_history.keys())}", flush=True)
    else:
        print("[BLAST] ⚠️ WARNING: Sales history is empty - no matches will be found!", flush=True)

    # Generate a blast_run ID
    blast_id = f"cards_ui_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    sent_count = 0
    skipped_count = 0
    results: List[Dict[str, Any]] = []

    for card in cards:
        card_id = card["id"]
        data = card["card_data"] or {}
        phone = data.get("phone")

        # Decision visibility: log what we know before eligibility checks
        print(
            "[BLAST_CHECK]",
            {
                "card_id": card_id,
                "type": card.get("type"),
                "phone": phone,
                "sales_state": card.get("sales_state"),
                "owner": card.get("owner"),
            },
            flush=True,
        )

        if not phone:
            print(
                f"[BLAST_SKIP] card_id={card_id} reason=NO_PHONE",
                flush=True,
            )
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

        # Find matching deal using new relational proof-point selector
        purchased_example = None
        
        # Log what we're matching (preserve original case for display)
        contact_frat = data.get("fraternity", "").strip()
        contact_frat_normalized = _normalize_fraternity_key(contact_frat) if contact_frat else ""
        contact_inst = (data.get("institution") or data.get("location") or "").strip()
        print(
            f"[BLAST_MATCH] Looking for match: fraternity='{contact_frat}' (normalized: '{contact_frat_normalized}') institution='{contact_inst}'",
            flush=True,
        )
        
        if isinstance(sales_history, dict):
            purchased_example = find_matching_fraternity(data, sales_history)
        elif isinstance(sales_history, list):
            # Legacy format - convert to dict format for matching
            # Preserve original key format (case-sensitive) for proper matching
            sales_dict = {}
            for row in sales_history:
                if isinstance(row, dict):
                    # Try various field name variations to find fraternity/abbreviation
                    # Keep original case to match JSON structure (e.g., "SigChi", "PhiDelt")
                    frat_key = (row.get("Abbreviation") or row.get("abbreviation") or 
                               row.get("fraternity") or row.get("Fraternity") or "").strip()
                    if frat_key:
                        # Use original case as key (matching will be case-insensitive)
                        if frat_key not in sales_dict:
                            sales_dict[frat_key] = []
                        sales_dict[frat_key].append(row)
            
            # Log available fraternities in sales data
            available_frats = list(sales_dict.keys())
            print(f"[BLAST_MATCH] Available fraternities in sales data: {available_frats}", flush=True)
            
            purchased_example = find_matching_fraternity(data, sales_dict)
        
        # Log the match result
        if purchased_example:
            matched_frat = _get_deal_field(purchased_example, "Abbreviation", "abbreviation", "fraternity", "Fraternity").upper()
            matched_inst = _get_deal_field(purchased_example, "Institution", "institution").lower()
            matched_names = _get_deal_names_given(purchased_example)
            matched_chapter = _get_deal_chapter(purchased_example)
            print(
                f"[BLAST_MATCH] ✅ Matched: {matched_frat} at {matched_inst} ({matched_names} names)",
                flush=True,
            )
            print(
                f"[BLAST_MATCH] Match details - Chapter: '{matched_chapter}', Institution: '{matched_inst}', Names: {matched_names}",
                flush=True,
            )
        else:
            print("[BLAST_MATCH] ❌ No match found - purchased_example is None", flush=True)
            print("[BLAST_MATCH] ⚠️ Template placeholders will not be substituted", flush=True)

        # Generate message text - try configured initial outreach first (rep-specific if available), fallback to template
        message = None
        try:
            # Check for configured initial outreach (rep-specific first, then global)
            with conn.cursor() as cur:
                if rep_user_id:
                    # Try rep-specific first
                    cur.execute("""
                        SELECT response_text FROM markov_responses 
                        WHERE state_key = '__initial_outreach__' AND user_id = %s
                    """, (rep_user_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        configured_outreach = row[0]
                        message = _substitute_template(configured_outreach, data, purchased_example)
                        print(f"[BLAST] Using rep-specific configured initial outreach message (user_id: {rep_user_id})")
                
                # Fallback to global if no rep-specific found
                if not message:
                    cur.execute("""
                        SELECT response_text FROM markov_responses 
                        WHERE state_key = '__initial_outreach__' AND user_id IS NULL
                    """)
                    row = cur.fetchone()
                    if row and row[0]:
                        configured_outreach = row[0]
                        message = _substitute_template(configured_outreach, data, purchased_example)
                        print(f"[BLAST] Using global configured initial outreach message")
        except Exception as e:
            print(f"[BLAST] Could not load configured outreach, using template: {e}")
        
        if not message:
            # Fallback to template-based generation using archive_intelligence
            try:
                message = generate_message(
                    contact=data,
                    purchased_example=purchased_example,
                    template_path=None,  # Will use default template
                )
                print(f"[BLAST] Using template-based message generation")
            except Exception as e:
                print(f"[BLAST] Template generation failed: {e}")
                # Final fallback: basic message
                name = data.get("name", "there")
                fraternity = data.get("fraternity", "your fraternity")
                message = (
                    f"Hello {name}, we would like to know how {fraternity}'s spring rush could be "
                    f"with a FRESH PNM list.\n\nI'm David with rt4orgs https://rt4orgs.com."
                )

        try:
            # #region agent log - Before send attempt
            try:
                import json as _json
                from pathlib import Path
                debug_log_path = Path(__file__).resolve().parent.parent / ".cursor" / "debug.log"
                debug_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(debug_log_path, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "location": "backend/blast.py:send_attempt:BEFORE",
                        "message": "About to attempt SMS send",
                        "data": {"card_id": card_id, "phone": phone, "message_length": len(message), "rep_user_id": rep_user_id},
                        "hypothesisId": "F"
                    }) + "\n")
            except Exception as e:
                print(f"[DEBUG_LOG] Failed to write debug log: {e}", flush=True)
            # #endregion
            
            print("=" * 80, flush=True)
            print(f"[BLAST_SEND_ATTEMPT] 🚀 ATTEMPTING TO SEND SMS", flush=True)
            print("=" * 80, flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Card ID: {card_id}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Phone: {phone}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Message length: {len(message)} chars", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Rep User ID: {rep_user_id}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Using System Phone Number (via Messaging Service)", flush=True)
            
            print(f"[BLAST_SEND_ATTEMPT] send_sms() will use system Twilio credentials from environment variables", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] ⚠️ BLAST MODE: No reply suppression, no state checks, no guards - sending unconditionally", flush=True)
            # 9️⃣ Right before Twilio send
            logger.error(f"[BLAST_SEND] 📤 Sending SMS to {phone} (card_id={card_id})")
            print(f"[BLAST_SEND] 📤 Sending SMS to {phone} (card_id={card_id})", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Calling send_sms() NOW...", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Request timestamp: {datetime.utcnow().isoformat()}", flush=True)
            # send_sms() now always uses environment variables - no parameters needed
            # BLAST MODE: Always send, no guards, no suppression
            try:
                print(f"[BLAST_SEND_ATTEMPT] ✅ EXECUTING send_sms() - BLAST MODE (no guards)", flush=True)
                sms_result = send_sms(phone, message)
                print(f"[BLAST_SEND_ATTEMPT] ✅ send_sms() returned successfully", flush=True)
                print(f"[BLAST_SEND_ATTEMPT] SMS Result: {sms_result}", flush=True)
            except Exception as send_error:
                print("=" * 80, flush=True)
                print(f"[BLAST_SEND_ATTEMPT] ❌ EXCEPTION in send_sms()", flush=True)
                print("=" * 80, flush=True)
                print(f"[BLAST_SEND_ATTEMPT] Error type: {type(send_error).__name__}", flush=True)
                print(f"[BLAST_SEND_ATTEMPT] Error message: {str(send_error)}", flush=True)
                import traceback
                print(f"[BLAST_SEND_ATTEMPT] Full traceback:", flush=True)
                traceback.print_exc()
                print("=" * 80, flush=True)
                raise
            
            print(f"[BLAST_SEND_ATTEMPT] send_sms() returned, processing result...", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Response timestamp: {datetime.utcnow().isoformat()}", flush=True)
            
            # #region agent log - After send attempt
            try:
                import json as _json
                from pathlib import Path
                debug_log_path = Path(__file__).resolve().parent.parent / ".cursor" / "debug.log"
                debug_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(debug_log_path, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "location": "backend/blast.py:send_attempt:AFTER",
                        "message": "SMS send attempt completed",
                        "data": {"twilio_sid": sms_result.get('sid'), "status": sms_result.get('status'), "error_code": sms_result.get('error_code')},
                        "hypothesisId": "G"
                    }) + "\n")
            except Exception as e:
                print(f"[DEBUG_LOG] Failed to write debug log: {e}", flush=True)
            # #endregion
            
            print("=" * 80, flush=True)
            print(f"[BLAST_SEND_ATTEMPT] ✅ send_sms() RETURNED", flush=True)
            print("=" * 80, flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Full result dictionary:", flush=True)
            for key, value in sms_result.items():
                print(f"[BLAST_SEND_ATTEMPT]   {key}: {value}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Result SID: {sms_result.get('sid')}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Result Status: {sms_result.get('status')} {'⚠️' if sms_result.get('status') in ['failed', 'undelivered', 'queued', 'accepted'] else '✅' if sms_result.get('status') in ['sent', 'delivered'] else ''}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Result To: {sms_result.get('to')}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Result From (actual sender): {sms_result.get('from')}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Error Code: {sms_result.get('error_code') or 'None (no error)'}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Error Message: {sms_result.get('error_message') or 'None (no error)'}", flush=True)
            print(f"[BLAST_SEND_ATTEMPT] Date Sent: {sms_result.get('date_sent') or 'Not sent yet'}", flush=True)
            
            # CRITICAL: Log status interpretation
            status = sms_result.get('status', '').lower()
            if status in ['queued', 'accepted']:
                print("=" * 80, flush=True)
                print(f"[BLAST_SEND_ATTEMPT] ⚠️⚠️⚠️ MESSAGE QUEUED - A2P 10DLC ISSUE", flush=True)
                print("=" * 80, flush=True)
                print(f"[BLAST_SEND_ATTEMPT] Status '{status}' means:", flush=True)
                print(f"[BLAST_SEND_ATTEMPT]   - Twilio accepted the message", flush=True)
                print(f"[BLAST_SEND_ATTEMPT]   - Message is queued by carrier", flush=True)
                print(f"[BLAST_SEND_ATTEMPT]   - Likely cause: A2P 10DLC registration incomplete", flush=True)
                print(f"[BLAST_SEND_ATTEMPT]   - Check: Phone number in Messaging Service sender pool?", flush=True)
                print(f"[BLAST_SEND_ATTEMPT]   - Check: Campaign fully approved and active?", flush=True)
                print(f"[BLAST_SEND_ATTEMPT]   - Check: Carrier routing configured?", flush=True)
                print("=" * 80, flush=True)
            
            # Enhanced status checking
            if sms_result.get('status') in ['failed', 'undelivered']:
                print(f"[BLAST_SEND_ATTEMPT] ⚠️⚠️⚠️ MESSAGE DELIVERY FAILED ⚠️⚠️⚠️", flush=True)
                print(f"[BLAST_SEND_ATTEMPT] This message was NOT delivered. Check Twilio Console.", flush=True)
            elif sms_result.get('status') in ['queued', 'accepted']:
                print(f"[BLAST_SEND_ATTEMPT] ℹ️ Message accepted, status: {sms_result.get('status')}", flush=True)
            elif sms_result.get('status') in ['sent', 'delivered']:
                print(f"[BLAST_SEND_ATTEMPT] ✅ Message successfully {sms_result.get('status')}", flush=True)
            
            print("=" * 80, flush=True)

            # Create legacy contact event folder for archive_intelligence compatibility
            folder = make_contact_event_folder(data.get("name") or card_id)
            write_initial_state(folder, data, purchased_example or {})
            write_initial_message(folder, message)

            # 🔥 ENVIRONMENT ISOLATION: Generate environment_id for this blast
            from backend.environment import generate_environment_id, store_message_event
            
            # Infer campaign_id from card data
            campaign_id = None
            if data.get("fraternity"):
                campaign_id = "frat_rt4orgs"
            elif data.get("faith_group"):
                campaign_id = "faith_rt4orgs"
            elif data.get("role") == "Office":
                campaign_id = "faith_rt4orgs"
            else:
                campaign_id = "default_rt4orgs"
            
            # Generate environment_id for this blast
            environment_id = generate_environment_id(rep_user_id, campaign_id)
            print(f"[BLAST] 🔥 Environment ID: {environment_id} (rep={rep_user_id}, campaign={campaign_id})", flush=True)
            
            # Record conversation row directly into conversations table
            # Also store outbound message in history
            with conn.cursor() as cur:
                # First, get existing history for this environment
                try:
                    cur.execute("""
                        SELECT COALESCE(history::text, '[]') as history
                        FROM conversations
                        WHERE phone = %s AND environment_id = %s;
                    """, (phone, environment_id))
                except psycopg2.ProgrammingError:
                    # Fallback if environment_id column doesn't exist
                    cur.execute("""
                        SELECT COALESCE(history::text, '[]') as history
                        FROM conversations
                        WHERE phone = %s;
                    """, (phone,))
                row = cur.fetchone()
                existing_history = []
                if row and row[0]:
                    try:
                        import json as _json
                        existing_history = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    except:
                        existing_history = []
                
                # POLICY A: Whoever blasts LAST owns the automation
                # routing_mode is now 'ai' for all (auto-responses enabled)
                # Ownership is determined by rep_user_id (NULL = owner, set = rep)
                routing_mode = 'ai'  # Always enable auto-responses (Policy A)
                
                print(f"[BLAST] 📝 Recording conversation: phone={phone}, rep_user_id={rep_user_id}, routing_mode={routing_mode}", flush=True)
                print(f"[BLAST] ✅ Policy A: Blast claims ownership - auto-responses enabled", flush=True)
                
                # 🔧 CRITICAL: Check for existing conversation BEFORE INSERT/UPDATE
                # This handles graceful transitions when different reps contact the same number
                existing_rep = None
                existing_state = None
                existing_card_id = None
                
                # Always check for existing conversation in this environment (not just when rep_user_id is set)
                try:
                    cur.execute("""
                        SELECT rep_user_id, state, card_id FROM conversations
                        WHERE phone = %s AND environment_id = %s
                        LIMIT 1
                    """, (phone, environment_id))
                except psycopg2.ProgrammingError:
                    # Fallback if environment_id column doesn't exist
                    cur.execute("""
                        SELECT rep_user_id, state, card_id FROM conversations
                        WHERE phone = %s
                        LIMIT 1
                    """, (phone,))
                existing_row = cur.fetchone()
                if existing_row:
                    existing_rep = existing_row[0]
                    existing_state = existing_row[1]
                    existing_card_id = existing_row[2]
                    print(f"[BLAST] 🔍 Found existing conversation in environment {environment_id}: rep={existing_rep}, state={existing_state}, card_id={existing_card_id}", flush=True)
                
                # Determine if ownership is changing
                ownership_changing = False
                if existing_rep is not None:
                    # Existing conversation with a rep
                    if rep_user_id is None:
                        # Owner blast - clearing rep ownership
                        ownership_changing = True
                        print(f"[BLAST] 🔄 Ownership transition detected: {existing_rep} → NULL (owner blast)", flush=True)
                    elif existing_rep != rep_user_id:
                        # Different rep is blasting
                        ownership_changing = True
                        print(f"[BLAST] 🔄 Ownership transition detected: {existing_rep} → {rep_user_id}", flush=True)
                elif existing_rep is None and rep_user_id:
                    # First time rep is claiming (no previous conversation or was owner-owned)
                    ownership_changing = True
                    print(f"[BLAST] 🔄 First rep claim: NULL → {rep_user_id}", flush=True)
                
                # ✅ CRITICAL FIX: Initialize new_state BEFORE it's used
                # Default to existing_state if available, otherwise 'awaiting_response'
                # Only change to 'initial_outreach' if ownership is changing
                new_state = existing_state if existing_state else 'awaiting_response'
                if ownership_changing:
                    new_state = 'initial_outreach'
                    print(f"[BLAST] 🔄 Resetting state to '{new_state}' for clean ownership transition", flush=True)
                
                # Add outbound message to history with correct state
                # Use new_state (which is 'initial_outreach' if ownership changing, 'awaiting_response' otherwise)
                # This ensures history reflects the actual conversation state, not always initial_outreach
                outbound_msg = {
                    "direction": "outbound",
                    "text": message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "state": new_state  # Use actual state, not hardcoded "initial_outreach"
                }
                updated_history = existing_history + [outbound_msg]
                if ownership_changing:
                    print(f"[BLAST] 🔄 Resetting state to '{new_state}' for clean ownership transition", flush=True)
                
                # Insert or update conversation with history (scoped to environment_id)
                # CRITICAL: Primary key is now (phone, environment_id) - each environment is isolated
                try:
                    # Try with environment_id (new schema)
                    cur.execute(
                        """
                        INSERT INTO conversations
                        (phone, environment_id, contact_id, card_id, owner, state, source_batch_id, last_outbound_at, history, routing_mode, rep_user_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                        ON CONFLICT (phone, environment_id)
                        DO UPDATE SET
                          last_outbound_at = EXCLUDED.last_outbound_at,
                          owner = EXCLUDED.owner,
                          state = EXCLUDED.state,
                          source_batch_id = EXCLUDED.source_batch_id,
                          card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                          history = EXCLUDED.history,
                          -- POLICY A: Always enable auto-responses (routing_mode = 'ai')
                          routing_mode = 'ai',
                          -- POLICY A: Last one to blast wins - rep_user_id determines ownership
                          -- If rep_user_id is NULL (owner blast), clears rep ownership
                          rep_user_id = EXCLUDED.rep_user_id;
                        """,
                        (
                            phone,
                            environment_id,
                            card_id,  # contact_id
                            card_id,
                            owner,
                            new_state,  # Use new_state (initial_outreach if ownership changing)
                            blast_id,
                            datetime.utcnow(),
                            json.dumps(updated_history),
                            routing_mode,
                            rep_user_id,
                        ),
                    )
                    print(f"[BLAST] ✅ Conversation recorded/updated: phone={phone}, env={environment_id}, rep_user_id={rep_user_id}, state={new_state}", flush=True)
                except psycopg2.ProgrammingError as e:
                    # Fallback if environment_id column or composite key doesn't exist yet
                    if 'environment_id' in str(e) or 'conversations_pkey' in str(e):
                        print(f"[BLAST] ⚠️ environment_id not available - using fallback schema", flush=True)
                        cur.execute(
                            """
                            INSERT INTO conversations
                            (phone, contact_id, card_id, owner, state, source_batch_id, last_outbound_at, history, routing_mode, rep_user_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                            ON CONFLICT (phone)
                            DO UPDATE SET
                              last_outbound_at = EXCLUDED.last_outbound_at,
                              owner = EXCLUDED.owner,
                              state = EXCLUDED.state,
                              source_batch_id = EXCLUDED.source_batch_id,
                              card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                              history = EXCLUDED.history,
                              routing_mode = 'ai',
                              rep_user_id = EXCLUDED.rep_user_id;
                            """,
                            (
                                phone,
                                card_id,  # contact_id
                                card_id,
                                owner,
                                new_state,
                                blast_id,
                                datetime.utcnow(),
                                json.dumps(updated_history),
                                routing_mode,
                                rep_user_id,
                            ),
                        )
                    else:
                        raise
                    
                    # Handle ownership transition with proper handoff logging
                    if ownership_changing:
                        from backend.handoffs import reset_markov_for_card, log_handoff
                        
                        if rep_user_id:
                            # Rep is claiming ownership (from another rep or from owner)
                            print(f"[BLAST] 🔄 Processing ownership transition: {existing_rep} → {rep_user_id}", flush=True)
                            reset_markov_for_card(conn, card_id, rep_user_id, 'blast_claim', rep_user_id)
                            log_handoff(
                                conn=conn,
                                card_id=card_id,
                                from_rep=existing_rep,
                                to_rep=rep_user_id,
                                reason='blast_claim',
                                state_before=existing_state,
                                state_after='initial_outreach',
                                assigned_by=rep_user_id
                            )
                            print(f"[BLAST] ✅ Ownership transition complete: rep {rep_user_id} now owns conversation", flush=True)
                        else:
                            # Owner is claiming ownership (clearing rep)
                            print(f"[BLAST] 🔄 Processing ownership transition: {existing_rep} → NULL (owner)", flush=True)
                            reset_markov_for_card(conn, card_id, None, 'blast_claim', owner)
                            log_handoff(
                                conn=conn,
                                card_id=card_id,
                                from_rep=existing_rep,
                                to_rep=None,  # NULL = owner
                                reason='blast_claim',
                                state_before=existing_state,
                                state_after='initial_outreach',
                                assigned_by=owner
                            )
                            print(f"[BLAST] ✅ Ownership transition complete: owner now owns conversation", flush=True)
                    
                    # Store outbound message event (CRITICAL: with message_sid to mark as "sent")
                    message_sid = sms_result.get("sid")
                    if message_sid:
                        store_message_event(
                            conn=conn,
                            phone_number=phone,
                            environment_id=environment_id,
                            direction="outbound",
                            message_text=message,
                            message_sid=message_sid,  # REQUIRED: Only messages with message_sid count as "sent"
                            rep_id=rep_user_id,
                            campaign_id=campaign_id,
                            state=new_state,
                            twilio_status=sms_result.get("status")
                        )
                        print(f"[BLAST] ✅ Stored outbound message event: env={environment_id}, sid={message_sid}", flush=True)
                    else:
                        print(f"[BLAST] ⚠️ WARNING: No message_sid from Twilio - message event not stored!", flush=True)
                    
                    # Verify the rep_user_id was actually saved
                    try:
                        cur.execute("""
                            SELECT rep_user_id FROM conversations 
                            WHERE phone = %s AND environment_id = %s
                        """, (phone, environment_id))
                    except psycopg2.ProgrammingError:
                        # Fallback if environment_id column doesn't exist
                        cur.execute("""
                            SELECT rep_user_id FROM conversations WHERE phone = %s
                        """, (phone,))
                    verify_row = cur.fetchone()
                    if verify_row:
                        print(f"[BLAST] ✅ Verified rep_user_id in DB: {verify_row[0]} (expected: {rep_user_id})", flush=True)
                    else:
                        print(f"[BLAST] ⚠️ WARNING: Could not verify rep_user_id was saved!", flush=True)
                except psycopg2.ProgrammingError as e:
                    # Handle case where new columns don't exist yet (backward compatibility)
                    if 'routing_mode' in str(e):
                        # Try without routing_mode columns
                        cur.execute(
                            """
                            INSERT INTO conversations
                            (phone, contact_id, card_id, owner, state, source_batch_id, last_outbound_at, history)
                            VALUES (%s, %s, %s, %s, 'awaiting_response', %s, %s, %s::jsonb)
                            ON CONFLICT (phone)
                            DO UPDATE SET
                              last_outbound_at = EXCLUDED.last_outbound_at,
                              owner = EXCLUDED.owner,
                              state = 'awaiting_response',
                              source_batch_id = EXCLUDED.source_batch_id,
                              card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                              history = EXCLUDED.history;
                            """,
                            (
                                phone,
                                card_id,  # contact_id
                                card_id,
                                owner,
                                blast_id,
                                datetime.utcnow(),
                                json.dumps(updated_history),
                            ),
                        )
                    elif 'history' in str(e):
                        # History column doesn't exist, update without it
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
                    else:
                        raise

            sent_count += 1
            results.append(
                {
                    "card_id": card_id,
                    "phone": phone,
                    "status": "sent",  # Our internal status (message was accepted by Twilio)
                    "twilio_sid": sms_result.get("sid"),
                    "twilio_status": sms_result.get("status"),  # Actual Twilio status (accepted, queued, sent, delivered, failed, etc.)
                    "twilio_error_code": sms_result.get("error_code"),
                    "twilio_error_message": sms_result.get("error_message"),
                    "twilio_date_sent": sms_result.get("date_sent"),
                }
            )
        except Exception as e:
            skipped_count += 1
            import traceback
            error_trace = traceback.format_exc()
            print(
                f"[BLAST_ERROR] card_id={card_id} phone={phone} error={e}",
                flush=True,
            )
            print(f"[BLAST_ERROR] Traceback:\n{error_trace}", flush=True)
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
    print("=" * 80, flush=True)
    print(f"[BLAST_RUN] ✅ BLAST COMPLETE", flush=True)
    print("=" * 80, flush=True)
    print(f"[BLAST_RUN] Sent: {sent_count}", flush=True)
    print(f"[BLAST_RUN] Skipped: {skipped_count}", flush=True)
    print(f"[BLAST_RUN] Total Cards: {len(cards)}", flush=True)
    print(f"[BLAST_RUN] Results: {len(results)}", flush=True)
    print("=" * 80, flush=True)
    
    return {
        "ok": True,
        "blast_run_id": blast_id,
        "sent": sent_count,
        "skipped": skipped_count,
        "results": results,
    }