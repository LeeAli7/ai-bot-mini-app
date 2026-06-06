# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Telegram Mini App (Web App) — full-featured AI bot interface accessed via Telegram's "Menu" button. FastAPI backend serves a Vanilla JS SPA frontend, REST API, and runs the Telegram bot in webhook mode. Supports multi-provider AI chat with SSE streaming, vibe-coding (AI writes code into project workspaces), multimodal input, and PTY terminal. SQLite via SQLAlchemy async; PostgreSQL-compatible.

## Commands

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run locally (needs BOT_TOKEN and JWT_SECRET in .env)
cd backend && uvicorn main:app --reload --port 8000

# Docker build and run
docker build -t ai-bot-mini-app .
docker run -p 8000:8000 -e BOT_TOKEN=... -e JWT_SECRET=... ai-bot-mini-app
```

There are no tests, no linters, and no pre-commit hooks configured for this project.

## Architecture

### Entry point (`backend/main.py`)
FastAPI app with `lifespan`: initializes DB, encryption, workspaces dir, cleans orphaned PTY processes, sets Telegram webhook on startup, deletes it on shutdown. Mounts API routers, bot webhook route, and static files (`/css`, `/js`). Root `/` serves `index.html` via `FileResponse`.

### Three roles of the FastAPI process
1. **REST API** (`/api/*`) — JWT-protected CRUD for providers, AI chat (SSE streaming), project/file management, multimodal, PTY terminal
2. **Static file server** — Vanilla JS SPA (no framework) with 4 screens: Chat, Providers, Vibe Coding, Settings
3. **Telegram bot webhook** (`/webhook`) — aiogram 3.x dispatcher receiving updates from Telegram

### API layer (`backend/api/`)
- **`deps.py`** — `get_current_user()` dependency: extracts JWT from `Authorization: Bearer` header, verifies, loads `User` from DB. Used by all protected endpoints.
- **`auth.py`** — `POST /api/auth/telegram`: validates Telegram `initData` (HMAC-SHA256 against bot token), creates/gets user, issues JWT (7-day expiry).
- **`chat.py`** — Non-streaming `POST /api/chat` and SSE streaming `GET /api/chat/stream`. Cancel via `POST /api/chat/cancel`. Module-level `_cancel_flags` dict keyed by user ID.
- **`providers.py`** — Full CRUD for AI providers. First provider auto-activates; delete auto-switches to another. API keys encrypted via `Provider.set_api_key()`.
- **`projects.py`** — Vibe-coding: create/list/delete projects, AI chat in project context with file parsing (`parse_ai_response`), zip import/export, SSE streaming variant.
- **`files.py`** — CRUD files within projects. Path traversal protection via `.resolve()` prefix check.
- **`multimodal.py`** — Vision (image + caption → AI reply), audio transcription (Whisper), document reading (text/image/video/zip/audio classification).
- **`settings.py`** — GET/PATCH user settings (`show_reasoning` toggle).
- **`terminal.py`** — PTY terminal: start, stdin, SSE output stream, kill, signal (SIGINT). Unix-only.

### Database layer (`backend/db/`)
- **`engine.py`** — `create_async_engine` with `pool_pre_ping=True` (pool 20 + 10 overflow). `init_db()` calls `Base.metadata.create_all`. `get_db()` yields sessions for FastAPI `Depends`.
- **`models.py`** — ORM models: `User`, `Provider` (dual `api_key`/`api_key_encrypted` columns with `set_api_key`/`get_api_key`), `Message` (with `chat_type`/`chat_id` for dm/group), `GroupSetting`, `BotResponse`, `Project`, `VibeSession` (full history as single JSON blob in `history_json`).
- **`queries.py`** — Reusable helpers: `get_or_create_user`, `get_active_provider`, `get_chat_history`, `save_messages`, `save_vibe_history`.

### Services (`backend/services/`)
Adapted from a standalone aiogram bot — no aiogram dependencies in this layer.
- **`ai_client.py`** — `AIProvider` dataclass with `generate_response()` and `generate_response_stream()` (SSE parsing). Retry with exponential backoff (3 attempts, 1s/2s/4s) on 5xx, 429, timeouts. Free functions `send_message()` / `send_message_stream()` wrap provider ORM objects.
- **`crypto.py`** — `CryptoService` using Fernet (PBKDF2). Falls back to `_MinimalFernet` (stdlib-only) if `cryptography` unavailable. Singleton via `init_crypto()` / `crypto_service()`.
- **`multimodal.py`** — Accepts raw `bytes` (not aiogram types): vision payload builder, Whisper transcription, document classifier (text/image/video/zip/audio), vision request with streaming.
- **`vibe.py`** — Workspace management (file tree, create/delete files, zip/unzip), AI response parser (`parse_ai_response` — extracts ` ```path/file\ncode``` ` blocks, writes to disk, handles DELETE), PTY subsystem (`start_pty`/`kill_pty`/`write_pty`/`read_pty`/`stream_pty_output`). **PTY is Unix-only** — guarded by `PTY_AVAILABLE` flag; functions raise `RuntimeError` or return early on Windows.

### Bot (`backend/bot/`)
Lightweight aiogram 3.x bot in webhook mode. Shares DB session pool with API. Handlers: `/start`, `/help`, `/reasoning` toggle, `/providers` list, `/cancel`, `/public` (group). Routes registered: common → providers → chat → group_chat. `DbSessionMiddleware` injects session per update.

### Frontend (`frontend/`)
Vanilla JS SPA (no build step). Component pattern: each screen has `render()` (returns HTML string) and `init()` (post-render setup). Router in `app.js` with 4-tab navigation. Auth flow: `Telegram.WebApp.initData` → `POST /api/auth/telegram` → JWT stored in `localStorage`. API client (`api.js`) attaches JWT to all requests. SSE streaming via `fetch()` + `ReadableStream` reader. Theme colors from `Telegram.WebApp` CSS variables.

## Configuration (`backend/config.py`)

Loads `.env` at import time. Key variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Telegram bot token |
| `JWT_SECRET` | Yes | — | HMAC key for JWT signing |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///bot.db` | Defaults to SQLite; set to PostgreSQL for production |
| `ENCRYPTION_SECRET_KEY` | No | auto-generated | Fernet key for API key encryption |
| `WEBHOOK_URL` | No | `""` | Base URL for Telegram webhook (e.g. `https://app.onrender.com`) |
| `WORKSPACES_DIR` | No | `workspaces` | Directory for vibe-coding project files |
| `GROUP_TARGET_NAMES` | No | `jack,ken` | Comma-separated names for group mention detection |

## Key patterns

- **JWT dependency injection**: `get_current_user` in `api/deps.py` decodes JWT, loads user, returns ORM object. Every protected endpoint declares `user: User = Depends(get_current_user)`.
- **SSE streaming pattern**: Endpoint returns `StreamingResponse(event_generator(), media_type="text/event-stream")`. Generator yields `data: {json}\n\n` lines. Cancel via module-level dict keyed by user ID.
- **API key encryption**: `Provider.set_api_key()` encrypts with Fernet and nulls legacy `api_key` column. `get_api_key()` decrypts or falls back to plaintext `api_key`.
- **Path traversal protection**: All file operations resolve paths and verify `str(target).startswith(str(root))` before reading/writing.
- **Static file serving**: CSS/JS mounted at `/css` and `/js` paths via `StaticFiles`. Root `/` serves `index.html` via `FileResponse`. Do NOT mount `StaticFiles` at `/` — it shadows API routes.
- **Bot webhook setup**: Called in `lifespan` startup via `bot.set_webhook()`. Deleted on shutdown. The webhook route itself is registered by `bot/webhook.py:setup_webhook()` as `POST /webhook`.
- **DB session management**: FastAPI endpoints use `Depends(get_db)`. Bot handlers use `DbSessionMiddleware`. Both share the same `AsyncSessionFactory` pool.
- **Vibe session history**: Stored as JSON blob in `VibeSession.history_json`. Every append rewrites the full string — avoid large histories.
- **PTY session key**: All PTY functions key sessions by user ID. Only one session per user at a time (old one is killed on `start_pty`).

## Deployment

Docker-based deploy on Render (native Python runtime fails due to missing C/Rust build tools for `cryptography` on newer Python versions). `render.yaml` exists for Blueprint reference but the live service uses Docker. Auto-deploy on push to `master`.

## Known issues

- **No tests** — zero test coverage
- **`VibeSession.history_json`** — JSON blob approach doesn't scale; should become a child `VibeMessage` table
- **SSE streaming duplicated** — `services/multimodal.py:send_vision_request_stream()` duplicates the SSE parsing loop from `services/ai_client.py`
- **`cancel_menu()` in `bot/handlers/`** — referenced but not fully implemented for the webhook-mode bot
- **`STATIC_DIR` path** — hardcoded as `parent.parent / "frontend"`; relies on `main.py` being exactly one level deep in `backend/`
- **No DB migrations** — uses `Base.metadata.create_all()` which doesn't handle schema changes
