from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str # "user" or "assistant" or "system"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None

class CopilotChatRequest(BaseModel):
    message: str
    building_id: str = "office_tower_01"
    history: List[ChatMessage] = []

class CopilotChatResponse(BaseModel):
    reply: str
    tools_used: List[str] = []
