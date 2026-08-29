from pydantic import BaseModel, Field

from app.models.ticket import TicketCategory, TicketPriority


class TicketWrite(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requester: str = Field(min_length=1, max_length=255)
    priority: TicketPriority
    category: TicketCategory
