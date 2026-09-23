import asyncio
from fastapi import APIRouter
from src.api.schemas.copilot import CopilotChatRequest, CopilotChatResponse
from src.agent.orchestrator import copilot_orchestrator

router = APIRouter(prefix="/api/v1/copilot", tags=["LLM Energy Copilot"])

@router.post("/chat", response_model=CopilotChatResponse)
async def chat_with_copilot(req: CopilotChatRequest):
    # Process reasoning in background thread so server event loop remains responsive
    history_dicts = [h.model_dump() for h in req.history]
    reply, tools_used = await asyncio.to_thread(
        copilot_orchestrator.process_chat,
        req.message,
        history_dicts
    )
    return CopilotChatResponse(
        reply=reply,
        tools_used=tools_used
    )
