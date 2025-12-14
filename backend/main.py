from fastapi import FastAPI
from datetime import datetime
import psycopg2
import os

app = FastAPI()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True


@app.post("/events/outbound")
async def outbound(event: dict):
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

