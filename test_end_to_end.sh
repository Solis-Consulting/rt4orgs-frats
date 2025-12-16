#!/bin/bash
# End-to-end test script for JSON-native CRM

set -e

echo "=========================================="
echo "JSON-Native CRM End-to-End Test"
echo "=========================================="
echo ""

# Check DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not set"
    echo ""
    echo "Please set it first:"
    echo "  export DATABASE_URL=postgresql://user:pass@localhost:5432/rt4"
    echo ""
    exit 1
fi

echo "✓ DATABASE_URL is set"
echo ""

# Step 1: Run migration
echo "Step 1: Running database migration..."
psql "$DATABASE_URL" -f backend/db/schema.sql
echo "✓ Migration complete"
echo ""

# Step 2: Upload card
echo "Step 2: Uploading card..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/cards/upload \
  -H "Content-Type: application/json" \
  -d @me.json)

echo "Response: $RESPONSE"
echo ""

# Check if upload succeeded
if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo "✓ Card uploaded successfully"
else
    echo "❌ Card upload failed"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi
echo ""

# Step 3: Verify card exists
echo "Step 3: Verifying card exists..."
CARD_RESPONSE=$(curl -s http://127.0.0.1:8000/cards/alan_solis_elrod)
echo "Card data:"
echo "$CARD_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CARD_RESPONSE"
echo ""

# Step 4: Send message
echo "Step 4: Sending message to card..."
MESSAGE_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "target": {
      "type": "contact",
      "id": "alan_solis_elrod"
    },
    "message_type": "initial_outreach"
  }')

echo "Message response:"
echo "$MESSAGE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$MESSAGE_RESPONSE"
echo ""

# Step 5: Verify conversation bridge
echo "Step 5: Verifying conversation bridge..."
psql "$DATABASE_URL" -c "SELECT phone, card_id, state FROM conversations WHERE card_id = 'alan_solis_elrod';"
echo ""

echo "=========================================="
echo "✅ End-to-end test complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. View card in UI: http://localhost:5173/index.html (Cards tab)"
echo "2. View card detail: http://localhost:5173/card.html?id=alan_solis_elrod"
echo ""

