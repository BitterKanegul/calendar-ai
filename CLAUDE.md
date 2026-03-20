# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Calendar AI (CALEN)** is an intelligent conversational calendar assistant using a multi-agent LangGraph architecture. Users manage schedules via natural language (text or voice). The project has two components: a Python/FastAPI backend and a React Native/Expo mobile app.

## Commands

### Backend

```bash
# Start Redis (required before running backend)
cd backend && docker compose up -d

# Run the backend server
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Install dependencies
cd backend && pip install -r requirements.txt

# Lint
cd backend && pylint **/*.py
```

### Mobile

```bash
# Install dependencies
cd mobile && npm install

# Start Expo dev server
cd mobile && npm start

# Run on specific platforms
cd mobile && npm run ios
cd mobile && npm run android
```

### No tests exist in this codebase.

## Environment Setup

The backend loads environment variables from `.env.{ENV}` files (e.g., `.env.development`). No `.env.example` exists — required variables:

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `SECRET_KEY` | Yes | JWT signing key |
| `OPENAI_API_KEY` | Yes | For GPT-4.1 |
| `REDIS_URL` | No | Default: `redis://localhost:6379` |
| `ENV` | No | Default: `development` |

## Architecture

### Backend Layering

```
controller/ → services/ → adapter/ → database/models/
```

- **controller/**: FastAPI route handlers; validate JWT and delegate to services
- **services/**: Business logic (event conflict detection, AI orchestration)
- **adapter/**: Direct SQLAlchemy database queries
- **database/models/**: `EventModel`, `UserModel` ORM definitions

All DB access is async (asyncpg + `AsyncSession`). Events and users expose public UUIDs (`event_id`, `user_id`) separate from internal DB integer PKs.

### Multi-Agent AI Flow (`flow/`)

LangGraph `StateGraph` with 15 nodes. Entry via `assistant_service.py` → `FlowBuilder.create_flow()` → `flow.ainvoke()`.

```
START → router_agent → (conditional)
  ├→ create_agent → check_event_conflict → END
  ├→ list_date_range_agent → list_event_by_date_range → list_filter_event_agent → END
  ├→ update_date_range_agent → get_events_for_update → update_filter_event_agent → END
  ├→ delete_date_range_agent → delete_event_by_date_range → delete_filter_event_agent → END
  └→ router_message_handler → END
```

- **`flow/state.py`**: `FlowState` TypedDict holds message arrays for each agent + event data
- **`flow/redis_checkpointer.py`**: Custom checkpointer that persists only message fields (not event data) to Redis
- **`flow/llm.py`**: ChatOpenAI `gpt-4.1`, temperature=0, with tenacity retry (3 attempts, exponential backoff)
- Each agent subdirectory contains the agent logic and its system prompt

### Mobile Architecture

```
App.tsx (nav stack)
  ├── screens/         # Full-page views (Login, Home, Calendar, Profile)
  ├── components/      # Reusable UI (CRUD modals, AI feedback display)
  ├── contexts/AuthContext.tsx  # JWT storage + auth state (AsyncStorage)
  ├── services/api.ts  # Axios client with automatic token refresh interceptor
  └── models/event.tsx # TypeScript event model
```

The axios interceptor in `api.ts` auto-refreshes expired access tokens using the refresh token before retrying failed requests.

### Authentication

JWT-based: access tokens (30 min) + refresh tokens (30 days). Backend: `utils/jwt.py`. All event/assistant endpoints call `get_user_id_from_token()` as a FastAPI `Depends`.

### API Routes

- `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`
- `GET|POST|PUT|DELETE /events/`
- `POST /assistant/` — main AI text processing endpoint
- `POST /transcribe/` — audio-to-text (Whisper)

## Key Design Notes

- **Conflict detection**: `event_service.py` checks time overlaps before creating events
- **Voice input**: `expo-av` records audio on mobile; sent to `/transcribe/` which returns text fed into `/assistant/`
- **No CI/CD**: No GitHub Actions or Dockerfile for the backend; only `docker-compose.yml` for Redis
- **CORS**: Currently set to `allow_origins=["*"]` in `main.py`
