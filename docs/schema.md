# Schema

Nine tables, ten linear Alembic migrations. Every timestamp column uses the
custom `UTCDateTime` type (`app/core/database.py`), not a plain
`DateTime(timezone=True)` — see `architecture.md` for why.

## Tables

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK | |
| `email` | `VARCHAR(255)` | `UNIQUE`, indexed, not null |
| `hashed_password` | `VARCHAR(255)` | bcrypt hash, not null |
| `role` | `VARCHAR(20)` | `"supervisor"` \| `"agent"`, not null |
| `created_at` | `DATETIME` | server default `now()` |

### `tickets`

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK | |
| `subject` | `VARCHAR(255)` | not null |
| `description` | `TEXT` | not null |
| `requester` | `VARCHAR(255)` | free text — name/email of the customer; customers have no `users` row at all |
| `priority` | `VARCHAR(20)` | `low`\|`normal`\|`high`\|`urgent`, not null |
| `category` | `VARCHAR(30)` | `bug`\|`billing`\|`how_to`\|`feature_request`\|`other`, not null |
| `status` | `VARCHAR(20)` | `new`\|`open`\|`pending`\|`resolved`\|`closed`, not null, defaults to `new` |
| `is_archived` | `BOOLEAN` | not null, defaults `false` |
| `primary_assignee_id` | `INTEGER` FK → `users.id` | not null — must be an agent, enforced only in `ticket_service.ensure_valid_assignee`, not by the FK itself |
| `created_at` | `DATETIME` | server default `now()` |
| `updated_at` | `DATETIME` | server default `now()`, updated on every ORM-level write |
| `resolved_at` | `DATETIME` | nullable; set on every entry into `Resolved`, overwritten on re-resolution after a reopen |

### `replies`

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK | |
| `ticket_id` | `INTEGER` FK → `tickets.id` | not null, indexed |
| `author_id` | `INTEGER` FK → `users.id` | not null |
| `body` | `TEXT` | not null |
| `is_internal` | `BOOLEAN` | not null, defaults `false` |
| `created_at` | `DATETIME` | server default `now()` |

### `ticket_collaborators`

Pure many-to-many join table, no surrogate key:

| Column | Type | Notes |
|---|---|---|
| `ticket_id` | `INTEGER` FK → `tickets.id`, part of composite PK | |
| `user_id` | `INTEGER` FK → `users.id`, part of composite PK | |

The composite primary key is also what prevents the same user being added
as a collaborator on the same ticket twice at the database level — the
duplicate-collaborator rejection in `collaborator_service.add_collaborator`
is a nicer error message in front of a constraint that would fail anyway.

### `ticket_pending_periods`, `ticket_closed_periods`, `ticket_resolved_periods`

Three structurally identical tables — one stretch of time logged per row,
`ended_at`/`reopened_at` null while the span is still open:

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK | |
| `ticket_id` | `INTEGER` FK → `tickets.id` | not null, indexed |
| `started_at` / `closed_at` | `DATETIME` | not null (column is named `closed_at` on `ticket_closed_periods`, `started_at` on the other two) |
| `ended_at` / `reopened_at` | `DATETIME` | nullable (named `reopened_at` on `ticket_closed_periods`) |

These three are the entire mechanism behind the SLA response clock —
`elapsed_response_time()` is wall-clock time since `tickets.created_at`,
minus every logged Pending/Closed/Resolved span. Nothing is ever "paused" in
memory; the clock is a pure function over these rows plus `as_of`.

### `ticket_history_events`

One append-only row per status change, reassignment, or reply:

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK | |
| `ticket_id` | `INTEGER` FK → `tickets.id` | not null, indexed |
| `actor_id` | `INTEGER` FK → `users.id` | not null — who did it |
| `event_type` | `VARCHAR(20)` | `status_change`\|`reassignment`\|`reply` |
| `created_at` | `DATETIME` | server default `now()` |
| `old_status` / `new_status` | `VARCHAR(20)`, nullable | set only when `event_type = status_change` |
| `old_assignee_id` / `new_assignee_id` | `INTEGER` FK → `users.id`, nullable | set only when `event_type = reassignment` |
| `reply_id` | `INTEGER` FK → `replies.id`, nullable | set only when `event_type = reply`; the row's body/internal-flag live on `replies`, not duplicated here |

This is one polymorphic table with three payload shapes sharing a row,
rather than three separate event tables unioned together for the timeline
view — see "Denormalization" below.

### `sla_acknowledgements`

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` PK | |
| `ticket_id` | `INTEGER` FK → `tickets.id` | not null, indexed |
| `user_id` | `INTEGER` FK → `users.id` | not null, indexed |
| `breach_epoch` | `INTEGER` | not null — how many times this ticket has been reopened from Closed so far |
| `acknowledged_at` | `DATETIME` | server default `now()` |
| — | `UNIQUE(ticket_id, user_id, breach_epoch)` | table-level constraint |

`breach_epoch` is what lets a dismissed alert reappear after a reopen: it's
computed on read as `COUNT(*)` of `ticket_closed_periods` rows with a
non-null `reopened_at`, not stored redundantly on the ticket itself.

## One-to-many vs many-to-many

- **One-to-many:** `users` → `tickets` (as `primary_assignee`), `users` →
  `replies` (as `author`), `tickets` → `replies`, `tickets` → each of the
  three period tables, `tickets` → `ticket_history_events`, `users` →
  `ticket_history_events` (as `actor`, and separately as `old_assignee` /
  `new_assignee` — two more nullable FKs to the same table), `tickets` →
  `sla_acknowledgements`, `users` → `sla_acknowledgements`.
- **Many-to-many:** `users` ↔ `tickets` via `ticket_collaborators` — any
  number of agents can collaborate on a ticket, one agent can collaborate on
  any number of tickets. This is the only true M:N relationship in the
  schema; everything else is 1:N, including the assignee relationship
  (one ticket has exactly one primary assignee).

## Constraints: database vs application

**Enforced by the database:**
- Primary keys, and the FK relationships listed above (a ticket can't
  reference a nonexistent user; a reply can't reference a nonexistent
  ticket).
- `users.email` uniqueness.
- The composite primary key on `ticket_collaborators` (no duplicate
  collaborator rows).
- The `(ticket_id, user_id, breach_epoch)` uniqueness on
  `sla_acknowledgements`.
- `NOT NULL` on every required column.

**Enforced only by the application, not the database — worth being explicit
about, since it's easy to assume otherwise:**
- **Every enum column** (`tickets.priority/category/status`, `users.role`,
  `ticket_history_events.event_type`) is a plain `VARCHAR` at the database
  level, with **no `CHECK` constraint** — confirmed directly against the
  actual SQLite schema, not assumed. SQLAlchemy's `Enum(..., native_enum=False)`
  only adds a `CHECK` constraint if `create_constraint=True` is passed
  explicitly, which none of these columns do. Validity is enforced entirely
  by Python's `Enum` type and Pydantic schema validation on the way in; a
  row inserted via raw SQL with an out-of-range string would be accepted by
  the database without complaint.
- **`tickets.primary_assignee_id` must reference a user with `role =
  "agent"`, never a supervisor.** The foreign key only guarantees the row
  exists, not its role. Enforced in `ticket_service.ensure_valid_assignee`,
  called on every ticket creation and every reassignment.
- **The entire ticket lifecycle state machine** (which `status` values can
  follow which) lives in `lifecycle_service.ALLOWED_TRANSITIONS`, a plain
  Python dict. The database has no opinion on whether `closed → new` is a
  legal update — it would happily accept it via a raw `UPDATE`.
- **Every role/ownership permission check** (`can_act_on_ticket`,
  `can_reassign_ticket`, `can_close_ticket`, `can_view_ticket`) —
  `app/services/permissions.py`. Nothing about the schema stops an agent's
  row from being the target of an `UPDATE` that reassigns a ticket to
  someone else; the application is the only thing that ever checks who's
  allowed to do that.
- **Immutability of `ticket_history_events`.** There's no database-level
  trigger or rule preventing an `UPDATE`/`DELETE` on this table — SQLite and
  Postgres would both allow it. The guarantee is structural instead:
  `app/services/history_service.py` exposes creation functions only, and no
  route in the application ever targets this table for anything else
  (verified directly in the review pass by enumerating every registered
  FastAPI route and confirming none accept a mutating HTTP method on any
  history-shaped path).

## Denormalization

- **`ticket_history_events` is one polymorphic table for three different
  event shapes** (status change / reassignment / reply) rather than three
  normalized tables with a shared parent, or a fully generic
  `EAV`-style `(field_name, old_value, new_value)` structure. The tradeoff:
  most columns are `NULL` on any given row (a reply-type event never
  populates `old_status`/`new_status`/`old_assignee_id`/`new_assignee_id`),
  which a stricter schema would avoid — but the ticket detail page needs
  one chronologically-ordered query across all three event types, and a
  single table with a `SELECT ... ORDER BY created_at` is simpler than a
  `UNION` across three tables or a second query to interleave in Python.
- **`ticket_history_events.reply_id` references `replies` rather than
  duplicating `body`/`is_internal` onto the history row.** This is the
  opposite tradeoff from the point above — normalized, not denormalized —
  specifically because reply content is real user data worth a single
  source of truth, whereas the other two event types' "content" (an old/new
  status or assignee pair) has nowhere else to live.
- **`SlaAcknowledgement.breach_epoch` is computed from `ticket_closed_periods`
  at read time, not stored as a running counter on `tickets`.** Storing it
  redundantly would risk drifting out of sync with the actual reopen count
  it's meant to track; deriving it keeps there being exactly one source of
  truth for "how many times has this been reopened."
- **`tickets.resolved_at` duplicates information that's also derivable from
  `ticket_history_events`** (the most recent `status_change` row where
  `new_status = 'resolved'`). It's stored directly on the ticket anyway
  because the dashboard's "resolved this week" query needs to filter and
  aggregate by it cheaply; deriving it from the history table on every
  dashboard load would mean a correlated subquery per ticket instead of a
  plain indexed column comparison.

## What would break first at 100x the data

The SLA/breach calculations are the first thing that would need to change.
`alerts_service.list_alerts`, `dashboard_service.headline_counts`, and
`export_service`'s CSV `breach_status` column (computed once per exported
row) all fetch every active ticket in the viewer's scope and call
`elapsed_response_time_for_ticket` on each one in a Python loop — and that
function itself issues two more queries per ticket (its pending and closed
periods; three once resolved periods are included). At current demo-data
volume (dozens of tickets) this is invisible; at 100x (thousands of active
tickets per viewer scope), it's an N+1 query pattern that would need to
become a single aggregate query — realistically, moving the breach
determination into SQL (or a materialized/cached column refreshed by a
background job) rather than a per-request Python loop.

Second: `ticket_service.matching_ticket_ids`, the shared scoping/filtering
subquery behind the queue, CSV export, dashboard, and alerts, does an
`OUTER JOIN` to `ticket_collaborators` and a `DISTINCT` to dedupe. This is
fine at current scale; at 100x it's the kind of query that would need the
`is_archived`, `status`, `priority`, and `primary_assignee_id` columns
covered by composite indexes rather than relying on the single-column index
on `ticket_id` that most of these tables currently have — none of the
tables in this schema have a composite index today.

Third: the text search (`ILIKE '%term%'` on `subject`/`description`) can't
use a B-tree index at all — it's a full table scan on every search request
regardless of scale. At 100x the data this would need a real text-search
index (Postgres `tsvector`/GIN, or an external search service); it was left
as a plain `ILIKE` here because goal 6 only asked for server-side filtering,
not for it to scale past a demo dataset.
