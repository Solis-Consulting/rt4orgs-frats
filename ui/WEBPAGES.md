# RT4 Webpages Reference

## Main Pages

### 1. **Login** (`login.html`)
- **Purpose**: Entry point for all users
- **Access**: Public (no auth required)
- **Features**:
  - API token input
  - Auto-redirects to admin or rep dashboard based on role
  - Owner key creation (if none exists)

### 2. **Admin Dashboard** (`admin.html`)
- **Purpose**: Owner/Admin control center
- **Access**: Owner API token required
- **Features**:
  - **Users & Phone Pairing** tab:
    - Create new rep users
    - View all users (owner + reps)
    - Edit phone pairing (Twilio phone, Account SID, Auth Token)
    - See full IDs (no truncation)
  - **Card Assignments** tab:
    - Assign cards to reps
    - View all assignments
    - Update assignment status
  - **Blast** tab:
    - View all cards
    - Select and blast any cards
    - Owner-only access

### 3. **Rep Dashboard** (`rep.html`)
- **Purpose**: Sales rep workspace
- **Access**: Rep API token required (entered each session)
- **Features**:
  - **My Cards** tab:
    - View only assigned cards
    - Search and filter assigned leads
    - Blast selected assigned leads
    - Blast all assigned leads (one-click)
  - **Conversations** tab:
    - View conversations for assigned cards
    - Message threads
    - Send replies
  - **Stats** tab:
    - Personal conversion metrics
    - Assignment counts by status

### 4. **Main Console** (`index.html`)
- **Purpose**: Legacy console view
- **Access**: Public (no auth required)
- **Features**:
  - **Leads** tab: View all conversations/leads
  - **Cards** tab: View all cards
    - Legacy blast (gate-locked, requires owner token unlock)
    - Delete cards
  - **Note**: This is the old interface, mostly replaced by admin/rep dashboards

### 5. **Card Detail** (`card.html`)
- **Purpose**: View single card details
- **Access**: Public (no auth required)
- **Features**:
  - Full card JSON data
  - Relationships (fraternity members, etc.)
  - Sales state
  - Conversation history

### 6. **Upload Cards** (`upload.html`)
- **Purpose**: Upload JSON cards to database
- **Access**: Public (no auth required)
- **Features**:
  - JSON card upload
  - Validation
  - Batch upload support

### 7. **Blast** (`blast.html`)
- **Purpose**: Legacy standalone blaster
- **Access**: Public (no auth required)
- **Features**:
  - Outbound message blasting
  - Limit controls
  - Batch ID tracking
  - **Note**: Legacy interface, use admin dashboard instead

### 8. **Lead** (`lead.html`)
- **Purpose**: View individual lead details
- **Access**: Public (no auth required)
- **Features**:
  - Lead conversation view
  - State tracking

### 9. **Webhook** (`webhook.html`)
- **Purpose**: Webhook configuration/testing
- **Access**: Public (no auth required)
- **Features**:
  - Webhook URL configuration
  - Test webhook calls

### 10. **Markov Responses** (`markov_responses.html`)
- **Purpose**: Configure AI response templates
- **Access**: Public (no auth required)
- **Features**:
  - Edit Markov response templates
  - State-based responses

## Access Flow

```
login.html
  ├─ Owner Token → admin.html
  │   ├─ Users & Phone Pairing
  │   ├─ Card Assignments
  │   └─ Blast
  │
  └─ Rep Token → rep.html
      ├─ My Cards
      ├─ Conversations
      └─ Stats
```

## Legacy Pages (Still Functional)

- `index.html` - Main console (legacy, mostly replaced)
- `blast.html` - Standalone blaster (legacy)
- `card.html` - Card detail view
- `upload.html` - Card upload
- `lead.html` - Lead detail
- `webhook.html` - Webhook config
- `markov_responses.html` - Response templates

## Recommended Usage

**For Admins:**
1. Use `login.html` with owner token
2. Access `admin.html` for all management
3. Use `index.html` only for legacy card viewing

**For Reps:**
1. Use `login.html` with rep token (or go directly to `rep.html`)
2. Access `rep.html` for all rep functions
3. Never access admin pages
