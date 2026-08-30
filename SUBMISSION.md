# Submission

Fill this in and commit it. This is the first file we open.

## Links

- **GitHub repository:** <[public repo URL](https://github.com/Gallant-Bhanu-Bhardwaj/support-ticketing-app)>
- **Live application:** <https://support-ticketing-foeo.onrender.com/>

## Notes for the reviewer

This is hosted on Render's free tier, which spins down after inactivity —
Render's own dashboard confirms requests can be delayed by 50+ seconds
after idle periods. If the app seems slow or unresponsive on first load,
wait roughly a minute and reload rather than assuming it's broken.

## Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Supervisor | supervisor@example.com | password123 |
| Agent | agent1@example.com | password123 |
| Agent | agent2@example.com | password123 |

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
| 2 | Tickets | Done | Create/edit with subject, description, requester, priority, category; archive and restore. Archived tickets are excluded from the default queue but keep their full history, and are reachable via a dedicated `/tickets/archived` view. |
| 3 | Replies inside tickets | Done | Every reply has a body, author, timestamp, and an internal/customer-visible flag; replies are shown in order on the ticket detail page, interleaved with the rest of the timeline (see goal 9). |
| 4 | Ticket lifecycle | Done  | New → Open → Pending → Resolved → Closed is enforced server-side (`lifecycle_service.ALLOWED_TRANSITIONS`); any other move is rejected with an explanatory message. The response clock pauses for the full duration a ticket sits in Pending, Closed, or Resolved-but-not-yet-Closed via dedicated period tables, and a Closed ticket can only be reopened within a 7-day window. The brief asks for a *customer* reply to auto-move Pending → Open; this app has no customer accounts, so every reply is authored by an agent/supervisor and isn't reliable evidence the customer responded — Pending → Open is a manual, explicit action instead, a documented decision (see `decisions.md`). |
| 5 | Collaborators | Done | One primary assignee plus any number of collaborators, all of whom can reply and update the ticket; one merged "my tickets" view for every ticket where the current agent is the assignee or a collaborator (`ticket_service.list_my_tickets`). |
| 6 | Finding tickets | Done | Server-side text search over subject/description, filters for status/priority/category/assignee, sort by created date/priority/last update, and pagination with a total match count — all built on one shared query function (`ticket_service.matching_ticket_ids`) so the queue, CSV export, dashboard, and alerts stay consistent. |
| 7 | Acting on many tickets at once | Done | Bulk reassign and bulk close from the queue, with a per-ticket result (succeeded / refused-and-why) rather than an all-or-nothing failure. CSV export respects whatever filters are currently applied to the queue. |
| 8 | A dashboard | Done | Headline counts (open, pending, resolved this week, breaching), breakdowns by status and by agent, and a Chart.js bar chart of tickets resolved per week over the last 8 weeks, fed by a small JSON endpoint. |
| 9 | History you cannot rewrite | Done | One timeline per ticket (`ticket_history_events`) covering every status change (old/new status, actor), every reassignment, and every reply. The service layer only ever inserts rows into this table — no route or service function updates or deletes one, including for supervisors. |
| 10 | SLA alerts | Done | Tickets past or nearing their priority's target response time appear in an alerts list with a nav badge count. An agent can acknowledge an alert for their own ticket, clearing it; the acknowledgement is scoped to a `breach_epoch` derived from the ticket's reopen count, so a dismissed alert reappears automatically if the ticket is reopened and breaches again. |

## How much time did you actually spend?

I estimated ~17-18 hours going in. Reconstructed from git commit
timestamps, the actual work spanned from 12:00 on 2026-08-29 to 00:29 the
following morning roughly 12.5 hours of calendar time, notably under
what I'd expected.

Within that window, goal-by-goal implementation was fast and consistent:
15-25 minutes per goal from prompt to committed, tested code, across all
10 goals. The time that actually added up wasn't writing code it was
review and decision-making around it, a ~3h45m stretch after goal 5
(collaborators) spent on review-pass followups and backfilling
decisions.md, and a further ~3h50m gap before evening deployment work
began. Deployment itself, once started, took under an hour to get right,
including diagnosing and fixing a Python-version mismatch; documentation
took 39 minutes the next morning.

The estimate wasn't wrong about total effort so much as about where the
time would go the code itself was never the bottleneck the review
discipline around each goal was.

## What would you do next, with another 12 hours?

In priority order:

1. Fix the N+1 query pattern behind SLA calculations. `alerts_service`,
   `dashboard_service`, and `export_service` each recompute
   `elapsed_response_time_for_ticket` per ticket in a Python loop, issuing
   3 extra queries per ticket. Correct at this data volume, but the first
   thing that would need to become a single aggregate query at real scale.
2. Add composite indexes. Every table currently has at most single-column
   indexes; the queue/dashboard/alerts filters combine status, priority,
   is_archived, and primary_assignee_id, none of which are covered by a
   matching composite index today.
3. A real dependency upgrade pass. pip-audit found 26 known
   vulnerabilities across 7 packages; the review pass investigated the
   most severe one and left the rest deliberately unfixed because
   upgrading starlette independently risked breaking the app given
   FastAPI's version pin. With more time, the right move is upgrading
   FastAPI itself first, then letting the rest cascade cleanly.
4. Replace the plain ILIKE text search with a real index Postgres
   tsvector/GIN since ILIKE can't use a B-tree index and is a full
   table scan regardless of queue size.


## What are you least happy with in this codebase, and why?
The enum columns tickets.priority/category/status, users.role,
ticket_history_events.event_type have no CHECK constraint at the
database level, confirmed directly against the actual schema, not
assumed. Validity is enforced entirely by Python's Enum type and Pydantic
on the way in. A row inserted via raw SQL with an out-of-range string
would be silently accepted. It's consistent with how the rest of the
authorization and business logic in this app works enforced in the
service layer, not the database — but it's the one place where I'd want
defense in depth, I didn't build a bad value getting in through anything
other than the app's own routes has no second line of defense.
