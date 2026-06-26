# TikTok Lab

A locally-hosted, single-operator dashboard for managing up to **5 TikTok accounts** from one place: posting and scheduling, cross-account analytics, formal A/B experiment tracking, and an AI agent that surfaces insights and recommendations.

> **The agent is recommend-only.** It can draft posts, suggest experiments, and flag
> underperformers, but it **never publishes without explicit user confirmation**. Posting
> is always a deliberate human action.

All TikTok I/O (posting, analytics, follower stats) goes through a third-party API,
**[Zernio](https://docs.zernio.com)** — the app never talks to TikTok directly.

## Features

- **Multi-account posting & scheduling** — one workflow across up to 5 connected accounts, with multi-account fan-out, presigned-URL media upload, retry with exponential backoff, and deletion detection.
- **Cross-account analytics** — time-series metrics (views, likes, comments, shares), engagement rates, follower trends, and combined/per-account dashboards.
- **A/B experiment engine** — hypothesis-driven experiments with Mann-Whitney U significance testing and a Bayesian posterior (pure Python, no scipy).
- **AI agent (analyst mode)** — dual-provider (Claude or OpenAI) agent with 8 tools that query the local database to brief you, detect anomalies, and recommend next actions.
- **AI content production (Phase 6, optional)** — Remotion-based variant rendering driven by an external OpenMontage install (see caveat below).

## Tech Stack

- **Backend**: Python 3.12, FastAPI (async), SQLAlchemy 2.0 (async) + aiosqlite, Alembic, APScheduler (in-process scheduling — no Redis).
- **Frontend**: React 19 + Vite + TypeScript + Tailwind CSS + Remotion.
- **AI agent**: Claude or OpenAI via raw `httpx`, configurable via `AGENT_PROVIDER`.
- **TikTok integration**: the Zernio Python SDK (`zernio-sdk`).

## Requirements

- Python 3.12 and Node 18+.
- A **Zernio** API key (`ZERNIO_API_KEY`) — accounts are connected on Zernio's dashboard and synced into the app.
- An LLM key for the agent: set **either** `ANTHROPIC_API_KEY` **or** `OPENAI_API_KEY` (and `AGENT_PROVIDER`). The agent is optional; the dashboard works without it.

## Build Phases

1. Data Foundation — **done** (schema, Zernio SDK, polling).
2. Dashboard — **done** (account cards, analytics charts).
3. Posting + Scheduling — **done** (multi-account posting, upload, retry, deletion detection).
4. Experiment Engine — **done** (CRUD, Mann-Whitney U, Bayesian posterior).
5. Agent: Analyst Mode — **done** (8 tools, dual-provider, chat, proactive insights).
6. AI Content Production — **in progress, and optional.** Requires an external OpenMontage install (see below).

## Phase 6 / OpenMontage caveat

Phase 6 (AI content production: pre-processing + Remotion rendering of post variants)
depends on a **separate, EXTERNAL [OpenMontage](https://github.com/) install that is NOT
bundled with this repository**. It is **disabled by default**.

To enable it, set `OPENMONTAGE_PATH` in your `.env` to the root of your OpenMontage
checkout; the Remotion composer is resolved relative to it. When `OPENMONTAGE_PATH` is
unset, production code paths raise a clear error and the rest of the app runs normally —
Phases 1-5 do not require OpenMontage.

## Setup

```bash
# 1. Configure environment
cp .env.example .env
# then edit .env — set ZERNIO_API_KEY and one LLM key

# 2. Backend deps
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..

# 3. Frontend deps
cd frontend && npm install && cd ..

# 4. Database
make db-upgrade          # apply Alembic migrations
# (the app also auto-creates tables on first startup via SQLAlchemy)

# 5. Run backend (:8000) + frontend (:5173)
make dev
```

The frontend proxies `/api` to the backend, so open <http://localhost:5173>.

## Tests

```bash
make test            # backend pytest + frontend typecheck/vitest
make test-backend    # pytest only (offline, in-memory SQLite)
cd frontend && npx tsc --noEmit   # type check
```

Backend tests run fully offline against in-memory SQLite; Zernio SDK calls are mocked.

## Notes

- **5-account ceiling** is enforced in `services/accounts.py`.
- **Agent trust boundary** (`draft → ready → scheduled → published`) is non-negotiable; nothing auto-publishes.
- See `ARCHITECTURE.md` and `STRUCTURE.md` for the full design and codebase map, and `CLAUDE.md` for working-in-the-repo guidance.

## License

MIT — see [LICENSE](./LICENSE).
