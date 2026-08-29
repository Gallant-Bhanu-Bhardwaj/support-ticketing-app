from pydantic import BaseModel, Field

from app.models.ticket import TicketCategory, TicketPriority


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requester: str = Field(min_length=1, max_length=255)
    priority: TicketPriority
    category: TicketCategory
    # Optional here because whether it's required depends on the actor's role
    # (agents default to self, supervisors must pick) -- that role-dependent
    # logic lives in ticket_service.create_ticket, not in this schema.
    primary_assignee_id: int | None = None


class TicketUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requester: str = Field(min_length=1, max_length=255)
    priority: TicketPriority
    category: TicketCategory
    # Always present in the form (a live <select> for supervisors, a hidden
    # field carrying the unchanged value for agents), so this is required --
    # ticket_service.update_ticket only treats it as a reassignment attempt
    # when it differs from the ticket's current assignee.
    primary_assignee_id: int
