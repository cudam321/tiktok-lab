# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TikTok Lab is a locally-hosted internal tool for managing TikTok accounts. It combines a posting/analytics dashboard, formal A/B experiment tracking, and an AI agent that surfaces insights and recommendations. Video production (Phase 6) is powered by an external OpenMontage install. All API interaction goes through Zernio.

## Tech Stack

- **Backend**: Python 3.12 / FastAPI (async), venv at `backend/.venv`
- **Database**: SQLite via SQLAlchemy (async, aiosqlite) + Alembic migrations
- **Frontend**: React 19 + Vite + Tailwind CSS (TypeScript)
- **Task scheduling**: APScheduler (in-process, no Redis)
- **AI agent**: Claude API or OpenAI (configurable, dual-provider) with tool use (recommend-only)
- **Video production**: external OpenMontage install at `$OPENMONTAGE_PATH` (Phase 6/v1.1; optional)
- **API integration**: Zernio Python SDK (`zernio-sdk` from GitHub) — Build plan, 120 req/min, Analytics add-on

## Architecture

```
React+Vite (:5173) <--REST (proxied)--> FastAPI (:8000)
                                             |
                                        APScheduler
                                        - poll metrics (30min)
                                        - follower stats (daily)
                                        - health check (6hr)
                                        - publish scheduled (1min)
                                        - agent briefing (daily 8am)
                                        - anomaly scan (2hr)
                                        - SQLite backup (daily 3am)
                                             |
                                   +---------+---------+
                                   |         |         |
                               SQLite    Claude/     Zernio SDK
                            (tiktok_lab.db) OpenAI   (zernio-sdk)
```

All Zernio calls go through `backend/services/zernio.py` (thin wrappers around SDK async methods). The frontend never calls Zernio directly.

## Key Development Commands

```bash
# Backend
cd backend && .venv/bin/pip install -r requirements.txt
cd backend && .venv/bin/uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install
cd frontend && npm run dev  # starts on :5173

# Tests
cd backend && .venv/bin/python -m pytest -v          # 81 tests
cd frontend && npx tsc --noEmit                      # type check

# Database
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/alembic revision --autogenerate -m "description"

# Run both
make dev
```

## Critical Constraints

- **5-account ceiling**: Enforced in `services/accounts.py`. Each Zernio profile holds 1 TikTok account. Accounts are connected on Zernio's dashboard, synced via `/api/accounts/sync`.
- **Agent trust boundary**: The agent can create drafts and suggestions, but NEVER publishes without explicit user confirmation. Post status flow: `draft → ready → scheduled → published`. Non-negotiable.
- **TikTok required fields**: Every post MUST include `content_preview_confirmed: true` and `express_consent_given: true` in tiktok_settings. Enforced in `services/zernio.py`.
- **Post failure retry**: 3 retries with exponential backoff (30s, 2min, 10min), then permanent failure. Track `failure_reason` for agent pattern learning.
- **Offline recovery**: APScheduler uses `misfire_grace_time=3600`. On startup, catch up missed polls. Never auto-post stale scheduled content.
- **SQLite backup**: Daily `.backup` to `data/backups/`, 30-day retention.
- **Deletion detection**: Poller marks posts as `deleted` if they disappear from Zernio analytics (deleted on TikTok natively). Published TikTok posts cannot be deleted via API.

## Configuration (.env)

```
ZERNIO_API_KEY=sk_...          # Only thing needed for Zernio
ANTHROPIC_API_KEY=             # Set for Claude agent
OPENAI_API_KEY=                # Or set for OpenAI agent
AGENT_PROVIDER=auto            # "anthropic", "openai", or "auto"
```

No OAuth client_id/secret — Zernio uses bearer token auth. No profile ID needed — accounts are synced from Zernio's connected accounts list.

## Database

SQLite at `data/tiktok_lab.db`. Core tables:

- `accounts` — Zernio-connected TikTok accounts, no local tokens (Zernio manages auth)
- `posts` — Content with status tracking: draft|producing|ready|scheduled|published|failed|deleted
- `metric_snapshots` — Time-series metrics per post (views, likes, comments, shares). `engagement_rate = (likes + comments + shares) / views * 100`
- `follower_snapshots` — Daily follower counts per account (upserted, unique per account+date)
- `experiments` — A/B test definitions with hypothesis, variable, variants, statistical results
- `experiment_assignments` — Maps posts to experiment variants
- `agent_insights` — Proactive briefings, alerts, suggestions from the agent
- `agent_conversations` — Rolling window of last 20 messages for chat context
- `agent_context_summaries` — Weekly structured summaries for agent proactive runs

## Zernio SDK Integration

Uses the official Python SDK: `git+https://github.com/zernio-dev/zernio-python.git` (package: `zernio-sdk`)

```python
from zernio import Zernio, Platform, TikTokPrivacyLevel
client = Zernio(api_key=settings.zernio_api_key)
```

Key SDK methods (all have async `a`-prefixed variants):
- `client.accounts.alist()` — returns `AccountsListResponse` object (not dict)
- `client.accounts.aget_follower_stats(account_ids=[...])` — keyword arg, takes list
- `client.accounts.aget_tik_tok_creator_info(id, media_type="video")` — pre-post validation
- `client.posts.acreate_post(content=, platforms=, tiktok_settings=, media_items=, publish_now=)` — snake_case params
- `client.analytics.aget_analytics(limit=, page=, account_id=, sort_by=, order=)` — paginated
- `client.media.aget_media_presigned_url(filename, content_type)` — requires both args

Important SDK gotchas:
- Returns typed objects (not dicts) — use `.accounts`, `.field_id` etc. to access
- Parameters are snake_case (`tiktok_settings`, `media_items`, `publish_now`)
- Presigned URL upload: GET url → PUT file → use publicUrl in post
- External posts (posted natively on TikTok) have `isExternal: true`
- Multi-account posting: multiple entries in `platforms[]` with `customContent` per account

## AI Agent

**Dual-provider**: Claude API (claude-sonnet-4) or OpenAI (gpt-4o), configured via `AGENT_PROVIDER`.

**8 core tools** query the local SQLite database:
`query_post_metrics`, `query_follower_trends`, `compare_experiments`, `get_account_health`, `get_content_calendar`, `suggest_next_post`, `suggest_experiment`, `flag_underperformers`

**Domain knowledge** from OpenMontage: hook science (3s retention tiers, 5 hook techniques), pacing rules (20-40 cuts/min), duration strategy (completion rates), caption science (80-85% watch muted), content quality scoring (100-point rubric).

**Anomaly detection thresholds:**
- Engagement drop: >50% below 7-day rolling average
- Follower loss: >2% decrease in 24 hours
- Viral spike: >5x median views within 6 hours
- Failure rate spike: >30% of posts failed in last 7 days
- Sync gap: no snapshots for >2 hours

## Experiment Tracking

Variables: hook_style, posting_time, hashtag_strategy, caption_style, edit_pace, video_length, content_type, text_overlay.

- Default `min_sample_size`: 10 posts per variant
- Preliminary Bayesian signal at 5 posts per variant (flagged as "preliminary")
- Final comparison: Mann-Whitney U test (pure Python, no scipy), p < 0.05
- Bayesian posterior: conjugate normal model, P(B>A), 95% credible intervals

## Zernio API Notes

- Auth: `Authorization: Bearer sk_...` (API key)
- Base URL: `https://zernio.com/api/v1`
- TikTok organic analytics: views, likes, comments, shares only (no reach/impressions)
- 13.1% post failure rate on TikTok via API — content moderation stricter than native app
- No inbox access (comments/DMs), no post editing after publish, no post deletion via API
- No TikTok music library access (except `auto_add_music` for photo carousels)
- TikTok privacy levels: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, FOLLOWER_OF_CREATOR, SELF_ONLY
- Must fetch creator-info before posting to validate allowed privacy levels
- Multi-account posting: one API call with multiple platform entries + customContent per account

## Development Practices

### Testing

- Backend: `pytest` + `pytest-asyncio`. Run from `backend/` with `.venv/bin/python -m pytest -v`
- Test against real SQLite (in-memory). Zernio SDK calls are the only layer that should be mocked.
- Agent tools have integration tests verifying SQL queries and output shapes.
- Statistical functions (Mann-Whitney U, Bayesian posteriors) have tests with known inputs/outputs.

### Commits

- Format: `type(scope): description`
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- Scopes: `accounts`, `posts`, `analytics`, `experiments`, `agent`, `poller`, `zernio`, `dashboard`, `db`

### Code Quality

- All FastAPI endpoints use Pydantic request/response models. No `dict` returns.
- `async def` for all route handlers and service methods.
- SQLAlchemy queries in `services/`, never in `api/` routes.
- Frontend: pages in `src/pages/`, components in `src/components/`, API calls in `src/lib/api.ts`.

## Build Phases

1. ~~Data Foundation~~ — DONE (schema, Zernio SDK, polling, database)
2. ~~Dashboard~~ — DONE (React scaffold, account cards, analytics charts, recharts)
3. ~~Posting + Scheduling~~ — DONE (multi-account posting, file upload via presigned URL, retry, deletion detection)
4. ~~Experiment Engine~~ — DONE (CRUD, Mann-Whitney U, Bayesian posterior, visualization)
5. ~~Agent: Analyst Mode~~ — DONE (8 tools, dual-provider, OpenMontage domain knowledge, chat, insights)
6. AI Content Production — **IN PROGRESS (rebuild #2)**

## Phase 6: AI Content Production Pipeline

### Current Status: FOUNDATION COMPLETE

Rebuilt from scratch on 2026-04-24. Architecture: **Remotion as single rendering engine** for both Workshop preview (`@remotion/player`) and production rendering (`npx remotion render`). Same React components, same props, identical output.

**Key decision**: No timeline editor. Workshop is a parameter tuner (sliders, dropdowns) with live video preview. This avoids the timeline bugs that killed DesignCombo/OpenCut attempts.

### Architecture

```
Workshop (browser)              Production (server)
  Preset Editor ──► video        npx remotion render
  (sliders/forms)   preview          │
                      │    SAME REMOTION    │
                      └─── COMPOSITIONS ────┘
                           (remotion-composer/src/)

Pre-processing: OpenMontage tools (color_grade, trimmer, etc.)
Overlays/Captions: Remotion compositions
```

### What's Built

**Backend (Phase 6a):**
- Models: `VariablePreset`, `Production`, `ProductionVariant` + enums
- Services: `services/openmontage.py` (tool invocation), `services/production.py` (pipeline logic)
- API: `api/presets.py` (CRUD + test), `api/productions.py` (upload, analyze, render, publish)

**Remotion Compositions (Phase 6b):**
- `VariablePreview.tsx` — simple video playback for pre-processed variables
- `VariableCaptions.tsx` — caption style with CaptionOverlay
- `VariableTextOverlay.tsx` — animated text overlays
- `VariableHook.tsx` — hook intro cards with transitions

**Frontend (Phase 6c/d):**
- `Workshop.tsx` — preset list + parameter editor + video preview
- `Production.tsx` — upload, analyze, variant config, render, publish

### UI Navigation

Sidebar: Dashboard | Analytics | Posts | **Workshop** | **Produce** | Lab | Agent | Settings
- `/workshop` — Variable preset editor with live preview
- `/produce` — Mass production pipeline (upload → analyze → configure → render → publish)
- `/lab` — Lab.tsx (Experiments only)
- `/experiments` → redirects to `/lab`

### Variable Types

| Type | Remotion Composition | Pre-process Tool |
|------|---------------------|-----------------|
| color_grade | VariablePreview | color_grade |
| captions | VariableCaptions | transcriber |
| speed | VariablePreview | video_trimmer |
| text_overlay | VariableTextOverlay | none |
| hook_intro | VariableHook | none |
| edit_pace | VariablePreview | silence_cutter |

### What's Next

- End-to-end testing: upload → analyze → configure → render → publish
- Render worker in APScheduler
- Agent tool: `suggest_production_variables`
