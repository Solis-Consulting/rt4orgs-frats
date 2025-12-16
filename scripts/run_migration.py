#!/usr/bin/env python3
"""
Run database migration to create cards table and related schema.
Can be run manually or called from the app.
"""

import os
import sys
import psycopg2
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_migration():
    """Run the database migration from backend/db/schema.sql"""
    
    # Get DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable is not set")
        print("\nPlease set it first:")
        print("  export DATABASE_URL=postgresql://user:pass@host:5432/dbname")
        return False
    
    # Read schema file
    schema_file = PROJECT_ROOT / "backend" / "db" / "schema.sql"
    if not schema_file.exists():
        print(f"❌ Schema file not found: {schema_file}")
        return False
    
    print("📄 Reading schema file...")
    with open(schema_file, 'r') as f:
        schema_sql = f.read()
    
    # Connect and run migration
    print("🔌 Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        
        with conn.cursor() as cur:
            print("🚀 Running migration...")
            cur.execute(schema_sql)
            print("✅ Migration completed successfully!")
            
            # Verify tables were created
            cur.execute("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                AND tablename IN ('cards', 'card_relationships')
                ORDER BY tablename;
            """)
            tables = cur.fetchall()
            
            if tables:
                print("\n✅ Created tables:")
                for table in tables:
                    print(f"   - {table[0]}")
            else:
                print("\n⚠️  Warning: Tables not found after migration")
        
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
