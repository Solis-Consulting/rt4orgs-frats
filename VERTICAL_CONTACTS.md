# Vertical-Based Contact Card System

This document describes the new vertical-based contact card upload system with pitch template support.

## Overview

The system now supports **6 vertical types** for contact cards, each with:
- Custom field requirements
- Vertical-specific validation
- Personalized pitch templates with placeholder replacement

## Vertical Types

### 1. Fraternities (`frats`)
**Required Fields:**
- `name` / `contact_name`
- `role` / `position`
- `chapter`
- `fraternity`
- `phone` / `phone_number`
- `email`

**Pitch Template:**
```
Hello {name}, we'd love to see how {fraternity} at {chapter} could engage with a FRESH PNM list.
We helped {purchased_chapter} at {purchased_institution} save DAYS of outreach. I'm David with RT4Orgs — https://rt4orgs.com
```

### 2. Faith / Religious Groups (`faith`)
**Required Fields:**
- `name` / `contact_name`
- `role` / `position`
- `faith_group`
- `university`
- `phone` / `phone_number`
- `email`

**Pitch Template:**
```
Hello {name}, we help {faith_group} at {university} reach students likely to be receptive to faith-based community.
Our lists allow your team to spend less time searching and more time welcoming, mentoring, and serving students.
I'm Sarah with RT4Orgs — https://rt4orgs.com
```

### 3. Academic / Program-Specific (`academic`)
**Required Fields:**
- `name` / `contact_name`
- `role` / `position`
- `program` / `program_name`
- `department` / `department_name`
- `university`
- `phone` / `phone_number`
- `email`

**Pitch Template:**
```
Hi {name}, we support {program} in {department} at {university} by providing a curated list of students already aligned with your program.
This helps your office save hours in outreach and focus on mentoring and advising.
I'm Alex with RT4Orgs — https://rt4orgs.com
```

### 4. Government / Student Government / Orgs (`government`)
**Required Fields:**
- `name` / `contact_name`
- `role` / `position`
- `org` / `organization_name`
- `university`
- `phone` / `phone_number`
- `email`

**Pitch Template:**
```
Hello {name}, we help {org} at {university} streamline communication with student leaders and members.
Our curated lists save your staff days of manual outreach, giving you more time for impactful student programming.
I'm Jordan with RT4Orgs — https://rt4orgs.com
```

### 5. Cultural / Faith-based (`cultural`)
**Required Fields:**
- `name` / `contact_name`
- `role` / `position`
- `group` / `faith_group_or_org`
- `university`

**Optional Fields:**
- `email` (can be empty string)
- `phone` / `phone_number`
- `insta`
- `other_social`
- `tags`
- `metadata`

**Pitch Template:**
```
Hello {name}, we help {group} at {university} connect with students interested in cultural and faith-based communities.
Our curated lists save your team time in outreach, allowing you to focus on building meaningful connections.
I'm {rep_name} with RT4Orgs — https://rt4orgs.com
```

### 6. Sports / Club (`sports`)
**Required Fields:**
- `name` / `contact_name`
- `role` / `position`
- `team` / `team_or_club`
- `university`

**Optional Fields:**
- `email` (can be empty string)
- `phone` / `phone_number`
- `insta`
- `other_social`
- `tags`
- `metadata`

**Pitch Template:**
```
Hello {name}, we help {team} at {university} streamline communication with athletes and club members.
Our curated lists save your staff time in outreach, giving you more time for training and team building.
I'm {rep_name} with RT4Orgs — https://rt4orgs.com
```

## Usage

### Upload UI

1. **Select Vertical**: Use the dropdown to select a vertical type (optional - can also be specified in JSON)
2. **Load Example**: Click "Load Example" to see a sample card for the selected vertical
3. **Paste/Upload JSON**: Paste your contact cards or load from a file
4. **Preview Pitch**: Click "Preview Pitch" to see the generated pitch for the first card
5. **Upload**: Click "Upload Cards" to store the cards

### JSON Format

**Note:** The `type` field is optional when `vertical` is present - it will automatically be set to `"person"`.

```json
[
  {
    "vertical": "cultural",
    "name": "Multicultural Engagement Center",
    "role": "Office",
    "group": "Multicultural Engagement Center",
    "university": "University of Texas at Austin",
    "phone": "(512) 232-2958",
    "email": "",
    "insta": "",
    "other_social": "",
    "tags": [],
    "metadata": {}
  },
  {
    "type": "person",
    "vertical": "frats",
    "name": "John Doe",
    "role": "President",
    "phone": "+1234567890",
    "email": "john@example.edu",
    "fraternity": "SigChi",
    "chapter": "Alpha",
    "sales_state": "cold"
  }
]
```

### API Endpoints

#### Get Vertical Information
```bash
GET /cards/verticals
GET /cards/verticals?vertical=frats
```

#### Generate Pitch
```bash
POST /cards/generate-pitch
Content-Type: application/json

{
  "card": {
    "type": "person",
    "vertical": "frats",
    "name": "John Doe",
    "fraternity": "SigChi",
    "chapter": "Alpha"
  },
  "vertical": "frats",
  "additional_data": {
    "purchased_chapter": "Beta",
    "purchased_institution": "State University",
    "rep_name": "David"
  }
}
```

#### Upload Cards (with vertical support)
```bash
POST /cards/upload
Content-Type: application/json

[
  {
    "type": "person",
    "vertical": "frats",
    ...
  }
]
```

## Field Name Variations

The system automatically handles field name variations:
- `contact_name` ↔ `name`
- `position` ↔ `role`
- `phone_number` ↔ `phone`
- `faith_group_or_org` ↔ `group`
- `team_or_club` ↔ `team`
- `program_name` ↔ `program`
- `department_name` ↔ `department`
- `organization_name` ↔ `org`

## Pitch Template Placeholders

Placeholders in pitch templates are replaced with actual card data:
- `{name}` - Contact name
- `{fraternity}` - Fraternity name (frats)
- `{chapter}` - Chapter name (frats)
- `{faith_group}` - Faith group name (faith)
- `{university}` - University name
- `{program}` - Program name (academic)
- `{department}` - Department name (academic)
- `{org}` - Organization name (government)
- `{group}` - Group name (cultural)
- `{team}` - Team name (sports)
- `{rep_name}` - Representative name (from additional_data)
- `{purchased_chapter}` - Example chapter (from additional_data)
- `{purchased_institution}` - Example institution (from additional_data)

## Implementation Details

### Backend (`backend/cards.py`)
- `VERTICAL_TYPES` - Dictionary defining all vertical types and their configurations
- `validate_card_schema()` - Updated to validate vertical-specific requirements
- `normalize_card()` - Handles field name variations and ensures vertical is preserved
- `generate_pitch()` - Generates personalized pitches from templates
- `get_vertical_info()` - Returns vertical type information

### Frontend (`ui/upload.html`)
- Vertical selector dropdown
- Auto-apply vertical to cards when selected
- Pitch preview button and display
- Vertical-specific example loader

### API (`main.py`)
- `GET /cards/verticals` - Get vertical information
- `POST /cards/generate-pitch` - Generate pitch from card

## Migration Notes

- Existing cards without `vertical` field will continue to work (legacy mode)
- New cards should include `vertical` field for proper validation and pitch generation
- Vertical field is optional but recommended for person cards
