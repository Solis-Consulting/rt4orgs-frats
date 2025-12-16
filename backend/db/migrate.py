"""
Database migration utility for Railway deployments.
Automatically creates tables on app startup.
"""

import os
import psycopg2
import json
from pathlib import Path
from typing import Tuple, Optional

# #region agent log - Log file path
_log_file = Path(__file__).resolve().parent.parent.parent / ".cursor" / "debug.log"
# #endregion


def check_table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
            """, (table_name,))
            return cur.fetchone()[0]
    except Exception:
        return False


def run_migration() -> Tuple[bool, Optional[str]]:
    """
    Run the database migration from backend/db/schema.sql.
    
    Returns:
        Tuple of (success: bool, message: str | None)
        If success is False, message contains error details.
    """
    # #region agent log - Migration function entry
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:MIGRATION_ENTRY",
                "message": "Migration function called",
                "data": {},
                "hypothesisId": "C"
            }) + "\n")
    except:
        pass
    # #endregion
    
    print("🚀 MIGRATION STARTED")
    
    # Get DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    
    # #region agent log - DATABASE_URL check
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:DATABASE_URL_CHECK",
                "message": "Checking DATABASE_URL",
                "data": {"present": bool(database_url), "length": len(database_url) if database_url else 0},
                "hypothesisId": "E"
            }) + "\n")
    except:
        pass
    # #endregion
    
    print(f"📋 DATABASE_URL present: {bool(database_url)}")
    if not database_url:
        return False, "DATABASE_URL environment variable is not set"
    
    # Read schema file - use absolute path resolution
    # In Railway, files are at /app, so we need to resolve from the module location
    schema_file = Path(__file__).resolve().parent / "schema.sql"
    
    # #region agent log - Schema path check
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:SCHEMA_PATH_CHECK",
                "message": "Checking schema file path",
                "data": {"path": str(schema_file), "exists": schema_file.exists(), "__file__": __file__},
                "hypothesisId": "D"
            }) + "\n")
    except:
        pass
    # #endregion
    
    print(f"📁 Schema path: {schema_file}")
    print(f"📁 Schema file exists: {schema_file.exists()}")
    
    if not schema_file.exists():
        # Try alternative path (in case we're running from different location)
        alt_path = Path("/app/backend/db/schema.sql")
        
        # #region agent log - Alternative path check
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:ALT_PATH_CHECK",
                    "message": "Checking alternative schema path",
                    "data": {"alt_path": str(alt_path), "exists": alt_path.exists()},
                    "hypothesisId": "D"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print(f"📁 Trying alternative path: {alt_path}")
        print(f"📁 Alternative exists: {alt_path.exists()}")
        if alt_path.exists():
            schema_file = alt_path
        else:
            return False, f"Schema file not found at {schema_file} or {alt_path}"
    
    try:
        print("📖 Reading schema file...")
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        print(f"✅ Schema file read successfully ({len(schema_sql)} bytes)")
    except Exception as e:
        print(f"❌ Failed to read schema file: {str(e)}")
        return False, f"Failed to read schema file: {str(e)}"
    
    # Connect and run migration
    try:
        # #region agent log - Before DB connection
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:BEFORE_DB_CONNECT",
                    "message": "About to connect to database",
                    "data": {"database_url_present": bool(database_url)},
                    "hypothesisId": "E"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        
        # #region agent log - After DB connection
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:AFTER_DB_CONNECT",
                    "message": "Database connection established",
                    "data": {"connection_status": "success"},
                    "hypothesisId": "E"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print("✅ Database connection established")
        
        # Check if cards table already exists
        print("🔍 Checking if cards table exists...")
        cards_exists = check_table_exists(conn, "cards")
        
        # #region agent log - Table existence check
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:TABLE_CHECK",
                    "message": "Checked if cards table exists",
                    "data": {"cards_exists": cards_exists},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print(f"📊 Cards table exists: {cards_exists}")
        
        if cards_exists:
            # Tables already exist, skip migration
            print("⏭️  Migration skipped: tables already exist")
            conn.close()
            return True, "Migration skipped: tables already exist"
        
        # Run migration
        print("🚀 Executing migration SQL...")
        
        # #region agent log - Before SQL execution
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:BEFORE_SQL_EXEC",
                    "message": "About to execute migration SQL",
                    "data": {"sql_length": len(schema_sql)},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        
        # #region agent log - After SQL execution
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:AFTER_SQL_EXEC",
                    "message": "Migration SQL executed",
                    "data": {"status": "success"},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print("✅ Migration SQL executed")
        
        # Verify tables were created
        print("🔍 Verifying tables were created...")
        cards_exists_after = check_table_exists(conn, "cards")
        relationships_exists = check_table_exists(conn, "card_relationships")
        
        # #region agent log - Table verification
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:TABLE_VERIFICATION",
                    "message": "Verified tables after migration",
                    "data": {"cards_exists": cards_exists_after, "relationships_exists": relationships_exists},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print(f"📊 Cards table exists after: {cards_exists_after}")
        print(f"📊 Relationships table exists: {relationships_exists}")
        
        conn.close()
        
        if cards_exists_after and relationships_exists:
            print("✅ Migration completed successfully")
            return True, "Migration completed successfully: created cards and card_relationships tables"
        elif cards_exists_after:
            print("⚠️  Migration completed (partial)")
            return True, "Migration completed: created cards table (card_relationships may already exist)"
        else:
            print("❌ Migration executed but tables were not created")
            return False, "Migration executed but tables were not created"
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {str(e)}")
        return False, f"Database error: {str(e)}"
    except Exception as e:
        print(f"❌ Migration error: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False, f"Migration error: {str(e)}"
