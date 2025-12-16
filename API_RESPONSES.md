# API Response Formats

## POST /cards/upload

### Request
```bash
curl -X POST http://127.0.0.1:8000/cards/upload \
  -H "Content-Type: application/json" \
  -d @me.json
```

### Response (Success)
```json
{
  "ok": true,
  "stored": 1,
  "errors": 0,
  "cards": [
    {
      "id": "alan_solis_elrod",
      "type": "person",
      "card_data": {
        "name": "Alan Solis Elrod",
        "role": "Founder",
        "phone": "+19195550123",
        "email": "alan@solisconsultinggroup.com",
        "tags": ["founder", "operator"],
        "metadata": {
          "company": "Solis Consulting",
          "product": "RT4Orgs"
        }
      },
      "sales_state": "qualified",
      "owner": null,
      "created_at": "2024-12-14T22:30:00.000000",
      "updated_at": "2024-12-14T22:30:00.000000"
    }
  ],
  "error_details": []
}
```

### Response (With Errors)
```json
{
  "ok": false,
  "stored": 0,
  "errors": 1,
  "cards": [],
  "error_details": [
    {
      "index": 0,
      "card": {...},
      "error": "Person card missing required field: phone"
    }
  ]
}
```

## GET /cards/{card_id}

### Request
```bash
curl http://127.0.0.1:8000/cards/alan_solis_elrod
```

### Response
```json
{
  "id": "alan_solis_elrod",
  "type": "person",
  "card_data": {...},
  "sales_state": "qualified",
  "owner": null,
  "created_at": "2024-12-14T22:30:00.000000",
  "updated_at": "2024-12-14T22:30:00.000000",
  "relationships": [],
  "conversations": [
    {
      "phone": "9195550123",
      "state": "awaiting_response",
      "last_outbound_at": "2024-12-14T22:35:00.000000",
      "last_inbound_at": null
    }
  ]
}
```

## GET /cards

### Request
```bash
curl "http://127.0.0.1:8000/cards?type=person&sales_state=qualified&limit=100"
```

### Response
```json
{
  "cards": [
    {
      "id": "alan_solis_elrod",
      "type": "person",
      "card_data": {...},
      "sales_state": "qualified",
      "owner": null,
      "created_at": "2024-12-14T22:30:00.000000",
      "updated_at": "2024-12-14T22:30:00.000000"
    }
  ],
  "count": 1
}
```

## POST /messages/send

### Request
```bash
curl -X POST http://127.0.0.1:8000/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "target": {
      "type": "contact",
      "id": "alan_solis_elrod"
    },
    "message_type": "initial_outreach",
    "owner": "david"
  }'
```

### Response (Success)
```json
{
  "ok": true,
  "target": {
    "type": "contact",
    "id": "alan_solis_elrod"
  },
  "contacts_resolved": 1,
  "messages_sent": 1,
  "results": [
    {
      "card_id": "alan_solis_elrod",
      "phone": "+19195550123",
      "status": "sent",
      "result": {
        "ok": true
      }
    }
  ]
}
```

### Target Types

#### Single Contact
```json
{
  "target": {
    "type": "contact",
    "id": "alan_solis_elrod"
  }
}
```

#### Entity (Fraternity)
```json
{
  "target": {
    "type": "entity",
    "entity_type": "fraternity",
    "id": "sigchi_alpha"
  }
}
```

#### Query Filter
```json
{
  "target": {
    "type": "query",
    "where": {
      "fraternity": "SNU",
      "sales_state": "interested"
    }
  }
}
```

## POST /events/outbound

### Request
```json
{
  "phone": "+19195550123",
  "card_id": "alan_solis_elrod",
  "owner": "david",
  "source_batch_id": "test_2024_12_14"
}
```

### Response
```json
{
  "ok": true
}
```

This creates/updates a conversation row with:
- `phone` = normalized phone number
- `card_id` = "alan_solis_elrod" (bridged!)
- `state` = "awaiting_response"
- `owner` = "david"

