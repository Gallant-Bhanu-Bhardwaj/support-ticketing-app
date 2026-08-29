from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.templates import templates
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services import collaborator_service, lifecycle_service, reply_service, ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _list_agents(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == UserRole.AGENT).order_by(User.email)))


def _form_choices(db: Session, current_user: User) -> dict:
    return {
        "priorities": list(TicketPriority),
        "categories": list(TicketCategory),
        "agents": _list_agents(db),
        "current_user": current_user,
    }


@router.get("")
def list_active(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tickets = ticket_service.list_tickets(db, archived=False, viewer=current_user)
    return templates.TemplateResponse(request, "tickets/list.html", {"tickets": tickets})


@router.get("/archived")
def list_archived(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tickets = ticket_service.list_tickets(db, archived=True, viewer=current_user)
    return templates.TemplateResponse(request, "tickets/archived.html", {"tickets": tickets})


@router.get("/mine")
def list_mine(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tickets = ticket_service.list_my_tickets(db, current_user.id)
    return templates.TemplateResponse(request, "tickets/mine.html", {"tickets": tickets})


@router.get("/new")
def new_form(
    request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request, "tickets/form.html", {"ticket": None, **_form_choices(db, current_user)}
    )


@router.post("")
def create(
    request: Request,
    ticket_in: Annotated[TicketCreate, Form()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.create_ticket(db, ticket_in, current_user)
    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=303)


@router.get("/{ticket_id}")
def detail(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_viewable_ticket_or_404(db, ticket_id, current_user)
    replies = reply_service.list_replies_for_ticket(db, ticket_id)
    available_agents = collaborator_service.available_agents_for_ticket(db, ticket)
    return templates.TemplateResponse(
        request,
        "tickets/detail.html",
        {
            "ticket": ticket,
            "replies": replies,
            "current_user": current_user,
            "available_agents": available_agents,
        },
    )


@router.get("/{ticket_id}/edit")
def edit_form(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    return templates.TemplateResponse(
        request, "tickets/form.html", {"ticket": ticket, **_form_choices(db, current_user)}
    )


@router.post("/{ticket_id}")
def edit(
    ticket_id: int,
    request: Request,
    ticket_in: Annotated[TicketUpdate, Form()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    ticket_service.update_ticket(db, ticket, ticket_in, current_user)
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@router.post("/{ticket_id}/status")
def change_status(
    ticket_id: int,
    request: Request,
    new_status: Annotated[TicketStatus, Form()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    try:
        lifecycle_service.transition(db, ticket, new_status, current_user)
    except HTTPException as exc:
        replies = reply_service.list_replies_for_ticket(db, ticket_id)
        available_agents = collaborator_service.available_agents_for_ticket(db, ticket)
        return templates.TemplateResponse(
            request,
            "tickets/detail.html",
            {
                "ticket": ticket,
                "replies": replies,
                "current_user": current_user,
                "available_agents": available_agents,
                "status_error": exc.detail,
            },
            status_code=exc.status_code,
        )
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@router.post("/{ticket_id}/archive")
def archive(
    ticket_id: int,
    request: Request,
    render: str = "panel",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    ticket = ticket_service.archive_ticket(db, ticket, current_user)
    return _archive_response(request, ticket, render)


@router.post("/{ticket_id}/restore")
def restore(
    ticket_id: int,
    request: Request,
    render: str = "panel",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    ticket = ticket_service.restore_ticket(db, ticket, current_user)
    return _archive_response(request, ticket, render)


def _archive_response(request: Request, ticket, render: str):
    if request.headers.get("HX-Request"):
        if render == "none":
            return HTMLResponse("")
        return templates.TemplateResponse(request, "tickets/partials/actions.html", {"ticket": ticket})
    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=303)
