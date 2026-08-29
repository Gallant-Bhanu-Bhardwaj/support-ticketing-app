from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime
from app.models.ticket import TicketStatus

if TYPE_CHECKING:
    from app.models.reply import Reply
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketHistoryEventType(str, enum.Enum):
    STATUS_CHANGE = "status_change"
    REASSIGNMENT = "reassignment"
    REPLY = "reply"


def _string_enum(enum_cls: type[enum.Enum], length: int) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class TicketHistoryEvent(Base):
    """Append-only. There is deliberately no update or delete path anywhere
    in the codebase for this table -- app.services.history_service exposes
    creation functions only, called as a side effect of the real action
    (a status transition, a reassignment, a reply), never on their own."""

    __tablename__ = "ticket_history_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[TicketHistoryEventType] = mapped_column(
        _string_enum(TicketHistoryEventType, 20), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    # Only set when event_type == STATUS_CHANGE
    old_status: Mapped[TicketStatus | None] = mapped_column(_string_enum(TicketStatus, 20), nullable=True)
    new_status: Mapped[TicketStatus | None] = mapped_column(_string_enum(TicketStatus, 20), nullable=True)

    # Only set when event_type == REASSIGNMENT
    old_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    new_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Only set when event_type == REPLY -- references the actual reply
    # rather than duplicating its body/is_internal onto this row.
    reply_id: Mapped[int | None] = mapped_column(ForeignKey("replies.id"), nullable=True)

    ticket: Mapped["Ticket"] = relationship()
    actor: Mapped["User"] = relationship(foreign_keys=[actor_id])
    old_assignee: Mapped["User | None"] = relationship(foreign_keys=[old_assignee_id])
    new_assignee: Mapped["User | None"] = relationship(foreign_keys=[new_assignee_id])
    reply: Mapped["Reply | None"] = relationship()
