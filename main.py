# CRITICAL: Add project root to Python path BEFORE any local imports
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now we can import everything
from fastapi import FastAPI, HTTPException, Form, Query, Body
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.requests import Request
from datetime import datetime
from contextlib import asynccontextmanager
import psycopg2
import os
import json
import logging
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from twilio.rest import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)
markov_logger = logging.getLogger("markov")

# Load environment variables from .env file
load_dotenv()

# Now import local modules (using proper package paths)
from intelligence.handler import handle_inbound
from intelligence.utils import normalize_phone
from intelligence.markov import CONVERSATION_TREE, ROOT_STATE
from intelligence.states import SUBTAM_DESCRIPTIONS

from backend.cards import (
    validate_card_schema,
    normalize_card,
    store_card,
    get_card,
    get_card_relationships,
)
from backend.query import build_list_query
from backend.resolve import resolve_target, extract_phones_from_cards
from backend.webhook_config import WEBHOOK_CONFIG, WebhookConfig
from backend.blast import run_blast_for_cards
from backend.auth import (
    get_user_by_token, create_user, list_users, update_user_twilio_config, get_user
)
from backend.assignments import (
    assign_card_to_rep, get_rep_assigned_cards, get_card_assignment,
    update_assignment_status, list_assignments
)
from backend.rep_messaging import (
    send_rep_message, get_rep_conversations, get_conversation_messages
)
from fastapi import Depends, Header
from starlette.responses import RedirectResponse

# Module-level verification - this will ALWAYS print
print("=" * 60)
print("📦 MAIN.PY MODULE LOADING")
print("=" * 60)

# Import migration function with error handling
try:
    from backend.db.migrate import run_migration
    print("✅ Migration module imported successfully")
    print(f"✅ run_migration function: {run_migration}")
except ImportError as e:
    print(f"❌ Failed to import migration module: {e}")
    import traceback
    traceback.print_exc()
    # Create a stub function if import fails
    def run_migration():
        return False, f"Migration module import failed: {e}"

# Import blast function lazily to prevent startup crashes if dependencies are missing
# Will be imported only when /admin/blast endpoint is called
run_blast = None

def _get_run_blast():
    """Lazy import of run_blast to avoid startup failures."""
    global run_blast
    if run_blast is None:
        try:
            from scripts.blast import run_blast as _run_blast
            run_blast = _run_blast
        except ImportError as e:
            # If blast dependencies are missing, return a stub function
            def _stub_blast(*args, **kwargs):
                return {"ok": False, "error": f"Blast functionality unavailable: {str(e)}"}
            run_blast = _stub_blast
    return run_blast

# #region agent log - Lifespan definition
_log_file = Path(__file__).resolve().parent / ".cursor" / "debug.log"
try:
    import json as _json
    with open(_log_file, "a") as f:
        f.write(_json.dumps({
            "sessionId": "debug-session",
            "runId": "run1",
            "timestamp": int(__import__("time").time() * 1000),
            "location": f"{__file__}:LIFESPAN_DEFINITION",
            "message": "Defining lifespan function",
            "data": {"migration_function": str(run_migration)},
            "hypothesisId": "A"
        }) + "\n")
except:
    pass
# #endregion

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Runs database migration on startup.
    """
    # #region agent log - Lifespan start
    try:
        with open(_log_file, "a") as f:
            f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(__import__("time").time() * 1000),
                "location": f"{__file__}:LIFESPAN_START",
                "message": "Lifespan function entered",
                "data": {"app": str(app)},
                "hypothesisId": "A"
            }) + "\n")
    except:
        pass
    # #endregion
    
    print("=" * 60)
    print("🚀 LIFESPAN START: Running database migration...")
    print("=" * 60)
    try:
        # #region agent log - Before migration call
        try:
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(__import__("time").time() * 1000),
                    "location": f"{__file__}:BEFORE_MIGRATION",
                    "message": "About to call run_migration",
                    "data": {"migration_function": str(run_migration), "has_database_url": bool(os.getenv("DATABASE_URL"))},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print(f"🔍 Calling run_migration function: {run_migration}")
        
        # Run migration synchronously - CRITICAL: This must complete before app serves requests
        # We're in an async context, but migration is sync. We need to run it in a way that blocks startup.
        # Using asyncio.to_thread (Python 3.9+) or run_in_executor to avoid blocking event loop setup
        import asyncio
        import sys
        
        # For Python 3.9+, use to_thread; otherwise use run_in_executor
        if sys.version_info >= (3, 9):
            success, message = await asyncio.to_thread(run_migration)
        else:
            loop = asyncio.get_event_loop()
            success, message = await loop.run_in_executor(None, run_migration)
        
        # #region agent log - After migration call
        try:
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(__import__("time").time() * 1000),
                    "location": f"{__file__}:AFTER_MIGRATION",
                    "message": "Migration call completed",
                    "data": {"success": success, "message": message},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        if success:
            print(f"✅ Database migration: {message}")
            
            # Verify tables were created
            try:
                conn = get_conn()
                with conn.cursor() as verify_cur:
                    verify_cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = 'cards'
                        );
                    """)
                    table_exists = verify_cur.fetchone()[0]
                    print(f"✅ Verification: cards table exists = {table_exists}")
            except Exception as verify_e:
                print(f"⚠️  Could not verify table creation: {verify_e}")
        else:
            print(f"⚠️  Database migration warning: {message}")
            # Don't crash the app if migration fails - it might be a transient issue
            # But log it prominently
            print("=" * 60)
            print("⚠️  WARNING: Migration did not complete successfully!")
            print(f"⚠️  Message: {message}")
            print("⚠️  Tables may not exist. Endpoints may fail.")
            print("⚠️  Run migration manually via: POST /admin/migrate")
            print("=" * 60)
    except Exception as e:
        # #region agent log - Migration exception
        try:
            import traceback as _tb
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(__import__("time").time() * 1000),
                    "location": f"{__file__}:MIGRATION_EXCEPTION",
                    "message": "Exception in migration",
                    "data": {"error": str(e), "error_type": type(e).__name__, "traceback": _tb.format_exc()},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        print(f"⚠️  Database migration error (non-fatal): {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        # Continue startup even if migration fails
    print("=" * 60)
    print("✅ LIFESPAN STARTUP COMPLETE")
    print("=" * 60)
    
    # Yield control to the app
    yield
    
    # Shutdown logic (if needed in the future)
    print("=" * 60)
    print("🛑 LIFESPAN SHUTDOWN")
    print("=" * 60)

# #region agent log - App initialization
try:
    with open(_log_file, "a") as f:
        f.write(_json.dumps({
            "sessionId": "debug-session",
            "runId": "run1",
            "timestamp": int(__import__("time").time() * 1000),
            "location": f"{__file__}:APP_INIT",
            "message": "Creating FastAPI app with lifespan",
            "data": {"lifespan_function": str(lifespan), "has_lifespan": True},
            "hypothesisId": "B"
        }) + "\n")
except:
    pass
# #endregion

# Module-level verification before app creation
print("=" * 60)
print("📦 CREATING FASTAPI APP")
print(f"📦 Lifespan function exists: {lifespan is not None}")
print(f"📦 Lifespan function: {lifespan}")
print(f"📦 run_migration function: {run_migration}")
print("=" * 60)

app = FastAPI(lifespan=lifespan)

print("=" * 60)
print("📦 FASTAPI APP CREATED")
print(f"📦 App instance: {app}")
print("=" * 60)

# Add CORS middleware to allow requests from Vercel
# Note: allow_credentials=True cannot be used with allow_origins=["*"]
# Use allow_credentials=False when allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific Vercel domain if needed
    allow_credentials=False,  # Must be False when using allow_origins=["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],  # Explicitly include OPTIONS
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.time()
    
    # Log request (don't read body here - it can only be read once)
    has_body = request.method in ("POST", "PUT", "PATCH")
    logger.info(
        f"➡️ {request.method} {request.url.path} "
        f"has_body={'<present>' if has_body else None}"
    )
    
    try:
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)
        logger.info(
            f"⬅️ {request.method} {request.url.path} "
            f"status={response.status_code} "
            f"{duration}ms"
        )
        return response
    except Exception as e:
        duration = round((time.time() - start) * 1000, 2)
        logger.error(
            f"❌ {request.method} {request.url.path} "
            f"Exception after {duration}ms: {str(e)}"
        )
        raise

# Mount UI directory for static file serving
UI_DIR = Path(__file__).resolve().parent / "ui"
if not UI_DIR.exists():
    raise RuntimeError(f"UI directory does not exist: {UI_DIR}")
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

# Module-level verification
print("=" * 60)
print("📦 main.py module loaded")
print(f"📦 FastAPI app instance: {app}")
print("=" * 60)

_conn = None

def get_conn():
    global _conn
    # #region agent log - Get conn entry
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:GET_CONN_ENTRY",
                "message": "get_conn called",
                "data": {"conn_exists": _conn is not None},
                "hypothesisId": "G"
            }) + "\n")
    except:
        pass
    # #endregion
    
    if _conn is None:
        # #region agent log - Creating new connection
        try:
            import time
            conn_start = time.time()
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:CREATING_CONN",
                    "message": "Creating new database connection",
                    "data": {"has_database_url": bool(os.getenv("DATABASE_URL"))},
                    "hypothesisId": "G"
                }) + "\n")
        except:
            pass
        # #endregion
        
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        
        try:
            _conn = psycopg2.connect(database_url, connect_timeout=10)
            _conn.autocommit = True
            
            # #region agent log - Connection created
            try:
                import time
                conn_duration = time.time() - conn_start
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:CONN_CREATED",
                        "message": "Database connection created",
                        "data": {"duration_ms": int(conn_duration * 1000)},
                        "hypothesisId": "G"
                    }) + "\n")
            except:
                pass
            # #endregion
        except Exception as conn_e:
            # #region agent log - Connection error
            try:
                import time
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:CONN_ERROR",
                        "message": "Database connection failed",
                        "data": {"error": str(conn_e), "error_type": type(conn_e).__name__},
                        "hypothesisId": "G"
                    }) + "\n")
            except:
                pass
            # #endregion
            raise
    
    # #region agent log - Returning connection
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:RETURNING_CONN",
                "message": "Returning database connection",
                "data": {},
                "hypothesisId": "G"
            }) + "\n")
    except:
        pass
    # #endregion
    
    return _conn


@app.post("/events/outbound")
async def outbound(event: dict):
    conn = get_conn()
    # Normalize phone number for consistent storage
    phone = normalize_phone(event["phone"])
    contact_id = event.get("contact_id")
    card_id = event.get("card_id") or contact_id  # Use card_id if provided, fallback to contact_id
    
    with conn.cursor() as cur:
        cur.execute("""
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
        """, (
            phone,
            contact_id,
            card_id,
            event["owner"],
            event.get("source_batch_id"),
            datetime.utcnow()
        ))
    return {"ok": True}


@app.post("/events/inbound")
async def inbound(event: dict):
    conn = get_conn()
    # Normalize phone number for consistent matching
    phone = normalize_phone(event["phone"])
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversations
            SET last_inbound_at = %s,
                state = 'replied'
            WHERE phone = %s;
        """, (
            datetime.utcnow(),
            phone
        ))
    return {"ok": True}


@app.post("/events/inbound_intelligent")
async def inbound_intelligent(event: dict):
    """
    Intelligence-aware inbound handler.
    Fetches conversation, computes next state using Markov logic,
    and updates the database.
    Auto-creates conversation if it doesn't exist.
    """
    conn = get_conn()
    phone_raw = event["phone"]
    # Normalize phone number for consistent matching
    phone = normalize_phone(phone_raw)
    inbound_text = event.get("text") or event.get("body") or ""
    
    # Intent can be provided in request, or defaults to empty dict
    intent = event.get("intent", {})
    
    # Fetch conversation by phone
    with conn.cursor() as cur:
        # Try to fetch with history column, fallback to without if column doesn't exist
        try:
            cur.execute("""
                SELECT phone, state, COALESCE(history::text, '[]') as history
                FROM conversations
                WHERE phone = %s;
            """, (phone,))
        except psycopg2.ProgrammingError:
            # History column might not exist, fetch without it
            cur.execute("""
                SELECT phone, state
                FROM conversations
                WHERE phone = %s;
            """, (phone,))
        
        row = cur.fetchone()
        
        # Find card by phone number to link conversation
        # Try multiple phone formats for matching
        card_id = None
        phone_variants = [
            phone_raw,  # Original format from Twilio
            f"+{phone}",  # + prefix with normalized
            phone,  # Normalized (last 10 digits)
            phone_raw.replace("+", ""),  # Without +
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for variant in phone_variants:
            if variant and variant not in seen:
                seen.add(variant)
                unique_variants.append(variant)
        
        # Try to find card by any phone variant
        for phone_variant in unique_variants:
            cur.execute("""
                SELECT id FROM cards
                WHERE type = 'person'
                AND card_data->>'phone' = %s
                LIMIT 1;
            """, (phone_variant,))
            card_row = cur.fetchone()
            if card_row:
                card_id = card_row[0]
                break
        
        # Also try normalized last 10 digits matching (for cases like +19843695080 vs 19843695080)
        if not card_id:
            # Extract last 10 digits from normalized phone
            last_10 = phone[-10:] if len(phone) >= 10 else phone
            cur.execute("""
                SELECT id FROM cards
                WHERE type = 'person'
                AND (
                    card_data->>'phone' LIKE %s
                    OR RIGHT(REPLACE(card_data->>'phone', '+', ''), 10) = %s
                )
                LIMIT 1;
            """, (f"%{last_10}", last_10))
            card_row = cur.fetchone()
            if card_row:
                card_id = card_row[0]
        
        # Auto-create conversation if it doesn't exist
        if not row:
            # Create new conversation with initial state and link to card if found
            try:
                cur.execute("""
                    INSERT INTO conversations
                    (phone, card_id, state, last_inbound_at, history)
                    VALUES (%s, %s, 'initial_outreach', %s, %s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET
                        card_id = COALESCE(EXCLUDED.card_id, conversations.card_id)
                    RETURNING phone, state, COALESCE(history::text, '[]') as history;
                """, (phone, card_id, datetime.utcnow(), json.dumps([])))
                row = cur.fetchone()
                # If still no row (conflict), fetch it
                if not row:
                    cur.execute("""
                        SELECT phone, state, COALESCE(history::text, '[]') as history
                        FROM conversations
                        WHERE phone = %s;
                    """, (phone,))
                    row = cur.fetchone()
            except psycopg2.ProgrammingError:
                # History column doesn't exist, create without it
                cur.execute("""
                    INSERT INTO conversations
                    (phone, card_id, state, last_inbound_at)
                    VALUES (%s, %s, 'initial_outreach', %s)
                    ON CONFLICT (phone) DO UPDATE SET
                        card_id = COALESCE(EXCLUDED.card_id, conversations.card_id)
                    RETURNING phone, state;
                """, (phone, card_id, datetime.utcnow()))
                row = cur.fetchone()
                # If still no row (conflict), fetch it
                if not row:
                    cur.execute("""
                        SELECT phone, state
                        FROM conversations
                        WHERE phone = %s;
                    """, (phone,))
                    row = cur.fetchone()
        
        # If conversation exists but card_id is missing, try to link it
        if row and not card_id:
            # Check if conversation already has a card_id
            cur.execute("""
                SELECT card_id FROM conversations WHERE phone = %s;
            """, (phone,))
            existing_card_id = cur.fetchone()
            if existing_card_id and existing_card_id[0]:
                card_id = existing_card_id[0]
        
        if not row:
            raise HTTPException(status_code=500, detail=f"Failed to create or fetch conversation for phone: {phone}")
        
        # Build conversation_row dict
        # Parse history, handling both old format (strings) and new format (objects)
        raw_history = []
        if len(row) > 2 and row[2]:
            try:
                raw_history = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            except:
                raw_history = []
        
        # Convert old format (strings) to new format (objects) for processing
        normalized_history = []
        for item in raw_history:
            if isinstance(item, str):
                # Old format: convert to object
                normalized_history.append({
                    "direction": "inbound",
                    "text": item,
                    "timestamp": None,  # We don't have timestamp for old messages
                    "state": None
                })
            else:
                # Already in new format
                normalized_history.append(item)
        
        conversation_row = {
            "phone": row[0],
            "state": row[1],
            "history": [item.get("text") if isinstance(item, dict) else item for item in normalized_history],  # Pass text only to handler
        }
        
        # Call intelligence handler
        result = handle_inbound(conversation_row, inbound_text, intent)
        
        # Add new inbound message as object to history
        inbound_msg = {
            "direction": "inbound",
            "text": inbound_text,
            "timestamp": datetime.utcnow().isoformat(),
            "state": result["next_state"]
        }
        updated_history = normalized_history + [inbound_msg]
        
        # Update conversations table with new state, history, and card_id
        # Try to update history if column exists
        try:
            cur.execute("""
                UPDATE conversations
                SET state = %s,
                    last_inbound_at = %s,
                    history = %s::jsonb,
                    card_id = COALESCE(%s, card_id)
                WHERE phone = %s;
            """, (
                result["next_state"],
                datetime.utcnow(),
                json.dumps(updated_history),
                card_id,  # Link to card if found
                phone,
            ))
        except psycopg2.ProgrammingError:
            # History column doesn't exist, update without it
            cur.execute("""
                UPDATE conversations
                SET state = %s,
                    last_inbound_at = %s,
                    card_id = COALESCE(%s, card_id)
                WHERE phone = %s;
            """, (
                result["next_state"],
                datetime.utcnow(),
                card_id,  # Link to card if found
                phone,
            ))
    
    return {
        "ok": True,
        "next_state": result["next_state"],
        "previous_state": result["previous_state"],
        "intent": result["intent"],
    }


@app.post("/twilio/inbound", response_class=PlainTextResponse)
async def twilio_inbound(request: Request):
    """
    Twilio webhook endpoint for inbound SMS.
    Receives form-encoded data from Twilio and processes through intelligence layer.
    Gated by webhook configuration (enabled, mode, logging).
    """
    # CRITICAL: Log raw body FIRST to catch requests even if form parsing fails
    try:
        raw_body = await request.body()
        print("=" * 60)
        print("[TWILIO_INBOUND] RAW INBOUND BODY:", raw_body.decode('utf-8', errors='replace'))
        print("=" * 60)
    except Exception as e:
        print(f"[TWILIO_INBOUND] ERROR reading raw body: {e}")
    
    print("[TWILIO_INBOUND] Webhook hit")
    
    # Check if webhook is enabled
    if not WEBHOOK_CONFIG.enabled:
        print("[TWILIO_INBOUND] Webhook disabled in config")
        return PlainTextResponse("Webhook disabled", status_code=200)
    
    # Parse form data (requires python-multipart)
    try:
        payload = await request.form()
        payload_dict = dict(payload)
    except Exception as e:
        print(f"[TWILIO_INBOUND] ERROR parsing form data: {e}")
        print(f"[TWILIO_INBOUND] This usually means python-multipart is missing from requirements.txt")
        return PlainTextResponse("OK", status_code=200)
    
    # Always log payload for debugging
    print(f"[TWILIO_INBOUND] Payload: {payload_dict}")
    
    # Log payload if enabled
    if WEBHOOK_CONFIG.log_payloads:
        print("TWILIO PAYLOAD:", payload_dict)
    
    # Handle dry_run mode
    if WEBHOOK_CONFIG.mode == "dry_run":
        print("[TWILIO_INBOUND] Dry run mode - returning OK without processing")
        return PlainTextResponse("Dry run OK", status_code=200)
    
    # Handle paused mode
    if WEBHOOK_CONFIG.mode == "paused":
        print("[TWILIO_INBOUND] Paused mode - returning OK without processing")
        return PlainTextResponse("Webhook paused", status_code=200)
    
    # Normal processing (mode == "prod")
    try:
        From = payload_dict.get("From", "")
        Body = payload_dict.get("Body", "")
        
        print(f"[TWILIO_INBOUND] From={From}, Body={Body[:50]}...")
        
        if not From:
            print("[TWILIO_INBOUND] ERROR: Missing From field")
            return PlainTextResponse("Missing From field", status_code=400)
        
        # Normalize phone number from Twilio (E.164 format)
        normalized_phone = normalize_phone(From)
        print(f"[TWILIO_INBOUND] Normalized phone: {normalized_phone}")
        
        # Get conversation to check routing mode
        conn = get_conn()
        routing_mode = 'ai'  # Default to AI
        rep_user_id = None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT routing_mode, rep_user_id FROM conversations WHERE phone = %s LIMIT 1
            """, (normalized_phone,))
            row = cur.fetchone()
            if row:
                routing_mode = row[0] or 'ai'
                rep_user_id = row[1]
        
        print(f"[TWILIO_INBOUND] Routing mode: {routing_mode}, Rep user ID: {rep_user_id}")
        
        # Store inbound message in history regardless of routing mode
        from backend.rep_messaging import add_message_to_history
        add_message_to_history(conn, normalized_phone, "inbound", Body, "contact")
        
        # If routing mode is 'rep', don't auto-respond - rep will handle via UI
        if routing_mode == 'rep':
            print(f"[TWILIO_INBOUND] Conversation in rep mode - storing message, no auto-response")
            return PlainTextResponse("OK", status_code=200)
        
        # Continue with AI processing for 'ai' mode
        # Classify intent from message text (simple keyword-based for now)
        intent = classify_intent_simple(Body)
        print(f"[TWILIO_INBOUND] Classified intent: {intent}")
        
        # Prepare event payload for inbound_intelligent
        event = {
            "phone": normalized_phone,
            "text": Body,
            "body": Body,
            "intent": intent
        }
        
        print(f"[TWILIO_INBOUND] Calling inbound_intelligent for {normalized_phone}")
        
        # Call the intelligence handler directly (no HTTP overhead)
        result = await inbound_intelligent(event)
        
        print(f"[TWILIO_INBOUND] Intelligence result: {result}")
        
        # Get card by phone to generate contextual reply
        card = None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT card_id FROM conversations WHERE phone = %s LIMIT 1
            """, (normalized_phone,))
            row = cur.fetchone()
            if row and row[0]:
                card_id = row[0]
                card = get_card(conn, card_id)
        
        # Generate reply message using configured Markov responses
        reply_text = None
        if result.get("next_state"):
            next_state = result["next_state"]
            previous_state = result.get("previous_state", "initial_outreach")
            
            print(f"[TWILIO_INBOUND] State transition: {previous_state} → {next_state}")
            
            # Try to get configured response for this state
            configured_response = get_markov_response(conn, next_state)
            
            if configured_response:
                # If we have a card, substitute template placeholders
                if card and card.get("card_data"):
                    from backend.blast import _substitute_template
                    from archive_intelligence.message_processor.utils import load_sales_history, find_matching_fraternity
                    
                    data = card["card_data"]
                    sales_history = load_sales_history()
                    purchased_example = None
                    if isinstance(sales_history, dict):
                        purchased_example = find_matching_fraternity(data, sales_history)
                    
                    reply_text = _substitute_template(configured_response, data, purchased_example)
                    print(f"[TWILIO_INBOUND] Using configured response for state '{next_state}' (with template substitution)")
                else:
                    reply_text = configured_response
                    print(f"[TWILIO_INBOUND] Using configured response for state '{next_state}' (no substitution)")
            else:
                # Fallback: provide a helpful default response based on state
                fallback_responses = {
                    "interest": "Great! What would you like to know?",
                    "light_interest": "Awesome! I can help you get a fresh PNM list. What questions do you have?",
                    "strong_interest": "Excellent! Let's get you set up. What's your timeline?",
                    "pricing": "I'd be happy to discuss pricing. What's your chapter size?",
                    "asks_for_price": "Pricing depends on chapter size and delivery timeline. What are you looking for?",
                    "question": "I'm here to help! What would you like to know?",
                    "demo": "I can show you examples. What would be most helpful?",
                    "asks_for_example_list": "I can send you a sample list. What chapter are you interested in?",
                }
                
                # Try to find a fallback based on state or category
                fallback = fallback_responses.get(next_state)
                if not fallback:
                    # Try category-based fallback
                    intent_category = result.get("intent", {}).get("category")
                    if intent_category:
                        fallback = fallback_responses.get(intent_category)
                
                if fallback:
                    reply_text = fallback
                    print(f"[TWILIO_INBOUND] Using fallback response for state '{next_state}': {fallback}")
                else:
                    print(f"[TWILIO_INBOUND] No configured response for state '{next_state}' and no fallback available")
                    # Don't send a reply if not configured - prevents unwanted messages
        
        # Send explicit reply via Twilio (webhook return does NOT send SMS)
        # Filter out "OK" messages - don't send standalone "OK" responses
        if reply_text:
            reply_text_clean = reply_text.strip().upper()
            # Skip sending if reply is just "OK" or variations
            if reply_text_clean in ["OK", "OKAY", "K", "OK."]:
                print(f"[TWILIO_INBOUND] Skipping 'OK' message - not sending reply")
                reply_text = None
        
        if reply_text:
            try:
                twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
                twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
                twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
                twilio_messaging_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
                
                if twilio_sid and twilio_token:
                    client = Client(twilio_sid, twilio_token)
                    
                    if twilio_messaging_sid:
                        # Use Messaging Service (preferred for A2P)
                        msg = client.messages.create(
                            to=From,  # Use original From, not normalized
                            messaging_service_sid=twilio_messaging_sid,
                            body=reply_text
                        )
                    elif twilio_phone:
                        # Fallback to direct From number
                        msg = client.messages.create(
                            to=From,
                            from_=twilio_phone,
                            body=reply_text
                        )
                    else:
                        print("[TWILIO_INBOUND] WARNING: No Twilio Messaging Service SID or Phone Number configured")
                    
                    # Store outbound reply in conversation history
                    try:
                        from backend.rep_messaging import add_message_to_history
                        twilio_sid_value = msg.sid if 'msg' in locals() else None
                        add_message_to_history(conn, normalized_phone, "outbound", reply_text, "ai", twilio_sid_value)
                    except Exception as history_error:
                        print(f"[TWILIO_INBOUND] WARNING: Could not store outbound message in history: {history_error}")
                    
                    print(f"[TWILIO_INBOUND] Reply sent: {reply_text[:50]}... (SID: {msg.sid if 'msg' in locals() else 'N/A'})")
                else:
                    print("[TWILIO_INBOUND] WARNING: Twilio credentials not configured")
            except Exception as send_error:
                print(f"[TWILIO_INBOUND] ERROR sending reply: {send_error}")
                import traceback
                print(f"[TWILIO_INBOUND] Traceback: {traceback.format_exc()}")
        
        print(f"[TWILIO_INBOUND] Success: {result}")
        return PlainTextResponse("OK", status_code=200)
    except Exception as e:
        # Log error but return ok to Twilio (prevents retries on transient errors)
        # In production, you might want to log this to a monitoring service
        import traceback
        print(f"[TWILIO_INBOUND] ERROR processing webhook: {e}")
        print(f"[TWILIO_INBOUND] Traceback: {traceback.format_exc()}")
        return PlainTextResponse("OK", status_code=200)


# ============================================================================
# Admin Webhook Configuration Endpoints
# ============================================================================

@app.get("/admin/webhook/config")
async def get_webhook_config():
    """Get current webhook configuration."""
    return WEBHOOK_CONFIG.model_dump()


@app.post("/admin/webhook/config")
async def update_webhook_config(cfg: WebhookConfig = Body(...)):
    """Update webhook configuration."""
    WEBHOOK_CONFIG.enabled = cfg.enabled
    WEBHOOK_CONFIG.mode = cfg.mode
    WEBHOOK_CONFIG.log_payloads = cfg.log_payloads
    return {"ok": True, "config": WEBHOOK_CONFIG.model_dump()}


# ============================================================================
# Debug Endpoints (temporary - for route verification)
# ============================================================================

@app.get("/")
def root():
    """Root endpoint to verify app is loaded correctly."""
    return {"status": "ok", "message": "FastAPI app is running", "service": "rt4orgs-frats-backend", "version": "2024-12-15"}


@app.get("/health")
def health():
    """Health check endpoint to verify routing works."""
    return {"status": "ok", "service": "rt4orgs-frats-backend"}


@app.get("/__routes")
def list_routes():
    """List all available API routes for debugging."""
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": route.name
            })
    return {"routes": routes, "total": len(routes)}


# ============================================================================
# Legacy Endpoints (for backwards compatibility)
# ============================================================================

@app.get("/all")
async def get_all():
    """
    Legacy endpoint for backwards compatibility with old UI.
    Returns empty dict - new system uses /cards endpoint.
    """
    return {}


@app.get("/leads")
async def get_leads():
    """
    Get all leads - cards that have received inbound messages (responses).
    Leads = any cards with last_inbound_at set (not null).
    """
    conn = get_conn()
    leads = []
    
    with conn.cursor() as cur:
        # Get all conversations with inbound messages
        cur.execute("""
            SELECT DISTINCT c.card_id, c.phone, c.state, c.last_inbound_at, c.last_outbound_at,
                   COALESCE(c.history::text, '[]') as history
            FROM conversations c
            WHERE c.card_id IS NOT NULL
              AND c.last_inbound_at IS NOT NULL
            ORDER BY c.last_inbound_at DESC;
        """)
        
        rows = cur.fetchall()
        
        # Get card details for each lead
        for row in rows:
            card_id = row[0]
            phone = row[1]
            state = row[2]
            last_inbound_at = row[3]
            last_outbound_at = row[4]
            history_raw = row[5] if len(row) > 5 else '[]'
            
            # Get card details
            card = get_card(conn, card_id)
            if not card:
                continue
            
            # Parse history
            try:
                history = json.loads(history_raw) if isinstance(history_raw, str) else history_raw
            except:
                history = []
            
            # Count inbound messages
            inbound_count = sum(1 for msg in history if (
                isinstance(msg, dict) and msg.get("direction") == "inbound"
            ) or isinstance(msg, str))
            
            card_data = card.get("card_data", {})
            lead = {
                "card_id": card_id,
                "name": card_data.get("name", card_id),
                "phone": phone,
                "state": state,
                "last_inbound_at": last_inbound_at.isoformat() if last_inbound_at else None,
                "last_outbound_at": last_outbound_at.isoformat() if last_outbound_at else None,
                "inbound_count": inbound_count,
                "card_data": card_data,
                "sales_state": card.get("sales_state", "cold"),
            }
            leads.append(lead)
    
    return {
        "leads": leads,
        "count": len(leads)
    }


@app.get("/lead/{name}")
async def get_lead(name: str):
    """
    Get lead information by name.
    Finds person card by name and returns card data with conversations.
    Compatible with legacy lead.html UI.
    """
    conn = get_conn()
    
    # Find person card by name (case-insensitive search in card_data JSONB)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, type, card_data, sales_state, owner, created_at, updated_at
            FROM cards
            WHERE type = 'person'
            AND LOWER(card_data->>'name') = LOWER(%s)
            LIMIT 1;
        """, (name,))
        
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Lead not found: {name}")
        
        card_id = row[0]
        card_data = row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {}
        
        # Get conversations for this card
        cur.execute("""
            SELECT phone, state, last_outbound_at, last_inbound_at, history
            FROM conversations
            WHERE card_id = %s
            ORDER BY last_outbound_at DESC NULLS LAST, last_inbound_at DESC NULLS LAST;
        """, (card_id,))
        
        conversations = []
        latest_state = None
        
        for conv_row in cur.fetchall():
            conv_phone = conv_row[0]
            conv_state = conv_row[1]
            last_outbound = conv_row[2]
            last_inbound = conv_row[3]
            history = conv_row[4] if len(conv_row) > 4 else None
            
            # Parse history if it's a string
            if isinstance(history, str):
                try:
                    history = json.loads(history)
                except:
                    history = []
            elif history is None:
                history = []
            
            # Use the most recent conversation state as latest_state
            if latest_state is None:
                latest_state = {
                    "next_state": conv_state or "initial_outreach"
                }
            
            # Format as folder (for compatibility with lead.html)
            folder = {
                "folder": f"conversation_{conv_phone}",
                "state": {
                    "phone": conv_phone,
                    "state": conv_state,
                    "last_outbound_at": last_outbound.isoformat() if last_outbound else None,
                    "last_inbound_at": last_inbound.isoformat() if last_inbound else None,
                    "history": history
                },
                "message": ""  # No message stored in conversations table
            }
            conversations.append(folder)
        
        # If no conversations, create a default state
        if latest_state is None:
            latest_state = {
                "next_state": "initial_outreach"
            }
        
        return {
            "name": card_data.get("name", name),
            "latest_state": latest_state,
            "folders": conversations
        }


# ============================================================================
# Admin Migration Endpoint
# ============================================================================

@app.get("/admin/migrate/status")
async def migration_status():
    """
    Check migration status - verify if tables exist and migration ran.
    """
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Check if cards table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'cards'
                );
            """)
            cards_exists = cur.fetchone()[0]
            
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'card_relationships'
                );
            """)
            relationships_exists = cur.fetchone()[0]
            
            # Check if we can query cards table
            can_query = False
            card_count = 0
            if cards_exists:
                try:
                    cur.execute("SELECT COUNT(*) FROM cards;")
                    card_count = cur.fetchone()[0]
                    can_query = True
                except Exception as e:
                    can_query = False
            
        return JSONResponse(
            content={
                "ok": True,
                "cards_table_exists": cards_exists,
                "relationships_table_exists": relationships_exists,
                "can_query_cards": can_query,
                "card_count": card_count,
                "migration_needed": not cards_exists
            },
            status_code=200
        )
    except Exception as e:
        return JSONResponse(
            content={
                "ok": False,
                "error": str(e),
                "error_type": e.__class__.__name__
            },
            status_code=500
        )

@app.post("/admin/migrate")
async def admin_migrate():
    """
    Manually trigger database migration.
    Useful for verifying migration status or re-running if needed.
    """
    try:
        success, message = run_migration()
        if success:
            return JSONResponse(
                content={"ok": True, "message": message},
                status_code=200
            )
        else:
            return JSONResponse(
                content={"ok": False, "error": message},
                status_code=500
            )
    except Exception as e:
        return JSONResponse(
            content={
                "ok": False,
                "error": str(e),
                "error_type": e.__class__.__name__
            },
            status_code=500
        )


# ============================================================================
# Card API Endpoints
# ============================================================================

@app.post("/cards/upload")
async def upload_cards(cards: List[Dict[str, Any]]):
    """
    Upload array of heterogeneous JSON card objects.
    Validates schema, normalizes IDs, resolves references, and stores cards.
    """
    print("=" * 60)
    print("UPLOAD HIT")
    print("=" * 60)
    print(f"📤 Upload request: {len(cards)} card(s)")
    
    try:
        conn = get_conn()
    except Exception as db_error:
        print(f"❌ Database connection failed: {db_error}")
        return JSONResponse(
            content={
                "ok": False,
                "stored": 0,
                "errors": len(cards),
                "cards": [],
                "error_details": [{"error": f"Database connection failed: {str(db_error)}"}]
            },
            status_code=500
        )
    
    results = []
    errors = []
    
    # Log card types for debugging
    card_types = {}
    for card in cards:
        card_type = card.get("type", "unknown")
        card_types[card_type] = card_types.get(card_type, 0) + 1
    print(f"📋 Card types: {card_types}")
    
    for idx, card in enumerate(cards):
        # Normalize card
        normalized = normalize_card(card)
        card_id = normalized.get("id", "unknown")
        
        # Validate schema
        is_valid, error = validate_card_schema(normalized)
        if not is_valid:
            print(f"  ❌ Card {idx + 1}/{len(cards)} validation failed: {card_id} - {error}")
            errors.append({
                "index": idx,
                "card": normalized,
                "error": error
            })
            continue
        
        # Store card (allow missing references for initial upload)
        success, error_msg, stored_card = store_card(conn, normalized, allow_missing_references=True)
        
        if success:
            print(f"  ✅ Card {idx + 1}/{len(cards)} stored: {card_id}")
            results.append(stored_card)
        else:
            print(f"  ❌ Card {idx + 1}/{len(cards)} storage failed: {card_id} - {error_msg}")
            errors.append({
                "index": idx,
                "card": normalized,
                "error": error_msg
            })
    
    print(f"📊 Upload complete: {len(results)} stored, {len(errors)} errors")
    
    # Determine HTTP status code
    if len(errors) == 0:
        status_code = 200
    elif len(results) == 0:
        # All cards failed
        status_code = 400
    else:
        # Partial success
        status_code = 207  # Multi-Status
    
    return JSONResponse(
        content={
            "ok": len(errors) == 0,
            "stored": len(results),
            "errors": len(errors),
            "cards": results,
            "error_details": errors
        },
        status_code=status_code
    )


@app.get("/cards/{card_id}")
async def get_card_endpoint(card_id: str):
    """Get a single card by ID."""
    conn = get_conn()
    card = get_card(conn, card_id)
    
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    
    # Get relationships
    relationships = get_card_relationships(conn, card_id)
    card["relationships"] = relationships
    
    # Get linked conversations with message history
    with conn.cursor() as cur:
        try:
            # Try to fetch with history column
            cur.execute("""
                SELECT phone, state, last_outbound_at, last_inbound_at, 
                       COALESCE(history::text, '[]') as history
                FROM conversations
                WHERE card_id = %s
                ORDER BY last_outbound_at DESC NULLS LAST;
            """, (card_id,))
        except psycopg2.ProgrammingError:
            # History column doesn't exist, fetch without it
            cur.execute("""
                SELECT phone, state, last_outbound_at, last_inbound_at
                FROM conversations
                WHERE card_id = %s
                ORDER BY last_outbound_at DESC NULLS LAST;
            """, (card_id,))
        
        conversations = []
        for row in cur.fetchall():
            conv_data = {
                "phone": row[0],
                "state": row[1],
                "last_outbound_at": row[2].isoformat() if row[2] else None,
                "last_inbound_at": row[3].isoformat() if row[3] else None,
            }
            
            # Include history if available
            if len(row) > 4 and row[4]:
                try:
                    history = json.loads(row[4]) if isinstance(row[4], str) else row[4]
                    conv_data["history"] = history
                except (json.JSONDecodeError, TypeError):
                    conv_data["history"] = []
            else:
                conv_data["history"] = []
            
            conversations.append(conv_data)
        card["conversations"] = conversations
    
    return card


@app.delete("/cards/{card_id}")
async def delete_card_endpoint(card_id: str):
    """Delete a card by ID. Also deletes related relationships and conversations."""
    conn = get_conn()
    
    # Check if card exists
    card = get_card(conn, card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    
    try:
        with conn.cursor() as cur:
            # Delete relationships (cascade should handle this, but explicit is safer)
            cur.execute(
                "DELETE FROM card_relationships WHERE parent_card_id = %s OR child_card_id = %s",
                (card_id, card_id)
            )
            
            # Delete conversations linked to this card
            cur.execute(
                "DELETE FROM conversations WHERE card_id = %s",
                (card_id,)
            )
            
            # Delete the card itself
            cur.execute("DELETE FROM cards WHERE id = %s", (card_id,))
            
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
        
        return {"ok": True, "message": f"Card {card_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting card: {str(e)}")


@app.get("/cards")
async def list_cards(
    type: Optional[str] = Query(None, description="Filter by card type"),
    sales_state: Optional[str] = Query(None, description="Filter by sales state"),
    owner: Optional[str] = Query(None, description="Filter by owner"),
    where: Optional[str] = Query(None, description="JSON where clause"),
    limit: Optional[int] = Query(10000, description="Limit results"),
    offset: Optional[int] = Query(0, description="Offset results")
):
    """
    List cards with optional filters.
    Supports type, sales_state, owner filters, or complex where clause.
    """
    # #region agent log - Cards endpoint entry
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:CARDS_ENDPOINT_ENTRY",
                "message": "Cards endpoint called",
                "data": {"type": type, "sales_state": sales_state, "owner": owner, "limit": limit},
                "hypothesisId": "F"
            }) + "\n")
    except:
        pass
    # #endregion
    
    try:
        # #region agent log - Before get_conn
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:BEFORE_GET_CONN",
                    "message": "About to get database connection",
                    "data": {},
                    "hypothesisId": "F"
                }) + "\n")
        except:
            pass
        # #endregion
        
        conn = get_conn()
        
        # #region agent log - After get_conn
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:AFTER_GET_CONN",
                    "message": "Database connection obtained",
                    "data": {"connection_status": "success"},
                    "hypothesisId": "F"
                }) + "\n")
        except:
            pass
        # #endregion
        
        # Quick check: Try a simple query first - if it fails with UndefinedTable, we know table doesn't exist
        # This is faster than checking information_schema
        # #region agent log - Quick table check
        table_exists = False
        try:
            import time
            check_start = time.time()
            with conn.cursor() as check_cur:
                # Set a short timeout for the check
                check_cur.execute("SET statement_timeout = '5s'")
                # Try a simple query - this will fail fast if table doesn't exist
                try:
                    check_cur.execute("SELECT 1 FROM cards LIMIT 1")
                    table_exists = True
                except psycopg2.errors.UndefinedTable:
                    table_exists = False
                except Exception as check_inner_e:
                    # Any other error means table probably doesn't exist
                    print(f"⚠️  Table check error: {check_inner_e}")
                    table_exists = False
            
            check_duration = time.time() - check_start
            
            # Best-effort logging; do not let log failures affect table_exists
            try:
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:TABLE_EXISTS_CHECK",
                        "message": "Checked if cards table exists",
                        "data": {"table_exists": table_exists, "check_duration_ms": int(check_duration * 1000)},
                        "hypothesisId": "F"
                    }) + "\n")
            except Exception:
                # Ignore logging errors entirely in production
                pass
        except Exception as check_outer_e:
            # If the check itself fails, assume table doesn't exist and try migration
            import time
            print(f"⚠️  Table check failed: {check_outer_e}")
            try:
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:TABLE_CHECK_EXCEPTION",
                        "message": "Table check threw exception",
                        "data": {"error": str(check_outer_e), "error_type": type(check_outer_e).__name__},
                        "hypothesisId": "F"
                    }) + "\n")
            except:
                pass
            table_exists = False
        
        # If table doesn't exist, try auto-migration BEFORE building query
        if not table_exists:
            # #region agent log - Table missing, attempting auto-migration
            try:
                import time
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:AUTO_MIGRATION_TRIGGER",
                        "message": "Table missing, attempting auto-migration",
                        "data": {},
                        "hypothesisId": "H"
                    }) + "\n")
            except:
                pass
            # #endregion
            
            # Auto-run migration as fallback
            print("⚠️  Cards table not found - running migration automatically...")
            try:
                success, message = run_migration()
                if success:
                    print(f"✅ Auto-migration successful: {message}")
                    # Verify table was created
                    try:
                        with conn.cursor() as verify_cur:
                            verify_cur.execute("SELECT 1 FROM cards LIMIT 1")
                            table_exists = True
                            print("✅ Verified: cards table now exists")
                    except psycopg2.errors.UndefinedTable:
                        table_exists = False
                        print("❌ Warning: Migration reported success but table still doesn't exist")
                else:
                    print(f"❌ Auto-migration failed: {message}")
                    return JSONResponse(
                        content={
                            "ok": False,
                            "error": f"cards table does not exist and auto-migration failed: {message}",
                            "error_type": "MigrationFailed",
                            "suggestion": "Run migration manually via POST /admin/migrate"
                        },
                        status_code=500
                    )
            except Exception as migration_error:
                print(f"❌ Auto-migration error: {migration_error}")
                import traceback
                print(f"📋 Traceback: {traceback.format_exc()}")
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": f"cards table does not exist and auto-migration error: {str(migration_error)}",
                        "error_type": "MigrationError",
                        "suggestion": "Run migration manually via POST /admin/migrate"
                    },
                    status_code=500
                )
            
            # If table still doesn't exist after migration, return error
            if not table_exists:
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "cards table does not exist after auto-migration attempt",
                        "error_type": "MissingTable",
                        "suggestion": "Run migration manually via POST /admin/migrate and check logs"
                    },
                    status_code=500
                )
        # #endregion
        
        # Build where clause
        where_dict = {}
        if type:
            where_dict["type"] = type
        if sales_state:
            where_dict["sales_state"] = sales_state
        if owner:
            where_dict["owner"] = owner
        
        # Parse where JSON if provided
        if where:
            try:
                where_json = json.loads(where)
                where_dict.update(where_json)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON in where parameter")
        
        # Build query
        query, params = build_list_query(where=where_dict if where_dict else None, limit=limit, offset=offset)
        
        # Execute query with timeout protection and immediate error handling
        cards = []
        
        # #region agent log - Before query execution
        try:
            import time
            query_start = time.time()
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:BEFORE_QUERY_EXEC_DETAILED",
                    "message": "About to execute SELECT query",
                    "data": {"query_preview": query[:100], "params_count": len(params)},
                    "hypothesisId": "F"
                }) + "\n")
        except:
            pass
        # #endregion
        
        try:
            with conn.cursor() as cur:
                # Set statement timeout to prevent hanging (10 seconds - fail fast)
                cur.execute("SET statement_timeout = '10s'")
                
                # Execute query - this will fail immediately if table doesn't exist
                cur.execute(query, params)
                
                # #region agent log - After query execution
                try:
                    import time
                    query_duration = time.time() - query_start
                    with open(_log_file, "a") as f:
                        f.write(_json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "timestamp": int(time.time() * 1000),
                            "location": f"{__file__}:AFTER_QUERY_EXEC",
                            "message": "Query executed successfully",
                            "data": {"duration_ms": int(query_duration * 1000)},
                            "hypothesisId": "F"
                        }) + "\n")
                except:
                    pass
                # #endregion
                
                rows = cur.fetchall()
                
                # #region agent log - After fetchall
                try:
                    import time
                    with open(_log_file, "a") as f:
                        f.write(_json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "timestamp": int(time.time() * 1000),
                            "location": f"{__file__}:AFTER_FETCHALL",
                            "message": "Fetched rows from query",
                            "data": {"row_count": len(rows)},
                            "hypothesisId": "F"
                        }) + "\n")
                except:
                    pass
                # #endregion
                
                for row in rows:
                    # Handle JSONB data - convert to dict if needed
                    card_data = row[2]
                    if isinstance(card_data, str):
                        try:
                            card_data = json.loads(card_data)
                        except:
                            pass
                    elif hasattr(card_data, 'dict'):  # psycopg2.extras.Json object
                        card_data = card_data.dict()
                    
                    cards.append({
                        "id": row[0],
                        "type": row[1],
                        "card_data": card_data,
                        "sales_state": row[3],
                        "owner": row[4],
                        "created_at": row[5].isoformat() if row[5] else None,
                        "updated_at": row[6].isoformat() if row[6] else None,
                    })
        except psycopg2.errors.UndefinedTable as table_error:
            # #region agent log - Table missing error from query
            try:
                import time
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:TABLE_MISSING_ERROR",
                        "message": "Table does not exist error from query - attempting auto-migration",
                        "data": {"error": str(table_error)},
                        "hypothesisId": "F"
                    }) + "\n")
            except:
                pass
            # #endregion
            
            # Table doesn't exist - try auto-migration as last resort
            print("⚠️  Query failed: cards table does not exist - running migration automatically...")
            try:
                success, message = run_migration()
                if success:
                    print(f"✅ Auto-migration successful: {message}")
                    # Retry the query after migration
                    try:
                        with conn.cursor() as retry_cur:
                            retry_cur.execute("SET statement_timeout = '10s'")
                            retry_cur.execute(query, params)
                            rows = retry_cur.fetchall()
                            cards = []
                            for row in rows:
                                card_data = row[2]
                                if isinstance(card_data, str):
                                    try:
                                        card_data = json.loads(card_data)
                                    except:
                                        pass
                                elif hasattr(card_data, 'dict'):
                                    card_data = card_data.dict()
                                
                                cards.append({
                                    "id": row[0],
                                    "type": row[1],
                                    "card_data": card_data,
                                    "sales_state": row[3],
                                    "owner": row[4],
                                    "created_at": row[5].isoformat() if row[5] else None,
                                    "updated_at": row[6].isoformat() if row[6] else None,
                                })
                            
                            result = {
                                "cards": cards,
                                "count": len(cards)
                            }
                            return JSONResponse(
                                content=jsonable_encoder(result),
                                status_code=200
                            )
                    except Exception as retry_error:
                        return JSONResponse(
                            content={
                                "ok": False,
                                "error": f"Migration succeeded but query retry failed: {str(retry_error)}",
                                "error_type": "RetryFailed",
                                "migration_message": message
                            },
                            status_code=500
                        )
                else:
                    return JSONResponse(
                        content={
                            "ok": False,
                            "error": f"cards table does not exist and auto-migration failed: {message}",
                            "error_type": "MigrationFailed",
                            "suggestion": "Run migration manually via POST /admin/migrate"
                        },
                        status_code=500
                    )
            except Exception as migration_error:
                import traceback
                print(f"❌ Auto-migration error: {migration_error}")
                print(f"📋 Traceback: {traceback.format_exc()}")
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": f"cards table does not exist and auto-migration error: {str(migration_error)}",
                        "error_type": "MigrationError",
                        "suggestion": "Run migration manually via POST /admin/migrate"
                    },
                    status_code=500
                )
        except psycopg2.errors.QueryCanceled as timeout_error:
            # #region agent log - Query timeout
            try:
                import time
                with open(_log_file, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(time.time() * 1000),
                        "location": f"{__file__}:QUERY_TIMEOUT",
                        "message": "Query timed out",
                        "data": {"error": str(timeout_error)},
                        "hypothesisId": "F"
                    }) + "\n")
            except:
                pass
            # #endregion
            return JSONResponse(
                content={
                    "ok": False,
                    "error": "Query timed out - database may be slow or table may not exist",
                    "error_type": "QueryTimeout",
                    "detail": str(timeout_error)
                },
                status_code=500
            )
        
        result = {
            "cards": cards,
            "count": len(cards)
        }
        
        # #region agent log - Before JSON response
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:BEFORE_JSON_RESPONSE",
                    "message": "About to return JSON response",
                    "data": {"card_count": len(cards)},
                    "hypothesisId": "F"
                }) + "\n")
        except:
            pass
        # #endregion
        
        # Force JSON serialization to handle any non-serializable types
        return JSONResponse(
            content=jsonable_encoder(result),
            status_code=200
        )
    except Exception as e:
        # Return detailed error for debugging
        import traceback
        # Use __class__ instead of type() to avoid shadowing issues
        error_type = e.__class__.__name__ if e else "UnknownError"
        
        error_detail = {
            "error": str(e) if e else "Unknown error occurred",
            "error_type": error_type,
            "traceback": traceback.format_exc()
        }
        
        # Return as JSONResponse to ensure proper serialization
        return JSONResponse(
            content=jsonable_encoder(error_detail),
            status_code=500
        )


# ============================================================================
# Messaging API Endpoints
# ============================================================================

@app.post("/messages/send")
async def send_message(request: Dict[str, Any]):
    """
    Send message to target (contact, entity, or query).
    Resolves target to contact cards, then sends via /events/outbound.
    """
    conn = get_conn()
    
    target = request.get("target")
    if not target:
        raise HTTPException(status_code=400, detail="Missing 'target' in request")
    
    message_type = request.get("message_type", "outbound")
    template = request.get("template")
    owner = request.get("owner", "system")
    source_batch_id = request.get("source_batch_id")
    
    # Resolve target to contact cards
    contact_cards, error = resolve_target(conn, target)
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    if not contact_cards:
        raise HTTPException(status_code=400, detail="Target resolved to no contact cards")
    
    # Extract phone numbers
    phones = extract_phones_from_cards(contact_cards)
    
    # Send to each contact via /events/outbound
    results = []
    for card in contact_cards:
        phone = card["card_data"].get("phone")
        if not phone:
            continue
        
        # Create outbound event
        event = {
            "phone": phone,
            "card_id": card["id"],  # Use card_id for new system
            "contact_id": card["id"],  # Keep for backward compatibility
            "owner": card.get("owner") or owner,
            "source_batch_id": source_batch_id,
        }
        
        # Call outbound endpoint (internal call)
        try:
            result = await outbound(event)
            results.append({
                "card_id": card["id"],
                "phone": phone,
                "status": "sent",
                "result": result
            })
        except Exception as e:
            results.append({
                "card_id": card["id"],
                "phone": phone,
                "status": "error",
                "error": str(e)
            })
    
    return {
        "ok": True,
        "target": target,
        "contacts_resolved": len(contact_cards),
        "messages_sent": len([r for r in results if r["status"] == "sent"]),
        "results": results
    }


# ============================================================================
# Markov Response Configuration Endpoints
# ============================================================================

def generate_state_color(state_key: str) -> str:
    """
    Generate a deterministic color for a state key using a simple hash.
    Returns a hex color code.
    """
    # Simple hash function for deterministic colors
    hash_val = hash(state_key) % (256 * 256 * 256)
    r = (hash_val >> 16) & 0xFF
    g = (hash_val >> 8) & 0xFF
    b = hash_val & 0xFF
    
    # Adjust brightness to ensure colors are visible (not too dark)
    r = max(100, min(220, r))
    g = max(100, min(220, g))
    b = max(100, min(220, b))
    
    return f"#{r:02x}{g:02x}{b:02x}"


def get_all_markov_states() -> List[Dict[str, Any]]:
    """
    Get all Markov states from the intelligence registry.
    Flattens the conversation tree and includes the root state.
    Returns list of {state_key, label, description, color}
    """
    all_states = set()
    
    # Add root state
    all_states.add(ROOT_STATE)
    
    # Flatten the tree - add all parent states and their children
    for parent, children in CONVERSATION_TREE.items():
        all_states.add(parent)
        all_states.update(children)
    
    # Convert to sorted list for consistent ordering
    state_list = sorted(all_states)
    
    # Build the response with metadata
    result = []
    for state_key in state_list:
        description = SUBTAM_DESCRIPTIONS.get(state_key, "")
        # Use human-readable label (convert snake_case to Title Case)
        label = state_key.replace("_", " ").title()
        
        result.append({
            "state_key": state_key,
            "label": label,
            "description": description,
            "color": generate_state_color(state_key),
        })
    
    return result


@app.get("/markov/states")
async def get_markov_states():
    """
    Get all possible Markov/SubTAM states from the intelligence registry.
    This is the authoritative source of which states exist (code-defined, not DB).
    Returns list of {state_key, label, description, color}
    """
    states = get_all_markov_states()
    return states


@app.get("/markov/responses")
async def get_markov_responses():
    """Get all configured Markov state responses."""
    conn = get_conn()
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT state_key, response_text, description, updated_at
            FROM markov_responses
            ORDER BY state_key;
        """)
        rows = cur.fetchall()
    
    responses = {
        row[0]: {
            "response_text": row[1],
            "description": row[2],
            "updated_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    }
    
    # Also get initial outreach (stored as special key)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT response_text FROM markov_responses WHERE state_key = '__initial_outreach__'
        """)
        row = cur.fetchone()
        initial_outreach = row[0] if row else None
    
    return {
        "responses": responses,
        "initial_outreach": initial_outreach,
    }


@app.post("/markov/response")
async def update_single_markov_response(payload: Dict[str, Any] = Body(...)):
    """Update a single Markov state response. Payload: {state_key: str, response_text: str, description: str?}"""
    logger.info("🧠 ENTER save_markov_response")
    logger.info(f"📦 payload={json.dumps(payload, indent=2)}")
    
    conn = get_conn()
    
    state_key = payload.get("state_key")
    response_text = payload.get("response_text", "")
    description = payload.get("description", "")
    
    if not state_key:
        logger.error("❌ Missing state_key in payload")
        raise HTTPException(status_code=400, detail="state_key is required")
    
    logger.info(f"✏️ Saving state: {state_key}")
    logger.debug(f"Response text length: {len(response_text)}")
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO markov_responses (state_key, response_text, description, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (state_key)
                DO UPDATE SET
                    response_text = EXCLUDED.response_text,
                    description = EXCLUDED.description,
                    updated_at = EXCLUDED.updated_at;
            """, (state_key, response_text, description, datetime.utcnow()))
        
        logger.info(f"✅ Saved state: {state_key}")
        logger.info("✅ SAVE COMPLETE")
        return {"ok": True, "state_key": state_key, "message": "Response saved successfully"}
    except Exception as e:
        logger.error(f"❌ Failed saving state: {state_key}")
        logger.exception(e)
        raise


@app.post("/markov/responses")
async def update_markov_responses(payload: Dict[str, Any] = Body(...)):
    """Update Markov state responses. Payload: {responses: {state_key: {response_text, description}}, initial_outreach: str}"""
    logger.info("📥 POST /markov/responses called (batch)")
    logger.info(f"📦 Payload keys: {list(payload.keys())}")
    
    responses = payload.get("responses", {})
    initial_outreach = payload.get("initial_outreach")
    
    logger.info(f"📥 JSON import triggered")
    logger.info(f"States in import: {list(responses.keys())}")
    logger.info(f"Initial outreach present: {initial_outreach is not None}")
    
    conn = get_conn()
    
    saved_count = 0
    failed_count = 0
    
    try:
        with conn.cursor() as cur:
            # Update/insert state responses
            for state_key, config in responses.items():
                logger.info(f"✏️ Saving state: {state_key}")
                response_text = config.get("response_text", "")
                description = config.get("description", "")
                logger.debug(f"Response text length: {len(response_text)}")
                
                try:
                    cur.execute("""
                        INSERT INTO markov_responses (state_key, response_text, description, updated_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (state_key)
                        DO UPDATE SET
                            response_text = EXCLUDED.response_text,
                            description = EXCLUDED.description,
                            updated_at = EXCLUDED.updated_at;
                    """, (state_key, response_text, description, datetime.utcnow()))
                    logger.info(f"✅ Saved state: {state_key}")
                    saved_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed saving state: {state_key}")
                    logger.exception(e)
                    failed_count += 1
            
            # Update initial outreach (special key)
            if initial_outreach is not None:
                logger.info("✏️ Saving initial_outreach")
                try:
                    cur.execute("""
                        INSERT INTO markov_responses (state_key, response_text, updated_at)
                        VALUES ('__initial_outreach__', %s, %s)
                        ON CONFLICT (state_key)
                        DO UPDATE SET
                            response_text = EXCLUDED.response_text,
                            updated_at = EXCLUDED.updated_at;
                    """, (initial_outreach, datetime.utcnow()))
                    logger.info("✅ Saved initial_outreach")
                    saved_count += 1
                except Exception as e:
                    logger.error("❌ Failed saving initial_outreach")
                    logger.exception(e)
                    failed_count += 1
        
        logger.info(f"✅ Batch save complete: {saved_count} saved, {failed_count} failed")
        return {"ok": True, "message": "Responses updated successfully", "saved": saved_count, "failed": failed_count}
    except Exception as e:
        logger.error("❌ Batch save failed")
        logger.exception(e)
        raise


def classify_intent_simple(text: str) -> Dict[str, Any]:
    """
    Simple keyword-based intent classifier.
    Returns intent dict with 'category' and/or 'subcategory' keys.
    """
    if not text:
        return {}
    
    text_lower = text.lower().strip()
    
    # Interest indicators
    if any(word in text_lower for word in ["interested", "yes", "sounds good", "tell me more", "i want", "i need"]):
        return {"category": "interest", "subcategory": "light_interest"}
    
    # Pricing questions
    if any(word in text_lower for word in ["price", "cost", "how much", "$", "dollar", "pay"]):
        return {"category": "pricing", "subcategory": "asks_for_price"}
    
    # Questions
    if any(word in text_lower for word in ["what", "how", "when", "where", "why", "?", "question"]):
        return {"category": "question"}
    
    # Objections
    if any(word in text_lower for word in ["no", "not interested", "don't", "can't", "won't", "too expensive"]):
        return {"category": "objection"}
    
    # Demo requests
    if any(word in text_lower for word in ["example", "sample", "demo", "show me", "preview"]):
        return {"category": "demo", "subcategory": "asks_for_example_list"}
    
    # Purchase intent
    if any(word in text_lower for word in ["buy", "purchase", "order", "sign up", "ready"]):
        return {"category": "purchase"}
    
    # Default: treat as interest if positive sentiment
    if any(word in text_lower for word in ["ok", "okay", "sure", "yeah", "yep"]):
        return {"category": "interest", "subcategory": "light_interest"}
    
    return {}


def get_markov_response(conn: Any, state_key: str) -> Optional[str]:
    """Get configured response text for a Markov state, or None if not configured."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT response_text FROM markov_responses WHERE state_key = %s
        """, (state_key,))
        row = cur.fetchone()
        return row[0] if row else None


def get_initial_outreach_message(conn: Any) -> Optional[str]:
    """Get configured initial outreach message, or None if not configured."""
    return get_markov_response(conn, "__initial_outreach__")


# ============================================================================
# Card-centric Blast Endpoint
# ============================================================================

# ============================================================================
# Authentication Dependency (must be defined before endpoints that use it)
# ============================================================================

async def get_current_user(request: Request) -> Dict[str, Any]:
    """FastAPI dependency to get current user from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    
    logger.info(f"[AUTH] Authorization header: {auth_header[:30] + '...' if auth_header and len(auth_header) > 30 else auth_header}")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("[AUTH] Missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = auth_header[7:]
    conn = get_conn()
    user = get_user_by_token(conn, token)
    
    if not user:
        logger.warning(f"[AUTH] Invalid API token (token preview: {token[:15]}...)")
        raise HTTPException(status_code=401, detail="Invalid API token")
    
    logger.info(f"[AUTH] Authenticated user: {user['id']} role={user['role']} username={user.get('username', 'N/A')}")
    return user


async def get_current_admin_user(request: Request) -> Dict[str, Any]:
    """FastAPI dependency to get current admin/owner user."""
    user = await get_current_user(request)
    # Owner (admin role) has full access
    if user.get("role") != "admin":
        logger.warning(f"[AUTH] Forbidden admin access by {user['id']} (role: {user.get('role')})")
        raise HTTPException(status_code=403, detail="Owner/Admin access required")
    logger.info(f"[AUTH] Admin access granted to {user['id']}")
    return user


async def get_current_owner_or_rep(request: Request) -> Dict[str, Any]:
    """FastAPI dependency that allows both owner and rep access."""
    return await get_current_user(request)


@app.post("/blast/run")
async def blast_run(
    request: Request, 
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_admin_user)  # GATE-LOCKED: Owner only
):
    """
    LEGACY BLAST ENDPOINT - Owner/Admin only.
    This is the old global blast endpoint. Use /rep/blast for rep-scoped blasting.
    
    Payload:
    {
      "card_ids": ["card_1", "card_2"],  # required
      "limit": 10,                       # optional, cap number of cards
      "owner": "system",                 # optional, defaults to 'system'
      "source": "cards_ui",              # optional, defaults to 'cards_ui'
      "auth_token": "token"              # optional, authorization token
    }
    
    Authorization can also be provided via Authorization header (Bearer token).
    """
    logger.info(f"[LEGACY_BLAST] Called by {current_user['id']} (role: {current_user.get('role')})")
    logger.warning(f"[LEGACY_BLAST] Legacy endpoint used - should migrate to admin dashboard or /rep/blast")
    card_ids = payload.get("card_ids") or []
    if not isinstance(card_ids, list) or not card_ids:
        raise HTTPException(status_code=400, detail="card_ids must be a non-empty array")

    limit = payload.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="limit must be an integer")

    owner = payload.get("owner") or "system"
    source = payload.get("source") or "cards_ui"
    
    # Get auth token from payload or Authorization header
    auth_token = payload.get("auth_token")
    if not auth_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]
    
    # Log auth token status (without exposing the full token)
    if auth_token:
        print(f"[BLAST_AUTH] ✅ Auth token received from request")
        print(f"[BLAST_AUTH]   Token preview: {auth_token[:15]}... (length: {len(auth_token)})")
        print(f"[BLAST_AUTH]   Source: {'payload' if payload.get('auth_token') else 'Authorization header'}")
    else:
        print("[BLAST_AUTH] ⚠️ No auth token provided in request, will use environment variable")

    conn = get_conn()

    try:
        result = run_blast_for_cards(
            conn=conn,
            card_ids=card_ids,
            limit=limit,
            owner=owner,
            source=source,
            auth_token=auth_token,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Blast failed: {str(e)}")


# Authentication dependencies are defined above, before /blast/run endpoint


# ============================================================================
# Admin Endpoints
# ============================================================================

@app.post("/admin/users")
async def admin_create_user(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_admin_user)
):
    """Create a new rep user."""
    logger.info(f"[ADMIN] create_user called by {current_user['id']}")
    logger.info(f"[ADMIN] payload = {payload}")
    
    username = payload.get("username")
    role = payload.get("role", "rep")
    twilio_phone = payload.get("twilio_phone_number")
    twilio_account_sid = payload.get("twilio_account_sid")
    twilio_auth_token = payload.get("twilio_auth_token")
    user_id = payload.get("user_id")
    
    if not username:
        logger.warning(f"[ADMIN] create_user failed: username required")
        raise HTTPException(status_code=400, detail="username is required")
    
    conn = get_conn()
    try:
        user = create_user(
            conn, username, role, twilio_phone,
            twilio_account_sid, twilio_auth_token, user_id
        )
        logger.info(f"[ADMIN] create_user success: {user['id']} ({user['username']})")
        return {"ok": True, "user": user}
    except Exception as e:
        logger.error(f"[ADMIN] create_user failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")


@app.get("/admin/users")
async def admin_list_users(current_user: Dict = Depends(get_current_admin_user)):
    """List all users."""
    conn = get_conn()
    users = list_users(conn, include_inactive=True)
    return {"ok": True, "users": users}


@app.put("/admin/users/{user_id}")
async def admin_update_user(
    user_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_admin_user)
):
    """Update a user's Twilio configuration (phone pairing)."""
    logger.info(f"[ADMIN] update_user called by {current_user['id']} for {user_id}")
    logger.info(f"[ADMIN] payload = {payload}")
    
    conn = get_conn()
    
    phone = payload.get("twilio_phone_number")
    account_sid = payload.get("twilio_account_sid")
    auth_token = payload.get("twilio_auth_token")
    
    try:
        success = update_user_twilio_config(conn, user_id, phone, account_sid, auth_token)
        
        if success:
            logger.info(f"[ADMIN] update_user success: {user_id}")
            return {"ok": True, "message": "User updated successfully"}
        else:
            logger.warning(f"[ADMIN] update_user failed: no rows updated for {user_id}")
            raise HTTPException(status_code=500, detail="Failed to update user")
    except Exception as e:
        logger.error(f"[ADMIN] update_user exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")


@app.post("/admin/assignments")
async def admin_assign_card(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_admin_user)
):
    """Assign a card to a rep."""
    logger.info(f"[ADMIN] assign_card called by {current_user['id']}")
    logger.info(f"[ADMIN] payload = {payload}")
    
    card_id = payload.get("card_id")
    user_id = payload.get("user_id")
    notes = payload.get("notes")
    
    if not card_id or not user_id:
        logger.warning(f"[ADMIN] assign_card failed: missing card_id or user_id")
        raise HTTPException(status_code=400, detail="card_id and user_id are required")
    
    conn = get_conn()
    try:
        success = assign_card_to_rep(conn, card_id, user_id, current_user["id"], notes)
        
        if success:
            logger.info(f"[ADMIN] assign_card success: {card_id} -> {user_id}")
            return {"ok": True, "message": "Card assigned successfully"}
        else:
            logger.warning(f"[ADMIN] assign_card failed: assignment function returned False")
            raise HTTPException(status_code=500, detail="Failed to assign card")
    except Exception as e:
        logger.error(f"[ADMIN] assign_card exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to assign card: {str(e)}")


@app.get("/admin/assignments")
async def admin_list_assignments(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: Dict = Depends(get_current_admin_user)
):
    """List all assignments."""
    conn = get_conn()
    assignments = list_assignments(conn, user_id=user_id, status=status)
    return {"ok": True, "assignments": assignments}


@app.put("/admin/assignments/{card_id}")
async def admin_update_assignment(
    card_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_admin_user)
):
    """Update assignment status."""
    status = payload.get("status")
    notes = payload.get("notes")
    
    if not status:
        raise HTTPException(status_code=400, detail="status is required")
    
    # Get assignment to find user_id
    conn = get_conn()
    assignment = get_card_assignment(conn, card_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    success = update_assignment_status(conn, card_id, assignment["user_id"], status, notes)
    
    if success:
        return {"ok": True, "message": "Assignment updated successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update assignment")


@app.delete("/admin/assignments/{card_id}/{user_id}")
async def admin_unassign_card(
    card_id: str,
    user_id: str,
    current_user: Dict = Depends(get_current_admin_user)
):
    """Unassign a card from a rep."""
    logger.info(f"[ADMIN] unassign_card called by {current_user['id']} for card {card_id} from user {user_id}")
    
    conn = get_conn()
    try:
        from backend.assignments import unassign_card
        success = unassign_card(conn, card_id, user_id)
        
        if success:
            logger.info(f"[ADMIN] unassign_card success: {card_id} unassigned from {user_id}")
            return {"ok": True, "message": "Card unassigned successfully"}
        else:
            logger.warning(f"[ADMIN] unassign_card failed: card {card_id} not assigned to {user_id}")
            raise HTTPException(status_code=404, detail="Assignment not found")
    except Exception as e:
        logger.error(f"[ADMIN] unassign_card exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to unassign card: {str(e)}")


# ============================================================================
# Rep Endpoints
# ============================================================================

@app.get("/rep/cards")
async def rep_get_cards(
    status: Optional[str] = None,
    current_user: Dict = Depends(get_current_owner_or_rep)
):
    """
    Get rep's assigned cards. 
    
    CRITICAL SECURITY: Reps can ONLY see assigned cards, never all cards.
    Owner (admin role) can see all cards for admin dashboard.
    
    Database relationship: card_assignments table links cards to reps via:
    - card_assignments.card_id -> cards.id
    - card_assignments.user_id -> users.id
    """
    conn = get_conn()
    
    user_role = current_user.get("role")
    user_id = current_user.get("id")
    username = current_user.get("username", "N/A")
    
    logger.info(f"[REP_CARDS] Request from user_id={user_id}, username={username}, role={user_role}")
    
    # CRITICAL: Reps can ONLY see assigned cards, never all cards
    # Double-check: if role is not explicitly "admin", treat as rep
    if user_role == "admin":
        # Owner: get all cards (for admin dashboard)
        logger.info(f"[REP_CARDS] Owner access - returning all cards")
        from backend.query import build_list_query
        query, params = build_list_query(where={}, limit=10000)
        
        cards = []
        with conn.cursor() as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                cards.append({
                    "id": row[0],
                    "type": row[1],
                    "card_data": row[2],
                    "sales_state": row[3],
                    "owner": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                    "updated_at": row[6].isoformat() if row[6] else None,
                })
        logger.info(f"[REP_CARDS] Owner - returning {len(cards)} total cards")
    else:
        # Rep: STRICT enforcement - ONLY assigned cards via card_assignments table
        # This is the security boundary - reps NEVER see unassigned cards
        logger.info(f"[REP_CARDS] Rep access (role={user_role}) - STRICT filtering via card_assignments table for user_id={user_id}")
        
        # Verify user_id exists
        if not user_id:
            logger.error(f"[REP_CARDS] ERROR: No user_id in current_user dict!")
            raise HTTPException(status_code=500, detail="User ID not found")
        
        # Check assignment count first
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM card_assignments WHERE user_id = %s", (user_id,))
            assignment_count = cur.fetchone()[0] or 0
            logger.info(f"[REP_CARDS] Rep {user_id} has {assignment_count} assignments in card_assignments table")
        
        # Get assigned cards via INNER JOIN (only cards in card_assignments)
        cards = get_rep_assigned_cards(conn, user_id, status=status)
        logger.info(f"[REP_CARDS] Rep {user_id} ({username}) - found {len(cards)} assigned cards via get_rep_assigned_cards")
        
        # Security check: verify count matches
        if len(cards) != assignment_count:
            logger.warning(f"[REP_CARDS] Count mismatch: {len(cards)} cards returned but {assignment_count} assignments exist (may be due to deleted cards)")
    
    return {"ok": True, "cards": cards}


@app.get("/rep/conversations")
async def rep_get_conversations(current_user: Dict = Depends(get_current_owner_or_rep)):
    """Get rep's active conversations. Owner sees all, reps see only their own."""
    conn = get_conn()
    
    # Owner can see all conversations, reps see only their own
    if current_user.get("role") == "admin":
        # Owner: get all conversations
        with conn.cursor() as cur:
            cur.execute("""
                SELECT phone, card_id, state, routing_mode, rep_user_id, rep_phone_number,
                       last_outbound_at, last_inbound_at, created_at, updated_at, history
                FROM conversations
                ORDER BY COALESCE(last_inbound_at, last_outbound_at, updated_at) DESC NULLS LAST
            """)
            
            conversations = []
            # Helper to convert datetime to ISO string
            def to_iso(dt):
                return dt.isoformat() if dt else None
            
            for row in cur.fetchall():
                history = row[10] or []
                if isinstance(history, str):
                    try:
                        import json
                        history = json.loads(history)
                    except:
                        history = []
                
                conversations.append({
                    "phone": row[0],
                    "card_id": row[1],
                    "state": row[2],
                    "routing_mode": row[3],
                    "rep_user_id": row[4],
                    "rep_phone_number": row[5],
                    "last_outbound_at": to_iso(row[6]),
                    "last_inbound_at": to_iso(row[7]),
                    "created_at": to_iso(row[8]),
                    "updated_at": to_iso(row[9]),
                    "unread_count": 0,  # Owner sees all, no unread concept
                })
    else:
        # Rep: get only their conversations
        conversations = get_rep_conversations(conn, current_user["id"])
    
    return {"ok": True, "conversations": conversations}


@app.post("/rep/blast")
async def rep_blast(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_owner_or_rep)
):
    """Blast cards. Owner can blast any cards, reps can only blast their assigned cards."""
    logger.info(f"[BLAST] rep_blast called by {current_user['id']} (role: {current_user.get('role')})")
    logger.info(f"[BLAST] payload = {payload}")
    
    limit = payload.get("limit")
    status_filter = payload.get("status", "assigned")
    card_ids = payload.get("card_ids")  # Optional: specific card IDs to blast
    
    conn = get_conn()
    
    # CRITICAL: Enforce assignment boundaries
    if current_user.get("role") == "admin":
        # Owner: can blast any cards
        if card_ids and isinstance(card_ids, list):
            # Use provided card IDs (owner has full access)
            pass
        else:
            # Get all cards (or filtered by query if needed)
            from backend.query import build_list_query
            query, params = build_list_query(where={}, limit=limit or 10000)
            
            card_ids = []
            with conn.cursor() as cur:
                cur.execute(query, params)
                for row in cur.fetchall():
                    card_ids.append(row[0])  # row[0] is the id
    else:
        # Rep: STRICT enforcement - can ONLY blast assigned cards
        logger.info(f"[BLAST] Rep {current_user['id']} attempting blast - enforcing assignment boundaries")
        
        # Get all cards assigned to this rep
        all_assigned = get_rep_assigned_cards(conn, current_user["id"])
        assigned_ids = {c["id"] for c in all_assigned}
        
        if card_ids and isinstance(card_ids, list):
            # Verify ALL specified cards are assigned to this rep
            unauthorized = [cid for cid in card_ids if cid not in assigned_ids]
            if unauthorized:
                logger.warning(f"[BLAST] Rep {current_user['id']} attempted to blast unauthorized cards: {unauthorized}")
                return {"ok": False, "error": f"Unauthorized: {len(unauthorized)} card(s) not assigned to you", "sent": 0, "skipped": 0}
            
            # Filter to only assigned cards (safety check)
            card_ids = [cid for cid in card_ids if cid in assigned_ids]
            
            if not card_ids:
                logger.warning(f"[BLAST] Rep {current_user['id']} - no valid assigned cards after filtering")
                return {"ok": False, "error": "None of the specified cards are assigned to you", "sent": 0, "skipped": 0}
        else:
            # Get rep's assigned cards (only uncontacted/active ones)
            cards = get_rep_assigned_cards(conn, current_user["id"], status=status_filter)
            if not cards:
                logger.info(f"[BLAST] Rep {current_user['id']} - no assigned cards found with status={status_filter}")
                return {"ok": False, "error": "No assigned cards found", "sent": 0, "skipped": 0}
            
            card_ids = [c["id"] for c in cards]
            
            # Apply limit if provided
            if limit:
                card_ids = card_ids[:limit]
        
        logger.info(f"[BLAST] Rep {current_user['id']} - authorized to blast {len(card_ids)} assigned cards")
    
    if not card_ids:
        return {"ok": False, "error": "No cards to blast", "sent": 0, "skipped": 0}
    
    # Run blast
    try:
        # Owner uses system phone, reps use their phone if configured
        rep_user_id = None if current_user.get("role") == "admin" else current_user["id"]
        rep_phone_number = None if current_user.get("role") == "admin" else current_user.get("twilio_phone_number")
        
        # For reps: Use system Account SID and Auth Token (from env vars), but rep's phone number
        # All reps use the same Account SID and Messaging Service, but different phone numbers
        rep_account_sid = None
        rep_auth_token = None
        if rep_user_id:
            # Reps use system Account SID and Auth Token (same for all)
            # Only their phone number is different
            import os
            rep_account_sid = os.getenv("TWILIO_ACCOUNT_SID")  # Use system Account SID for all reps
            rep_auth_token = os.getenv("TWILIO_AUTH_TOKEN")  # Use system Auth Token for all reps
            
            logger.info(f"[BLAST] Rep {rep_user_id} using system Account SID: {rep_account_sid[:10] if rep_account_sid else 'NOT SET'}..., rep phone: {rep_phone_number}")
        
        logger.info(f"[BLAST] Running blast for {len(card_ids)} cards, rep_user_id={rep_user_id}, rep_phone={rep_phone_number}, using_system_account_sid={bool(rep_account_sid)}")
        
        result = run_blast_for_cards(
            conn=conn,
            card_ids=card_ids,
            limit=None,  # Already applied limit above if needed
            owner=current_user["id"],
            source="owner_ui" if current_user.get("role") == "admin" else "rep_ui",
            auth_token=rep_auth_token,  # System auth token for all reps
            account_sid=rep_account_sid,  # System account SID for all reps
            rep_user_id=rep_user_id,
            rep_phone_number=rep_phone_number,  # Rep's specific phone number
        )
        
        logger.info(f"[BLAST] Blast completed: sent={result.get('sent', 0)}, skipped={result.get('skipped', 0)}")
        return result
    except Exception as e:
        logger.error(f"[BLAST] Blast failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Blast failed: {str(e)}")


@app.post("/rep/messages/send")
async def rep_send_message(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_owner_or_rep)
):
    """Send a message to a specific card/phone. Owner can send to any, reps to their assigned cards."""
    card_id = payload.get("card_id")
    phone = payload.get("phone")
    message = payload.get("message")
    
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    
    if not card_id and not phone:
        raise HTTPException(status_code=400, detail="card_id or phone is required")
    
    conn = get_conn()
    
    # If phone provided but not card_id, try to find card_id
    if phone and not card_id:
        # First try from conversations table
        with conn.cursor() as cur:
            cur.execute("SELECT card_id FROM conversations WHERE phone = %s LIMIT 1", (phone,))
            row = cur.fetchone()
            if row and row[0]:
                card_id = row[0]
        
        # If still not found, try to find card by phone number
        if not card_id:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM cards
                    WHERE type = 'person'
                    AND card_data->>'phone' = %s
                    LIMIT 1
                """, (phone,))
                row = cur.fetchone()
                if row and row[0]:
                    card_id = row[0]
    
    if not card_id:
        raise HTTPException(status_code=404, detail="Card not found for phone number")
    
    # Reps can only send to their assigned cards
    if current_user.get("role") != "admin":
        assigned = get_rep_assigned_cards(conn, current_user["id"])
        assigned_ids = {c["id"] for c in assigned}
        if card_id not in assigned_ids:
            raise HTTPException(status_code=403, detail="Card is not assigned to you")
    
    try:
        # Owner sends from system phone, reps from their phone
        if current_user.get("role") == "admin":
            # Owner: use system Twilio
            from scripts.blast import send_sms
            from backend.cards import get_card
            card = get_card(conn, card_id)
            phone_num = card.get("card_data", {}).get("phone") if card else phone
            if not phone_num:
                raise HTTPException(status_code=400, detail="Phone number not found")
            
            result = send_sms(phone_num, message)
            # Store in conversation history
            from backend.rep_messaging import add_message_to_history
            add_message_to_history(conn, phone_num, "outbound", message, "owner", result.get("sid"))
            
            return {"ok": True, "result": result}
        else:
            # Rep: use rep messaging system
            result = send_rep_message(conn, current_user["id"], card_id, message)
            return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.get("/rep/messages/{phone}")
async def rep_get_messages(
    phone: str,
    current_user: Dict = Depends(get_current_owner_or_rep)
):
    """Get conversation history for a phone number. Owner can see all, reps only their own."""
    conn = get_conn()
    
    # Reps can only see their assigned conversations
    if current_user.get("role") != "admin":
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rep_user_id, card_id FROM conversations WHERE phone = %s
            """, (phone,))
            row = cur.fetchone()
            if row and row[0] and row[0] != current_user["id"]:
                # Check if card is assigned to rep
                if row[1]:
                    assigned = get_card_assignment(conn, row[1])
                    if not assigned or assigned["user_id"] != current_user["id"]:
                        raise HTTPException(status_code=403, detail="Not authorized to view this conversation")
    
    messages = get_conversation_messages(conn, phone)
    return {"ok": True, "messages": messages}


@app.get("/rep/stats")
async def rep_get_stats(current_user: Dict = Depends(get_current_owner_or_rep)):
    """Get conversion metrics. Owner sees all stats, reps see only their own."""
    conn = get_conn()
    
    if current_user.get("role") == "admin":
        # Owner: get all stats
        with conn.cursor() as cur:
            # Total cards
            cur.execute("SELECT COUNT(*) FROM cards")
            total_cards = cur.fetchone()[0] or 0
            
            # Total conversations
            cur.execute("SELECT COUNT(*) FROM conversations")
            total_conversations = cur.fetchone()[0] or 0
            
            # Assignment stats
            cur.execute("""
                SELECT status, COUNT(*) as count
                FROM card_assignments
                GROUP BY status
            """)
            
            stats = {
                "assigned": 0,
                "active": 0,
                "closed": 0,
                "lost": 0,
                "total_cards": total_cards,
                "total_conversations": total_conversations,
            }
            
            for row in cur.fetchall():
                status = row[0]
                count = row[1]
                if status in stats:
                    stats[status] = count
    else:
        # Rep: get only their stats
        user_id = current_user["id"]
        with conn.cursor() as cur:
            # Get assignment status counts
            cur.execute("""
                SELECT status, COUNT(*) as count
                FROM card_assignments
                WHERE user_id = %s
                GROUP BY status
            """, (user_id,))
            
            stats = {
                "assigned": 0,
                "active": 0,
                "closed": 0,
                "lost": 0,
            }
            
            for row in cur.fetchall():
                status = row[0]
                count = row[1]
                if status in stats:
                    stats[status] = count
            
            # Get total conversations (rep mode + assigned cards in AI mode)
            cur.execute("""
                SELECT COUNT(DISTINCT c.phone)
                FROM conversations c
                LEFT JOIN card_assignments ca ON c.card_id = ca.card_id
                WHERE (
                    c.rep_user_id = %s
                    OR (c.card_id IS NOT NULL AND ca.user_id = %s)
                )
            """, (user_id, user_id))
            row = cur.fetchone()
            stats["total_conversations"] = row[0] if row else 0
            
            # Get messages sent count (outbound messages from rep)
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations c
                WHERE c.rep_user_id = %s
                AND c.history::text LIKE '%"direction":"outbound"%'
            """, (user_id,))
            row = cur.fetchone()
            stats["messages_sent"] = row[0] if row else 0
            
            # Get messages received count (inbound messages to rep)
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations c
                WHERE c.rep_user_id = %s
                AND c.history::text LIKE '%"direction":"inbound"%'
            """, (user_id,))
            row = cur.fetchone()
            stats["messages_received"] = row[0] if row else 0
    
    return {"ok": True, "stats": stats}

