# RT4 Orgs - Fraternity Lead Management System

A SaaS platform for managing fraternity rush leads with automated SMS conversations, state tracking, and a real-time lead console.

## 🏗️ Project Structure

```
rt4orgs-frats/
│
├── backend/                    # Backend services
│   ├── server.js              # Lead console API (Node.js/Express)
│   ├── twilio_server.py       # Twilio webhook receiver (FastAPI)
│   ├── message_processor/     # NLP + Markov classification
│   │   ├── classifier.py     # Semantic intent classification
│   │   ├── markov_chain.py   # State transition logic
│   │   ├── handler.py        # Message handler
│   │   ├── generate_message.py # Response generation
│   │   ├── utils.py          # Utilities (paths, data loading)
│   │   └── subtam_descriptions.py # State descriptions
│   ├── contacts/             # Contact event folders (filesystem storage)
│   ├── data/                 # JSON data files (leads, sales history)
│   ├── templates/            # Message templates
│   ├── config.py             # Configuration
│   └── requirements.txt      # Python dependencies
│
├── ui/                        # Vercel frontend
│   ├── index.html            # Lead console dashboard
│   ├── lead.html             # Individual lead detail page
│   └── vercel.json           # Vercel deployment config
│
├── scripts/                   # CLI utilities
│   ├── blast.py              # Outbound SMS blast script
│   ├── dedupe_contacts.py    # Contact deduplication
│   └── generate_message.py   # Message generation utility
│
└── README.md
```

## 🚀 Architecture

### Data Flow

```
Twilio SMS → FastAPI (twilio_server.py) → message_processor/ → contacts/ folders
                                                                    ↓
Node.js (server.js) ← reads contacts/ ←────────────────────────────┘
         ↓
    Vercel UI (index.html)
```

### Components

1. **Twilio Backend** (`backend/twilio_server.py`)
   - FastAPI server receiving Twilio webhooks
   - Processes inbound SMS messages
   - Classifies intent using semantic embeddings
   - Updates Markov state machine
   - Generates responses
   - Writes event folders to `contacts/`

2. **Lead Console Backend** (`backend/server.js`)
   - Node.js/Express API server
   - Reads contact folders from filesystem
   - Serves JSON API endpoints (`/api/all`, `/api/lead/:name`)
   - Serves UI static files

3. **Message Processor** (`backend/message_processor/`)
   - Semantic classifier using sentence transformers
   - Markov chain state transitions
   - Response generation based on state

4. **UI** (`ui/`)
   - Static HTML/JS frontend
   - Real-time lead dashboard
   - Individual lead detail pages
   - Deploys to Vercel

## 📦 Setup

### Backend Setup

1. Install Python dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Set up environment variables (create `backend/.env`):
```
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
```

3. Start the Twilio backend:
```bash
cd backend
python twilio_server.py
# Runs on http://0.0.0.0:5005
```

4. Start the lead console backend:
```bash
cd backend
node server.js
# Runs on http://localhost:3005
```

### Twilio Webhook Setup

1. Use ngrok to expose local server:
```bash
ngrok http 5005
```

2. Set Twilio webhook URL to:
```
https://your-ngrok-id.ngrok-free.app/twilio
```

### UI Deployment (Vercel)

1. Deploy the `ui/` folder to Vercel:
```bash
cd ui
vercel deploy
```

2. Update `ui/vercel.json` to point API rewrites to your backend URL

## 🛠️ Usage

### Running Scripts

**Blast outbound messages:**
```bash
python scripts/blast.py
```

**Deduplicate contacts:**
```bash
python scripts/dedupe_contacts.py
```

### Accessing the Lead Console

- Local: http://localhost:3005
- Production: https://rt4-ui.vercel.app (after deployment)

## 📝 Data Storage

Currently uses filesystem storage:
- `backend/contacts/` - One folder per message event (timestamped)
- `backend/data/leads.json` - Lead contact information
- `backend/data/sales_history.json` - Sales history for matching

Each contact event folder contains:
- `message.txt` - The inbound message
- `state.json` - State transition data, intent, contact info

## 🔄 Next Steps

Choose your deployment path:

- **Option A**: Convert filesystem → Postgres (deploy to Fly.io/Railway)
- **Option B**: Deploy Twilio backend to cloud (Railway/Fly.io)
- **Option C**: Upgrade Vercel UI to full CRM dashboard
- **Option D**: Create Docker setup for production deployment

## 📄 License

Private - RT4 Orgs

