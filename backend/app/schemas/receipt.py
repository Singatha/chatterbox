from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ReceiptEventData(BaseModel):
    message_id: UUID
    conversation_id: UUID
    user_id: UUID
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]

