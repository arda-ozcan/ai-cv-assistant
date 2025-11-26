from typing import List, Literal, Optional
from pydantic import BaseModel


Role = Literal["system", "assistant", "user"]


class ChatMessage(BaseModel):
    role: Role
    content: str



class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] | None = None
    session_id: Optional[str] = None   # 🔥 frontend’den gelen id
    


class ChatResponse(BaseModel):
    reply: str
 
