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
    
    # Read schema file - try multiple possible paths
    # In Railway, the working directory is /app, and files are relative to project root
    possible_paths = [
        Path(__file__).resolve().parent / "schema.sql",  # Relative to migrate.py (most reliable)
        Path("/app/backend/db/schema.sql"),  # Absolute Railway path
        Path("backend/db/schema.sql"),  # Relative to current working directory
        Path("./backend/db/schema.sql"),  # Relative with explicit current dir
    ]
    
    # Also try resolving from main.py location (project root)
    try:
        import sys
        # Find project root by looking for main.py in parent directories
        current = Path(__file__).resolve().parent
        for _ in range(5):  # Check up to 5 levels up
            if (current / "main.py").exists():
                possible_paths.insert(0, current / "backend" / "db" / "schema.sql")
                print(f"📁 Found project root: {current}")
                break
            current = current.parent
    except Exception as root_e:
        print(f"⚠️  Could not find project root: {root_e}")
    
    schema_file = None
    checked_paths = []
    for path in possible_paths:
        checked_paths.append(str(path))
        abs_path = path.resolve() if not path.is_absolute() else path
        if abs_path.exists():
            schema_file = abs_path
            print(f"✅ Found schema file at: {schema_file}")
            break
    
    # #region agent log - Schema path check
    try:
        import time
        with open(_log_file, "a") as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "timestamp": int(time.time() * 1000),
                "location": f"{__file__}:SCHEMA_PATH_CHECK",
                "message": "Checking schema file paths",
                "data": {
                    "checked_paths": checked_paths,
                    "found_path": str(schema_file) if schema_file else None,
                    "__file__": __file__,
                    "cwd": str(Path.cwd()),
                    "migrate_file_dir": str(Path(__file__).resolve().parent)
                },
                "hypothesisId": "D"
            }) + "\n")
    except:
        pass
    # #endregion
    
    if not schema_file:
        all_paths_str = "\n  - ".join(checked_paths)
        print(f"❌ Schema file not found. Checked paths:")
        for p in checked_paths:
            print(f"  - {p} (exists: {Path(p).exists()})")
        print(f"📁 Current working directory: {Path.cwd()}")
        print(f"📁 __file__ location: {__file__}")
        print(f"📁 migrate.py directory: {Path(__file__).resolve().parent}")
        return False, f"Schema file not found. Checked {len(checked_paths)} paths. Current dir: {Path.cwd()}"
    
    print(f"📁 Using schema path: {schema_file}")
    print(f"📁 Schema file exists: {schema_file.exists()}")
    
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
        
        # Check which tables exist
        print("🔍 Checking existing tables...")
        cards_exists = check_table_exists(conn, "cards")
        markov_responses_exists = check_table_exists(conn, "markov_responses")
        users_exists = check_table_exists(conn, "users")
        
        # #region agent log - Table existence check
        try:
            import time
            with open(_log_file, "a") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "timestamp": int(time.time() * 1000),
                    "location": f"{__file__}:TABLE_CHECK",
                    "message": "Checked table existence",
                    "data": {"cards_exists": cards_exists, "markov_responses_exists": markov_responses_exists},
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print(f"📊 Cards table exists: {cards_exists}")
        print(f"📊 Markov responses table exists: {markov_responses_exists}")
        print(f"📊 Users table exists: {users_exists}")
        
        # Check if all required tables exist
        required_tables_exist = cards_exists and markov_responses_exists
        
        # Run main schema migration if needed
        if not required_tables_exist:
            # Some tables are missing - run migration (schema.sql uses IF NOT EXISTS, so safe to run)
            if cards_exists and not markov_responses_exists:
                print("🔧 Missing markov_responses table - running migration to add it...")
            elif not cards_exists:
                print("🔧 Missing tables - running full migration...")
            
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
        
        # Run additional migrations (always check, migrations use IF NOT EXISTS)
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        if migrations_dir.exists():
            migration_files = sorted([f for f in migrations_dir.glob("*.sql")])
            for migration_file in migration_files:
                print(f"🔧 Running additional migration: {migration_file.name}")
                try:
                    with open(migration_file, 'r') as f:
                        migration_sql = f.read()
                    with conn.cursor() as cur:
                        cur.execute(migration_sql)
                    print(f"✅ Migration {migration_file.name} executed")
                except Exception as e:
                    print(f"⚠️  Migration {migration_file.name} failed: {e}")
                    # Continue with other migrations
        else:
            print("📁 No migrations directory found, skipping additional migrations")
        
        # Check if we should skip (all tables exist)
        if required_tables_exist and users_exists:
            print("⏭️  Core tables exist, migrations completed")
        else:
            print("✅ Migrations completed")
        
        # Verify tables were created
        print("🔍 Verifying tables were created...")
        cards_exists_after = check_table_exists(conn, "cards")
        relationships_exists = check_table_exists(conn, "card_relationships")
        markov_responses_exists_after = check_table_exists(conn, "markov_responses")
        users_exists_after = check_table_exists(conn, "users")
        card_assignments_exists = check_table_exists(conn, "card_assignments")
        
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
                    "data": {
                        "cards_exists": cards_exists_after,
                        "relationships_exists": relationships_exists,
                        "markov_responses_exists": markov_responses_exists_after
                    },
                    "hypothesisId": "C"
                }) + "\n")
        except:
            pass
        # #endregion
        
        print(f"📊 Cards table exists after: {cards_exists_after}")
        print(f"📊 Relationships table exists: {relationships_exists}")
        print(f"📊 Markov responses table exists: {markov_responses_exists_after}")
        print(f"📊 Users table exists: {users_exists_after}")
        print(f"📊 Card assignments table exists: {card_assignments_exists}")
        
        conn.close()
        
        # Check if all critical tables exist
        if cards_exists_after and markov_responses_exists_after:
            print("✅ Migration completed successfully")
            return True, "Migration completed successfully: created required tables"
        elif cards_exists_after:
            print("⚠️  Migration completed (partial - markov_responses may still be missing)")
            return True, "Migration completed: created cards table"
        else:
            print("❌ Migration executed but critical tables were not created")
            return False, "Migration executed but critical tables were not created"
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {str(e)}")
        return False, f"Database error: {str(e)}"
    except Exception as e:
        print(f"❌ Migration error: {str(e)}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return False, f"Migration error: {str(e)}"
