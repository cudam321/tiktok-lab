"""Proactive agent runs — daily briefings and anomaly scans."""

import logging

from db.database import async_session
from db.models import InsightType
from services.agent_service import run_proactive
from agent.prompts import DAILY_BRIEFING_PROMPT, ANOMALY_SCAN_PROMPT

logger = logging.getLogger(__name__)


async def daily_briefing():
    """Run daily briefing (scheduled at 8am)."""
    logger.info("Running daily briefing...")
    async with async_session() as db:
        await run_proactive(db, DAILY_BRIEFING_PROMPT, InsightType.briefing)


async def anomaly_scan():
    """Run anomaly scan (every 2 hours)."""
    logger.info("Running anomaly scan...")
    async with async_session() as db:
        await run_proactive(db, ANOMALY_SCAN_PROMPT, InsightType.alert)
