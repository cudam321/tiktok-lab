"""AI agent service — supports both Anthropic (Claude) and OpenAI with tool use."""

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import AgentConversation, AgentInsight, InsightType, InsightPriority
from agent.tools import TOOL_DEFINITIONS, execute_tool
from agent.prompts import ANALYST_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_CONVERSATION_MESSAGES = 20
MAX_TOOL_ROUNDS = 5


def _get_provider() -> str:
    """Determine which AI provider to use."""
    if settings.agent_provider != "auto":
        return settings.agent_provider
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.openai_api_key:
        return "openai"
    return "none"


async def chat(db: AsyncSession, user_message: str) -> str:
    """Process a user chat message through the agent with tool use."""
    await _save_message(db, "user", user_message)
    history = await _get_conversation_history(db)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    assistant_text = await _run_agent_loop(db, messages)

    await _save_message(db, "assistant", assistant_text)
    await _trim_conversation(db)
    return assistant_text


async def run_proactive(db: AsyncSession, prompt: str, insight_type: InsightType) -> AgentInsight | None:
    """Run a proactive agent task (briefing, anomaly scan) and save as insight."""
    messages = [{"role": "user", "content": prompt}]

    try:
        text = await _run_agent_loop(db, messages)
    except Exception as e:
        logger.error(f"Proactive agent run failed: {e}")
        return None

    if not text or text.strip().lower() == "no anomalies detected.":
        return None

    priority = InsightPriority.medium
    if insight_type == InsightType.alert:
        priority = InsightPriority.high
    elif insight_type == InsightType.briefing:
        priority = InsightPriority.low

    lines = text.strip().split("\n")
    title = lines[0][:120] if lines else "Agent Insight"
    title = title.lstrip("#").strip()

    insight = AgentInsight(
        type=insight_type,
        title=title,
        body=text,
        priority=priority,
    )
    db.add(insight)
    await db.commit()
    await db.refresh(insight)
    logger.info(f"Saved {insight_type.value} insight: {title[:60]}")
    return insight


async def get_insights(
    db: AsyncSession,
    insight_type: InsightType | None = None,
    unread_only: bool = False,
    limit: int = 20,
) -> list[AgentInsight]:
    query = select(AgentInsight).order_by(AgentInsight.created_at.desc()).limit(limit)
    if insight_type:
        query = query.where(AgentInsight.type == insight_type)
    if unread_only:
        query = query.where(AgentInsight.is_read == False)
    return list((await db.execute(query)).scalars().all())


async def mark_insight_read(db: AsyncSession, insight_id: int) -> bool:
    insight = (
        await db.execute(select(AgentInsight).where(AgentInsight.id == insight_id))
    ).scalar_one_or_none()
    if not insight:
        return False
    insight.is_read = True
    await db.commit()
    return True


# --- Agent Loop (dispatches to provider) ---


async def _run_agent_loop(db: AsyncSession, messages: list[dict]) -> str:
    provider = _get_provider()
    if provider == "anthropic":
        return await _run_anthropic(db, messages)
    elif provider == "openai":
        return await _run_openai(db, messages)
    else:
        return "Agent not configured — set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env to enable AI features."


# --- Anthropic (Claude) ---


async def _run_anthropic(db: AsyncSession, messages: list[dict]) -> str:
    api_key = settings.anthropic_api_key
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOL_DEFINITIONS
    ]

    text_parts: list[str] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for _round in range(MAX_TOOL_ROUNDS):
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 4096,
                    "system": ANALYST_SYSTEM_PROMPT,
                    "tools": tools,
                    "messages": messages,
                },
            )

            if response.status_code != 200:
                logger.error(f"Anthropic API error {response.status_code}: {response.text}")
                return f"Agent error: API returned {response.status_code}"

            data = response.json()
            stop_reason = data.get("stop_reason")
            content_blocks = data.get("content", [])

            text_parts = []
            tool_uses = []
            for block in content_blocks:
                if block["type"] == "text":
                    text_parts.append(block["text"])
                elif block["type"] == "tool_use":
                    tool_uses.append(block)

            if stop_reason == "end_turn" or not tool_uses:
                return "\n".join(text_parts) or "No response generated."

            messages.append({"role": "assistant", "content": content_blocks})

            tool_results = []
            for tool_use in tool_uses:
                result = await execute_tool(db, tool_use["name"], tool_use.get("input", {}))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use["id"],
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})

    return "\n".join(text_parts) if text_parts else "Agent completed without response."


# --- OpenAI ---


async def _run_openai(db: AsyncSession, messages: list[dict]) -> str:
    api_key = settings.openai_api_key

    # Convert tool definitions to OpenAI function format
    tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOL_DEFINITIONS
    ]

    # Prepend system message
    openai_messages: list[dict] = [
        {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
    ]
    for m in messages:
        openai_messages.append({"role": m["role"], "content": m["content"]})

    async with httpx.AsyncClient(timeout=60.0) as client:
        for _round in range(MAX_TOOL_ROUNDS):
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "max_tokens": 4096,
                    "tools": tools,
                    "messages": openai_messages,
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                return f"Agent error: API returned {response.status_code}"

            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")

            # Append assistant message to history
            openai_messages.append(message)

            tool_calls = message.get("tool_calls")

            if finish_reason == "stop" or not tool_calls:
                return message.get("content") or "No response generated."

            # Process tool calls
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}

                result = await execute_tool(db, func_name, func_args)

                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, default=str),
                })

    return message.get("content", "") if "message" in dir() else "Agent completed without response."


# --- Conversation Management ---


async def _save_message(db: AsyncSession, role: str, content: str):
    msg = AgentConversation(role=role, content=content)
    db.add(msg)
    await db.commit()


async def _get_conversation_history(db: AsyncSession) -> list[dict]:
    messages = (
        await db.execute(
            select(AgentConversation)
            .order_by(AgentConversation.created_at.desc())
            .limit(MAX_CONVERSATION_MESSAGES)
        )
    ).scalars().all()

    return [
        {"role": m.role, "content": m.content}
        for m in reversed(messages)
    ]


async def _trim_conversation(db: AsyncSession):
    """Keep only the last MAX_CONVERSATION_MESSAGES messages."""
    count = (await db.execute(select(func.count(AgentConversation.id)))).scalar_one()
    if count > MAX_CONVERSATION_MESSAGES:
        oldest = (
            await db.execute(
                select(AgentConversation)
                .order_by(AgentConversation.created_at)
                .limit(count - MAX_CONVERSATION_MESSAGES)
            )
        ).scalars().all()
        for msg in oldest:
            await db.delete(msg)
        await db.commit()
