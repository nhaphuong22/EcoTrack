import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter
from pydantic import BaseModel

from src.agent.orchestrator import copilot_orchestrator
from src.agent.experiment_logger import experiment_logger

router = APIRouter(prefix="/internal/copilot", tags=["Energy Copilot"])


class InternalChatRequest(BaseModel):
    message: str
    building_id: str = "office_tower_01"
    history: List[Dict[str, Any]] = []


@router.post("/chat")
async def chat_with_copilot(req: InternalChatRequest):
    """Processes conversational reasoning with ReAct energy tools."""
    reply, tools_used = await asyncio.to_thread(
        copilot_orchestrator.process_chat,
        req.message,
        req.history,
    )
    return {
        "reply": reply,
        "tools_used": tools_used,
    }


@router.get("/experiment-stats")
async def get_experiment_stats():
    """Returns AI Copilot benchmark metrics and telemetry statistics."""
    return experiment_logger.get_summary_statistics()
