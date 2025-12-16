# JSON-Native CRM System

This document describes the JSON-native CRM system that stores contact cards and entity cards as first-class objects.

## Overview

The system implements a **JSON-native CRM** where:
- Contacts are **nodes** (person cards)
- Entities (fraternities, teams, businesses) are **first-class objects**
- Sales states are **attributes** on cards (separate from Markov conversation states)
- Messaging targets are **resolvable sets** (contact, entity, or query)

## Database Schema

Run the migration to create the necessary tables:

```bash
psql $DATABASE_URL -f backend/db/schema.sql
```

This creates:
- `cards` table - stores card data as JSONB
- `card_relationships` table - stores relationships between cards
- `card_id` column on `conversations` table - bridges conversations to cards

## Card Types

### Person Card
```json
{
  "type": "person",
  "name": "Aidan Scheible",
  "role": "President",
  "phone": "+12489962425",
  "email": "scheibae@miamioh.edu",
  "fraternity": "SigChi",
  "chapter": "Alpha",
  "tags": ["fraternity", "rush", "decision_maker"],
  "sales_state": "cold",
  "metadata": {
    "insta": "",
    "other_social": ""
  }
}
```

### Fraternity Card
```json
{
  "id": "sigchi_alpha",
  "type": "fraternity",
  "name": "Sigma Chi – Alpha Chapter",
  "school": "Miami University",
  "members": ["aidan_scheible_sigchi_alpha"],
  "sales_state": "active_outreach",
  "owner": "david"
}
```

### Team Card
```json
{
  "id": "rt4orgs_sales_team",
  "type": "team",
  "members": ["david", "kashni", "edward"]
}
```

### Business Card
```json
{
  "id": "acme_roofing",
  "type": "business",
  "industry": "roofing",
  "contacts": ["john_capone_phi_gamma_epsilon"],
  "sales_state": "qualified"
}
```

## API Endpoints

### Upload Cards
```bash
POST /cards/upload
Content-Type: application/json

[
  {
    "type": "person",
    "name": "John Doe",
    "phone": "+1234567890",
    ...
  }
]
```

### Get Card
```bash
GET /cards/{card_id}
```

### List Cards
```bash
GET /cards?type=person&sales_state=cold&limit=100
```

### Send Message
```bash
POST /messages/send
Content-Type: application/json

{
  "target": {
    "type": "entity",
    "entity_type": "fraternity",
    "id": "sigchi_alpha"
  },
  "message_type": "followup",
  "owner": "david"
}
```

Target types:
- `{type: "contact", id: "..."}` - single contact
- `{type: "entity", entity_type: "fraternity", id: "..."}` - expand members
- `{type: "query", where: {"fraternity": "SNU", "sales_state": "interested"}}` - query filter

## UI

- **Upload Cards**: `ui/upload.html` - Upload JSON cards with validation
- **Card List**: `ui/index.html` - View all cards (Cards tab)
- **Card Detail**: `ui/card.html?id={card_id}` - View single card with relationships

## Migration

To link existing conversations to cards:

```bash
# Dry run (see what would be updated)
python scripts/bridge_conversations_to_cards.py

# Actually update
python scripts/bridge_conversations_to_cards.py --execute
```

## State Separation

- **Sales State** (`cards.sales_state`): cold, qualified, negotiating, won, lost
- **Markov State** (`conversations.state`): pricing_question, buy_signal, followup_24hr

These are **orthogonal** - never conflate them.

## Key Features

1. **JSON-native storage** - Cards stored as JSONB, not normalized rows
2. **Entity support** - Fraternities, teams, businesses as first-class objects
3. **Group messaging** - Message entities, they expand to members
4. **Query-based targeting** - Filter cards by any JSONB field
5. **Relationship tracking** - Automatic relationship storage for members/contacts
6. **Bridge to conversations** - Link conversations to cards by phone number

