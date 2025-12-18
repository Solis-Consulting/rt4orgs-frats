#!/bin/bash
# Test script to verify backend blast endpoint works
# Usage: ./test_blast_curl.sh [CARD_ID]

CARD_ID="${1:-test_card_id}"
BACKEND_URL="https://rt4orgs-frats-production.up.railway.app"
API_TOKEN="Da3XWjpeCVwA5o3f8Vmk3Jh0xuPsVA9r7GCZFdyjPto"

echo "=========================================="
echo "Testing /rep/blast endpoint"
echo "=========================================="
echo "Backend: $BACKEND_URL"
echo "Card ID: $CARD_ID"
echo ""

echo "Sending POST request..."
curl -v -X POST "${BACKEND_URL}/rep/blast" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -d "{\"card_ids\":[\"${CARD_ID}\"]}" \
  2>&1 | tee /tmp/blast_curl_response.txt

echo ""
echo "=========================================="
echo "Response saved to /tmp/blast_curl_response.txt"
echo "=========================================="
echo ""
echo "Check Railway logs for:"
echo "  - POST /rep/blast"
echo "  - 🔥🔥🔥 ENTERED /rep/blast HANDLER 🔥🔥🔥"
echo ""
