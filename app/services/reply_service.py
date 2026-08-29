from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reply import Reply
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.reply import ReplyCreate
from app.services import history_service, permissions


def list_replies_for_ticket(db: Session, ticket_id: int) -> list[Reply]:
    stmt = (
        select(Reply)
        .where(Reply.ticket_id == ticket_id)
        .order_by(Reply.created_at.asc(), Reply.id.asc())
    )
    return list(db.scalars(stmt))


def add_reply(db: Session, ticket: Ticket, author: User, data: ReplyCreate) -> Reply:
    if not permissions.can_act_on_ticket(author, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reply to tickets you're assigned to or collaborating on.",
        )

    reply = Reply(
        ticket_id=ticket.id,
        author_id=author.id,
        body=data.body,
        is_internal=data.is_internal,
    )
    db.add(reply)
    db.flush()  # assigns reply.id, needed by the history row referencing it
    history_service.record_reply(db, ticket, reply, author)
    db.commit()
    db.refresh(reply)
    return reply
