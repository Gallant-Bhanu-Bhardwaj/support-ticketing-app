from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime


class SlaAcknowledgement(Base):
    """An agent/collaborator/supervisor dismissing one alert, for one
    breach instance. `breach_epoch` is how many times the ticket has been
    reopened from Closed so far (see alerts_service.current_breach_epoch) --
    scoping the ack to that number, rather than a permanent flag on the
    ticket, is what lets the alert come back after a reopen re-breaches:
    the old ack's epoch no longer matches the ticket's current one."""

    __tablename__ = "sla_acknowledgements"
    __table_args__ = (
        UniqueConstraint("ticket_id", "user_id", "breach_epoch", name="uq_sla_ack_ticket_user_epoch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    breach_epoch: Mapped[int] = mapped_column(nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
