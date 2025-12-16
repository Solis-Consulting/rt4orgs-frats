# Quick Start Guide - JSON-Native CRM

## Prerequisites

1. PostgreSQL database running
2. Python 3.8+ with dependencies installed
3. `DATABASE_URL` environment variable set

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Database URL

```bash
export DATABASE_URL=postgresql://user:pass@localhost:5432/rt4
```

### 3. Run Database Migration

```bash
psql $DATABASE_URL -f backend/db/schema.sql
```

This creates:
- `cards` table (JSONB storage)
- `card_relationships` table
- `card_id` column on `conversations` table

### 4. Start Backend Server

```bash
uvicorn main:app --reload
```

Server runs on: `http://127.0.0.1:8000`

API docs: `http://127.0.0.1:8000/docs`

## End-to-End Test

### Step 1: Create Sample Card

The `me.json` file is already created with a sample card.

### Step 2: Run Test Script

```bash
./test_end_to_end.sh
```

Or run manually:

### Step 2a: Upload Card

```bash
curl -X POST http://127.0.0.1:8000/cards/upload \
  -H "Content-Type: application/json" \
  -d @me.json
```

Expected response:
```json
{
  "ok": true,
  "stored": 1,
  "errors": 0,
  "cards": [...]
}
```

### Step 2b: Verify Card

```bash
curl http://127.0.0.1:8000/cards/alan_solis_elrod
```

### Step 2c: Send Message

```bash
curl -X POST http://127.0.0.1:8000/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "target": {
      "type": "contact",
      "id": "alan_solis_elrod"
    },
    "message_type": "initial_outreach"
  }'
```

### Step 2d: Verify Conversation Bridge

```sql
SELECT phone, card_id, state
FROM conversations
WHERE card_id = 'alan_solis_elrod';
```

## UI Access

### Start UI Server

```bash
cd ui
python -m http.server 5173
```

### Access Points

- **Card List**: http://localhost:5173/index.html (click "Cards" tab)
- **Upload Cards**: http://localhost:5173/upload.html
- **Card Detail**: http://localhost:5173/card.html?id=alan_solis_elrod

## Mental Model

```
JSON card (me.json)
 → POST /cards/upload
 → cards table (JSONB)
 → POST /messages/send (by card_id)
 → conversations table (bridged via card_id)
 → Markov intelligence (conversations.state)
```

**Key Separation:**
- `cards.sales_state` = Sales pipeline state (cold, qualified, negotiating, won, lost)
- `conversations.state` = Markov conversation state (pricing_question, buy_signal, etc.)

These are **orthogonal** - never conflate them.

## Next Steps

1. Upload more cards (person, fraternity, team, business)
2. Create entity relationships (fraternity → members)
3. Test group messaging (message fraternity → expands to all members)
4. Test query-based targeting (`{"type": "query", "where": {...}}`)

## Troubleshooting

### Import Errors

If you see import errors, make sure you're running from the repo root and `backend/` is in Python path (handled automatically by `main.py`).

### Database Connection

Verify `DATABASE_URL` is set correctly:
```bash
echo $DATABASE_URL
```

### Migration Errors

If migration fails, check:
1. Database exists
2. User has CREATE TABLE permissions
3. Tables don't already exist (safe to re-run)

### API Not Responding

Check server logs:
```bash
uvicorn main:app --reload --log-level debug
```

