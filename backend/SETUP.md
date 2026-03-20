# Backend Setup Guide

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12+ | Tested on 3.12 |
| PostgreSQL | 14+ | Any recent version works |
| Docker | 20+ | Used to run Redis only |
| Node.js | — | Not needed for backend |

---

## 1. Clone & Enter the Backend Directory

```bash
git clone <repo-url>
cd calendar-ai/backend
```

---

## 2. Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> The first install takes a few minutes because `sentence-transformers` downloads
> a ~90 MB embedding model (`all-MiniLM-L6-v2`) on first use.

---

## 4. Create the Environment File

The app loads variables from `.env.{ENV}` (default: `.env.development`).
Create the file:

```bash
cp .env.development.example .env.development   # if the example exists
# or create it from scratch:
touch .env.development
```

Paste and fill in the following:

```dotenv
# ── Required ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/calendar_ai
SECRET_KEY=your-long-random-secret-key-here
OPENAI_API_KEY=sk-...

# ── Optional (defaults shown) ─────────────────────────────────────────────────
ENV=development
REDIS_URL=redis://localhost:6379

# ── Ticketmaster API (only needed for the Leisure Search feature) ─────────────
TICKETMASTER_API_KEY=

# ── Google / Gmail OAuth2 (only needed for the Email RAG feature) ─────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

### Generating a SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. Start Redis

Redis is required for LangGraph conversation checkpointing.

```bash
docker compose up -d
```

This starts a Redis container on `localhost:6379` using `docker-compose.yml`.
Verify it is running:

```bash
docker compose ps
# or
redis-cli ping   # should return PONG
```

---

## 6. Create the PostgreSQL Database

```bash
psql -U postgres -c "CREATE DATABASE calendar_ai;"
```

> If your PostgreSQL user or host differs, adjust the `DATABASE_URL` accordingly.
> The `asyncpg` driver is used; **do not** use the `psycopg2://` prefix.

---

## 7. Initialize the Database Schema

```bash
# The server calls init_db() on startup which runs SQLAlchemy's create_all().
# You can also trigger it manually:
python -c "import asyncio; from database.config import init_db; asyncio.run(init_db())"
```

### Run the metadata migration (priority / flexibility / category columns)

If you are upgrading an existing database that was created before PLAN-01,
run the migration script to add the three new event columns:

```bash
python -m database.migrate_add_event_metadata
```

This uses `ALTER TABLE … ADD COLUMN IF NOT EXISTS` so it is safe to re-run.

---

## 8. (Optional) Gmail / Email RAG Setup

Required only if you want the "check my emails" feature.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials.
2. Create an **OAuth 2.0 Client ID** (Web application type).
3. Add `http://localhost:8000/auth/google/callback` as an authorized redirect URI.
4. Copy **Client ID** and **Client Secret** into `.env.development`.
5. Enable the **Gmail API** in the same project.

First-time authorization flow (per user):

```
GET /auth/google/connect      → returns a URL
# Open the URL in a browser, grant access
# Google redirects to /auth/google/callback automatically
GET /auth/google/status       → {"connected": true}
```

Credentials are stored per-user at `./data/gmail_credentials/{user_id}.json`
(excluded from git via `.gitignore`).

---

## 9. Start the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should see:

```
INFO  Starting Calendar AI API
INFO  CORS middleware configured
INFO  Authentication routes included
INFO  Event routes included
INFO  Database initialized successfully
INFO  Uvicorn running on http://0.0.0.0:8000
```

Interactive API docs are available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc

---

## 10. Verify the Installation

```bash
curl http://localhost:8000/
# {"message":"Calendar AI API is running!"}
```

Register a test user:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"test@example.com","password":"secret123"}'
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login, returns access + refresh tokens |
| POST | `/auth/refresh` | Refresh an expired access token |
| GET | `/events/` | List events (JWT required) |
| POST | `/events/` | Create an event |
| PUT | `/events/{id}` | Update an event |
| DELETE | `/events/{id}` | Delete an event |
| POST | `/assistant/` | Main AI text processing endpoint |
| POST | `/transcribe/` | Audio (base64) → text via Whisper |
| GET | `/auth/google/connect` | Start Gmail OAuth2 flow |
| GET | `/auth/google/callback` | OAuth2 callback (set as redirect URI) |
| GET | `/auth/google/status` | Check if Gmail is connected |
| DELETE | `/auth/google/disconnect` | Revoke Gmail access |

All `/events/` and `/assistant/` endpoints require a JWT in the
`Authorization: Bearer <token>` header.

---

## Running the Evaluation Framework

The eval framework tests the multi-agent router against a single-agent
baseline. No database connection is needed for the intent classification tests.

```bash
# List all 28 test cases
python -m eval.run_eval --list-cases

# Run router + baseline comparison
python -m eval.run_eval

# Include LLM-as-a-judge scoring (uses extra API calls)
python -m eval.run_eval --judge

# Run only specific categories
python -m eval.run_eval --filter create update delete

# Save a JSON report
python -m eval.run_eval --judge --output eval/results/
```

---

## Common Issues

### `asyncpg.exceptions.InvalidCatalogNameError: database "calendar_ai" does not exist`
Create the database first: `psql -U postgres -c "CREATE DATABASE calendar_ai;"`

### `redis.exceptions.ConnectionError: Error connecting to localhost:6379`
Redis is not running. Start it: `docker compose up -d`

### `openai.AuthenticationError`
`OPENAI_API_KEY` is missing or incorrect in `.env.development`.

### `ModuleNotFoundError` on startup
The virtual environment is not activated.
Run `source .venv/bin/activate` first.

### `sentence_transformers` model download hangs
First run downloads `all-MiniLM-L6-v2` (~90 MB). Let it finish once; it is
cached locally afterwards.

### Port 8000 already in use
Kill the existing process or run on a different port:
`uvicorn main:app --reload --port 8001`

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL URL (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | Yes | — | JWT signing key (32+ random bytes) |
| `OPENAI_API_KEY` | Yes | — | OpenAI key for GPT-4.1 |
| `ENV` | No | `development` | Environment name; selects `.env.{ENV}` file |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection URI |
| `TICKETMASTER_API_KEY` | No | — | Ticketmaster Discovery API key ([get free key](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/)) |
| `GOOGLE_CLIENT_ID` | No | — | Gmail OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | No | — | Gmail OAuth2 client secret |
| `GOOGLE_REDIRECT_URI` | No | `http://localhost:8000/auth/google/callback` | OAuth2 redirect URI |
| `CHROMA_PERSIST_DIR` | No | `./data/chroma` | ChromaDB storage for email embeddings |
| `GMAIL_CREDENTIALS_DIR` | No | `./data/gmail_credentials` | Per-user Gmail token storage |
| `EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Sentence-transformer model name |
| `EMAIL_INDEX_REFRESH_MINUTES` | No | `15` | Minimum gap between email re-indexes |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `DEBUG` | No | `true` | Enable debug mode |
