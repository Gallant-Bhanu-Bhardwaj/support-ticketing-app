# CLAUDE.md — BUSY Infotech Support Ticketing (Take-Home Assignment)

## Source of truth

`README.md` in this repository is the complete and only source of
requirements. Read the relevant section of it fresh before implementing each
goal — do not rely on a paraphrase or your memory of an earlier read,
including anything below. Never invent, remove, or weaken a requirement from
it. If something seems ambiguous or underspecified, say so and propose an
option rather than silently deciding.

This is a hiring assignment. Correctness, maintainability, security, test
coverage, and genuine incremental git history all matter, in addition to the
app working.

## Who you're working with

I'm primarily a Python/AI developer, more comfortable with Python than
JavaScript/TypeScript. Keep the implementation simple, readable, idiomatic
Python — prefer boring and explicit over clever.

## Required stack — use only this

**Backend:** Python 3.12+, FastAPI, Uvicorn
**Database:** SQLite for local dev, PostgreSQL-compatible design for
production, SQLAlchemy 2.0, Alembic for migrations
**Validation/config:** Pydantic v2, pydantic-settings, python-dotenv where
appropriate
**Auth/security:** JWT, passlib/bcrypt (or the current standard-appropriate
package) for password hashing, authorization enforced server-side
**Frontend:** Jinja2, HTMX, Bootstrap 5, Chart.js — server-rendered, no SPA
**Testing:** pytest, pytest-asyncio where required, httpx/TestClient
**Other:** standard library `csv` for export, Git/GitHub, Render-compatible
deployment

## Do not introduce

React, Next.js, a Node.js backend, Express, TypeScript, Prisma, MongoDB,
Redux, GraphQL, or unnecessary microservices. The frontend stays
server-rendered Jinja2, enhanced with HTMX. This was already decided — don't
revisit it.

## Known trip points

These goals have exact rules in README.md that are easy to implement only
partially right. Re-read the relevant paragraph before touching the code, not
just once at the start of the project:

- The ticket lifecycle's response clock, and exactly how Pending affects it
- What must happen, and be reported back, on a bulk action
- What makes the audit timeline genuinely immutable, not just unedited by the UI
- When a dismissed SLA alert is and isn't allowed to reappear
- Where authorization is enforced — server, not just hidden in a template

## Process rules

- Implement one goal (or the scaffold) per session — wait for review between
  goals rather than chaining several together unprompted.
- Every business rule and permission check is enforced in route/service code,
  never only in a template or the frontend.
- Any illegal or disallowed action is rejected by the server with a message
  explaining why — never a silent no-op or a generic 400.
- Add or extend pytest tests for every goal you implement, including the edge
  cases README.md calls out explicitly, before considering it done.
- Commit after each working feature with a message describing what changed
  and why — never batch multiple goals into one commit.
- Keep secrets in `.env`, never in code or committed to the repo.

## Docs — what you may and may not write

You may draft `docs/architecture.md` and `docs/schema.md` when asked, based
strictly on the code as it actually exists in the repo — not aspirational
design.

Do not write `docs/decisions.md`, `docs/plan.md`, or `docs/ai-prompts.md`
under any circumstances, even if asked to "help" with them. Those are my own
record of decisions, sessions, and prompts, and need to come from me.

## Scope

The 10 numbered goals in README.md are the entire scope. Stretch ideas are
optional and only relevant after all 10 goals are solidly done — do not start
on one unless I ask.

## Project layout (once scaffolded)

    app/
      models/       SQLAlchemy models
      schemas/       Pydantic schemas
      routers/       FastAPI route modules
      services/      business logic / state machine / SLA calculations
      core/          config, security, dependencies
      templates/     Jinja2 templates
      static/        CSS/JS assets (Bootstrap, HTMX, Chart.js via CDN unless noted)
    tests/
    alembic/
    docs/

## Common commands (once scaffolded)

    source .venv/bin/activate
    uvicorn app.main:app --reload
    pytest
    alembic revision --autogenerate -m "message"
    alembic upgrade head
