import math
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.templates import templates
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services import (
    bulk_service,
    collaborator_service,
    export_service,
    history_service,
    lifecycle_service,
    ticket_service,
)

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


def _parse_enum_filter(raw: str | None, enum_cls):
    """Query params come from a <select> whose reset option is value="" --
    that must mean "no filter", not a 422 from trying to parse "" as a member."""
    if not raw:
        return None
    try:
        return enum_cls(raw)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"'{raw}' is not a valid value for this filter.",
        )


def _parse_int_filter(raw: str | None):
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"'{raw}' is not a valid id.")


def _parse_filters(status: str | None, priority: str | None, category: str | None, assignee_id: str | None):
    return (
        _parse_enum_filter(status, TicketStatus),
        _parse_enum_filter(priority, TicketPriority),
        _parse_enum_filter(category, TicketCategory),
        _parse_int_filter(assignee_id),
    )


@router.get("")
def list_active(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    assignee_id: str | None = None,
    sort: Literal["created", "priority", "updated"] = "created",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status_filter, priority_filter, category_filter, assignee_filter = _parse_filters(
        status, priority, category, assignee_id
    )

    tickets, total = ticket_service.search_tickets(
        db,
        current_user,
        archived=False,
        search=q,
        status_filter=status_filter,
        priority_filter=priority_filter,
        category_filter=category_filter,
        assignee_id=assignee_filter,
        sort=sort,
        direction=direction,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, math.ceil(total / page_size))

    base_params = {"sort": sort, "direction": direction, "page_size": page_size}
    if q:
        base_params["q"] = q
    if status_filter:
        base_params["status"] = status_filter.value
    if priority_filter:
        base_params["priority"] = priority_filter.value
    if category_filter:
        base_params["category"] = category_filter.value
    if assignee_filter:
        base_params["assignee_id"] = assignee_filter

    return templates.TemplateResponse(
        request,
        "tickets/list.html",
        {
            "tickets": tickets,
            "current_user": current_user,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "q": q or "",
            "status": status_filter,
            "priority": priority_filter,
            "category": category_filter,
            "assignee_id": assignee_filter,
            "sort": sort,
            "direction": direction,
            "statuses": list(TicketStatus),
            "priorities": list(TicketPriority),
            "categories": list(TicketCategory),
            "agents": _list_agents(db),
            "base_query_string": urlencode(base_params),
        },
    )


@router.get("/export.csv")
def export_csv(
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    assignee_id: str | None = None,
    sort: Literal["created", "priority", "updated"] = "created",
    direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exports every ticket matching the current filters, not just the
    visible page -- reuses ticket_service's filter/scope logic directly
    rather than re-deriving it here."""
    status_filter, priority_filter, category_filter, assignee_filter = _parse_filters(
        status, priority, category, assignee_id
    )

    tickets = ticket_service.all_matching_tickets(
        db,
        current_user,
        archived=False,
        search=q,
        status_filter=status_filter,
        priority_filter=priority_filter,
        category_filter=category_filter,
        assignee_id=assignee_filter,
        sort=sort,
        direction=direction,
    )
    csv_content = export_service.tickets_to_csv(db, tickets)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets.csv"},
    )


@router.post("/bulk/reassign")
def bulk_reassign(
    request: Request,
    new_assignee_id: Annotated[int, Form()],
    ticket_ids: Annotated[list[int], Form()] = [],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="Select at least one ticket.")

    results = bulk_service.bulk_reassign(db, ticket_ids, new_assignee_id, current_user)
    return templates.TemplateResponse(
        request, "tickets/bulk_result.html", {"action": "Reassign", "results": results}
    )


@router.post("/bulk/close")
def bulk_close(
    request: Request,
    ticket_ids: Annotated[list[int], Form()] = [],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="Select at least one ticket.")

    results = bulk_service.bulk_close(db, ticket_ids, current_user)
    return templates.TemplateResponse(
        request, "tickets/bulk_result.html", {"action": "Close", "results": results}
    )


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
    timeline = history_service.list_timeline(db, ticket_id)
    available_agents = collaborator_service.available_agents_for_ticket(db, ticket)
    return templates.TemplateResponse(
        request,
        "tickets/detail.html",
        {
            "ticket": ticket,
            "timeline": timeline,
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
    ticket = ticket_service.get_editable_ticket_or_404(db, ticket_id, current_user)
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
        timeline = history_service.list_timeline(db, ticket_id)
        available_agents = collaborator_service.available_agents_for_ticket(db, ticket)
        return templates.TemplateResponse(
            request,
            "tickets/detail.html",
            {
                "ticket": ticket,
                "timeline": timeline,
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
