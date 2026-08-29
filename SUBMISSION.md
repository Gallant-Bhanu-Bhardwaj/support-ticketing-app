# Submission

Fill this in and commit it. This is the first file we open.

## Links

- **GitHub repository:** <[public repo URL](https://github.com/Gallant-Bhanu-Bhardwaj/support-ticketing-app)>
- **Live application:** <https://support-ticketing-foeo.onrender.com/>

## Notes for the reviewer

<Anything we should know before opening the link — e.g. your host sleeps when idle and the first
request can take up to a minute.>

## Demo credentials

| Role | Email | Password |
|------|-------|----------|
| <role 1> | | |
| <role 2> | | |

## Stack

| Layer | What you used | Why |
|-------|---------------|-----|
| Frontend | Jinja2 server-rendered templates, Bootstrap 5, HTMX, Chart.js (all via CDN) | No SPA needed for a server-rendered CRUD app; HTMX covers the few spots (archive/restore, alert badge) that want a partial update without a full JS build/toolchain |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, Pydantic Settings, python-jose (JWT), passlib + bcrypt | FastAPI's dependency injection made per-request auth (`get_current_user`) and DB session handling straightforward; SQLAlchemy + Alembic keep the schema and its migration history explicit and portable between SQLite and Postgres |
| Database | SQLite locally (`app.db`), Postgres in production (Render-managed) | One `DATABASE_URL` setting selects the backend with no code branching beyond a single connect-args check in `app/core/database.py`; SQLite is zero-setup for local dev, Postgres is what the free hosting tier provides |
| Hosting | Render (Blueprint via `render.yaml`) — one web service (`uvicorn`) plus a managed Postgres database | Free tier covers both a web service and a database with a `DATABASE_URL` wired automatically; `render.yaml` keeps the build/start commands and required env vars (`JWT_SECRET_KEY`, `ENVIRONMENT`, `PYTHON_VERSION`) versioned in the repo |

## Goal checklist

Mark each honestly. Partial is fine — say what is partial.

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Email/password sign-in, JWT in an HTTP-only cookie, supervisor and agent roles. Every mutating route re-checks role/ownership in the service layer (`app/services/permissions.py`), not just in templates — e.g. an agent submitting a ticket assigned to someone else, or trying to reassign a ticket away from themselves, gets a server-side 403. |
| 2 | Tickets | Done | Create/edit with subject, description, requester, priority, category; archive and restore. Archived tickets are excluded from the default queue but keep their full history and are reachable via an "include archived" filter. |
| 3 | Replies inside tickets | Done | Every reply has a body, author, timestamp, and an internal/customer-visible flag; replies are shown in order on the ticket detail page, interleaved with the rest of the timeline (see goal 9). |
| 4 | Ticket lifecycle | Partial | New → Open → Pending → Resolved → Closed is enforced server-side (`lifecycle_service.ALLOWED_TRANSITIONS`); any other move is rejected with an explanatory message. The response clock genuinely pauses for the full duration a ticket sits in Pending (and separately, in Closed) via dedicated period tables, and a Closed ticket can only be reopened within a 7-day window. What's partial: the brief asks for a *customer* reply to auto-move Pending → Open and resume the clock, but this app has no customer accounts — every reply is authored by an agent or supervisor, so a reply is not reliable evidence the customer actually responded. Pending → Open is implemented as a manual, explicit action instead of an automatic side effect of replying (see the comment in `lifecycle_service.py`). |
| 5 | Collaborators | Done | One primary assignee plus any number of collaborators, all of whom can reply and update the ticket; one merged "my tickets" view for every ticket where the current agent is the assignee or a collaborator (`ticket_service.list_my_tickets`). |
| 6 | Finding tickets | Done | Server-side text search over subject/description, filters for status/priority/category/assignee, sort by created date/priority/last update, and pagination with a total match count — all built on one shared query function (`ticket_service.matching_ticket_ids`) so the queue, CSV export, dashboard, and alerts stay consistent. |
| 7 | Acting on many tickets at once | Done | Bulk reassign and bulk close from the queue, with a per-ticket result (succeeded / refused-and-why) rather than an all-or-nothing failure. CSV export respects whatever filters are currently applied to the queue. |
| 8 | A dashboard | Done | Headline counts (open, pending, resolved this week, breaching), breakdowns by status and by agent, and a Chart.js bar chart of tickets resolved per week over the last 8 weeks, fed by a small JSON endpoint. |
| 9 | History you cannot rewrite | Done | One timeline per ticket (`ticket_history_events`) covering every status change (old/new status, actor), every reassignment, and every reply. The service layer only ever inserts rows into this table — no route or service function updates or deletes one, including for supervisors. |
| 10 | SLA alerts | Done | Tickets past or nearing their priority's target response time appear in an alerts list with a nav badge count. An agent can acknowledge an alert for their own ticket, clearing it; the acknowledgement is scoped to a `breach_epoch` derived from the ticket's reopen count, so a dismissed alert reappears automatically if the ticket is reopened and breaches again, with no separate "un-acknowledge" step needed. |

## How much time did you actually spend?

## What would you do next, with another 12 hours?

## What are you least happy with in this codebase, and why?
