from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TicketCollaborator(Base):
    """Many-to-many join: any number of agents can collaborate on a ticket,
    and one agent can collaborate on any number of tickets."""

    __tablename__ = "ticket_collaborators"

    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
