"""Agent chat endpoint and insight feed."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import InsightType, InsightPriority
from services import agent_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


# --- Models ---


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class InsightResponse(BaseModel):
    id: int
    type: InsightType
    title: str
    body: str
    priority: InsightPriority
    is_read: bool
    is_acted_on: bool
    account_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Routes ---


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a message to the AI agent and get a response."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    response = await agent_service.chat(db, body.message.strip())
    return ChatResponse(response=response)


@router.get("/insights", response_model=list[InsightResponse])
async def list_insights(
    type: InsightType | None = None,
    unread_only: bool = False,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    insights = await agent_service.get_insights(db, type, unread_only, limit)
    return [InsightResponse.model_validate(i) for i in insights]


@router.post("/insights/{insight_id}/read")
async def mark_read(insight_id: int, db: AsyncSession = Depends(get_db)):
    success = await agent_service.mark_insight_read(db, insight_id)
    if not success:
        raise HTTPException(status_code=404, detail="Insight not found")
    return {"detail": "Marked as read"}


@router.post("/briefing")
async def trigger_briefing(db: AsyncSession = Depends(get_db)):
    """Manually trigger a daily briefing."""
    from agent.prompts import DAILY_BRIEFING_PROMPT

    insight = await agent_service.run_proactive(db, DAILY_BRIEFING_PROMPT, InsightType.briefing)
    if not insight:
        return {"detail": "Briefing generated no actionable content"}
    return InsightResponse.model_validate(insight)


@router.post("/scan")
async def trigger_anomaly_scan(db: AsyncSession = Depends(get_db)):
    """Manually trigger an anomaly scan."""
    from agent.prompts import ANOMALY_SCAN_PROMPT

    insight = await agent_service.run_proactive(db, ANOMALY_SCAN_PROMPT, InsightType.alert)
    if not insight:
        return {"detail": "No anomalies detected"}
    return InsightResponse.model_validate(insight)
