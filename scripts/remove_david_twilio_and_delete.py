#!/usr/bin/env python3
"""
Script to remove Twilio config from david, regenerate API token, and optionally delete david user.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from backend.auth import (
    get_user, clear_twilio_config, regenerate_api_token, delete_user
)

def get_conn():
    """Get database connection from DATABASE_URL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    return psycopg2.connect(database_url)

def main():
    """Main execution."""
    print("=" * 80)
    print("REMOVE DAVID TWILIO CONFIG AND DELETE USER")
    print("=" * 80)
    print()
    
    conn = get_conn()
    
    user_id = "david"
    
    # Check if user exists
    user = get_user(conn, user_id)
    if not user:
        print(f"❌ User '{user_id}' not found")
        return
    
    print(f"Found user: {user['username']} (ID: {user['id']}, Role: {user['role']})")
    print(f"Current Twilio Phone: {user.get('twilio_phone_number') or 'None'}")
    print(f"Current Twilio Account SID: {user.get('twilio_account_sid') or 'None'}")
    print()
    
    # Step 1: Clear Twilio config
    print("Step 1: Clearing Twilio configuration...")
    try:
        success = clear_twilio_config(conn, user_id)
        if success:
            print("✅ Twilio configuration cleared (phone, account_sid, auth_token set to NULL)")
        else:
            print("⚠️ No rows updated (user may not exist)")
    except Exception as e:
        print(f"❌ Error clearing Twilio config: {e}")
        conn.rollback()
        return
    
    # Step 2: Regenerate API token
    print()
    print("Step 2: Regenerating API token...")
    try:
        new_token = regenerate_api_token(conn, user_id)
        if new_token:
            print("✅ New API token generated")
            print(f"   NEW API TOKEN: {new_token}")
            print("   ⚠️  SAVE THIS TOKEN - IT WILL NOT BE SHOWN AGAIN")
        else:
            print("⚠️ Failed to regenerate token (user may not exist)")
    except Exception as e:
        print(f"❌ Error regenerating token: {e}")
        conn.rollback()
        return
    
    # Step 3: Delete user
    print()
    confirm = input("Step 3: Delete user 'david'? This will also delete all card assignments. (yes/no): ").strip().lower()
    if confirm == "yes":
        try:
            success = delete_user(conn, user_id)
            if success:
                print("✅ User 'david' deleted successfully")
                print("   All card assignments for this user have also been deleted")
            else:
                print("⚠️ User not found or already deleted")
        except Exception as e:
            print(f"❌ Error deleting user: {e}")
            conn.rollback()
            return
    else:
        print("⏭️  Skipping user deletion")
    
    # Commit all changes
    try:
        conn.commit()
        print()
        print("=" * 80)
        print("✅ ALL OPERATIONS COMPLETED SUCCESSFULLY")
        print("=" * 80)
        if new_token and confirm != "yes":
            print(f"NEW API TOKEN FOR DAVID: {new_token}")
            print("⚠️  SAVE THIS TOKEN - IT WILL NOT BE SHOWN AGAIN")
    except Exception as e:
        print(f"❌ Error committing changes: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
