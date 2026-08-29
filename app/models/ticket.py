from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.reply import Reply


class TicketPriority(str, enum.Enum):
    """Drives the SLA target response time once goal 4 adds the lifecycle clock."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, enum.Enum):
    BUG = "bug"
    BILLING = "billing"
    HOW_TO = "how_to"
    FEATURE_REQUEST = "feature_request"
    OTHER = "other"


class TicketStatus(str, enum.Enum):
    """Full lifecycle is defined here so the column supports every state up
    front, but transition rules (goal 4) aren't enforced yet -- this goal
    only ever sets NEW on create."""

    NEW = "new"
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


def _string_enum(enum_cls: type[enum.Enum], length: int) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requester: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[TicketPriority] = mapped_column(_string_enum(TicketPriority, 20), nullable=False)
    category: Mapped[TicketCategory] = mapped_column(_string_enum(TicketCategory, 30), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        _string_enum(TicketStatus, 20), nullable=False, default=TicketStatus.NEW
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    replies: Mapped[list["Reply"]] = relationship(
        back_populates="ticket", order_by="Reply.created_at"
    )
