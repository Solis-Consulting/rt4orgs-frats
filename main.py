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
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Now import local modules (using proper package paths)
from intelligence.handler import handle_inbound
from intelligence.utils import normalize_phone

from backend.cards import (
    validate_card_schema,
    normalize_card,
    store_card,
    get_card,
    get_card_relationships
)
from backend.query import build_list_query
from backend.resolve import resolve_target, extract_phones_from_cards
from backend.webhook_config import WEBHOOK_CONFIG, WebhookConfig

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        
        # Auto-create conversation if it doesn't exist
        if not row:
            # Create new conversation with initial state
            try:
                cur.execute("""
                    INSERT INTO conversations
                    (phone, state, last_inbound_at, history)
                    VALUES (%s, 'initial_outreach', %s, %s::jsonb)
                    ON CONFLICT (phone) DO NOTHING
                    RETURNING phone, state, COALESCE(history::text, '[]') as history;
                """, (phone, datetime.utcnow(), json.dumps([])))
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
                    (phone, state, last_inbound_at)
                    VALUES (%s, 'initial_outreach', %s)
                    ON CONFLICT (phone) DO NOTHING
                    RETURNING phone, state;
                """, (phone, datetime.utcnow()))
                row = cur.fetchone()
                # If still no row (conflict), fetch it
                if not row:
                    cur.execute("""
                        SELECT phone, state
                        FROM conversations
                        WHERE phone = %s;
                    """, (phone,))
                    row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=500, detail=f"Failed to create or fetch conversation for phone: {phone}")
        
        # Build conversation_row dict
        conversation_row = {
            "phone": row[0],
            "state": row[1],
            "history": json.loads(row[2]) if len(row) > 2 and row[2] else [],
        }
        
        # Call intelligence handler
        result = handle_inbound(conversation_row, inbound_text, intent)
        
        # Update conversations table with new state
        # Try to update history if column exists
        try:
            cur.execute("""
                UPDATE conversations
                SET state = %s,
                    last_inbound_at = %s,
                    history = %s::jsonb
                WHERE phone = %s;
            """, (
                result["next_state"],
                datetime.utcnow(),
                json.dumps(result["updated_history"]),
                phone,
            ))
        except psycopg2.ProgrammingError:
            # History column doesn't exist, update without it
            cur.execute("""
                UPDATE conversations
                SET state = %s,
                    last_inbound_at = %s
                WHERE phone = %s;
            """, (
                result["next_state"],
                datetime.utcnow(),
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
    # Check if webhook is enabled
    if not WEBHOOK_CONFIG.enabled:
        return PlainTextResponse("Webhook disabled", status_code=200)
    
    # Parse form data
    payload = await request.form()
    
    # Log payload if enabled
    if WEBHOOK_CONFIG.log_payloads:
        print("TWILIO PAYLOAD:", dict(payload))
    
    # Handle dry_run mode
    if WEBHOOK_CONFIG.mode == "dry_run":
        return PlainTextResponse("Dry run OK", status_code=200)
    
    # Handle paused mode
    if WEBHOOK_CONFIG.mode == "paused":
        return PlainTextResponse("Webhook paused", status_code=200)
    
    # Normal processing (mode == "prod")
    try:
        From = payload.get("From", "")
        Body = payload.get("Body", "")
        
        if not From:
            return PlainTextResponse("Missing From field", status_code=400)
        
        # Normalize phone number from Twilio (E.164 format)
        normalized_phone = normalize_phone(From)
        
        # Prepare event payload for inbound_intelligent
        event = {
            "phone": normalized_phone,
            "text": Body,
            "body": Body,
            "intent": {}  # Empty intent - can be enhanced with LLM classification later
        }
        
        # Call the intelligence handler directly (no HTTP overhead)
        result = await inbound_intelligent(event)
        return "ok"
    except Exception as e:
        # Log error but return ok to Twilio (prevents retries on transient errors)
        # In production, you might want to log this to a monitoring service
        print(f"Error processing Twilio webhook: {e}")
        return "ok"


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
# Admin Blast Endpoint
# ============================================================================

@app.post("/admin/blast")
async def trigger_blast(request: Request, payload: Dict[str, Any] = Body(...)):
    """
    Trigger outbound blast to unblasted contacts.
    
    Payload:
    {
      "limit": 25,  # Optional: max messages to send
      "owner": "system",  # Optional: owner name
      "source_batch_id": "custom_id"  # Optional: batch tracking ID
    }
    """
    # #region agent log - API endpoint entry
    _log_file = Path(__file__).resolve().parent / ".cursor" / "debug.log"
    try:
        import json as _json
        from datetime import datetime
        with open(_log_file, "a") as f:
            f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "location": f"{__file__}:API_ENTRY",
                "message": "Blast API endpoint called",
                "data": {"payload": payload},
                "hypothesisId": "D"
            }) + "\n")
    except:
        pass
    # #endregion
    
    # Get base URL from request
    base_url = str(request.base_url).rstrip('/')
    
    # Extract parameters
    limit = payload.get("limit")
    owner = payload.get("owner", "system")
    source_batch_id = payload.get("source_batch_id")
    
    # Run blast (auto_confirm=True for API use)
    try:
        # #region agent log - Before calling run_blast
        _log_file = Path(__file__).resolve().parent / ".cursor" / "debug.log"
        try:
            import json as _json
            from datetime import datetime
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": f"{__file__}:BEFORE_RUN_BLAST",
                    "message": "About to call run_blast",
                    "data": {"limit": limit, "owner": owner, "base_url": base_url},
                    "hypothesisId": "D"
                }) + "\n")
        except:
            pass
        # #endregion
        
        # Lazy import to avoid startup failures
        blast_func = _get_run_blast()
        result = blast_func(
            limit=limit,
            auto_confirm=True,
            base_url=base_url,
            owner=owner,
            source_batch_id=source_batch_id
        )
        
        # #region agent log - After calling run_blast
        try:
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": f"{__file__}:AFTER_RUN_BLAST",
                    "message": "run_blast returned",
                    "data": {"result_ok": result.get("ok") if isinstance(result, dict) else None},
                    "hypothesisId": "D"
                }) + "\n")
        except:
            pass
        # #endregion
        
        return result
    except Exception as e:
        # #region agent log - Exception in blast
        try:
            with open(_log_file, "a") as f:
                f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "location": f"{__file__}:BLAST_EXCEPTION",
                    "message": "Exception in run_blast",
                    "data": {"error": str(e), "error_type": e.__class__.__name__},
                    "hypothesisId": "D"
                }) + "\n")
        except:
            pass
        # #endregion
        raise HTTPException(status_code=500, detail=f"Blast failed: {str(e)}")


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
    
    # Get linked conversations
    with conn.cursor() as cur:
        cur.execute("""
            SELECT phone, state, last_outbound_at, last_inbound_at
            FROM conversations
            WHERE card_id = %s
            ORDER BY last_outbound_at DESC NULLS LAST;
        """, (card_id,))
        
        conversations = []
        for row in cur.fetchall():
            conversations.append({
                "phone": row[0],
                "state": row[1],
                "last_outbound_at": row[2].isoformat() if row[2] else None,
                "last_inbound_at": row[3].isoformat() if row[3] else None,
            })
        card["conversations"] = conversations
    
    return card


@app.get("/cards")
async def list_cards(
    type: Optional[str] = Query(None, description="Filter by card type"),
    sales_state: Optional[str] = Query(None, description="Filter by sales state"),
    owner: Optional[str] = Query(None, description="Filter by owner"),
    where: Optional[str] = Query(None, description="JSON where clause"),
    limit: Optional[int] = Query(100, description="Limit results"),
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

