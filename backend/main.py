"""TikTok Lab — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from services.poller import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="TikTok Lab",
    description="Multi-account TikTok dashboard with AI agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from api.accounts import router as accounts_router
from api.analytics import router as analytics_router
from api.posts import router as posts_router
from api.experiments import router as experiments_router
from api.agent import router as agent_router
from api.presets import router as presets_router
from api.productions import router as productions_router
app.include_router(accounts_router)
app.include_router(analytics_router)
app.include_router(posts_router)
app.include_router(experiments_router)
app.include_router(agent_router)
app.include_router(presets_router)
app.include_router(productions_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
