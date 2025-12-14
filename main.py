from fastapi import FastAPI
from datetime import datetime
import psycopg2
import os

app = FastAPI()

_conn = None

def get_conn():
    global _conn
    if _conn is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        _conn = psycopg2.connect(database_url)
        _conn.autocommit = True
    return _conn


@app.post("/events/outbound")
async def outbound(event: dict):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO conversations
            (phone, contact_id, owner, state, source_batch_id, last_outbound_at)
            VALUES (%s, %s, %s, 'awaiting_response', %s, %s)
            ON CONFLICT (phone)
            DO UPDATE SET
              last_outbound_at = EXCLUDED.last_outbound_at,
              owner = EXCLUDED.owner,
              state = 'awaiting_response',
              source_batch_id = EXCLUDED.source_batch_id;
        """, (
            event["phone"],
            event.get("contact_id"),
            event["owner"],
            event.get("source_batch_id"),
            datetime.utcnow()
        ))
    return {"ok": True}


@app.post("/events/inbound")
async def inbound(event: dict):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversations
            SET last_inbound_at = %s,
                state = 'replied'
            WHERE phone = %s;
        """, (
            datetime.utcnow(),
            event["phone"]
        ))
    return {"ok": True}

