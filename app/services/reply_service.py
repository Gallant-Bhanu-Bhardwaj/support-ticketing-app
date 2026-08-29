from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reply import Reply
from app.models.user import User
from app.schemas.reply import ReplyCreate


def list_replies_for_ticket(db: Session, ticket_id: int) -> list[Reply]:
    stmt = (
        select(Reply)
        .where(Reply.ticket_id == ticket_id)
        .order_by(Reply.created_at.asc(), Reply.id.asc())
    )
    return list(db.scalars(stmt))


def add_reply(db: Session, ticket_id: int, author: User, data: ReplyCreate) -> Reply:
    reply = Reply(
        ticket_id=ticket_id,
        author_id=author.id,
        body=data.body,
        is_internal=data.is_internal,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply
