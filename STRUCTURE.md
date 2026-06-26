# TikTok Lab — Codebase Structure & Session Context

This document is the single source of truth for any new Claude Code session. Read this first.

## Root Paths

| What | Path |
|------|------|
| Project root | `{root}/` (this checkout) |
| Backend (FastAPI) | `{root}/backend/` |
| Frontend (React+Vite) | `{root}/frontend/` |
| OpenMontage (video tools) | `$OPENMONTAGE_PATH/` (external; Phase 6 only) |
| Remotion Composer | `$OPENMONTAGE_PATH/remotion-composer/` |
| Environment vars | `{root}/.env` |
| SQLite database | `{root}/backend/data/tiktok_lab.db` |
| CLAUDE.md (main instructions) | `{root}/CLAUDE.md` |

## Backend Structure (`backend/`)

```
backend/
├── main.py                     # FastAPI app, CORS, router registration, lifespan
├── config.py                   # Settings (env vars, paths, API keys)
├── db/
│   ├── database.py             # SQLAlchemy async engine, session, init_db()
│   ├── models.py               # ALL models: Account, Post, Experiment, VariablePreset,
│   │                           #   Production, ProductionVariant + enums
│   └── migrations/
│       └── env.py              # Alembic config
├── api/                        # FastAPI routers (Pydantic models + endpoints)
│   ├── accounts.py             # /api/accounts — sync, list, update, delete
│   ├── analytics.py            # /api/analytics — post metrics, follower trends, summary
│   ├── posts.py                # /api/posts — CRUD, upload, schedule, publish, retry
│   ├── experiments.py          # /api/experiments — CRUD, start, compare, assign
│   ├── agent.py                # /api/agent — chat, insights, briefing, scan
│   ├── presets.py              # /api/presets — CRUD, test, transcribe (Whisper API)
│   └── productions.py          # /api/productions — upload, analyze, variants, render, publish
├── services/                   # Business logic (async, talks to DB + external)
│   ├── accounts.py             # Account sync from Zernio
│   ├── posts.py                # Post lifecycle: draft → ready → scheduled → published
│   ├── experiments.py          # Experiment CRUD, Mann-Whitney U, Bayesian posterior
│   ├── agent_service.py        # AI chat, proactive insights
│   ├── zernio.py               # Thin wrappers around Zernio SDK async methods
│   ├── poller.py               # APScheduler jobs: metrics, followers, health, backup, scheduled posts
│   ├── openmontage.py          # Runs OpenMontage tools via subprocess + Remotion render
│   ├── production.py           # Production pipeline: create, analyze, render variants, publish
│   └── combined_analytics.py   # Cross-account aggregation (KPIs, daily/cumulative timeseries,
│                               #   leaderboard, top posts, follower aggregation, LOCF semantics)
├── agent/
│   ├── tools.py                # 8 agent tools (query_post_metrics, etc.)
│   ├── prompts.py              # System prompts with domain knowledge
│   └── scheduler.py            # daily_briefing, anomaly_scan
└── tests/
    ├── conftest.py             # In-memory SQLite fixtures
    ├── test_accounts.py
    ├── test_agent.py
    ├── test_analytics.py
    ├── test_experiments.py
    └── test_posts.py
```

### Key Backend Patterns
- All routes use Pydantic request/response models
- All handlers and services are `async def`
- DB queries live in `services/`, never in `api/`
- Zernio SDK is the ONLY external API layer mocked in tests
- 92 tests passing (added 11 combined-analytics tests in 2026-04-26 work)

## Frontend Structure (`frontend/src/`)

```
frontend/src/
├── main.tsx                    # React Router: routes for all pages
├── App.tsx                     # Layout shell (Sidebar + Outlet)
├── index.css                   # Tailwind imports
├── vite-env.d.ts
├── lib/
│   └── api.ts                  # ALL types + API methods (singleton `api` object)
├── components/
│   ├── Sidebar.tsx             # Nav links: Dashboard, Analytics, Posts, Workshop, Produce, Lab, Agent
│   ├── AccountCard.tsx
│   ├── EmptyState.tsx
│   ├── MetricCard.tsx
│   ├── PostTable.tsx
│   └── analytics/
│       ├── CombinedAnalytics.tsx     # Cross-account KPIs + daily/cumulative chart + heatmap
│       │                              #   + decay curve + leaderboard + top posts
│       └── PerAccountAnalytics.tsx   # Single-account deep dive (legacy view)
├── pages/
│   ├── Dashboard.tsx           # Account cards, quick metrics
│   ├── Analytics.tsx           # Tabbed shell: Combined (default) | Per Account
│   ├── PostManager.tsx         # Post CRUD, upload, scheduling
│   ├── Workshop.tsx            # Phase 6: Preset editor + Remotion Player preview
│   ├── Production.tsx          # Phase 6: Upload → analyze → variants → render → publish
│   ├── Lab.tsx                 # Experiment management (A/B tests)
│   ├── Experiments.tsx         # Redirects to /lab
│   ├── Agent.tsx               # Chat + insights feed
│   └── Settings.tsx            # App config
└── remotion/                   # Remotion compositions for Workshop preview
    ├── CaptionOverlay.tsx      # Word-by-word caption overlay (shared component)
    └── compositions.tsx        # VariablePreview, VariableCaptions, VariableTextOverlay, VariableHook
```

### Key Frontend Patterns
- API client: `src/lib/api.ts` — all types and methods in one file
- Pages in `src/pages/`, components in `src/components/`
- Remotion compositions in `src/remotion/` for `@remotion/player` preview
- Tailwind CSS for all styling, dark theme (gray-900/950 backgrounds)

## Remotion Composer (`$OPENMONTAGE_PATH/remotion-composer/src/`)

These are the **production rendering** compositions. The frontend has its own copies for Player preview.

```
remotion-composer/src/
├── Root.tsx                    # Registers ALL compositions (including Variable*)
├── Explainer.tsx               # Data-driven explainer videos
├── TalkingHead.tsx             # Talking head + captions + overlays
├── TitledVideo.tsx             # Titled intro + footage
├── CinematicRenderer.tsx       # Multi-scene cinematic
├── VariablePreview.tsx         # Phase 6: simple video playback
├── VariableCaptions.tsx        # Phase 6: caption styles
├── VariableTextOverlay.tsx     # Phase 6: text overlays
├── VariableHook.tsx            # Phase 6: hook intro cards
└── components/
    ├── CaptionOverlay.tsx      # Word-by-word highlight captions
    ├── TextCard.tsx, StatCard.tsx, CalloutBox.tsx, etc.
    └── charts/ (BarChart, LineChart, PieChart, KPIGrid)
```

## OpenMontage (`$OPENMONTAGE_PATH/`)

75 tools with uniform `BaseTool` interface: `execute(inputs) -> ToolResult`.

Key tools for Phase 6:
- `transcriber` — faster-whisper, word-level timestamps
- `color_grade` — cinematic color grading (FFmpeg LUTs)
- `video_trimmer` — cut, speed, concat
- `silence_cutter` — jump cut planning
- `remotion_caption_burn` — renders captions via Remotion (pattern for all production rendering)
- `auto_reframe` — aspect ratio conversion

Tool invocation from TikTok Lab: `backend/services/openmontage.py` runs tools via subprocess.

## Database Tables

### Phases 1-5 (existing)
- `accounts` — 5 TikTok accounts synced from Zernio
- `posts` — Content lifecycle (draft → published), has `production_id` for Phase 6
- `metric_snapshots` — Views, likes, comments, shares per post
- `follower_snapshots` — Daily follower counts per account
- `experiments` — A/B test definitions
- `experiment_assignments` — Post → experiment variant mapping
- `agent_insights` — Proactive AI briefings/alerts
- `agent_conversations` — Chat history (rolling 20)
- `agent_context_summaries` — Weekly summaries

### Phase 6 (new)
- `variable_presets` — Reusable variable configs (name, type, remotion_composition, params, pre_process)
- `productions` — Source video + analysis (transcript, duration, resolution)
- `production_variants` — Each variant to render (preset, tool_config, render_status, output_path)

## API Endpoints Summary

### Phases 1-5
- `GET/POST/PATCH/DELETE /api/accounts` — Account management
- `GET /api/analytics/posts/{account_id}` — Per-account post metrics
- `GET /api/analytics/summary` — Per-account summary (legacy)
- `GET /api/analytics/followers/{account_id}` — Per-account follower trend
- `GET /api/analytics/combined?days=N` — **Cross-account combined**: KPIs (in-window + all-time),
  daily/cumulative timeseries, follower aggregation, leaderboard, top posts (one round trip)
- `GET /api/analytics/combined/best-time` — Zernio proxy (30-min cached): best day/hour to post
- `GET /api/analytics/combined/decay` — Zernio proxy (30-min cached): engagement accumulation curve
- `GET /api/analytics/combined/posting-frequency` — Zernio proxy (30-min cached)
- `GET/POST/PATCH/DELETE /api/posts` — Post CRUD + upload + schedule + publish
- `GET/POST/DELETE /api/experiments` — Experiment CRUD + compare + assign
- `POST /api/agent/chat` + `GET /api/agent/insights` — AI agent

### Phase 6
- `GET/POST/PUT/DELETE /api/presets` — Variable preset CRUD
- `POST /api/presets/{id}/test` — Test preset on uploaded clip
- `POST /api/presets/transcribe` — Transcribe clip via OpenAI Whisper API
- `GET /api/presets/tools/list` — List OpenMontage tools + schemas
- `POST /api/productions` — Upload source video
- `POST /api/productions/{id}/analyze` — Run transcription + video analysis
- `POST /api/productions/{id}/variants` — Add variant
- `POST /api/productions/{id}/render` — Batch render all variants
- `GET /api/productions/{id}/status` — Poll render progress
- `POST /api/productions/{id}/publish` — Create Post drafts + auto-experiment

## UI Routes

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Dashboard | Account cards, quick metrics |
| `/analytics` | Analytics | Charts, trends |
| `/posts` | PostManager | Post CRUD, upload, schedule |
| `/workshop` | Workshop | Build/test variable presets with Remotion Player |
| `/produce` | Production | Mass production pipeline |
| `/lab` | Lab | A/B experiment management |
| `/agent` | Agent | AI chat + insights |
| `/settings` | Settings | App config |

## How to Start

```bash
# Backend
cd backend && .venv/bin/uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev  # :5173

# Tests
cd backend && .venv/bin/python -m pytest -v    # 92 tests
cd frontend && npx tsc --noEmit                # type check
```

## Phase 6 Architecture (current)

**Single rendering engine**: Remotion for both preview and production.
- Workshop: `@remotion/player` in browser renders compositions from `frontend/src/remotion/`
- Production: `npx remotion render` on server renders compositions from `remotion-composer/src/`
- Same component logic, same props structure = identical output

**Two categories of variables:**
1. **Pre-process** (color_grade, speed, edit_pace): OpenMontage FFmpeg tools transform the video file BEFORE Remotion
2. **Overlay** (captions, text_overlay, hook_intro): Remotion compositions render on top of the video

**Transcription**: OpenAI Whisper API (`whisper-1`) via `POST /api/presets/transcribe`. Fast (~3s), word-level timestamps.

## Deployment Plan (NOT YET EXECUTED)

Plan file: `~/.claude/plans/can-we-pushlish-the-nifty-neumann.md`

**Goal**: publish read-only `/analytics` view at `analytics.<domain>` on Hetzner VPS, fed by sanitized SQLite snapshots rsync'd from the laptop every 5 min. Posting / agent / productions stay local-only.

**Key architectural choices baked into the plan:**
- `PUBLIC_MODE=true` env flag in `backend/main.py` mounts only `analytics_router` + `/api/health`, skips APScheduler.
- `VITE_PUBLIC_MODE=true` build flag in `frontend/.env.public` produces a sidebar-less SPA where every route redirects to `/analytics`.
- No Zernio API key on Hetzner — best-time/decay panels degrade gracefully via existing `502 → "Not available"` UI.
- Sanitized DB snapshot strips `agent_conversations`, `agent_insights`, `variable_presets`, `productions`, `production_variants`, `experiments` before sync.
- Caddy on VPS does TLS via Let's Encrypt + reverse proxy + SPA fallback.
- launchd plist on laptop runs sync every 5 min.

## Critical Decisions (DO NOT re-propose abandoned approaches)

Read `memory/project_decisions_made.md` for the full list. Key ones:
- Workshop = parameter tuner (sliders), NOT a timeline editor
- Remotion = single rendering engine for both preview and production
- 1 clip = 1 implicit experiment, no manual experiment CRUD
- DesignCombo, OpenVideo, OpenCut reverse-engineer — all ABANDONED
- No server-side render for workshop preview
- No CSS overlay for caption preview (use Remotion Player)
