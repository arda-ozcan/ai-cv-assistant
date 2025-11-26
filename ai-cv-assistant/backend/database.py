from datetime import datetime
from pydantic import BaseModel

class ChatLog(BaseModel):
    user_message: str
    assistant_reply: str
    timestamp: datetime = datetime.utcnow()
