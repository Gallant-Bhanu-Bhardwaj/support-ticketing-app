from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime


class TicketPendingPeriod(Base):
    """One stretch of time a ticket spent in Pending. `ended_at` is null while
    the ticket is still pending. The response clock excludes the whole span
    -- this is the log the clock is computed from, not a pause flag."""

    __tablename__ = "ticket_pending_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class TicketClosedPeriod(Base):
    """One stretch of time a ticket spent Closed. `reopened_at` is null while
    still closed. Symmetric to TicketPendingPeriod: excluded from the clock so
    a ticket reopened after sitting closed for weeks doesn't instantly show as
    breaching its target."""

    __tablename__ = "ticket_closed_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    closed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    reopened_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class TicketResolvedPeriod(Base):
    """One stretch of time a ticket spent Resolved. `ended_at` is null while
    still sitting in Resolved (the only legal exit is Resolved -> Closed, so
    it ends exactly when a TicketClosedPeriod begins). Once resolved, the
    customer already has their response -- the clock should stop, the same
    way it stops for Closed, not keep running until someone gets around to
    the administrative step of closing the ticket."""

    __tablename__ = "ticket_resolved_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
