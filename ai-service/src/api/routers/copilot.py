import json
import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
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
    """Processes conversational reasoning with ReAct energy tools, RAG, and multi-turn history."""
    reply, tools_used, sources, engine = await asyncio.to_thread(
        copilot_orchestrator.process_chat,
        req.message,
        req.history,
    )
    return {
        "reply": reply,
        "tools_used": tools_used,
        "sources": sources,
        "engine": engine,
    }


@router.post("/chat/stream")
async def chat_with_copilot_stream(req: InternalChatRequest):
    """Streams token-by-token Copilot answer over Server-Sent Events (SSE)."""
    async def event_generator():
        try:
            async for event in copilot_orchestrator.stream_chat(req.message, req.history):
                event_type = event.get("type", "token")
                data_json = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data_json}\n\n"
        except Exception as err:
            err_json = json.dumps({"error": str(err)}, ensure_ascii=False)
            yield f"event: error\ndata: {err_json}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/experiment-stats")
async def get_experiment_stats():
    """Returns AI Copilot benchmark metrics and telemetry statistics."""
    return experiment_logger.get_summary_statistics()
