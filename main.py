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
    delete_card,
    get_vertical_info,
    generate_pitch,
    VERTICAL_TYPES,
)
from backend.query import build_list_query
from backend.resolve import resolve_target, extract_phones_from_cards
from backend.webhook_config import WEBHOOK_CONFIG, WebhookConfig
from backend.blast import run_blast_for_cards
from backend.auth import (
    get_user_by_token, create_user, list_users, update_user_twilio_config, get_user,
    delete_user, regenerate_api_token, clear_twilio_config
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
    # Validate critical Twilio configuration
    import os
    twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")  # Send directly from phone number
    
    print("=" * 60)
    print("🔍 TWILIO CONFIGURATION CHECK")
    print("=" * 60)
    print(f"TWILIO_ACCOUNT_SID: {'✅ SET' if twilio_account_sid else '❌ NOT SET'}")
    if twilio_account_sid:
        print(f"  Value: {twilio_account_sid[:10]}...{twilio_account_sid[-4:] if len(twilio_account_sid) > 14 else twilio_account_sid} (length: {len(twilio_account_sid)})")
    print(f"TWILIO_AUTH_TOKEN: {'✅ SET' if twilio_auth_token else '❌ NOT SET'}")
    if twilio_auth_token:
        print(f"  Value: {twilio_auth_token[:10]}...{twilio_auth_token[-4:] if len(twilio_auth_token) > 14 else twilio_auth_token} (length: {len(twilio_auth_token)})")
    print(f"TWILIO_PHONE_NUMBER: {'✅ SET' if twilio_phone_number else '❌ NOT SET - BLAST WILL FAIL!'}")
    if twilio_phone_number:
        print(f"  Value: {twilio_phone_number}")
        print(f"  Note: Sending directly from phone number (avoids Messaging Service filtering)")
    else:
        print(f"  ⚠️  WARNING: Phone number not configured!")
        print(f"  ⚠️  All blast operations will fail until TWILIO_PHONE_NUMBER is set in Railway environment variables")
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
    
    # CRITICAL: Log ALL POST requests to diagnose missing requests
    if request.method == "POST":
        print("=" * 80, flush=True)
        print(f"[MIDDLEWARE] 🚨 POST REQUEST DETECTED", flush=True)
        print("=" * 80, flush=True)
        print(f"[MIDDLEWARE] Path: {request.url.path}", flush=True)
        print(f"[MIDDLEWARE] Method: {request.method}", flush=True)
        print(f"[MIDDLEWARE] Headers include Authorization: {'Authorization' in request.headers}", flush=True)
        print(f"[MIDDLEWARE] Content-Type: {request.headers.get('Content-Type', 'NOT SET')}", flush=True)
        print(f"[MIDDLEWARE] Content-Length: {request.headers.get('Content-Length', 'NOT SET')}", flush=True)
        print(f"[MIDDLEWARE] Origin: {request.headers.get('Origin', 'NOT SET')}", flush=True)
        print(f"[MIDDLEWARE] Client: {request.client}", flush=True)
        print("=" * 80, flush=True)
    
    # 🔥 CRITICAL: Extra logging for /rep/blast specifically
    if request.method == "POST" and "/rep/blast" in str(request.url.path):
        print("=" * 80, flush=True)
        print(f"[MIDDLEWARE] 🔥🔥🔥 /rep/blast REQUEST IN MIDDLEWARE 🔥🔥🔥", flush=True)
        print("=" * 80, flush=True)
        print(f"[MIDDLEWARE] Full URL: {request.url}", flush=True)
        print(f"[MIDDLEWARE] Path: {request.url.path}", flush=True)
        print(f"[MIDDLEWARE] Query: {request.url.query}", flush=True)
        print(f"[MIDDLEWARE] Authorization header present: {'Authorization' in request.headers}", flush=True)
        if 'Authorization' in request.headers:
            auth_header = request.headers.get('Authorization', '')
            print(f"[MIDDLEWARE] Authorization header length: {len(auth_header)}", flush=True)
            print(f"[MIDDLEWARE] Authorization header starts with Bearer: {auth_header.startswith('Bearer ')}", flush=True)
        print("=" * 80, flush=True)
    
    # CRITICAL: Log OPTIONS requests (CORS preflight) to see if they're being blocked
    if request.method == "OPTIONS":
        print("=" * 80, flush=True)
        print(f"[MIDDLEWARE] 🔵 OPTIONS (CORS PREFLIGHT) REQUEST", flush=True)
        print("=" * 80, flush=True)
        print(f"[MIDDLEWARE] Path: {request.url.path}", flush=True)
        print(f"[MIDDLEWARE] Access-Control-Request-Method: {request.headers.get('Access-Control-Request-Method', 'NOT SET')}", flush=True)
        print(f"[MIDDLEWARE] Access-Control-Request-Headers: {request.headers.get('Access-Control-Request-Headers', 'NOT SET')}", flush=True)
        print(f"[MIDDLEWARE] Origin: {request.headers.get('Origin', 'NOT SET')}", flush=True)
        print("=" * 80, flush=True)
    
    logger.info(
        f"➡️ {request.method} {request.url.path} "
        f"has_body={'<present>' if has_body else None}"
    )
    
    try:
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)
        
        # CRITICAL: Enhanced logging for POST /rep/blast responses
        if request.method == "POST" and "/rep/blast" in str(request.url.path):
            print("=" * 80, flush=True)
            print(f"[MIDDLEWARE] 🚨 POST /rep/blast RESPONSE", flush=True)
            print("=" * 80, flush=True)
            print(f"[MIDDLEWARE] Status: {response.status_code}", flush=True)
            print(f"[MIDDLEWARE] Duration: {duration}ms", flush=True)
            print("=" * 80, flush=True)
        
        logger.info(
            f"⬅️ {request.method} {request.url.path} "
            f"status={response.status_code} "
            f"{duration}ms"
        )
        return response
    except Exception as e:
        duration = round((time.time() - start) * 1000, 2)
        
        # CRITICAL: Enhanced logging for POST /rep/blast exceptions
        if request.method == "POST" and "/rep/blast" in str(request.url.path):
            print("=" * 80, flush=True)
            print(f"[MIDDLEWARE] 🚨 POST /rep/blast EXCEPTION", flush=True)
            print("=" * 80, flush=True)
            print(f"[MIDDLEWARE] Error: {str(e)}", flush=True)
            print(f"[MIDDLEWARE] Error type: {type(e).__name__}", flush=True)
            import traceback
            print(f"[MIDDLEWARE] Traceback:", flush=True)
            traceback.print_exc()
            print("=" * 80, flush=True)
        
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
    
    # Fetch conversation by phone (scoped to environment_id if provided)
    environment_id = event.get("environment_id")
    current_state = event.get("current_state")  # Use provided state if available
    
    with conn.cursor() as cur:
        # Try to fetch with environment_id scoping if provided
        if environment_id:
            try:
                cur.execute("""
                    SELECT phone, state, COALESCE(history::text, '[]') as history
                    FROM conversations
                    WHERE phone = %s AND environment_id = %s;
                """, (phone, environment_id))
                row = cur.fetchone()
                if row:
                    print(f"[INBOUND_INTELLIGENT] ✅ Found conversation scoped to environment {environment_id}", flush=True)
                else:
                    print(f"[INBOUND_INTELLIGENT] ⚠️ No conversation found for environment {environment_id}, trying phone-only lookup", flush=True)
                    # Fallback to phone-only if environment-scoped lookup fails
                    cur.execute("""
                        SELECT phone, state, COALESCE(history::text, '[]') as history
                        FROM conversations
                        WHERE phone = %s
                        ORDER BY updated_at DESC
                        LIMIT 1;
                    """, (phone,))
                    row = cur.fetchone()
            except psycopg2.ProgrammingError:
                # environment_id column doesn't exist, fall back to phone-only
                cur.execute("""
                    SELECT phone, state, COALESCE(history::text, '[]') as history
                    FROM conversations
                    WHERE phone = %s;
                """, (phone,))
                row = cur.fetchone()
        else:
            # No environment_id provided, use phone-only lookup
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
        
        # Use provided current_state if available (from webhook handler), otherwise use DB state
        conversation_state = current_state if current_state else row[1]
        
        conversation_row = {
            "phone": row[0],
            "state": conversation_state,  # Use provided state or DB state
            "history": [item.get("text") if isinstance(item, dict) else item for item in normalized_history],  # Pass text only to handler
        }
        
        print(f"[INBOUND_INTELLIGENT] 🔍 Markov evaluation:", flush=True)
        print(f"[INBOUND_INTELLIGENT]   Current state: {conversation_state}", flush=True)
        print(f"[INBOUND_INTELLIGENT]   Intent: {json.dumps(intent, indent=2)}", flush=True)
        print(f"[INBOUND_INTELLIGENT]   Inbound text: '{inbound_text}'", flush=True)
        
        # Call intelligence handler
        result = handle_inbound(conversation_row, inbound_text, intent)
        
        print(f"[INBOUND_INTELLIGENT] ✅ Markov result:", flush=True)
        print(f"[INBOUND_INTELLIGENT]   Previous state: {result.get('previous_state')}", flush=True)
        print(f"[INBOUND_INTELLIGENT]   Next state: {result.get('next_state')}", flush=True)
        print(f"[INBOUND_INTELLIGENT]   Intent: {json.dumps(result.get('intent'), indent=2)}", flush=True)
        
        # Add new inbound message as object to history
        inbound_msg = {
            "direction": "inbound",
            "text": inbound_text,
            "timestamp": datetime.utcnow().isoformat(),
            "state": result["next_state"]
        }
        updated_history = normalized_history + [inbound_msg]
        
        # Update conversations table with new state, history, and card_id
        # Scope update to environment_id if provided
        try:
            if environment_id:
                # Try to update scoped to environment
                try:
                    cur.execute("""
                        UPDATE conversations
                        SET state = %s,
                            last_inbound_at = %s,
                            history = %s::jsonb,
                            card_id = COALESCE(%s, card_id)
                        WHERE phone = %s AND environment_id = %s;
                    """, (
                        result["next_state"],
                        datetime.utcnow(),
                        json.dumps(updated_history),
                        card_id,  # Link to card if found
                        phone,
                        environment_id,
                    ))
                    print(f"[INBOUND_INTELLIGENT] ✅ Updated conversation scoped to environment {environment_id}", flush=True)
                except psycopg2.ProgrammingError:
                    # environment_id column doesn't exist, fall back to phone-only
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
                        card_id,
                        phone,
                    ))
            else:
                # No environment_id, use phone-only update
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
            if environment_id:
                try:
                    cur.execute("""
                        UPDATE conversations
                        SET state = %s,
                            last_inbound_at = %s,
                            card_id = COALESCE(%s, card_id)
                        WHERE phone = %s AND environment_id = %s;
                    """, (
                        result["next_state"],
                        datetime.utcnow(),
                        card_id,
                        phone,
                        environment_id,
                    ))
                except psycopg2.ProgrammingError:
                    cur.execute("""
                        UPDATE conversations
                        SET state = %s,
                            last_inbound_at = %s,
                            card_id = COALESCE(%s, card_id)
                        WHERE phone = %s;
                    """, (
                        result["next_state"],
                        datetime.utcnow(),
                        card_id,
                        phone,
                    ))
            else:
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
    # 🔥 CRITICAL: Log IMMEDIATELY - this proves the webhook was called
    print("🔥🔥🔥 TWILIO INBOUND WEBHOOK HIT 🔥🔥🔥", flush=True)
    logger.error("🔥 TWILIO INBOUND WEBHOOK HIT")
    
    # CRITICAL: Log raw body FIRST to catch requests even if form parsing fails
    try:
        raw_body = await request.body()
        print("=" * 60, flush=True)
        print("[TWILIO_INBOUND] RAW INBOUND BODY:", raw_body.decode('utf-8', errors='replace'), flush=True)
        print("=" * 60, flush=True)
    except Exception as e:
        print(f"[TWILIO_INBOUND] ERROR reading raw body: {e}", flush=True)
    
    print("[TWILIO_INBOUND] Webhook hit", flush=True)
    
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
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND] 🔥🔥🔥 INBOUND WEBHOOK RECEIVED 🔥🔥🔥", flush=True)
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND] Original From: {From}", flush=True)
        print(f"[TWILIO_INBOUND] Normalized phone: {normalized_phone}", flush=True)
        print(f"[TWILIO_INBOUND] Message body: {Body[:100]}...", flush=True)
        print(f"[TWILIO_INBOUND] Message body length: {len(Body)}", flush=True)
        
        # Initialize twilio_phone at the top to avoid UnboundLocalError
        twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
        
        # 🔥 CRITICAL: Prevent bot loop - check if we just sent a message to this number
        # We'll still process/store the inbound (so it appears in leads) but skip auto-reply
        conn = get_conn()
        skip_auto_reply = False
        try:
            with conn.cursor() as loop_check_cur:
                loop_check_cur.execute("""
                    SELECT sent_at, direction, message_text
                    FROM message_events
                    WHERE phone_number = %s
                      AND direction = 'outbound'
                      AND message_sid IS NOT NULL
                    ORDER BY sent_at DESC
                    LIMIT 1
                """, (normalized_phone,))
                recent_outbound = loop_check_cur.fetchone()
                if recent_outbound:
                    sent_at = recent_outbound[0]
                    # Handle timezone-aware and naive datetimes
                    from datetime import datetime, timezone
                    now_utc = datetime.now(timezone.utc) if hasattr(datetime, 'now') else datetime.utcnow()
                    if sent_at.tzinfo is None:
                        # If naive, assume UTC and make it timezone-aware
                        sent_at_aware = sent_at.replace(tzinfo=timezone.utc)
                    else:
                        sent_at_aware = sent_at
                    time_since_sent = (now_utc - sent_at_aware).total_seconds()
                    if time_since_sent < 5:  # Less than 5 seconds ago
                        print(f"[TWILIO_INBOUND] 🛑 BOT LOOP PREVENTION: Detected recent outbound {time_since_sent:.2f}s ago", flush=True)
                        print(f"[TWILIO_INBOUND]   Will still store inbound message (for leads) but skip auto-reply", flush=True)
                        skip_auto_reply = True
        except Exception as loop_check_error:
            print(f"[TWILIO_INBOUND] ⚠️ Error checking for bot loop (continuing anyway): {loop_check_error}", flush=True)
        
        
        # 🔧 FIX C: Resolve card_id EARLY by looking up card by phone number
        # This ensures we have card_id available for rep hydration, even if conversation doesn't have it
        # CRITICAL: Use E.164 format for phone lookup (preserve + and country code)
        print(f"[TWILIO_INBOUND] 🔍 Step 1: Resolving card by phone number...", flush=True)
        print(f"[TWILIO_INBOUND]   Looking up card with phone (E.164): {From}", flush=True)
        card_id = None
        card = None
        with conn.cursor() as cur:
            # Try to find card by phone number in card_data JSONB
            # Try both E.164 format and normalized format for backward compatibility
            cur.execute("""
                SELECT id, type, card_data, sales_state, owner
                FROM cards
                WHERE type = 'person'
                AND (card_data->>'phone' = %s OR card_data->>'phone' = %s)
                LIMIT 1
            """, (From, normalized_phone))
            card_row = cur.fetchone()
            if card_row:
                card_id = card_row[0]
                card = {
                    "id": card_row[0],
                    "type": card_row[1],
                    "card_data": card_row[2],
                    "sales_state": card_row[3],
                    "owner": card_row[4],
                }
                print(f"[TWILIO_INBOUND] ✅ Card found by phone: card_id={card_id}", flush=True)
            else:
                print(f"[TWILIO_INBOUND] ⚠️ No card found by phone number: {normalized_phone}", flush=True)
        
        # 🔥 ENVIRONMENT ISOLATION: Route inbound to environment that last sent outbound
        # This is the critical fix - we must route to the correct environment, not just any conversation
        print(f"[TWILIO_INBOUND] 🔍 Step 2: Routing to environment (last outbound wins)...", flush=True)
        from backend.environment import route_inbound_to_environment, get_or_create_environment, store_message_event
        
        # Route to environment that last sent an outbound SMS
        environment_id, routed_rep_id, routed_campaign_id = route_inbound_to_environment(conn, normalized_phone)
        
        # If no prior outbound, create new environment based on current context
        if not environment_id:
            print(f"[TWILIO_INBOUND] ⚠️ No prior outbound found - creating new environment", flush=True)
            # Resolve rep_id from card_assignments if we have card_id
            resolved_rep_user_id = None
            if card_id:
                from backend.handoffs import resolve_current_rep
                resolved_rep_user_id = resolve_current_rep(conn, card_id)
            
            # Infer campaign_id from card if available
            campaign_id = None
            if card and card.get("card_data"):
                card_data = card["card_data"]
                if card_data.get("fraternity"):
                    campaign_id = "frat_rt4orgs"
                elif card_data.get("faith_group"):
                    campaign_id = "faith_rt4orgs"
                elif card_data.get("role") == "Office":
                    campaign_id = "faith_rt4orgs"
                else:
                    campaign_id = "default_rt4orgs"
            
            environment_id = get_or_create_environment(conn, normalized_phone, resolved_rep_user_id, campaign_id, card_id)
            routed_rep_id = resolved_rep_user_id
            routed_campaign_id = campaign_id
            print(f"[TWILIO_INBOUND] ✅ Created new environment: {environment_id} (rep={routed_rep_id}, campaign={routed_campaign_id})", flush=True)
        else:
            print(f"[TWILIO_INBOUND] ✅ Routed to existing environment: {environment_id} (rep={routed_rep_id}, campaign={routed_campaign_id})", flush=True)
        
        # Get conversation for this specific environment
        routing_mode = 'ai'  # Default to AI
        rep_user_id = routed_rep_id
        conversation_state = None
        conversation_card_id = None
        conversation_row = None
        with conn.cursor() as cur:
            # Try to query with environment_id (new schema)
            try:
                cur.execute("""
                    SELECT routing_mode, rep_user_id, state, card_id 
                    FROM conversations 
                    WHERE phone = %s AND environment_id = %s
                    LIMIT 1
                """, (normalized_phone, environment_id))
                row = cur.fetchone()
                if row:
                    conversation_row = row
                    routing_mode = row[0] or 'ai'
                    rep_user_id = row[1] or routed_rep_id  # Use routed rep if conversation has NULL
                    conversation_state = row[2]
                    conversation_card_id = row[3]
                    print(f"[TWILIO_INBOUND] ✅ Conversation found for environment {environment_id}", flush=True)
                    print(f"[TWILIO_INBOUND]   routing_mode: {routing_mode}", flush=True)
                    print(f"[TWILIO_INBOUND]   rep_user_id: {rep_user_id}", flush=True)
                    print(f"[TWILIO_INBOUND]   current_state: {conversation_state}", flush=True)
                    print(f"[TWILIO_INBOUND]   card_id: {conversation_card_id}", flush=True)
                else:
                    print(f"[TWILIO_INBOUND] ⚠️ No conversation found for environment {environment_id}", flush=True)
            except psycopg2.ProgrammingError as e:
                # environment_id column doesn't exist yet (pre-migration) - fallback to phone-only lookup
                if 'environment_id' in str(e):
                    print(f"[TWILIO_INBOUND] ⚠️ environment_id column not found - using fallback lookup", flush=True)
                    cur.execute("""
                        SELECT routing_mode, rep_user_id, state, card_id FROM conversations WHERE phone = %s LIMIT 1
                    """, (normalized_phone,))
                    row = cur.fetchone()
                    if row:
                        conversation_row = row
                        routing_mode = row[0] or 'ai'
                        rep_user_id = row[1] or routed_rep_id
                        conversation_state = row[2]
                        conversation_card_id = row[3]
                else:
                    raise
        
        # Define conversation_exists based on whether we found a row
        conversation_exists = conversation_row is not None
        
        # Use card_id from conversation if available, otherwise use the one we just resolved
        if conversation_card_id and not card_id:
            card_id = conversation_card_id
            print(f"[TWILIO_INBOUND] ✅ Using card_id from conversation: {card_id}", flush=True)
        elif card_id and not conversation_card_id:
            print(f"[TWILIO_INBOUND] ✅ Using card_id resolved from phone lookup: {card_id}", flush=True)
        elif card_id and conversation_card_id and card_id != conversation_card_id:
            print(f"[TWILIO_INBOUND] ⚠️ WARNING: card_id mismatch! conversation={conversation_card_id}, lookup={card_id}", flush=True)
            # Prefer conversation's card_id as it's the source of truth
            card_id = conversation_card_id
        
        print(f"[TWILIO_INBOUND] 📋 Final card_id for rep resolution: {card_id}", flush=True)
        
        # 🔧 POLICY A: Inbound ownership reconciliation - ALWAYS recompute from card_assignments
        # Source of truth: card_assignments determines ownership (last blaster wins)
        # This ensures inbound sees blast-claim changes immediately
        print(f"[TWILIO_INBOUND] 🔍 POLICY A: Resolving current owner from card_assignments...", flush=True)
        print(f"[TWILIO_INBOUND]   DEBUG: card_id={card_id}, conversation.rep_user_id={rep_user_id}", flush=True)
        
        # Resolve current owner from card_assignments (source of truth for Policy A)
        resolved_rep_user_id = None
        if card_id:
            from backend.handoffs import resolve_current_rep
            resolved_rep_user_id = resolve_current_rep(conn, card_id)
            print(f"[TWILIO_INBOUND]   ✅ Resolved owner from card_assignments: {resolved_rep_user_id} (NULL = owner, set = rep)", flush=True)
        
        # 🔥 CRITICAL: Reconcile stale conversation ownership (Policy A invariant)
        # Must handle ALL cases:
        # 1. rep_user_id != resolved_rep_user_id (ownership changed via blast)
        # 2. rep_user_id is None but resolved_rep_user_id exists (rep assigned)
        # 3. rep_user_id exists but resolved_rep_user_id is None (owner reclaimed)
        if conversation_exists and card_id and rep_user_id != resolved_rep_user_id:
            from backend.handoffs import reset_markov_for_card, log_handoff, get_conversation_state
            state_before = get_conversation_state(conn, card_id) or conversation_state
            
            print(f"[TWILIO_INBOUND] ⚠️ [HANDOFF] Inbound ownership mismatch — correcting", flush=True)
            print(f"[TWILIO_INBOUND]   conversation.rep_user_id: {rep_user_id}", flush=True)
            print(f"[TWILIO_INBOUND]   resolved_rep_user_id (from card_assignments): {resolved_rep_user_id}", flush=True)
            print(f"[TWILIO_INBOUND]   state_before: {state_before}", flush=True)
            
            # Reset Markov state to initial_outreach (Policy A: ownership change = reset)
            reset_markov_for_card(conn, card_id, resolved_rep_user_id, 'inbound_reconciliation', 'system')
            
            # Log handoff event
            log_handoff(
                conn=conn,
                card_id=card_id,
                from_rep=rep_user_id,
                to_rep=resolved_rep_user_id,
                reason='inbound_reconciliation',
                state_before=state_before,
                state_after='initial_outreach',
                assigned_by='system',
                conversation_id=None  # Will be set by reset_markov_for_card if available
            )
            
            # Update conversation atomically with new ownership (scoped to environment)
            with conn.cursor() as update_cur:
                try:
                    update_cur.execute("""
                        UPDATE conversations
                        SET rep_user_id = %s, state = 'initial_outreach', updated_at = NOW()
                        WHERE phone = %s AND environment_id = %s
                    """, (resolved_rep_user_id, normalized_phone, environment_id))
                except psycopg2.ProgrammingError:
                    # Fallback if environment_id column doesn't exist
                    update_cur.execute("""
                        UPDATE conversations
                        SET rep_user_id = %s, state = 'initial_outreach', updated_at = NOW()
                        WHERE phone = %s
                    """, (resolved_rep_user_id, normalized_phone))
            
            # Update local variable for rest of handler
            rep_user_id = resolved_rep_user_id
            conversation_state = 'initial_outreach'
            
            print(f"[TWILIO_INBOUND] ✅ [HANDOFF] Fixed ownership mismatch: rep_user_id={rep_user_id}, state reset to initial_outreach", flush=True)
        
        # If no conversation exists yet but we have resolved_rep, use it
        if not conversation_exists and resolved_rep_user_id:
            rep_user_id = resolved_rep_user_id
            print(f"[TWILIO_INBOUND] ✅ Using resolved rep_user_id for new conversation: {rep_user_id}", flush=True)
        
        # 🔧 CRITICAL FIX: Final rep_user_id fallback using priority order
        # Priority: conversation.rep_user_id OR last_outbound.rep_user_id OR card.owner
        # This ensures we always have a rep_user_id for auto-assignment if any ownership exists
        if not rep_user_id:
            print(f"[TWILIO_INBOUND] 🔍 rep_user_id is None - applying fallback priority...", flush=True)
            
            # Try 1: conversation.rep_user_id (already checked above, but double-check)
            if conversation_row and conversation_row[1]:
                rep_user_id = conversation_row[1]
                print(f"[TWILIO_INBOUND]   ✅ Using conversation.rep_user_id: {rep_user_id}", flush=True)
            
            # Try 2: last_outbound.rep_user_id (from routing)
            elif routed_rep_id:
                rep_user_id = routed_rep_id
                print(f"[TWILIO_INBOUND]   ✅ Using last_outbound.rep_user_id (routed_rep_id): {rep_user_id}", flush=True)
            
            # Try 3: card.owner (if card exists)
            elif card and card.get("owner"):
                rep_user_id = card["owner"]
                print(f"[TWILIO_INBOUND]   ✅ Using card.owner: {rep_user_id}", flush=True)
            
            if rep_user_id:
                print(f"[TWILIO_INBOUND] ✅ Final rep_user_id after fallback: {rep_user_id}", flush=True)
            else:
                print(f"[TWILIO_INBOUND] ⚠️ No rep_user_id found after all fallbacks - will block auto-assignment", flush=True)
        
        # Final ownership determination for logging
        final_owner = "OWNER" if not rep_user_id else f"REP({rep_user_id})"
        print(f"[TWILIO_INBOUND] 📋 POLICY A: Final resolved owner: {final_owner}", flush=True)
        
        print(f"[TWILIO_INBOUND] 📋 Conversation Summary:", flush=True)
        print(f"[TWILIO_INBOUND]   Phone: {normalized_phone} (original: {From})", flush=True)
        print(f"[TWILIO_INBOUND]   Routing mode: {routing_mode}", flush=True)
        print(f"[TWILIO_INBOUND]   Rep user ID: {rep_user_id}", flush=True)
        print(f"[TWILIO_INBOUND]   Current state: {conversation_state}", flush=True)
        if rep_user_id:
            print(f"[TWILIO_INBOUND] ✅ Will use rep-specific Markov responses for user_id: {rep_user_id}", flush=True)
        else:
            print(f"[TWILIO_INBOUND] ⚠️ Will use global Markov responses (no rep assigned)", flush=True)
            # Debug: Check if conversation exists but rep_user_id is NULL
            with conn.cursor() as debug_cur:
                debug_cur.execute("""
                    SELECT rep_user_id, last_outbound_at, owner FROM conversations WHERE phone = %s
                """, (normalized_phone,))
                debug_row = debug_cur.fetchone()
                if debug_row:
                    print(f"[TWILIO_INBOUND] DEBUG: Conversation exists - rep_user_id={debug_row[0]}, last_outbound_at={debug_row[1]}, owner={debug_row[2]}", flush=True)
        
        # Store inbound message in history and message_events
        from backend.rep_messaging import add_message_to_history
        add_message_to_history(conn, normalized_phone, "inbound", Body, "contact")
        
        # Store inbound message event (no message_sid for inbound - it's from Twilio)
        store_message_event(
            conn=conn,
            phone_number=normalized_phone,
            environment_id=environment_id,
            direction="inbound",
            message_text=Body,
            message_sid=None,  # Inbound messages don't have our message_sid
            rep_id=rep_user_id,
            campaign_id=routed_campaign_id,
            state=conversation_state
        )
        
        # POLICY A: Whoever blasts LAST owns the automation
        # Auto-responses work for the current owner (rep or owner)
        # No special "rep mode" that disables automation - ownership determines responses
        print(f"[TWILIO_INBOUND] 📋 Routing mode: {routing_mode}, Rep user ID: {rep_user_id}", flush=True)
        print(f"[TWILIO_INBOUND] ✅ Policy A: Auto-responses enabled for current owner", flush=True)
        
        # Continue with AI processing for 'ai' mode
        # Classify intent from message text (simple keyword-based for now)
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND] 🔍 MARKOV INTENT CLASSIFICATION", flush=True)
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND]   Message text: '{Body}'", flush=True)
        print(f"[TWILIO_INBOUND]   Current conversation state: {conversation_state}", flush=True)
        print(f"[TWILIO_INBOUND]   Card ID: {card_id}", flush=True)
        print(f"[TWILIO_INBOUND]   Rep user ID: {rep_user_id}", flush=True)
        intent = classify_intent_simple(Body)
        print(f"[TWILIO_INBOUND] ✅ Classified intent: {json.dumps(intent, indent=2)}", flush=True)
        print(f"[TWILIO_INBOUND]   category: {intent.get('category', 'NONE')}", flush=True)
        print(f"[TWILIO_INBOUND]   subcategory: {intent.get('subcategory', 'NONE')}", flush=True)
        if not intent:
            print(f"[TWILIO_INBOUND] ⚠️ WARNING: Intent classifier returned empty dict - no category detected", flush=True)
        print("=" * 80, flush=True)
        
        # Prepare event payload for inbound_intelligent
        # Include environment_id and conversation state for proper scoping
        event = {
            "phone": normalized_phone,
            "text": Body,
            "body": Body,
            "intent": intent,
            "environment_id": environment_id,  # Pass environment for proper scoping
            "current_state": conversation_state,  # Pass current state to avoid re-lookup
            "rep_user_id": rep_user_id,  # Pass rep_user_id for context
        }
        
        print(f"[TWILIO_INBOUND] 📞 Calling inbound_intelligent for {normalized_phone}", flush=True)
        print(f"[TWILIO_INBOUND]   Event payload: {json.dumps(event, indent=2)}", flush=True)
        print(f"[TWILIO_INBOUND]   Current conversation state: {conversation_state}", flush=True)
        print(f"[TWILIO_INBOUND]   Environment ID: {environment_id}", flush=True)
        print(f"[TWILIO_INBOUND]   Rep user ID: {rep_user_id}", flush=True)
        print(f"[TWILIO_INBOUND]   Card ID: {card_id}", flush=True)
        
        # Call the intelligence handler directly (no HTTP overhead)
        result = await inbound_intelligent(event)
        
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND] ✅ MARKOV INTELLIGENCE RESULT", flush=True)
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND]   Full result: {json.dumps(result, indent=2, default=str)}", flush=True)
        print(f"[TWILIO_INBOUND]   next_state: {result.get('next_state')}", flush=True)
        print(f"[TWILIO_INBOUND]   previous_state: {result.get('previous_state')}", flush=True)
        print(f"[TWILIO_INBOUND]   intent: {result.get('intent')}", flush=True)
        print("=" * 80, flush=True)
        
        # 🔧 CRITICAL: Update last_inbound_at and card_id on the conversation scoped to environment_id
        # The inbound_intelligent function updates by phone only, but we need to update
        # the specific conversation for this environment to mark it as a lead
        # Also ensure card_id is set (required for leads endpoint)
        print(f"[TWILIO_INBOUND] 🔧 Updating last_inbound_at and card_id for environment {environment_id}...", flush=True)
        with conn.cursor() as update_cur:
            try:
                # Update last_inbound_at and card_id scoped to environment
                update_cur.execute("""
                    UPDATE conversations 
                    SET last_inbound_at = NOW(), 
                        updated_at = NOW(),
                        card_id = COALESCE(%s, card_id)
                    WHERE phone = %s AND environment_id = %s
                """, (card_id, normalized_phone, environment_id))
                if update_cur.rowcount > 0:
                    print(f"[TWILIO_INBOUND] ✅ Updated last_inbound_at and card_id for conversation (environment {environment_id}, card_id={card_id})", flush=True)
                else:
                    print(f"[TWILIO_INBOUND] ⚠️ No conversation found to update (phone={normalized_phone}, environment_id={environment_id})", flush=True)
                    # Try to create conversation if it doesn't exist
                    if not conversation_exists:
                        print(f"[TWILIO_INBOUND] 🔧 Creating new conversation for lead...", flush=True)
                        try:
                            update_cur.execute("""
                                INSERT INTO conversations (phone, card_id, state, last_inbound_at, environment_id, rep_user_id)
                                VALUES (%s, %s, %s, NOW(), %s, %s)
                                ON CONFLICT (phone, environment_id) DO UPDATE SET
                                    last_inbound_at = NOW(),
                                    card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                                    updated_at = NOW()
                            """, (normalized_phone, card_id, result.get("next_state", "initial_outreach"), environment_id, rep_user_id))
                            print(f"[TWILIO_INBOUND] ✅ Created/updated conversation for lead", flush=True)
                        except psycopg2.ProgrammingError:
                            # Fallback if environment_id column doesn't exist
                            update_cur.execute("""
                                INSERT INTO conversations (phone, card_id, state, last_inbound_at)
                                VALUES (%s, %s, %s, NOW())
                                ON CONFLICT (phone) DO UPDATE SET
                                    last_inbound_at = NOW(),
                                    card_id = COALESCE(EXCLUDED.card_id, conversations.card_id),
                                    updated_at = NOW()
                            """, (normalized_phone, card_id, result.get("next_state", "initial_outreach")))
                            print(f"[TWILIO_INBOUND] ✅ Created/updated conversation for lead (legacy mode)", flush=True)
            except psycopg2.ProgrammingError:
                # Fallback if environment_id column doesn't exist
                update_cur.execute("""
                    UPDATE conversations 
                    SET last_inbound_at = NOW(), 
                        updated_at = NOW(),
                        card_id = COALESCE(%s, card_id)
                    WHERE phone = %s
                """, (card_id, normalized_phone))
                if update_cur.rowcount > 0:
                    print(f"[TWILIO_INBOUND] ✅ Updated last_inbound_at and card_id for conversation (legacy mode, card_id={card_id})", flush=True)
                else:
                    print(f"[TWILIO_INBOUND] ⚠️ No conversation found to update (phone={normalized_phone})", flush=True)
            except Exception as update_error:
                print(f"[TWILIO_INBOUND] ⚠️ Error updating last_inbound_at: {update_error}", flush=True)
                import traceback
                print(f"[TWILIO_INBOUND] Traceback: {traceback.format_exc()}", flush=True)
        
        # Get card by phone to generate contextual reply (use card we already resolved earlier)
        # Card should already be loaded from Step 1, but double-check if needed
        if not card and card_id:
            print(f"[TWILIO_INBOUND] 🔍 Card not loaded yet, fetching by card_id: {card_id}", flush=True)
            card = get_card(conn, card_id)
        
        # Generate reply message using configured Markov responses
        reply_text = None
        next_state = None  # Define at higher scope for campaign suppression check
        
        # 🔒 SAFETY INVARIANT: Check if card is assigned before auto-responding
        # Do not auto-respond to unassigned cards (prevents spam loops)
        # ✅ OPTION A: Auto-assign on first inbound to conversation owner
        card_assigned = False
        if card_id:
            from backend.assignments import get_card_assignment, assign_card_to_rep
            assignment = get_card_assignment(conn, card_id)
            card_assigned = assignment is not None and assignment.get("user_id") is not None
            
            if not card_assigned:
                print(f"[TWILIO_INBOUND] 🔍 Card {card_id} is not assigned", flush=True)
                
                # Auto-assign to conversation owner (rep_user_id) if available
                if rep_user_id:
                    print(f"[TWILIO_INBOUND] 🔄 Auto-assigning card to conversation owner: {rep_user_id}", flush=True)
                    assign_success = assign_card_to_rep(
                        conn=conn,
                        card_id=card_id,
                        user_id=rep_user_id,
                        assigned_by=rep_user_id,  # Self-assigned via inbound
                        notes="Auto-assigned on first inbound message"
                    )
                    if assign_success:
                        print(f"[TWILIO_INBOUND] ✅ Card auto-assigned successfully to {rep_user_id}", flush=True)
                        card_assigned = True
                        # Re-fetch assignment to ensure it's fresh
                        assignment = get_card_assignment(conn, card_id)
                    else:
                        print(f"[TWILIO_INBOUND] ⚠️ Failed to auto-assign card {card_id} to {rep_user_id}", flush=True)
                else:
                    print(f"[TWILIO_INBOUND] 🛑 SAFETY: Card {card_id} is not assigned and no rep_user_id available - skipping auto-response (inbound will still be stored)", flush=True)
        
        # Skip reply generation if bot loop detected OR card is unassigned (but still process/store inbound for leads)
        if skip_auto_reply:
            print(f"[TWILIO_INBOUND] 🛑 Skipping reply generation due to bot loop prevention (inbound will still be stored)", flush=True)
            reply_text = None
        elif not card_assigned and card_id:
            # Card is still unassigned after auto-assignment attempt
            # This means either:
            # 1. No rep_user_id was available (conversation has no owner)
            # 2. Auto-assignment failed
            print(f"[TWILIO_INBOUND] 🛑 Skipping reply generation - card is unassigned (inbound will still be stored)", flush=True)
            print(f"[TWILIO_INBOUND]   Reason: Card {card_id} has no assignment and no rep_user_id to assign to", flush=True)
            reply_text = None
        elif result.get("next_state"):
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND] 🔄 MARKOV STATE TRANSITION DETECTED", flush=True)
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND]   Previous state: {result.get('previous_state', 'unknown')}", flush=True)
            print(f"[TWILIO_INBOUND]   Next state: {result.get('next_state')}", flush=True)
            print(f"[TWILIO_INBOUND]   Intent category: {result.get('intent', {}).get('category', 'unknown')}", flush=True)
            print(f"[TWILIO_INBOUND]   Intent subcategory: {result.get('intent', {}).get('subcategory', 'unknown')}", flush=True)
            print("=" * 80, flush=True)
            next_state = result["next_state"]
            previous_state = result.get("previous_state", "initial_outreach")
            
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND] 🔄 STATE TRANSITION", flush=True)
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND]   Previous state: {previous_state}", flush=True)
            print(f"[TWILIO_INBOUND]   Next state: {next_state}", flush=True)
            print(f"[TWILIO_INBOUND]   Transition: {previous_state} → {next_state}", flush=True)
            print("=" * 80, flush=True)
            
            # CRITICAL: Get rep-specific Markov response text
            # - NLP logic (state transitions) is SHARED across all reps (same conversation tree)
            # - Response TEXT is REP-SPECIFIC (each rep can customize their pitch/responses)
            # - If rep_user_id is set, uses that rep's responses; otherwise uses global responses
            # - If multiple reps messaged, rep_user_id reflects the LAST rep to message (conflict resolution)
            
            # 🔥 CRITICAL: Re-read rep_user_id from database RIGHT BEFORE loading Markov responses
            # This ensures we use the absolute latest value after any ownership changes from blasts
            # This handles graceful transitions when different reps contact the same number
            # CRITICAL: Must scope to environment_id
            print(f"[TWILIO_INBOUND] 🔄 Re-reading conversation rep_user_id from DB (for Markov lookup)...", flush=True)
            with conn.cursor() as verify_cur:
                try:
                    verify_cur.execute("""
                        SELECT rep_user_id FROM conversations 
                        WHERE phone = %s AND environment_id = %s
                        LIMIT 1
                    """, (normalized_phone, environment_id))
                except psycopg2.ProgrammingError:
                    # Fallback if environment_id column doesn't exist
                    verify_cur.execute("""
                        SELECT rep_user_id FROM conversations WHERE phone = %s LIMIT 1
                    """, (normalized_phone,))
                verify_row = verify_cur.fetchone()
                if verify_row:
                    latest_rep_user_id = verify_row[0]
                    if latest_rep_user_id != rep_user_id:
                        print(f"[TWILIO_INBOUND] ⚠️ rep_user_id changed! Old: {rep_user_id}, New: {latest_rep_user_id}", flush=True)
                        print(f"[TWILIO_INBOUND] ✅ Using latest rep_user_id from DB: {latest_rep_user_id}", flush=True)
                        rep_user_id = latest_rep_user_id
                    else:
                        print(f"[TWILIO_INBOUND] ✅ rep_user_id unchanged: {rep_user_id}", flush=True)
                else:
                    print(f"[TWILIO_INBOUND] ⚠️ No conversation found in DB for re-read, using current rep_user_id: {rep_user_id}", flush=True)
            
            print(f"[TWILIO_INBOUND] 🔍 Looking up Markov response:", flush=True)
            print(f"[TWILIO_INBOUND]   state_key: '{next_state}'", flush=True)
            print(f"[TWILIO_INBOUND]   rep_user_id (final): {rep_user_id}", flush=True)
            print(f"[TWILIO_INBOUND]   phone: {normalized_phone}", flush=True)
            print(f"[TWILIO_INBOUND]   routing_mode: {routing_mode}", flush=True)
            configured_response = get_markov_response(conn, next_state, rep_user_id)
            if configured_response:
                print("=" * 80, flush=True)
                print(f"[TWILIO_INBOUND] ✅ RESPONSE FOUND", flush=True)
                print("=" * 80, flush=True)
                print(f"[TWILIO_INBOUND]   Response length: {len(configured_response)} chars", flush=True)
                print(f"[TWILIO_INBOUND]   Response preview: {configured_response[:100]}...", flush=True)
                print(f"[TWILIO_INBOUND]   Full response: {configured_response}", flush=True)
                print("=" * 80, flush=True)
            else:
                print("=" * 80, flush=True)
                print(f"[TWILIO_INBOUND] ⚠️ NO RESPONSE FOUND", flush=True)
                print("=" * 80, flush=True)
                print(f"[TWILIO_INBOUND]   State: '{next_state}'", flush=True)
                print(f"[TWILIO_INBOUND]   Rep user ID: {rep_user_id}", flush=True)
                print(f"[TWILIO_INBOUND]   💡 Suggestion: Rep should configure a response for this state, or owner should set a global default", flush=True)
                print("=" * 80, flush=True)
            
            if configured_response:
                print(f"[TWILIO_INBOUND] ✅ Configured response found, processing...", flush=True)
                print(f"[TWILIO_INBOUND]   Original response: {configured_response}", flush=True)
                print(f"[TWILIO_INBOUND]   Response length: {len(configured_response)} chars", flush=True)
                
                # If we have a card, substitute template placeholders
                if card and card.get("card_data"):
                    print(f"[TWILIO_INBOUND] 📋 Card found, applying template substitution...", flush=True)
                    from backend.blast import _substitute_template
                    from archive_intelligence.message_processor.utils import load_sales_history, find_matching_fraternity
                    
                    data = card["card_data"]
                    sales_history = load_sales_history()
                    purchased_example = None
                    if isinstance(sales_history, dict):
                        purchased_example = find_matching_fraternity(data, sales_history)
                    
                    reply_text = _substitute_template(configured_response, data, purchased_example)
                    print(f"[TWILIO_INBOUND] ✅ Template substitution complete", flush=True)
                    print(f"[TWILIO_INBOUND]   Substituted response: {reply_text}", flush=True)
                    print(f"[TWILIO_INBOUND]   Substituted length: {len(reply_text)} chars", flush=True)
                else:
                    reply_text = configured_response
                    print(f"[TWILIO_INBOUND] ✅ Using configured response as-is (no card for substitution)", flush=True)
                    print(f"[TWILIO_INBOUND]   Final reply_text: {reply_text}", flush=True)
            else:
                # No configured response found (neither rep-specific nor global)
                print("=" * 80, flush=True)
                print(f"[TWILIO_INBOUND] ⚠️ NO MARKOV RESPONSE CONFIGURED", flush=True)
                print("=" * 80, flush=True)
                print(f"[TWILIO_INBOUND]   State: '{next_state}'", flush=True)
                print(f"[TWILIO_INBOUND]   Rep user ID: {rep_user_id}", flush=True)
                print(f"[TWILIO_INBOUND]   This means neither the rep nor the owner has configured a response for this state", flush=True)
                print(f"[TWILIO_INBOUND]   💡 Action: Configure a response in Markov Editor for state '{next_state}'", flush=True)
                print("=" * 80, flush=True)
                
                # FALLBACK: Send a generic acknowledgment if no response configured
                # This prevents dead air and confirms the system is working
                if card_assigned:
                    print(f"[TWILIO_INBOUND] 🔄 Using fallback response (no configured response for state '{next_state}')", flush=True)
                    name = (card.get("card_data", {}) or {}).get("name", "there")
                    reply_text = f"Thanks for your message, {name}! We'll get back to you soon."
                    print(f"[TWILIO_INBOUND]   Fallback response: {reply_text}", flush=True)
                else:
                    # Don't send a reply if card is unassigned
                    reply_text = None
        else:
            # No next_state from Markov engine - this shouldn't happen but handle gracefully
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND] ⚠️ NO STATE TRANSITION FROM MARKOV ENGINE", flush=True)
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND]   Result keys: {list(result.keys())}", flush=True)
            print(f"[TWILIO_INBOUND]   Result: {json.dumps(result, indent=2, default=str)}", flush=True)
            print(f"[TWILIO_INBOUND]   This means the Markov engine did not return a next_state", flush=True)
            print(f"[TWILIO_INBOUND]   💡 Check: Is the intent classifier working? Is the state transition logic correct?", flush=True)
            print("=" * 80, flush=True)
            reply_text = None
        
        # Send explicit reply via Twilio (webhook return does NOT send SMS)
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND] 📤 MARKOV REPLY DECISION", flush=True)
        print("=" * 80, flush=True)
        print(f"[TWILIO_INBOUND]   Will send reply: {reply_text is not None}", flush=True)
        print(f"[TWILIO_INBOUND]   reply_text: {reply_text}", flush=True)
        print(f"[TWILIO_INBOUND]   reply_text type: {type(reply_text)}", flush=True)
        if reply_text:
            print(f"[TWILIO_INBOUND]   reply_text length: {len(reply_text)}", flush=True)
            print(f"[TWILIO_INBOUND]   reply_text preview: {reply_text[:100]}...", flush=True)
        else:
            print(f"[TWILIO_INBOUND]   ⚠️ No reply will be sent", flush=True)
            if not card_assigned and card_id:
                print(f"[TWILIO_INBOUND]     Reason: Card is unassigned (safety invariant)", flush=True)
            elif skip_auto_reply:
                print(f"[TWILIO_INBOUND]     Reason: Bot loop prevention", flush=True)
            elif not result.get("next_state"):
                print(f"[TWILIO_INBOUND]     Reason: No state transition from Markov engine", flush=True)
            else:
                print(f"[TWILIO_INBOUND]     Reason: No configured response for state '{next_state}'", flush=True)
        print("=" * 80, flush=True)
        
        # Filter out "OK" messages - don't send standalone "OK" responses
        if reply_text:
            reply_text_clean = reply_text.strip().upper()
            print(f"[TWILIO_INBOUND]   Cleaned reply_text: '{reply_text_clean}'", flush=True)
            # Skip sending if reply is just "OK" or variations
            if reply_text_clean in ["OK", "OKAY", "K", "OK."]:
                print(f"[TWILIO_INBOUND] ⚠️ Skipping 'OK' message - not sending reply", flush=True)
                reply_text = None
            else:
                print(f"[TWILIO_INBOUND] ✅ Reply text is valid (not 'OK')", flush=True)
        
        # 🔧 FIX: Campaign scoping and test overrides
        # Extract campaign_id from card metadata (if present)
        # Campaign ID can be inferred from vertical (frat vs faith) or explicitly set
        campaign_id = None
        force_send = False
        is_test_number = False
        
        if card and card.get("card_data"):
            card_data = card["card_data"]
            metadata = card_data.get("metadata") or {}
            
            # Try explicit campaign_id first
            campaign_id = metadata.get("campaign_id") or card_data.get("campaign_id")
            
            # If no explicit campaign_id, infer from vertical/role
            if not campaign_id:
                # Infer campaign from card data
                if card_data.get("fraternity"):
                    campaign_id = "frat_rt4orgs"
                elif card_data.get("faith_group"):
                    campaign_id = "faith_rt4orgs"
                elif card_data.get("role") == "Office":
                    # Office role suggests faith vertical
                    campaign_id = "faith_rt4orgs"
                else:
                    # Default campaign for unknown verticals
                    campaign_id = "default_rt4orgs"
            
            force_send = metadata.get("force_send", False) or card_data.get("force_send", False)
            
            # Auto-detect test numbers (founder/test numbers)
            # Check if this is a known test number
            test_numbers = [
                os.getenv("TWILIO_PHONE_NUMBER", ""),  # System phone
                "+19843695080",  # Alan's test number (from logs)
                "+19194436288",  # System phone from logs
            ]
            # Also check if card name contains "test" or "Test"
            card_name = card_data.get("name", "").lower()
            is_test_number = (
                normalized_phone in test_numbers or
                "test" in card_name or
                force_send
            )
            
            print(f"[TWILIO_INBOUND] 🔍 Campaign & Test Detection:", flush=True)
            print(f"[TWILIO_INBOUND]   campaign_id: {campaign_id} (inferred from card data)", flush=True)
            print(f"[TWILIO_INBOUND]   force_send: {force_send}", flush=True)
            print(f"[TWILIO_INBOUND]   is_test_number: {is_test_number}", flush=True)
            if is_test_number:
                print(f"[TWILIO_INBOUND]   ✅ TEST NUMBER DETECTED - bypassing all guards", flush=True)
        
        # 🔧 FIX: Check for duplicate outbound suppression (environment-scoped)
        # Only suppress if same environment_id and same state, and not a test number
        # CRITICAL: Only check messages with message_sid (actually sent, not just generated)
        should_suppress = False
        suppression_reason = None
        
        if reply_text and next_state and not is_test_number and not force_send:
            with conn.cursor() as check_cur:
                try:
                    # Check message_events for recent outbound in same environment and state
                    # CRITICAL: Only messages with message_sid count as "sent"
                    check_cur.execute("""
                        SELECT COUNT(*) FROM message_events
                        WHERE phone_number = %s
                          AND environment_id = %s
                          AND direction = 'outbound'
                          AND message_sid IS NOT NULL
                          AND state = %s
                    """, (normalized_phone, environment_id, next_state))
                    duplicate_count = check_cur.fetchone()[0]
                    if duplicate_count > 0:
                        should_suppress = True
                        suppression_reason = f"Duplicate outbound detected: environment_id={environment_id}, state={next_state}"
                        print(f"[TWILIO_INBOUND] ⚠️ BLAST GUARD: {suppression_reason}", flush=True)
                        print(f"[TWILIO_INBOUND]   Found {duplicate_count} prior outbound(s) in same environment/state", flush=True)
                        print(f"[TWILIO_INBOUND]   Suppressing to prevent duplicate send", flush=True)
                except psycopg2.ProgrammingError as e:
                    # message_events table doesn't exist - fallback to history check
                    if 'message_events' in str(e):
                        print(f"[TWILIO_INBOUND] ⚠️ message_events table not found - using history fallback", flush=True)
                        try:
                            check_cur.execute("""
                                SELECT history FROM conversations 
                                WHERE phone = %s AND environment_id = %s
                                LIMIT 1
                            """, (normalized_phone, environment_id))
                        except psycopg2.ProgrammingError:
                            # environment_id column doesn't exist either
                            check_cur.execute("""
                                SELECT history FROM conversations 
                                WHERE phone = %s
                                LIMIT 1
                            """, (normalized_phone,))
                        history_row = check_cur.fetchone()
                        
                        if history_row and history_row[0]:
                            try:
                                history = json.loads(history_row[0]) if isinstance(history_row[0], str) else history_row[0]
                                if isinstance(history, list):
                                    # Check last outbound message
                                    for msg in reversed(history):
                                        if isinstance(msg, dict) and msg.get("direction") == "outbound":
                                            last_state = msg.get("state")
                                            
                                            # Suppress if same state (prevent duplicate sends)
                                            if last_state == next_state:
                                                should_suppress = True
                                                suppression_reason = f"Duplicate outbound detected: state={next_state}"
                                                print(f"[TWILIO_INBOUND] ⚠️ BLAST GUARD (fallback): {suppression_reason}", flush=True)
                                                break
                            except Exception as e:
                                print(f"[TWILIO_INBOUND] ⚠️ Error checking history for suppression: {e}", flush=True)
                    else:
                        raise
        
        if should_suppress and not force_send:
            print(f"[TWILIO_INBOUND] 🚫 SUPPRESSING SEND: {suppression_reason}", flush=True)
            print(f"[TWILIO_INBOUND]   Use force_send=true in card metadata to override", flush=True)
            print(f"[TWILIO_INBOUND]   Or use different campaign_id to send to same number in different vertical", flush=True)
            reply_text = None
        
        if reply_text:
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND] 🚀 SENDING REPLY VIA TWILIO", flush=True)
            print("=" * 80, flush=True)
            print(f"[TWILIO_INBOUND]   To: {normalized_phone}", flush=True)
            print(f"[TWILIO_INBOUND]   From: {twilio_phone}", flush=True)
            print(f"[TWILIO_INBOUND]   Message: {reply_text}", flush=True)
            print(f"[TWILIO_INBOUND]   Message length: {len(reply_text)} chars", flush=True)
            try:
                twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
                twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
                messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
                # twilio_phone already initialized at top of function (fallback if Messaging Service not set)
                
                print(f"[TWILIO_INBOUND] 🔑 Twilio credentials:", flush=True)
                print(f"[TWILIO_INBOUND]   Account SID: {twilio_sid[:10]}... (length: {len(twilio_sid) if twilio_sid else 0})", flush=True)
                print(f"[TWILIO_INBOUND]   Auth Token: {'✅ SET' if twilio_token else '❌ NOT SET'} (length: {len(twilio_token) if twilio_token else 0})", flush=True)
                
                # 🔒 ENFORCE: Messaging Service takes precedence if set
                use_messaging_service = bool(messaging_service_sid)
                send_mode = "MESSAGING_SERVICE" if use_messaging_service else "DIRECT_NUMBER"
                
                if use_messaging_service:
                    print(f"[TWILIO_INBOUND]   Messaging Service SID: {messaging_service_sid[:10]}...{messaging_service_sid[-4:]} (length: {len(messaging_service_sid)})", flush=True)
                    print(f"[TWILIO_INBOUND]   Phone Number: NOT REQUIRED (using Messaging Service)", flush=True)
                else:
                    print(f"[TWILIO_INBOUND]   Phone Number: {twilio_phone}", flush=True)
                    print(f"[TWILIO_INBOUND]   ⚠️ Messaging Service not set - using direct phone number", flush=True)
                
                # Validate credentials based on send mode
                if use_messaging_service:
                    valid = twilio_sid and twilio_token and messaging_service_sid
                else:
                    valid = twilio_sid and twilio_token and twilio_phone
                
                if valid:
                    print(f"[TWILIO_INBOUND] 🔑 Twilio credentials validated", flush=True)
                    print(f"[TWILIO_INBOUND] 📡 Send Mode: {send_mode}", flush=True)
                    print(f"[TWILIO_INBOUND] 📞 Creating Twilio client...", flush=True)
                    
                    client = Client(twilio_sid, twilio_token)
                    
                    # 🔒 PREPARE MESSAGE PARAMETERS: Use Messaging Service if available
                    message_params = {
                        "to": From,  # Use original From, not normalized
                        "body": reply_text
                    }
                    
                    if use_messaging_service:
                        message_params["messaging_service_sid"] = messaging_service_sid
                        # CRITICAL: Do NOT set from_ when using Messaging Service
                        assert "from_" not in message_params, "Cannot use from_ with Messaging Service"
                        print(f"[TWILIO_INBOUND] 📨 Creating message (Messaging Service):", flush=True)
                        print(f"[TWILIO_INBOUND]   to: {From} (original Twilio From)", flush=True)
                        print(f"[TWILIO_INBOUND]   messaging_service_sid: {messaging_service_sid[:10]}...{messaging_service_sid[-4:]}", flush=True)
                        print(f"[TWILIO_INBOUND]   from_: NOT SET (using Messaging Service)", flush=True)
                    else:
                        message_params["from_"] = twilio_phone
                        # CRITICAL: Do NOT set messaging_service_sid when using direct phone
                        assert "messaging_service_sid" not in message_params, "Cannot use messaging_service_sid with direct phone"
                        print(f"[TWILIO_INBOUND] 📨 Creating message (Direct Phone):", flush=True)
                        print(f"[TWILIO_INBOUND]   to: {From} (original Twilio From)", flush=True)
                        print(f"[TWILIO_INBOUND]   from_: {twilio_phone}", flush=True)
                    
                    print(f"[TWILIO_INBOUND]   body: {reply_text}", flush=True)
                    print(f"[TWILIO_INBOUND]   body length: {len(reply_text)} chars", flush=True)
                    
                    msg = client.messages.create(**message_params)
                    
                    print("=" * 80, flush=True)
                    print(f"[TWILIO_INBOUND] ✅✅✅ REPLY SENT SUCCESSFULLY ✅✅✅", flush=True)
                    print("=" * 80, flush=True)
                    print(f"[TWILIO_INBOUND]   Twilio SID: {msg.sid}", flush=True)
                    print(f"[TWILIO_INBOUND]   Status: {msg.status}", flush=True)
                    print(f"[TWILIO_INBOUND]   To: {msg.to}", flush=True)
                    print(f"[TWILIO_INBOUND]   From: {msg.from_}", flush=True)
                    actual_messaging_service = getattr(msg, 'messaging_service_sid', None)
                    print(f"[TWILIO_INBOUND]   Messaging Service SID: {actual_messaging_service or 'N/A'}", flush=True)
                    print(f"[TWILIO_INBOUND]   🔒 Send Mode Used: {send_mode}", flush=True)
                    if use_messaging_service and not actual_messaging_service:
                        print(f"[TWILIO_INBOUND] ⚠️⚠️⚠️ WARNING: Expected Messaging Service but response shows N/A!", flush=True)
                    print(f"[TWILIO_INBOUND]   Body: {msg.body}", flush=True)
                    print(f"[TWILIO_INBOUND]   Date Created: {msg.date_created}", flush=True)
                    print("=" * 80, flush=True)
                    
                    # Store outbound reply in conversation history with campaign_id and state
                    try:
                        from backend.rep_messaging import add_message_to_history
                        # Add campaign_id and state to message metadata for proper scoping
                        add_message_to_history(conn, normalized_phone, "outbound", reply_text, "ai", msg.sid)
                        
                        # Store outbound message event (CRITICAL: with message_sid to mark as "sent")
                        store_message_event(
                            conn=conn,
                            phone_number=normalized_phone,
                            environment_id=environment_id,
                            direction="outbound",
                            message_text=reply_text,
                            message_sid=msg.sid,  # REQUIRED: Only messages with message_sid count as "sent"
                            rep_id=rep_user_id,
                            campaign_id=routed_campaign_id,
                            state=next_state,
                            twilio_status=msg.status
                        )
                        
                        # 🔧 FIX: Update conversation state to next_state (not always initial_outreach)
                        # This ensures proper state tracking and prevents reusing initial_outreach for all messages
                        # CRITICAL: Must scope to environment_id
                        if next_state:
                            with conn.cursor() as update_cur:
                                try:
                                    # Update conversation state scoped to environment
                                    update_cur.execute("""
                                        UPDATE conversations 
                                        SET state = %s, updated_at = NOW()
                                        WHERE phone = %s AND environment_id = %s
                                    """, (next_state, normalized_phone, environment_id))
                                except psycopg2.ProgrammingError:
                                    # Fallback if environment_id column doesn't exist
                                    update_cur.execute("""
                                        UPDATE conversations 
                                        SET state = %s, updated_at = NOW()
                                        WHERE phone = %s
                                    """, (next_state, normalized_phone))
                                print(f"[TWILIO_INBOUND] ✅ Updated conversation state to: {next_state} (was: {conversation_state})", flush=True)
                        
                        # Update history entry with campaign_id and state if available
                        if campaign_id or next_state:
                            with conn.cursor() as update_cur:
                                # Query scoped to environment
                                try:
                                    update_cur.execute("""
                                        SELECT history FROM conversations 
                                        WHERE phone = %s AND environment_id = %s
                                        LIMIT 1
                                    """, (normalized_phone, environment_id))
                                except psycopg2.ProgrammingError:
                                    # Fallback if environment_id column doesn't exist
                                    update_cur.execute("""
                                        SELECT history FROM conversations WHERE phone = %s LIMIT 1
                                    """, (normalized_phone,))
                                hist_row = update_cur.fetchone()
                                if hist_row and hist_row[0]:
                                    try:
                                        history = json.loads(hist_row[0]) if isinstance(hist_row[0], str) else hist_row[0]
                                        if isinstance(history, list) and history:
                                            # Update last message with campaign_id and state
                                            last_msg = history[-1]
                                            if isinstance(last_msg, dict) and last_msg.get("direction") == "outbound":
                                                if campaign_id:
                                                    last_msg["campaign_id"] = campaign_id
                                                if next_state:
                                                    last_msg["state"] = next_state
                                                if is_test_number:
                                                    last_msg["is_test"] = True
                                                
                                                # Save updated history (scoped to environment)
                                                try:
                                                    update_cur.execute("""
                                                        UPDATE conversations 
                                                        SET history = %s::jsonb 
                                                        WHERE phone = %s AND environment_id = %s
                                                    """, (json.dumps(history), normalized_phone, environment_id))
                                                except psycopg2.ProgrammingError:
                                                    # Fallback if environment_id column doesn't exist
                                                    update_cur.execute("""
                                                        UPDATE conversations 
                                                        SET history = %s::jsonb 
                                                        WHERE phone = %s
                                                    """, (json.dumps(history), normalized_phone))
                                                print(f"[TWILIO_INBOUND] ✅ Updated history with campaign_id={campaign_id}, state={next_state}", flush=True)
                                    except Exception as e:
                                        print(f"[TWILIO_INBOUND] ⚠️ Could not update history metadata: {e}", flush=True)
                    except Exception as history_error:
                        print(f"[TWILIO_INBOUND] WARNING: Could not store outbound message in history: {history_error}", flush=True)
                    
                    print(f"[TWILIO_INBOUND] Reply sent: {reply_text[:50]}... (SID: {msg.sid})", flush=True)
                else:
                    missing = []
                    if not twilio_sid:
                        missing.append("TWILIO_ACCOUNT_SID")
                    if not twilio_token:
                        missing.append("TWILIO_AUTH_TOKEN")
                    if not twilio_phone:
                        missing.append("TWILIO_PHONE_NUMBER")
                    print(f"[TWILIO_INBOUND] ❌ WARNING: Missing Twilio config: {', '.join(missing)}", flush=True)
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
async def upload_cards(
    cards: List[Dict[str, Any]],
    request: Request
):
    """
    Upload array of heterogeneous JSON card objects.
    Validates schema, normalizes IDs, resolves references, and stores cards.
    Requires owner or rep authentication.
    """
    # Authenticate user
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UPLOAD] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    print("=" * 60)
    print("UPLOAD HIT")
    print("=" * 60)
    print(f"📤 Upload request: {len(cards)} card(s)")
    
    # Generate upload batch ID for this upload session
    from datetime import datetime
    import hashlib
    upload_timestamp = datetime.utcnow().isoformat()
    batch_hash = hashlib.md5(f"{upload_timestamp}_{len(cards)}".encode()).hexdigest()[:8]
    upload_batch_id = f"upload_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{batch_hash}"
    print(f"📦 Upload batch ID: {upload_batch_id}")
    
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
        # Pass upload_batch_id to track which upload batch this card came from
        success, error_msg, stored_card = store_card(conn, normalized, allow_missing_references=True, upload_batch_id=upload_batch_id)
        
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


@app.get("/cards/verticals")
async def get_verticals_endpoint(vertical: Optional[str] = Query(None), request: Request = None):
    """
    Get information about vertical types.
    Returns all verticals or specific vertical if 'vertical' query param provided.
    """
    # Optional authentication - allow public access to vertical info
    try:
        await get_current_owner_or_rep(request)
    except:
        pass  # Allow unauthenticated access to vertical info
    
    info = get_vertical_info(vertical)
    return info


@app.post("/cards/generate-pitch")
async def generate_pitch_endpoint(
    data: Dict[str, Any],
    request: Request
):
    """
    Generate a personalized pitch from a card using the vertical's pitch template.
    
    Body:
    {
        "card": {...},
        "vertical": "frats",
        "additional_data": {
            "purchased_chapter": "...",
            "rep_name": "..."
        }
    }
    """
    # Authenticate user
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GENERATE_PITCH] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    card = data.get("card")
    vertical = data.get("vertical")
    additional_data = data.get("additional_data", {})
    
    if not card:
        raise HTTPException(status_code=400, detail="Missing 'card' in request body")
    
    if not vertical:
        vertical = card.get("vertical")
    
    if not vertical:
        raise HTTPException(status_code=400, detail="Missing 'vertical' - provide in request body or card")
    
    if vertical not in VERTICAL_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid vertical: {vertical}. Must be one of: {', '.join(VERTICAL_TYPES.keys())}"
        )
    
    pitch = generate_pitch(card, vertical, additional_data)
    
    if not pitch:
        raise HTTPException(status_code=500, detail="Failed to generate pitch")
    
    return {"pitch": pitch, "vertical": vertical}


@app.get("/cards/{card_id}")
async def get_card_endpoint(card_id: str, request: Request):
    """
    Get a single card by ID.
    
    SECURITY: 
    - Owner/admin can view any card
    - Reps can ONLY view cards assigned to them
    """
    # Authenticate user
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_CARD] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = get_conn()
    card = get_card(conn, card_id)

    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    
    # Security check: Reps can only view cards assigned to them
    if current_user.get("role") != "admin":
        from backend.assignments import get_card_assignment
        assignment = get_card_assignment(conn, card_id)
        if not assignment or assignment["user_id"] != current_user["id"]:
            logger.warning(f"[GET_CARD] Rep {current_user['id']} attempted to view unauthorized card: {card_id}")
            raise HTTPException(status_code=403, detail="Card is not assigned to you")
    
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
async def delete_card_endpoint(card_id: str, request: Request):
    """
    Delete a card by ID. Also deletes related relationships, conversations, and assignments.
    Logs terminal handoff event (not a handoff - to_rep=NULL indicates deletion).
    Requires owner authentication.
    """
    # Authenticate user (owner only for deletion)
    try:
        current_user = await get_current_admin_user(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CARD_DELETE] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = get_conn()
    
    # Check if card exists
    card = get_card(conn, card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")

    # Use the new delete_card function which handles cleanup and handoff logging
    success, error_message = delete_card(conn, card_id, current_user['id'])
    
    if not success:
        raise HTTPException(status_code=500, detail=error_message or f"Error deleting card: {card_id}")

    return {"ok": True, "message": f"Card {card_id} deleted successfully"}


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
                    
                    # Handle both old schema (7 columns) and new schema (8 columns with upload_batch_id)
                    card_obj = {
                        "id": row[0],
                        "type": row[1],
                        "card_data": card_data,
                        "sales_state": row[3],
                        "owner": row[4],
                        "created_at": row[5].isoformat() if row[5] else None,
                        "updated_at": row[6].isoformat() if row[6] else None,
                    }
                    # Add upload_batch_id if column exists (8th column)
                    if len(row) > 7:
                        card_obj["upload_batch_id"] = row[7]
                    cards.append(card_obj)
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
                                
                                card_obj = {
                                    "id": row[0],
                                    "type": row[1],
                                    "card_data": card_data,
                                    "sales_state": row[3],
                                    "owner": row[4],
                                    "created_at": row[5].isoformat() if row[5] else None,
                                    "updated_at": row[6].isoformat() if row[6] else None,
                                }
                                # Add upload_batch_id if column exists (8th column)
                                if len(row) > 7:
                                    card_obj["upload_batch_id"] = row[7]
                                cards.append(card_obj)
                            
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
async def get_markov_responses(
    request: Request
):
    """Get all configured Markov state responses. Owner gets global, reps get their own."""
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MARKOV_RESPONSES] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = get_conn()
    user_role = current_user.get("role")
    user_id = None if user_role == "admin" else current_user.get("id")
    
    with conn.cursor() as cur:
        if user_id:
            # Rep: get rep-specific responses, but also include owner's defaults for states they haven't customized
            # First get rep-specific responses
            cur.execute("""
                SELECT state_key, response_text, description, updated_at
                FROM markov_responses
                WHERE user_id = %s
                ORDER BY state_key;
            """, (user_id,))
            rep_rows = cur.fetchall()
            
            # Then get owner's global responses
            cur.execute("""
                SELECT state_key, response_text, description, updated_at
                FROM markov_responses
                WHERE user_id IS NULL
                ORDER BY state_key;
            """)
            global_rows = cur.fetchall()
            
            # Merge: rep-specific overrides global, but include global for states rep hasn't customized
            rep_responses = {row[0]: row for row in rep_rows}
            global_responses = {row[0]: row for row in global_rows}
            
            # Start with global defaults, then override with rep-specific
            responses = {}
            for state_key, row in global_responses.items():
                responses[state_key] = {
                    "response_text": row[1],
                    "description": row[2],
                    "updated_at": row[3].isoformat() if row[3] else None,
                    "is_custom": False,  # This is from owner's defaults
                }
            # Override with rep-specific customizations
            for state_key, row in rep_responses.items():
                responses[state_key] = {
                    "response_text": row[1],
                    "description": row[2],
                    "updated_at": row[3].isoformat() if row[3] else None,
                    "is_custom": True,  # This is rep's customization
                }
        else:
            # Owner: get global responses (user_id IS NULL)
            cur.execute("""
                SELECT state_key, response_text, description, updated_at
                FROM markov_responses
                WHERE user_id IS NULL
                ORDER BY state_key;
            """)
            rows = cur.fetchall()
            
            responses = {
                row[0]: {
                    "response_text": row[1],
                    "description": row[2],
                    "updated_at": row[3].isoformat() if row[3] else None,
                    "is_custom": True,  # Owner's responses are always "custom" (they're the defaults)
                }
                for row in rows
            }
    
    # Also get initial outreach (stored as special key)
    with conn.cursor() as cur:
        if user_id:
            # Try rep-specific first
            cur.execute("""
                SELECT response_text FROM markov_responses 
                WHERE state_key = '__initial_outreach__' AND user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                # Fallback to global
                cur.execute("""
                    SELECT response_text FROM markov_responses 
                    WHERE state_key = '__initial_outreach__' AND user_id IS NULL
                """)
                row = cur.fetchone()
        else:
            # Owner: get global
            cur.execute("""
                SELECT response_text FROM markov_responses 
                WHERE state_key = '__initial_outreach__' AND user_id IS NULL
            """)
            row = cur.fetchone()
        initial_outreach = row[0] if row else None
    
    return {
        "responses": responses,
        "initial_outreach": initial_outreach,
    }


@app.post("/markov/response")
async def update_single_markov_response(
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    """
    Update a single Markov state response.
    
    CRITICAL: Owner saves global (user_id=NULL), reps save their own (user_id=rep_id).
    Reps can ONLY modify their own responses, never the owner's defaults.
    If a rep doesn't have a custom response, the system falls back to owner's default.
    """
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MARKOV_RESPONSE] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    logger.info("🧠 ENTER save_markov_response")
    logger.info(f"📦 payload={json.dumps(payload, indent=2)}")
    
    conn = get_conn()
    user_role = current_user.get("role")
    user_id = None if user_role == "admin" else current_user.get("id")
    
    # CRITICAL: Reps can ONLY save their own responses, never modify owner's defaults
    # The owner's responses (user_id=NULL) are protected - only admin role can modify them
    if user_role != "admin" and user_id is None:
        logger.error(f"[MARKOV_RESPONSE] ❌ Rep attempted to modify global response - BLOCKED")
        raise HTTPException(status_code=403, detail="Reps can only modify their own responses, not global defaults")
    
    state_key = payload.get("state_key")
    response_text = payload.get("response_text", "")
    description = payload.get("description", "")
    
    if not state_key:
        logger.error("❌ Missing state_key in payload")
        raise HTTPException(status_code=400, detail="state_key is required")
    
    logger.info(f"✏️ Saving state: {state_key} (user_id: {user_id or 'global'})")
    logger.debug(f"Response text length: {len(response_text)}")
    
    try:
        with conn.cursor() as cur:
            if user_id:
                # Rep: save with user_id (use partial unique index)
                # Use UPDATE ... WHERE pattern since ON CONFLICT with partial indexes is tricky
                cur.execute("""
                    UPDATE markov_responses
                    SET response_text = %s, description = %s, updated_at = %s
                    WHERE state_key = %s AND user_id = %s;
                """, (response_text, description, datetime.utcnow(), state_key, user_id))
                if cur.rowcount == 0:
                    cur.execute("""
                        INSERT INTO markov_responses (state_key, response_text, description, updated_at, user_id)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (state_key, response_text, description, datetime.utcnow(), user_id))
            else:
                # Owner: save global (user_id IS NULL)
                cur.execute("""
                    UPDATE markov_responses
                    SET response_text = %s, description = %s, updated_at = %s
                    WHERE state_key = %s AND user_id IS NULL;
                """, (response_text, description, datetime.utcnow(), state_key))
                if cur.rowcount == 0:
                    cur.execute("""
                        INSERT INTO markov_responses (state_key, response_text, description, updated_at, user_id)
                        VALUES (%s, %s, %s, %s, NULL);
                    """, (state_key, response_text, description, datetime.utcnow()))
        
        logger.info(f"✅ Saved state: {state_key}")
        
        # Verify the save worked by querying it back
        with conn.cursor() as verify_cur:
            if user_id:
                verify_cur.execute("""
                    SELECT response_text FROM markov_responses
                    WHERE state_key = %s AND user_id = %s
                """, (state_key, user_id))
            else:
                verify_cur.execute("""
                    SELECT response_text FROM markov_responses
                    WHERE state_key = %s AND user_id IS NULL
                """, (state_key,))
            verify_row = verify_cur.fetchone()
            if verify_row:
                logger.info(f"✅ Verified: Response saved successfully (length: {len(verify_row[0])} chars)")
                logger.info(f"✅ Verified: Preview: {verify_row[0][:50]}...")
            else:
                logger.warning(f"⚠️ WARNING: Could not verify saved response for state_key={state_key}, user_id={user_id}")
        
        logger.info("✅ SAVE COMPLETE")
        return {"ok": True, "state_key": state_key, "message": "Response saved successfully"}
    except Exception as e:
        logger.error(f"❌ Failed saving state: {state_key}")
        logger.exception(e)
        raise


@app.post("/markov/responses")
async def update_markov_responses(
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    """
    Update Markov state responses (batch).
    
    CRITICAL: Owner saves global (user_id=NULL), reps save their own (user_id=rep_id).
    Reps can ONLY modify their own responses, never the owner's defaults.
    If a rep doesn't have a custom response, the system falls back to owner's default.
    """
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MARKOV_RESPONSES_BATCH] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    logger.info("📥 POST /markov/responses called (batch)")
    logger.info(f"📦 Payload keys: {list(payload.keys())}")
    
    conn = get_conn()
    user_role = current_user.get("role")
    user_id = None if user_role == "admin" else current_user.get("id")
    
    # CRITICAL: Reps can ONLY save their own responses, never modify owner's defaults
    if user_role != "admin" and user_id is None:
        logger.error(f"[MARKOV_RESPONSES_BATCH] ❌ Rep attempted to modify global responses - BLOCKED")
        raise HTTPException(status_code=403, detail="Reps can only modify their own responses, not global defaults")
    
    responses = payload.get("responses", {})
    initial_outreach = payload.get("initial_outreach")
    
    logger.info(f"📥 JSON import triggered (user_id: {user_id or 'global'})")
    logger.info(f"States in import: {list(responses.keys())}")
    logger.info(f"Initial outreach present: {initial_outreach is not None}")
    
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
                    if user_id:
                        # Rep: save with user_id (use partial unique index)
                        cur.execute("""
                            UPDATE markov_responses
                            SET response_text = %s, description = %s, updated_at = %s
                            WHERE state_key = %s AND user_id = %s;
                        """, (response_text, description, datetime.utcnow(), state_key, user_id))
                        if cur.rowcount == 0:
                            cur.execute("""
                                INSERT INTO markov_responses (state_key, response_text, description, updated_at, user_id)
                                VALUES (%s, %s, %s, %s, %s);
                            """, (state_key, response_text, description, datetime.utcnow(), user_id))
                    else:
                        # Owner: save global
                        cur.execute("""
                            UPDATE markov_responses
                            SET response_text = %s, description = %s, updated_at = %s
                            WHERE state_key = %s AND user_id IS NULL;
                        """, (response_text, description, datetime.utcnow(), state_key))
                        if cur.rowcount == 0:
                            cur.execute("""
                                INSERT INTO markov_responses (state_key, response_text, description, updated_at, user_id)
                                VALUES (%s, %s, %s, %s, NULL);
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
                    if user_id:
                        # Rep: save with user_id (use partial unique index)
                        cur.execute("""
                            UPDATE markov_responses
                            SET response_text = %s, updated_at = %s
                            WHERE state_key = '__initial_outreach__' AND user_id = %s;
                        """, (initial_outreach, datetime.utcnow(), user_id))
                        if cur.rowcount == 0:
                            cur.execute("""
                                INSERT INTO markov_responses (state_key, response_text, updated_at, user_id)
                                VALUES ('__initial_outreach__', %s, %s, %s);
                            """, (initial_outreach, datetime.utcnow(), user_id))
                    else:
                        # Owner: save global
                        cur.execute("""
                            UPDATE markov_responses
                            SET response_text = %s, updated_at = %s
                            WHERE state_key = '__initial_outreach__' AND user_id IS NULL;
                        """, (initial_outreach, datetime.utcnow()))
                        if cur.rowcount == 0:
                            cur.execute("""
                                INSERT INTO markov_responses (state_key, response_text, updated_at, user_id)
                                VALUES ('__initial_outreach__', %s, %s, NULL);
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
    
    # Confused interest - user is confused but maybe interested
    if any(word in text_lower for word in ["confused", "confusion", "not sure", "unsure", "don't understand", "unclear"]):
        return {"category": "interest", "subcategory": "confused_interest"}
    
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


def get_markov_response(conn: Any, state_key: str, user_id: Optional[str] = None) -> Optional[str]:
    """
    Get configured response text for a Markov state, or None if not configured.
    
    CRITICAL: This implements the rep-specific Markov handler system:
    - If user_id is provided (rep), tries rep-specific response first
    - Falls back to global (owner's default) if rep hasn't customized
    - If user_id is None (owner), returns global response only
    
    Args:
        conn: Database connection
        state_key: The Markov state key
        user_id: Optional user ID for rep-scoped responses. If None, returns global response.
                 If provided, tries rep-specific first, then falls back to global.
    
    Returns:
        Response text or None
    """
    # Normalize state_key - ensure it's a string and strip whitespace
    if not isinstance(state_key, str):
        state_key = str(state_key)
    state_key = state_key.strip()
    
    print("=" * 80, flush=True)
    print(f"[GET_MARKOV_RESPONSE] 🔍 STARTING RESPONSE LOOKUP", flush=True)
    print("=" * 80, flush=True)
    print(f"[GET_MARKOV_RESPONSE]   state_key (raw): '{state_key}'", flush=True)
    print(f"[GET_MARKOV_RESPONSE]   state_key (normalized): '{state_key}'", flush=True)
    print(f"[GET_MARKOV_RESPONSE]   state_key length: {len(state_key)}", flush=True)
    print(f"[GET_MARKOV_RESPONSE]   user_id: {user_id}", flush=True)
    print(f"[GET_MARKOV_RESPONSE]   user_id type: {type(user_id)}", flush=True)
    if user_id:
        print(f"[GET_MARKOV_RESPONSE]   user_id (normalized): '{user_id.strip() if isinstance(user_id, str) else user_id}'", flush=True)
    
    with conn.cursor() as cur:
        if user_id:
            # Normalize user_id to string and strip
            user_id_str = str(user_id).strip() if user_id else None
            if not user_id_str:
                print(f"[GET_MARKOV_RESPONSE] ⚠️ user_id is empty after normalization, skipping rep-specific lookup", flush=True)
                user_id_str = None  # Ensure it's None for consistency
            else:
                # Try rep-specific first
                print(f"[GET_MARKOV_RESPONSE] 🔎 Querying rep-specific response...", flush=True)
                print(f"[GET_MARKOV_RESPONSE]   SQL: SELECT response_text FROM markov_responses WHERE state_key = '{state_key}' AND user_id = '{user_id_str}'", flush=True)
                print(f"[GET_MARKOV_RESPONSE]   SQL params: state_key='{state_key}', user_id='{user_id_str}'", flush=True)
                cur.execute("""
                    SELECT response_text FROM markov_responses
                    WHERE state_key = %s AND user_id = %s
                """, (state_key, user_id_str))
                row = cur.fetchone()
                print(f"[GET_MARKOV_RESPONSE]   Query returned: {row}", flush=True)
                if row and row[0]:
                    response_text = row[0].strip()
                    print(f"[GET_MARKOV_RESPONSE]   Raw response_text: '{response_text}'", flush=True)
                    print(f"[GET_MARKOV_RESPONSE]   Response_text length: {len(response_text)}", flush=True)
                    if response_text:  # Make sure it's not empty
                        print("=" * 80, flush=True)
                        print(f"[GET_MARKOV_RESPONSE] ✅✅✅ FOUND REP-SPECIFIC RESPONSE ✅✅✅", flush=True)
                        print("=" * 80, flush=True)
                        print(f"[GET_MARKOV_RESPONSE]   state_key: '{state_key}'", flush=True)
                        print(f"[GET_MARKOV_RESPONSE]   user_id: '{user_id_str}'", flush=True)
                        print(f"[GET_MARKOV_RESPONSE]   response_text: '{response_text}'", flush=True)
                        print(f"[GET_MARKOV_RESPONSE]   length: {len(response_text)} chars", flush=True)
                        print("=" * 80, flush=True)
                        return response_text
                    else:
                        print(f"[GET_MARKOV_RESPONSE] ⚠️ Rep-specific response exists but is empty, falling back to global", flush=True)
                else:
                    print(f"[GET_MARKOV_RESPONSE] ⚠️ No rep-specific response found, falling back to global", flush=True)
                    # Debug: Check what responses exist for this user
                    cur.execute("""
                        SELECT state_key, response_text FROM markov_responses
                        WHERE user_id = %s
                        ORDER BY state_key
                    """, (user_id_str,))
                    all_rep_responses = cur.fetchall()
                    print(f"[GET_MARKOV_RESPONSE]   Debug: All rep responses for user_id='{user_id_str}': {len(all_rep_responses)} total", flush=True)
                    for resp_row in all_rep_responses[:10]:  # Show first 10
                        state_in_db = resp_row[0]
                        response_preview = resp_row[1][:50] if resp_row[1] else 'EMPTY'
                        match_status = "✅ MATCH" if state_in_db == state_key else "❌ NO MATCH"
                        print(f"[GET_MARKOV_RESPONSE]     {match_status} state_key='{state_in_db}' response='{response_preview}...'", flush=True)
                    state_in_db = resp_row[0]
                    response_preview = resp_row[1][:50] if resp_row[1] else 'EMPTY'
                    match_status = "✅ MATCH" if state_in_db == state_key else "❌ NO MATCH"
                    print(f"[GET_MARKOV_RESPONSE]     {match_status} state_key='{state_in_db}' response='{response_preview}...'", flush=True)
        
        # Fallback to global (user_id IS NULL) - owner's defaults
        print(f"[GET_MARKOV_RESPONSE] 🔎 Querying global (owner) response...", flush=True)
        print(f"[GET_MARKOV_RESPONSE]   SQL: SELECT response_text FROM markov_responses WHERE state_key = '{state_key}' AND user_id IS NULL", flush=True)
        cur.execute("""
            SELECT response_text FROM markov_responses
            WHERE state_key = %s AND user_id IS NULL
        """, (state_key,))
        row = cur.fetchone()
        print(f"[GET_MARKOV_RESPONSE]   Query returned: {row}", flush=True)
        if row and row[0]:
            response_text = row[0].strip()
            print(f"[GET_MARKOV_RESPONSE]   Raw response_text: '{response_text}'", flush=True)
            print(f"[GET_MARKOV_RESPONSE]   Response_text length: {len(response_text)}", flush=True)
            if response_text:  # Make sure it's not empty
                print("=" * 80, flush=True)
                print(f"[GET_MARKOV_RESPONSE] ✅✅✅ FOUND GLOBAL (OWNER) RESPONSE ✅✅✅", flush=True)
                print("=" * 80, flush=True)
                print(f"[GET_MARKOV_RESPONSE]   state_key: '{state_key}'", flush=True)
                print(f"[GET_MARKOV_RESPONSE]   response_text: '{response_text}'", flush=True)
                print(f"[GET_MARKOV_RESPONSE]   length: {len(response_text)} chars", flush=True)
                print("=" * 80, flush=True)
                return response_text
            else:
                print(f"[GET_MARKOV_RESPONSE] ⚠️ Global response exists but is empty", flush=True)
        else:
            print(f"[GET_MARKOV_RESPONSE] ❌ No global response found either", flush=True)
            # Debug: Check what global responses exist
            cur.execute("""
                SELECT state_key, response_text FROM markov_responses
                WHERE user_id IS NULL
                ORDER BY state_key
            """)
            all_global_responses = cur.fetchall()
            print(f"[GET_MARKOV_RESPONSE]   Debug: All global responses: {len(all_global_responses)} total", flush=True)
            for resp_row in all_global_responses[:5]:  # Show first 5
                print(f"[GET_MARKOV_RESPONSE]     - {resp_row[0]}: '{resp_row[1][:50] if resp_row[1] else 'EMPTY'}...'", flush=True)
        
        print("=" * 80, flush=True)
        print(f"[GET_MARKOV_RESPONSE] ❌❌❌ NO RESPONSE FOUND ❌❌❌", flush=True)
        print("=" * 80, flush=True)
        print(f"[GET_MARKOV_RESPONSE]   state_key: '{state_key}'", flush=True)
        print(f"[GET_MARKOV_RESPONSE]   user_id: {user_id}", flush=True)
        print(f"[GET_MARKOV_RESPONSE]   Result: None", flush=True)
        print("=" * 80, flush=True)
        return None


def get_initial_outreach_message(conn: Any, user_id: Optional[str] = None) -> Optional[str]:
    """Get configured initial outreach message, or None if not configured."""
    return get_markov_response(conn, "__initial_outreach__", user_id)


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
    print(f"[AUTH] Authorization header received: {auth_header[:50]}...", flush=True)
    
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("[AUTH] Missing or invalid Authorization header")
        print("[AUTH] ❌ Missing or invalid Authorization header", flush=True)
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = auth_header[7:]
    print(f"[AUTH] Extracted token: {token[:20]}... (length: {len(token)})", flush=True)
    
    conn = get_conn()
    user = get_user_by_token(conn, token)
    
    if not user:
        # Enhanced logging for token validation failure
        import hashlib
        hashed_token = hashlib.sha256(token.encode()).hexdigest()
        print(f"[AUTH] ❌ Invalid API token", flush=True)
        print(f"[AUTH] Token preview: {token[:20]}...", flush=True)
        print(f"[AUTH] Token length: {len(token)}", flush=True)
        print(f"[AUTH] Hashed token: {hashed_token[:20]}...", flush=True)
        logger.warning(f"[AUTH] Invalid API token (token preview: {token[:15]}..., hashed: {hashed_token[:20]}...)")
        raise HTTPException(status_code=401, detail="Invalid API token")
    
    logger.info(f"[AUTH] Authenticated user: {user['id']} role={user['role']} username={user.get('username', 'N/A')}")
    print(f"[AUTH] ✅ Authenticated user: {user['id']} (role: {user.get('role')}, username: {user.get('username', 'N/A')})", flush=True)
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
    print(f"[AUTH_DEPENDENCY] get_current_owner_or_rep called", flush=True)
    try:
        user = await get_current_user(request)
        print(f"[AUTH_DEPENDENCY] ✅ User authenticated: {user.get('id')} (role: {user.get('role')})", flush=True)
        return user
    except Exception as e:
        print(f"[AUTH_DEPENDENCY] ❌ Exception in get_current_owner_or_rep: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise


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
        # run_blast_for_cards() now always uses environment variables - no auth params needed
        result = run_blast_for_cards(
            conn=conn,
            card_ids=card_ids,
            limit=limit,
            owner=owner,
            source=source,
            rep_user_id=None,  # Legacy endpoint doesn't track rep_user_id
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


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    current_user: Dict = Depends(get_current_admin_user)
):
    """Delete a user and all their card assignments."""
    logger.info(f"[ADMIN] delete_user called by {current_user['id']} for {user_id}")
    
    # Prevent deleting yourself
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own user account")
    
    conn = get_conn()
    try:
        success = delete_user(conn, user_id)
        
        if success:
            logger.info(f"[ADMIN] delete_user success: {user_id}")
            return {"ok": True, "message": "User deleted successfully"}
        else:
            logger.warning(f"[ADMIN] delete_user failed: user not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN] delete_user exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


@app.post("/admin/users/{user_id}/regenerate-token")
async def admin_regenerate_token(
    user_id: str,
    current_user: Dict = Depends(get_current_admin_user)
):
    """Regenerate API token for a user. Returns new token (only shown once)."""
    logger.info(f"[ADMIN] regenerate_token called by {current_user['id']} for {user_id}")
    
    conn = get_conn()
    try:
        new_token = regenerate_api_token(conn, user_id)
        
        if new_token:
            logger.info(f"[ADMIN] regenerate_token success: {user_id}")
            return {"ok": True, "api_token": new_token, "message": "New API token generated. Save this token - it will not be shown again."}
        else:
            logger.warning(f"[ADMIN] regenerate_token failed: user not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN] regenerate_token exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to regenerate token: {str(e)}")


@app.post("/admin/users/{user_id}/set-token")
async def admin_set_token(
    user_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: Dict = Depends(get_current_admin_user)
):
    """Set a specific API token for a user. Admin only."""
    token = payload.get("api_token")
    if not token:
        raise HTTPException(status_code=400, detail="api_token is required in payload")
    
    logger.info(f"[ADMIN] set_token called by {current_user['id']} for {user_id}")
    
    conn = get_conn()
    
    try:
        from backend.auth import hash_token
        
        hashed_token = hash_token(token)
        
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="User not found")
            
            # Update token
            cur.execute("""
                UPDATE users
                SET api_token = %s, updated_at = NOW()
                WHERE id = %s
            """, (hashed_token, user_id))
            
            if cur.rowcount > 0:
                logger.info(f"[ADMIN] set_token success: {user_id}")
                return {"ok": True, "message": f"API token set for user {user_id}"}
            else:
                raise HTTPException(status_code=500, detail="Failed to update token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN] set_token exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set token: {str(e)}")


@app.post("/admin/users/{user_id}/clear-twilio")
async def admin_clear_twilio(
    user_id: str,
    current_user: Dict = Depends(get_current_admin_user)
):
    """Clear all Twilio configuration (phone, account_sid, auth_token) for a user."""
    logger.info(f"[ADMIN] clear_twilio called by {current_user['id']} for {user_id}")
    
    conn = get_conn()
    try:
        success = clear_twilio_config(conn, user_id)
        
        if success:
            logger.info(f"[ADMIN] clear_twilio success: {user_id}")
            return {"ok": True, "message": "Twilio configuration cleared successfully"}
        else:
            logger.warning(f"[ADMIN] clear_twilio failed: user not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN] clear_twilio exception: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to clear Twilio config: {str(e)}")


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
    request: Request,
    status: Optional[str] = None
):
    """
    Get rep's assigned cards. 
    
    CRITICAL SECURITY: Reps can ONLY see assigned cards, never all cards.
    Owner (admin role) can see all cards for admin dashboard.
    
    Database relationship: card_assignments table links cards to reps via:
    - card_assignments.card_id -> cards.id
    - card_assignments.user_id -> users.id
    """
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REP_CARDS] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
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
async def rep_get_conversations(request: Request):
    """Get rep's active conversations. Owner sees all, reps see only their own."""
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REP_CONVERSATIONS] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
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


@app.get("/rep/leads")
async def rep_get_leads(request: Request):
    """
    Get rep's leads - cards that have received inbound messages (responses) to the rep's webhook.
    Owner sees all leads, reps see only leads that responded to their messages.
    """
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REP_LEADS] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    conn = get_conn()
    leads = []
    rep_user_id = current_user["id"] if current_user.get("role") != "admin" else None
    
    with conn.cursor() as cur:
        # Get conversations with inbound messages
        # For reps: filter by rep_user_id. For owner: show all.
        if rep_user_id:
            # Rep: only their assigned cards with inbound messages (≥1 inbound = lead)
            # Join with card_assignments to filter by assigned cards only
            try:
                # Try with environment_id (new schema)
                cur.execute("""
                    SELECT DISTINCT c.card_id, c.phone, c.state, c.last_inbound_at, c.last_outbound_at,
                           COALESCE(c.history::text, '[]') as history, c.environment_id
                    FROM conversations c
                    INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                    WHERE c.card_id IS NOT NULL
                      AND c.last_inbound_at IS NOT NULL
                      AND ca.user_id = %s
                    ORDER BY c.last_inbound_at DESC;
                """, (rep_user_id,))
            except psycopg2.ProgrammingError:
                # Fallback if environment_id column doesn't exist
                cur.execute("""
                    SELECT DISTINCT c.card_id, c.phone, c.state, c.last_inbound_at, c.last_outbound_at,
                           COALESCE(c.history::text, '[]') as history
                    FROM conversations c
                    INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                    WHERE c.card_id IS NOT NULL
                      AND c.last_inbound_at IS NOT NULL
                      AND ca.user_id = %s
                    ORDER BY c.last_inbound_at DESC;
                """, (rep_user_id,))
        else:
            # Owner: all conversations with inbound messages
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


# 🔥 TEST ENDPOINT: No auth required - just to verify requests reach the server
@app.post("/test/blast-ping")
async def test_blast_ping(request: Request):
    """Test endpoint to verify POST requests are reaching the server"""
    print("=" * 80, flush=True)
    print(f"[TEST_PING] 🔥 TEST ENDPOINT HIT", flush=True)
    print("=" * 80, flush=True)
    print(f"[TEST_PING] Method: {request.method}", flush=True)
    print(f"[TEST_PING] Path: {request.url.path}", flush=True)
    print(f"[TEST_PING] Headers: {dict(request.headers)}", flush=True)
    try:
        body = await request.json()
        print(f"[TEST_PING] Body: {body}", flush=True)
    except:
        body_text = await request.body()
        print(f"[TEST_PING] Body (text): {body_text}", flush=True)
    print("=" * 80, flush=True)
    return {"ok": True, "message": "Test endpoint reached successfully", "timestamp": datetime.utcnow().isoformat()}


@app.post("/rep/blast")
async def rep_blast(
    request: Request
):
    """Blast cards. Owner can blast any cards, reps can only blast their assigned cards."""
    # 🔥 CRITICAL: Log IMMEDIATELY - BEFORE ANYTHING ELSE
    # This MUST be the absolute first line - if this doesn't log, FastAPI is rejecting before handler
    logger.error("🔥🔥🔥 ENTERED /rep/blast HANDLER 🔥🔥🔥")
    print("🔥🔥🔥 ENTERED /rep/blast HANDLER 🔥🔥🔥", flush=True)
    print(f"[REP_BLAST] Request method: {request.method}", flush=True)
    print(f"[REP_BLAST] Request path: {request.url.path}", flush=True)
    print(f"[REP_BLAST] Request headers: {dict(request.headers)}", flush=True)
    
    # Authenticate user manually
    try:
        print(f"[REP_BLAST] Attempting authentication...", flush=True)
        user = await get_current_owner_or_rep(request)
        print(f"[REP_BLAST] ✅ Authentication successful: {user.get('id')} (role: {user.get('role')})", flush=True)
    except HTTPException as auth_exc:
        print(f"[REP_BLAST] ❌ Auth HTTPException: {auth_exc.status_code} - {auth_exc.detail}", flush=True)
        logger.error(f"[REP_BLAST] Auth HTTPException: {auth_exc.status_code} - {auth_exc.detail}")
        raise
    except Exception as e:
        print(f"[REP_BLAST] ❌ Auth error: {type(e).__name__}: {str(e)}", flush=True)
        logger.error(f"[REP_BLAST] Auth error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Parse JSON directly - bypasses all FastAPI validation
    try:
        payload = await request.json()
        logger.error(f"🔥 BLAST PAYLOAD: {payload}")
        print(f"🔥 BLAST PAYLOAD: {payload}", flush=True)
    except Exception as json_err:
        logger.error(f"🔥 BLAST PAYLOAD PARSE ERROR: {json_err}")
        print(f"🔥 BLAST PAYLOAD PARSE ERROR: {json_err}", flush=True)
        import traceback
        traceback.print_exc()
        payload = {}
    
    # Use 'user' instead of 'current_user' to match dependency name
    current_user = user
    
    # Now continue with the rest of the handler logic
    try:
        # CRITICAL: Log immediately when endpoint is hit - BEFORE anything else
        import sys
        sys.stdout.flush()
        sys.stderr.flush()
        
        print("=" * 80, flush=True)
        print(f"[BLAST_ENDPOINT] 🚀 ENDPOINT CALLED", flush=True)
        print("=" * 80, flush=True)
        print(f"[BLAST_ENDPOINT] Request method: {request.method}", flush=True)
        print(f"[BLAST_ENDPOINT] Request path: {request.url.path}", flush=True)
        print(f"[BLAST_ENDPOINT] Request headers: {dict(request.headers)}", flush=True)
        print(f"[BLAST_ENDPOINT] Payload type: {type(payload)}", flush=True)
        print(f"[BLAST_ENDPOINT] Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'NOT A DICT'}", flush=True)
        print(f"[BLAST_ENDPOINT] Payload: {payload}", flush=True)
        print(f"[BLAST_ENDPOINT] Current user: {current_user}", flush=True)
        logger.info("=" * 80)
        logger.info("[BLAST_ENDPOINT] 🚀 ENDPOINT CALLED")
        logger.info("=" * 80)
        
        # #region agent log - Blast endpoint entry
        try:
            import json as _json
            from datetime import datetime
            from pathlib import Path
            debug_log_path = Path(__file__).resolve().parent / ".cursor" / "debug.log"
            debug_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_log_path, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": "main.py:rep_blast:ENTRY",
                    "message": "Blast endpoint called",
                    "data": {"user_id": current_user.get('id'), "role": current_user.get('role'), "payload_keys": list(payload.keys())},
                    "hypothesisId": "A"
                }) + "\n")
        except Exception as e:
            logger.error(f"[DEBUG_LOG] Failed to write debug log: {e}")
        # #endregion
        
        logger.info(f"[BLAST] rep_blast called by {current_user['id']} (role: {current_user.get('role')})")
        logger.info(f"[BLAST] payload = {payload}")
        print(f"[BLAST_ENDPOINT] User: {current_user['id']} (role: {current_user.get('role')})", flush=True)
        print(f"[BLAST_ENDPOINT] Payload keys: {list(payload.keys())}", flush=True)
        print(f"[BLAST_ENDPOINT] Payload: {payload}", flush=True)
        
        # ✅ FIX 3: Normalize payload defensively - handle multiple payload shapes
        # Frontend might send: card_ids, ids, leads, or other variations
        card_ids = (
            payload.get("card_ids")
            or payload.get("ids")
            or payload.get("leads")
            or payload.get("cardIds")  # camelCase variant
            or []
        )
        
        # Ensure card_ids is a list
        if not isinstance(card_ids, list):
            if card_ids:
                card_ids = [card_ids]  # Convert single value to list
            else:
                card_ids = []
        
        limit = payload.get("limit")
        status_filter = payload.get("status", "assigned")
        
        print(f"[BLAST_ENDPOINT] Normalized card_ids: {card_ids} (type: {type(card_ids)}, length: {len(card_ids)})", flush=True)
        
        print(f"[BLAST_ENDPOINT] Extracted parameters:", flush=True)
        print(f"[BLAST_ENDPOINT]   limit: {limit}", flush=True)
        print(f"[BLAST_ENDPOINT]   status_filter: {status_filter}", flush=True)
        print(f"[BLAST_ENDPOINT]   card_ids: {card_ids} (type: {type(card_ids)}, length: {len(card_ids) if card_ids else 0})", flush=True)
        logger.info(f"[BLAST] limit={limit}, status_filter={status_filter}, card_ids={card_ids} (count: {len(card_ids) if card_ids else 0})")
        
        # #region agent log - Blast parameters
        try:
            import json as _json
            from datetime import datetime
            from pathlib import Path
            debug_log_path = Path(__file__).resolve().parent / ".cursor" / "debug.log"
            debug_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_log_path, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": "main.py:rep_blast:PARAMS",
                    "message": "Blast parameters extracted",
                    "data": {"limit": limit, "status_filter": status_filter, "card_ids": card_ids, "card_ids_count": len(card_ids) if card_ids else 0},
                    "hypothesisId": "B"
                }) + "\n")
        except Exception as e:
            logger.error(f"[DEBUG_LOG] Failed to write debug log: {e}")
        # #endregion
        
        print(f"[BLAST_ENDPOINT] Getting database connection...", flush=True)
        conn = get_conn()
        print(f"[BLAST_ENDPOINT] Database connection obtained", flush=True)
        
        # ✅ FIX 4: Allow admin blasting explicitly
        user_role = current_user.get("role")
        print(f"[BLAST_ENDPOINT] Checking user role: {user_role}", flush=True)
        
        if user_role == "admin":
            logger.info("🔥 Admin blast mode enabled")
            print(f"[BLAST_ENDPOINT] ✅ Admin user - full access granted", flush=True)
            print(f"[BLAST_ENDPOINT] User is admin - can blast any cards", flush=True)
            # Owner: can blast any cards
            if card_ids and isinstance(card_ids, list):
                # Use provided card IDs (owner has full access)
                print(f"[BLAST_ENDPOINT] Admin using provided card_ids: {card_ids}", flush=True)
                pass
            else:
                print(f"[BLAST_ENDPOINT] Admin - no card_ids provided, fetching all cards...", flush=True)
                # Get all cards (or filtered by query if needed)
                print(f"[BLAST_ENDPOINT] Building query for all cards...", flush=True)
                from backend.query import build_list_query
                query, params = build_list_query(where={}, limit=limit or 10000)
                print(f"[BLAST_ENDPOINT] Query built, executing...", flush=True)
                
                card_ids = []
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    print(f"[BLAST_ENDPOINT] Fetched {len(rows)} cards from database", flush=True)
                    for row in rows:
                        card_ids.append(row[0])  # row[0] is the id
                print(f"[BLAST_ENDPOINT] Admin - final card_ids count: {len(card_ids)}", flush=True)
        else:
            # Rep: STRICT enforcement - can ONLY blast assigned cards
            print(f"[BLAST_ENDPOINT] User is rep - enforcing assignment boundaries", flush=True)
            logger.info(f"[BLAST] Rep {current_user['id']} attempting blast - enforcing assignment boundaries")
            
            # Get all cards assigned to this rep
            print(f"[BLAST_ENDPOINT] Fetching assigned cards for rep {current_user['id']}...", flush=True)
            all_assigned = get_rep_assigned_cards(conn, current_user["id"])
            print(f"[BLAST_ENDPOINT] Found {len(all_assigned)} assigned cards", flush=True)
            assigned_ids = {c["id"] for c in all_assigned}
            print(f"[BLAST_ENDPOINT] Assigned card IDs: {list(assigned_ids)[:5]}..." if len(assigned_ids) > 5 else f"[BLAST_ENDPOINT] Assigned card IDs: {list(assigned_ids)}", flush=True)
            
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
        
        print(f"[BLAST_ENDPOINT] Final card_ids count: {len(card_ids) if card_ids else 0}", flush=True)
        if not card_ids:
            print(f"[BLAST_ENDPOINT] ❌ No cards to blast - returning error", flush=True)
            return {"ok": False, "error": "No cards to blast", "sent": 0, "skipped": 0}
        
        print(f"[BLAST_ENDPOINT] ✅ Card validation passed - {len(card_ids)} cards to blast", flush=True)
        
        # Run blast
        print(f"[BLAST_ENDPOINT] Starting blast execution...", flush=True)
        try:
            # All users (admin and reps) use system phone number via Messaging Service
            rep_user_id = None if current_user.get("role") == "admin" else current_user["id"]
            print(f"[BLAST_ENDPOINT] rep_user_id: {rep_user_id}", flush=True)
            
            # Validate phone number is configured (send directly from phone, not Messaging Service)
            import os
            print(f"[BLAST_ENDPOINT] Validating Twilio environment variables...", flush=True)
            phone_number = os.getenv("TWILIO_PHONE_NUMBER")
            if not phone_number:
                error_msg = "TWILIO_PHONE_NUMBER is not set in environment variables. Blast cannot proceed."
                print(f"[BLAST_ENDPOINT] ❌ {error_msg}", flush=True)
                logger.error(f"[BLAST] ❌ {error_msg}")
                return {"ok": False, "error": error_msg, "sent": 0, "skipped": 0}
            print(f"[BLAST_ENDPOINT] ✅ TWILIO_PHONE_NUMBER: {phone_number}", flush=True)
            
            # All users (admin and reps) use system Account SID and Auth Token (from env vars)
            # All messages sent directly from system phone number (not via Messaging Service to avoid filtering)
            account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            auth_token = os.getenv("TWILIO_AUTH_TOKEN")
            
            if not account_sid:
                error_msg = "TWILIO_ACCOUNT_SID is not set in environment variables. Blast cannot proceed."
                print(f"[BLAST_ENDPOINT] ❌ {error_msg}", flush=True)
                logger.error(f"[BLAST] ❌ {error_msg}")
                return {"ok": False, "error": error_msg, "sent": 0, "skipped": 0}
            print(f"[BLAST_ENDPOINT] ✅ TWILIO_ACCOUNT_SID: {account_sid[:10]}...", flush=True)
            
            if not auth_token:
                error_msg = "TWILIO_AUTH_TOKEN is not set in environment variables. Blast cannot proceed."
                print(f"[BLAST_ENDPOINT] ❌ {error_msg}", flush=True)
                logger.error(f"[BLAST] ❌ {error_msg}")
                return {"ok": False, "error": error_msg, "sent": 0, "skipped": 0}
            print(f"[BLAST_ENDPOINT] ✅ TWILIO_AUTH_TOKEN: {auth_token[:10]}...", flush=True)
            
            logger.info(f"[BLAST] User {current_user['id']} (role: {current_user.get('role')}) using system Account SID: {account_sid[:10]}...")
            logger.info(f"[BLAST] Phone Number: {phone_number}")
            logger.info(f"[BLAST] Sending directly from phone number (not Messaging Service) to avoid filtering")
            logger.info(f"[BLAST] Running blast for {len(card_ids)} cards, rep_user_id={rep_user_id}")
            print(f"[BLAST_ENDPOINT] ✅ All validations passed - calling run_blast_for_cards()", flush=True)
            
            # #region agent log - Before run_blast_for_cards
            try:
                import json as _json
                from datetime import datetime
                from pathlib import Path
                debug_log_path = Path(__file__).resolve().parent / ".cursor" / "debug.log"
                debug_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(debug_log_path, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "location": "main.py:rep_blast:BEFORE_RUN",
                        "message": "About to call run_blast_for_cards",
                        "data": {"card_ids_count": len(card_ids), "rep_user_id": rep_user_id, "has_account_sid": bool(account_sid), "has_auth_token": bool(auth_token), "has_phone_number": bool(phone_number)},
                        "hypothesisId": "C"
                    }) + "\n")
            except Exception as e:
                logger.error(f"[DEBUG_LOG] Failed to write debug log: {e}")
            # #endregion
            
            print(f"[BLAST_ENDPOINT] About to call run_blast_for_cards() with:", flush=True)
            print(f"[BLAST_ENDPOINT]   card_ids: {card_ids}", flush=True)
            print(f"[BLAST_ENDPOINT]   owner: {current_user['id']}", flush=True)
            print(f"[BLAST_ENDPOINT]   source: {'owner_ui' if current_user.get('role') == 'admin' else 'rep_ui'}", flush=True)
            print(f"[BLAST_ENDPOINT]   rep_user_id: {rep_user_id}", flush=True)
            print(f"[BLAST_ENDPOINT] Calling run_blast_for_cards() NOW...", flush=True)
            
            try:
                result = run_blast_for_cards(
                    conn=conn,
                    card_ids=card_ids,
                    limit=None,  # Already applied limit above if needed
                    owner=current_user["id"],
                    source="owner_ui" if current_user.get("role") == "admin" else "rep_ui",
                    rep_user_id=rep_user_id,
                )
                print(f"[BLAST_ENDPOINT] ✅ run_blast_for_cards() returned successfully", flush=True)
            except Exception as run_error:
                print("=" * 80, flush=True)
                print(f"[BLAST_ENDPOINT] ❌ EXCEPTION in run_blast_for_cards()", flush=True)
                print("=" * 80, flush=True)
                print(f"[BLAST_ENDPOINT] Error type: {type(run_error).__name__}", flush=True)
                print(f"[BLAST_ENDPOINT] Error message: {str(run_error)}", flush=True)
                import traceback
                print(f"[BLAST_ENDPOINT] Full traceback:", flush=True)
                traceback.print_exc()
                print("=" * 80, flush=True)
                raise
            
            logger.info(f"[BLAST] Blast completed: sent={result.get('sent', 0)}, skipped={result.get('skipped', 0)}")
            logger.info(f"[BLAST] Result details: {result}")
            print(f"[BLAST_ENDPOINT] Blast result: ok={result.get('ok')}, sent={result.get('sent', 0)}, skipped={result.get('skipped', 0)}", flush=True)
            
            # #region agent log - Blast result
            try:
                import json as _json
                from datetime import datetime
                from pathlib import Path
                debug_log_path = Path(__file__).resolve().parent / ".cursor" / "debug.log"
                debug_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(debug_log_path, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "location": "main.py:rep_blast:RESULT",
                        "message": "Blast completed successfully",
                        "data": {"ok": result.get('ok'), "sent": result.get('sent', 0), "skipped": result.get('skipped', 0), "results_count": len(result.get('results', []))},
                        "hypothesisId": "D"
                    }) + "\n")
            except Exception as e:
                logger.error(f"[DEBUG_LOG] Failed to write debug log: {e}")
            # #endregion
            
            return result
        except Exception as e:
            # #region agent log - Blast exception
            try:
                import json as _json
                from datetime import datetime
                import traceback
                from pathlib import Path
                debug_log_path = Path(__file__).resolve().parent / ".cursor" / "debug.log"
                debug_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(debug_log_path, "a") as f:
                    f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "location": "main.py:rep_blast:EXCEPTION",
                        "message": "Blast failed with exception",
                        "data": {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()},
                        "hypothesisId": "E"
                    }) + "\n")
            except Exception as log_err:
                logger.error(f"[DEBUG_LOG] Failed to write debug log: {log_err}")
            # #endregion
            
            # CRITICAL: Log exception immediately
            print("=" * 80, flush=True)
            print(f"[BLAST_ENDPOINT] ❌ EXCEPTION CAUGHT", flush=True)
            print(f"[BLAST_ENDPOINT] Error: {str(e)}", flush=True)
            print(f"[BLAST_ENDPOINT] Error type: {type(e).__name__}", flush=True)
            import traceback
            error_trace = traceback.format_exc()
            print(f"[BLAST_ENDPOINT] Full traceback:\n{error_trace}", flush=True)
            print("=" * 80, flush=True)
            
            # This should never be reached because we catch exceptions above
            logger.error(f"[BLAST] ❌ EXCEPTION in rep_blast: {e}")
            logger.error(f"[BLAST] Traceback:\n{error_trace}")
            raise HTTPException(status_code=500, detail=f"Blast failed: {str(e)}")
    except Exception as e:
        # Outer try block exception handler
        print("=" * 80, flush=True)
        print(f"[BLAST_ENDPOINT] ❌ OUTER EXCEPTION CAUGHT", flush=True)
        print(f"[BLAST_ENDPOINT] Error: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        print("=" * 80, flush=True)
        raise HTTPException(status_code=500, detail=f"Blast failed: {str(e)}")


@app.post("/rep/messages/send")
async def rep_send_message(
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    """Send a message to a specific card/phone. Owner can send to any, reps to their assigned cards."""
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REP_SEND_MESSAGE] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
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
        # All users (admin and reps) send from system phone via Messaging Service
        if current_user.get("role") == "admin":
            # Admin: use system Twilio
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
            # Rep: use rep messaging system (also uses system phone via Messaging Service)
            result = send_rep_message(conn, current_user["id"], card_id, message)
            return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.get("/rep/messages/{phone}")
async def rep_get_messages(
    phone: str,
    request: Request
):
    """Get conversation history for a phone number. Owner can see all, reps only their own."""
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REP_GET_MESSAGES] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
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
async def rep_get_stats(request: Request):
    """Get conversion metrics. Owner sees all stats, reps see only their own."""
    # Authenticate user manually
    try:
        current_user = await get_current_owner_or_rep(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REP_STATS] Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication required")
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
            
            # Get total cards assigned (all statuses)
            cur.execute("""
                SELECT COUNT(DISTINCT card_id)
                FROM card_assignments
                WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            total_assigned = row[0] if row else 0
            stats["total_assigned"] = total_assigned
            
            # Get total leads (assigned cards with inbound messages)
            cur.execute("""
                SELECT COUNT(DISTINCT c.card_id)
                FROM conversations c
                INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                WHERE ca.user_id = %s
                  AND c.card_id IS NOT NULL
                  AND c.last_inbound_at IS NOT NULL
            """, (user_id,))
            row = cur.fetchone()
            total_leads = row[0] if row else 0
            stats["total_leads"] = total_leads
            
            # Calculate response rate (leads / assigned)
            response_rate = (total_leads / total_assigned * 100) if total_assigned > 0 else 0
            stats["response_rate"] = round(response_rate, 1)
            
            # Calculate close rate (closed / assigned or closed / leads)
            close_rate_assigned = (stats["closed"] / total_assigned * 100) if total_assigned > 0 else 0
            close_rate_leads = (stats["closed"] / total_leads * 100) if total_leads > 0 else 0
            stats["close_rate_assigned"] = round(close_rate_assigned, 1)
            stats["close_rate_leads"] = round(close_rate_leads, 1)
            
            # Get total conversations (rep mode + assigned cards in AI mode)
            cur.execute("""
                SELECT COUNT(DISTINCT c.phone)
                FROM conversations c
                INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                WHERE ca.user_id = %s
                  AND c.card_id IS NOT NULL
            """, (user_id,))
            row = cur.fetchone()
            stats["total_conversations"] = row[0] if row else 0
            
            # Get active conversations (with recent activity in last 7 days)
            from datetime import datetime, timedelta
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            cur.execute("""
                SELECT COUNT(DISTINCT c.phone)
                FROM conversations c
                INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                WHERE ca.user_id = %s
                  AND c.card_id IS NOT NULL
                  AND (
                    c.last_inbound_at >= %s
                    OR c.last_outbound_at >= %s
                    OR c.updated_at >= %s
                  )
            """, (user_id, seven_days_ago, seven_days_ago, seven_days_ago))
            row = cur.fetchone()
            stats["active_conversations"] = row[0] if row else 0
            
            # Get messages sent count (outbound messages) - count from history JSONB
            cur.execute("""
                SELECT 
                    SUM(jsonb_array_length(COALESCE(c.history, '[]'::jsonb))) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM jsonb_array_elements(c.history) AS msg
                            WHERE msg->>'direction' = 'outbound'
                        )
                    )
                FROM conversations c
                INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                WHERE ca.user_id = %s
                  AND c.card_id IS NOT NULL
                  AND c.history IS NOT NULL
            """, (user_id,))
            row = cur.fetchone()
            # Alternative: count individual messages
            if row and row[0] is not None:
                stats["messages_sent"] = int(row[0])
            else:
                # Fallback: count by checking history array
                cur.execute("""
                    SELECT COUNT(*)
                    FROM conversations c
                    INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                    WHERE ca.user_id = %s
                      AND c.card_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM jsonb_array_elements(COALESCE(c.history, '[]'::jsonb)) AS msg
                          WHERE msg->>'direction' = 'outbound'
                      )
                """, (user_id,))
                row = cur.fetchone()
                stats["messages_sent"] = row[0] if row and row[0] else 0
            
            # Get messages received count (inbound messages) - count from history JSONB
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations c
                INNER JOIN card_assignments ca ON c.card_id = ca.card_id
                WHERE ca.user_id = %s
                  AND c.card_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(COALESCE(c.history, '[]'::jsonb)) AS msg
                      WHERE msg->>'direction' = 'inbound'
                  )
            """, (user_id,))
            row = cur.fetchone()
            stats["messages_received"] = row[0] if row and row[0] else 0
            
            # Log stats for debugging
            logger.info(f"[REP_STATS] Rep {user_id} stats: {stats}")
    
    # Ensure all expected keys exist (even if 0)
    default_stats = {
        "assigned": 0,
        "active": 0,
        "closed": 0,
        "lost": 0,
        "total_assigned": 0,
        "total_leads": 0,
        "response_rate": 0,
        "close_rate_assigned": 0,
        "close_rate_leads": 0,
        "total_conversations": 0,
        "active_conversations": 0,
        "messages_sent": 0,
        "messages_received": 0,
    }
    
    # Merge defaults with actual stats
    final_stats = {**default_stats, **stats}
    
    logger.info(f"[REP_STATS] Returning stats: {final_stats}")
    return {"ok": True, "stats": final_stats}

