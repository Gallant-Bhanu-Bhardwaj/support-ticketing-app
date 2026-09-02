## Session 1 — Scaffold

### Prompt
Implement the project scaffold only — no ticketing logic yet.

- Folder structure: app/ (models, schemas, routers, services, core, templates,
  static), tests/, alembic/.
- FastAPI app instance with a /healthz endpoint.
- SQLAlchemy 2.0 engine + session dependency, configured via pydantic-settings
  reading DATABASE_URL from .env. Structure it so swapping in a Postgres URL
  for production needs no code changes, only a different DATABASE_URL.
- Initialize Alembic, generate an empty first migration.
- Jinja2 templates: one base.html pulling in Bootstrap 5 and HTMX from CDN,
  plus a placeholder home page.
- pytest config and one trivial test hitting /healthz.
- requirements.txt (or pyproject.toml) pinned to the stack in CLAUDE.md.
- Update .gitignore to also exclude *.db, .venv/, .pytest_cache/.

Do not build any ticketing logic yet. Stop once this runs locally and the
test passes, and show me the folder tree.

### What you got
app/ package with models, schemas, routers, services, core, templates, static; app/core/config.py (pydantic-settings reading DATABASE_URL); app/core/database.py (engine/session/Base, with SQLite-vs-Postgres connect_args branch); app/main.py (FastAPI instance, static mount, / route); app/routers/health.py (/healthz); base.html/home.html (Bootstrap 5 + HTMX via CDN); requirements.txt pinned to CLAUDE.md's stack; pytest.ini; tests/test_healthz.py; Alembic initialized and wired to app.core.config and Base.metadata, empty first migration generated and applied; .gitignore updated; .env/.env.example created. pip install, alembic revision/upgrade, and pytest all succeeded on the first run: 1 passed, no failures. Manual curl checks of /healthz, /, and the static file all returned expected results on the first try.

### What you corrected
Nothing I asked for, no correction prompt was needed for the scaffold. One self initiated change worth noting, after the first pytest run printed a PytestDeprecationWarning, Claude Code added `asyncio_default_fixture_loop_scope = function` to pytest.ini on its own, before I saw any output, to silence it. Not a fix to something broken, just a proactive cleanup I didn't ask for.

Commit: d2eba29


## Session 2 — Accounts & roles (Goal 1)

### Prompt
Implement goal 1 only: accounts and roles.

- User model: email, hashed password (passlib/bcrypt), role (supervisor | agent).
- JWT login at POST /auth/login, token stored in an HttpOnly cookie for the
  Jinja2/HTMX frontend — not localStorage.
- get_current_user and require_role() dependencies used on every protected route.
  Authorization must live in the dependency/service layer, never only hidden in
  a template.
- Supervisors: can reassign any ticket to any agent, close tickets, see the
  entire queue. Agents: can act only on tickets where they're primary assignee
  or a collaborator, and cannot reassign a ticket away from themselves. There
  are no tickets yet, so stub a permissions module with these function
  signatures now for goal 2+ to use directly.
- A seed command creating one supervisor and two agent demo users.
- Login page and a protected placeholder page showing "Signed in as {email}
  ({role})".
- Tests: login success/failure, a protected route 403s without a token, and the
  role dependency actually blocks the wrong role — not just checks for any token.

Commit when tests pass.

### What you got
User model (email, bcrypt hash, supervisor/agent role); security.py with token creation/decoding and password hash/verify; get_current_user and require_role() dependencies applied to every protected route; POST /auth/login (HttpOnly, samesite=lax cookie) and POST /auth/logout; app/services/permissions.py with real logic built against a TicketLike Protocol so goal 2's Ticket model plugs straight in; python -m app.seed creating 1 supervisor + 2 agents; login page + a /dashboard placeholder; /admin added specifically to give require_role a supervisor-only route to test against. 16 tests passed. 
Committed as a52a5bd.

### What you corrected
Real bug: pip installed bcrypt==5.0.0 (unpinned). Passlib 1.7.4 detects its bcrypt backend via bcrypt.__about__.__version__, an attribute bcrypt removed in 4.1+. Passlib's internal self test broke, and every hash_password() call failed with a misleading "password cannot be longer than 72 bytes" ValueError unrelated to actual password length. Fixed by pinning bcrypt==4.0.1 in requirements.txt.

Also caught before it ran: SQLAlchemy Enum column defaults to storing the Python enum member name (SUPERVISOR/AGENT) rather than its value. Added values_callable so the database stores supervisor/agent as expected.

Design call to document separately in decisions.md: chose uniform 403 for missing token, invalid token, and wrong role, instead of the conventional 401/403 split.

Reversed later: originally kept uniform 403 for all auth failures (missing token, invalid token, wrong role). Revisited in a later session (commit 405798a) and split it to the conventional 401 (missing/invalid/expired token) vs 403 (valid token, wrong role), see docs/decisions.md. Only three tests were actually asserting the old 403-for-missing-token behavior (test_protected_route_without_token_is_forbidden, renamed to expect 401; test_tickets_route_requires_authentication; test_reply_requires_authentication). Every other 403 in the suite was already a genuine role/ownership check and needed no change.


## Session 3 — Tickets, archive/restore (Goal 2)

### Prompt
Implement goal 2 only: tickets.

- Ticket model: subject, description, requester, priority, category, status
  (default "New"), is_archived, created_at, updated_at. Document your priority
  and category enums.
- Create/edit usable by both agents and supervisors.
- Archive/restore: archiving removes a ticket from every default queue view
  without deleting the row or its history.
- Jinja2 + HTMX: creation form, detail page, edit form, archive/restore buttons
  with partial-page HTMX updates.
- Tests: create, edit, archive removes it from the default list endpoint,
  restore brings it back, and the row + history still exist in the DB after
  archiving.

Commit when done.

### What you got
Ticket model (subject, description, requester, priority/category/status enums, is_archived, timestamps) + migration; GET/POST /tickets (list + create), GET /tickets/new, GET/POST /tickets/{id} (detail + edit), GET /tickets/{id}/edit, POST /tickets/{id}/archive|restore, GET /tickets/archived. Bootstrap-styled templates; archive/restore use genuine HTMX partial swaps, no full-page reloads. Enums: priority (low/normal/high/urgent, chosen to map onto goal 4's SLA targets), category (bug/billing/how_to/feature_request/other, arbitrary generic taxonomy), status (all five lifecycle states exist on the column, but this goal only ever writes "new"; transitions are goal 4's job). 26 tests passing (10 new). 
Committed as 1b9f9bc.

### What you corrected
No failures this session. Verified FastAPI's Annotated[TicketWrite, Form()] pattern actually works with the pinned FastAPI version before committing to it, since it's a newer feature.

Three decisions logged for decisions.md: 
(1) create/edit/archive/restore open to any authenticated user for now, no ownership check yet, since primary_assignee_id doesn't exist until goal 5, explicitly flagged to revisit, and goal 5 prompt was updated to add it back in when that data exists. 
(2) requester kept as a single free text field, not split into name/email, since the brief only asks for "a requester." (3) Added /tickets/archived as a UI only addition beyond the literal ask, since restore needs somewhere to trigger from once a ticket leaves the default list.

## Session 4 — Replies (Goal 3)

### Prompt
Implement goal 3 only: replies.

- Reply model: belongs to exactly one ticket, message body, author (FK to
  user), timestamp, is_internal boolean.
- POST endpoint to add a reply at any time. For now, any authenticated agent
  or supervisor can reply to any ticket — same as goal 2's create/edit/
  archive decision, since there's no primary_assignee_id or collaborator
  data yet to restrict by. That restriction lands in goal 5 once the data
  exists; don't invent a placeholder assignee field to get around this now.
- Ticket detail page shows all replies in chronological order, visually
  distinguishing internal notes from customer-visible replies.
- Tests: a reply attaches to the right ticket with the right author/
  timestamp, and both internal and customer-visible replies are stored and
  returned in order.

Commit when done.

### What you got
Reply model (ticket FK, body, author FK, timestamp, is_internal bool) with Ticket.replies / Reply.ticket / Reply.author relationships, using TYPE_CHECKING-guarded forward references with no circular-import issues. POST endpoint open to any authenticated agent or supervisor for now, ownership restriction deferred to goal 5, consistent with goal 2's earlier decision. Ticket detail page renders replies chronologically, internal notes visually distinguished from customer-visible ones. Checkbox-to-bool binding (is_internal=on → True, field omitted → default False) worked via Pydantic's form coercion on the first try. 32 tests passing (6 new). 
Committed as bbd6dc8.

### What you corrected
None. First run passed clean, no failures.


## Session 5 — Lifecycle + SLA clock (Goal 4)

### Prompt
Implement goal 4 only: ticket lifecycle. Re-read the README's exact wording on
this one before writing any code.

- Enforce New → Open → Pending → Resolved → Closed at the service layer. Any
  transition not explicitly allowed must be rejected with a clear message
  explaining why — write this as an explicit table or function, not scattered
  if/else checks.
- Every ticket has a response clock measured against a target response time set
  by its priority. Pick and document your per-priority targets in
  docs/decisions.md.
- Pending means waiting on the customer: while a ticket sits in Pending, elapsed
  time must not accumulate against the agent. Model this by recording when each
  Pending period starts/ends and excluding that duration from the elapsed-time
  calculation — don't try to "pause a timer" in memory.
- A customer reply while Pending returns the ticket to Open and resumes the
  clock.
- A Closed ticket can be reopened only within a fixed window afterward (pick
  and document a window, e.g. 7 days) — past that, the server rejects the
  reopen with an explanatory message.
- Tests: every legal transition succeeds, at least two illegal transitions are
  rejected with a message, and a specific unit test asserting elapsed time
  excludes time spent in Pending.

Show me your state-transition table before implementing, so I can check it
against the README first.

### What you got
Design proposed before any code: full state transition table, TicketPendingPeriod log table (not an in-memory pause), priority based SLA targets (urgent=4h/high=8h/normal=24h/low=72h), 7-day reopen window. Implementation: ALLOWED_TRANSITIONS dict in lifecycle_service.py; TicketPendingPeriod + TicketClosedPeriod log tables, elapsed_response_time() as a pure function over period lists (unit-testable without DB setup) plus a DB backed wrapper, Resolved→Closed gated by goal 1 permissions.can_close_ticket, manual only Pending Open with a regression test proving a reply never auto resumes the clock. 56 tests passing (24 new).
 Committed as e07ba00.
  Manually walked new→open→pending→open→resolved, agent blocked from closing, supervisor closes, reopen within window, and illegal new→closed (409) through the running server. All matched.

### What you corrected
Two design gaps caught in review before implementation. First, the original design auto resumed the clock on any non internal reply added while Pending. Corrected to manual only, since every reply is authored by an agent or supervisor and a customer visible reply isn't reliable evidence the customer actually replied. Second, elapsed() didn't account for time spent Closed, meaning a ticket reopened after sitting Closed for days would show as instantly, massively breaching. Corrected by adding a TicketClosedPeriod table symmetric to the Pending one.

Real bug, not invented: SQLite returns naive datetimes from a DateTime(timezone=True) column regardless of the column declaration, while Postgres (production) returns tz aware ones. Comparing either against a tz aware "now" would crash locally or silently miscompute in production. Fixed with a UTCDateTime TypeDecorator, verified empirically, applied retroactively to every existing datetime column.

Logged for decisions.md: dropped the standalone Ticket.closed_at column in favor of deriving it from the open TicketClosedPeriod row, one source of truth for both the reopen window guard and the elapsed time exclusion.

Addendum 
Multi cycle check requested separately: confirmed the gap was real. Added test_elapsed_excludes_multiple_pending_periods_summed and test_elapsed_excludes_multiple_closed_periods_summed (pure function, hand built period lists) plus test_elapsed_for_ticket_with_multiple_pending_cycles and test_elapsed_for_ticket_with_multiple_closed_cycles (driven through real repeated transitions, not hand-built lists). All 60 tests pass. 
Committed as 0d27053.



## Session 6 — Collaborators (Goal 5)

### Prompt
Implement goal 5 only: collaborators.

- Add primary_assignee_id (FK to User, required, must reference an agent —
  never a supervisor; goal 1 only ever describes supervisors reassigning
  tickets to agents, never becoming assignees themselves). Goal 2's create
  flow doesn't collect this yet: extend it so creating agents default to
  themselves as primary assignee (still changeable), and supervisors must
  explicitly pick an agent. Decide and document in docs/decisions.md how the
  migration handles tickets already created without one.
- Any number of collaborators (many-to-many between users and tickets).
- Collaborators can reply to and update the ticket, same as the assignee.
- One "my tickets" endpoint/page per agent: every ticket where they're primary
  assignee OR a collaborator.
- Wire the permission stubs from goal 1 to actually use this now — and this
  means going back to retrofit, not just gating new code. Goals 2, 3, and 4
  left ticket edit, archive/restore, replies, and status transitions open to
  any authenticated agent because there was no assignee data to restrict by
  (closing stays supervisor-only regardless, per goal 1). That data exists
  now: restrict all of those routes so agents can only act on tickets where
  they're primary assignee or a collaborator, same as this goal's own
  actions. Supervisors remain unrestricted throughout.
- Tests: adding/removing a collaborator, a collaborator can reply, an agent's
  "my tickets" list includes both assigned and collaborated tickets and
  nothing else, creating a ticket as an agent defaults to self-assigned,
  creating one as a supervisor requires picking an agent, AND an agent
  hitting edit/archive/reply/status-transition on a ticket they're neither
  assigned to nor collaborating on is rejected by the server.

Commit when done.

### What you got
Ticket.primary_assignee_id (required FK, must be an agent) + TicketCollaborator join table; Ticket.collaborators/collaborator_ids finally satisfy goal 1's TicketLike protocol, unused since goal 1. Create/edit assignment rules enforced server-side (agents always self-assign; supervisors must pick or get 422). GET /tickets/mine. Add/remove-collaborator endpoints. Retrofit: permissions.can_act_on_ticket now gates edit, archive, restore, reply, and status transitions across ticket_service, reply_service, lifecycle_service, and collaborator_service, not just new code. 79 tests passing. Committed as f201784.

### What you corrected
Two real bugs, not invented. First, a test asserted the literal string "I'm collaborating here" in rendered HTML, but Jinja2's autoescaping turns into &#39;. Confirmed via a standalone Jinja2 repro that this was correct app behavior, and fixed the test data instead of the app. Second, the first Alembic migration attempt failed on SQLite's lack of standalone ALTER TABLE ADD CONSTRAINT outside batch mode, leaving orphaned DDL behind. Cleaned up the orphaned table/column by hand before retrying with the corrected batch mode version.

Decisions logged for decisions.md, agents can't set a different assignee even at creation, collaborators must be agents too, collaborator management gated by the same can_act_on_ticket check (resolves the "needs explicit decision" flag on this from Session 1 original roles table), migration backfill assigned pre existing tickets to the earliest created agent, explicitly flagged as a placeholder, not a real triage strategy.

Real gap surfaced and flagged rather than guessed: GET /tickets and GET /tickets/{id} weren't restricted by assignment. Resolved in a follow up - see addendum.

Addendum — three-point follow-up (commit 491cac0):

1. View scoping fixed: ticket_service.list_tickets now takes a viewer and delegates to list_my_tickets for non-supervisors. GET /tickets and GET /tickets/archived inherit this. GET /tickets/{id} now goes through get_viewable_ticket_or_404, applying can_view_ticket. Verified on the live server, agent2 got 403 on agent1's ticket, agent2's queue excluded it, and agent1's and the supervisor's queues both included it.

2. Edit time reassignment: checked, already correct, no gap. test_agent_cannot_reassign_via_edit and test_supervisor_can_reassign_via_edit were already written and passing from goal 5. update_ticket already routes assignee changes through permissions.can_reassign_ticket. No change made, verified before deciding not to touch it.

3. Create time silent override fixed: create_ticket now raises 403 ("Agents can only create tickets assigned to themselves.") instead of silently forcing self assignment. Confirmed via the live server response body. Normal UI unaffected, since the create form never sends primary_assignee_id for agents.

86 tests passing.

Related gap surfaced and closed in a followup: GET /tickets/{id}/edit had no permission check at all, letting an unrelated agent load a prefilled edit form even though submitting it would be rejected. Fixed via get_editable_ticket_or_404 (can_act_on_ticket, stricter than can_view_ticket). 
Audited every other GET route for the same pattern: GET /tickets/new has no specific ticket's data to leak; collaborators and replies expose only POST endpoints /dashboard, /admin, /auth/login aren't ticket-specific. Nothing else had this pattern. Verified on the live server: the 403 response contains zero occurrences of the ticket's subject. 90 tests passing.
 Committed as 2e3dd93.



## Session 7 — Search, filter, sort, pagination (Goal 6)

### Prompt
Implement goal 6 only: finding tickets. Everything below must happen in the
database query — check your own implementation for accidentally loading all
tickets into Python and filtering in memory before you commit.

- This must build on top of the existing viewer-scoped query from goal 5
  (list_tickets/list_my_tickets) — agents still see only tickets where
  they're primary assignee or collaborator, supervisors still see
  everything. Search/filter/sort/pagination narrows within that scope; it
  does not replace or bypass it.
- One list endpoint/page: text search over subject + description, filters for
  status/priority/category/assignee, sorting by created date/priority/last
  update, pagination that also returns the total match count.
- Wire this to the queue page with query-string-driven filters so the URL is
  shareable.
- Tests: search matches subject and description, each filter narrows results
  correctly, sorting orders correctly, pagination + total count are correct
  against a seeded dataset larger than one page, AND an agent's search/filter
  results never include a ticket they're not assigned to or collaborating
  on, even when the search term would otherwise match it.

### What you got
search_tickets() in ticket_service.py, layered on the same viewer-scoping goal 5 established. An agent's search/filter/sort runs entirely inside their own assigned-or-collaborating scope. Text search over subject and description via .ilike(). Filters for status, priority, category, and assignee. Sort by created date, priority, or last-updated. Pagination with a real SQL-computed total count. Wired to GET /tickets via query params, pagination links preserving full filter state. Verified the "no in-Python filtering" requirement by printing the actual compiled SQL and confirming real WHERE/ORDER BY/LIMIT/OFFSET clauses, including viewer-scoping baked into the same query. Confirmed .ilike() compiles portably (lower(col) LIKE lower(pattern)), not Postgres-specific ILIKE. 106 tests passing (16 new). Committed as 7ef9014.

### What you corrected
Two real bugs, not invented. 
First, priority sorting would have been alphabetical (high, low, normal, urgent) since priority is stored as a plain string. Fixed with an explicit CASE-based severity rank (1-4), and added a test that fails loudly against the naive column sort version. 
Second, empty filter dropdowns would have 422'd the entire queue page, since FastAPI can't parse "" into Optional[int]/Optional[Enum]. Verified empirically before fixing, then accepted filters as raw strings and parsed them explicitly, treating empty as "no filter" and a genuinely invalid value as a real 422 with a clear message.

Addendum — Three item check requested separately (commit 9bf193b): all three were test-coverage gaps, not functional bugs. The underlying code was already correct in all three cases.

1. Combined filters: No test previously exercised more than one filter at once. Added test_combined_filters_apply_as_and_not_or, using three tickets (matches only status, matches only priority, matches both) to prove AND semantics specifically.
2. Sort direction: Code already handled both directions generically (sort_column.asc()/desc() by branch), but tests only covered one direction per field. Added the missing direction for each field.
3. Total count: No bug. Total and the page of results both derive from the same matching_ticket_ids subquery, so they can't structurally drift apart. Added a test proving total reflects the filtered count, plus a stronger regression guard combining a filter with pagination.

112 tests passing.


## Session 8 — Bulk actions and CSV export (Goal 7)

### Prompt
Implement goal 7 only: bulk actions and export.

- Bulk reassign and bulk close from the queue view, operating on a set of
  selected ticket IDs. Both must reuse the exact same per-ticket
  authorization checks as the single-ticket paths — can_reassign_ticket for
  reassign, can_close_ticket for close — not new bulk-specific logic. Since
  both are already supervisor-only, flag explicitly whether that means the
  bulk toolbar itself should only be shown to supervisors in the UI, since
  every bulk action an agent attempts would otherwise come back as a
  100%-refused batch — don't decide this silently either way.
- The response must report per-ticket outcome — which succeeded, which were
  refused and why (e.g. an already-closed ticket can't be bulk-closed again,
  or the actor isn't authorized on that specific ticket) — never fail the
  whole batch because one ticket was ineligible.
- CSV export of the currently filtered queue, reusing the goal 6 filter
  logic and viewer-scoping rather than duplicating it, generated with the
  standard library csv module.
- Tests: a mixed-eligibility bulk reassignment returns correct per-ticket
  results (including a ticket the actor isn't authorized on), and CSV
  export respects active filters, respects viewer-scoping, and produces a
  parseable file with the expected rows.

### What you got
Bulk reassign and bulk close from the queue view. Both reuse the exact per-ticket authorization checks as the single-ticket paths: _apply_reassignment extracted so update_ticket and the new reassign_ticket share identical can_act_on_ticket/can_reassign_ticket checks; bulk_close calls lifecycle_service.transition() directly, getting the full state-machine legality check for free (e.g. "Cannot move a ticket from closed to closed."). No blanket role check on the bulk endpoints themselves, verified role-agnostic with test_agent_bulk_close_gets_all_refused_report_not_a_blanket_403, confirming a crafted agent request gets 200 with a per-ticket refused report, not 403. Bulk toolbar hidden from agents entirely in the UI. CSV export reuses ticket_service's filter/scope logic via extracted _matching_ticket_ids, shared with search_tickets; confirmed uncapped by page size (test_csv_export_is_not_capped_by_page_size). Mixed-eligibility test for bulk reassign distinguishes two genuinely different rejection reasons: an agent's own ticket fails at the reassignment-specific check, a ticket with zero relationship fails earlier at the access check. 126 tests passing. Committed as ce2853a.

### What you corrected
Real bug, not invented: the "N succeeded, M refused" summary line rendered correct counts in manual checks, but a newline in the template between the two numbers broke every text matching test. Fixed by collapsing to one line, genuinely better UI output, not just a test compatibility fix.

Addendum — Three item check requested separately (commit 8d5aa45):

1. CSV columns: breach_status was genuinely missing, added as binary (breaching/on_track) via elapsed_response_time_for_ticket + TARGET_RESPONSE_TIME. Deliberately binary, not three state, since the "at risk" threshold belongs to goal 10's design.
2. CSV viewer scoping: Already covered, test_csv_export_respects_viewer_scoping already existed, no gap.
3. Bulk close mixed eligibility: Real gap, fixed, with one structural finding. A true three way mix (success + state machine refusal + access refusal) in one batch is impossible under the current permission model, since success requires a supervisor (who's never access denied), and access refusal requires an agent (who never succeeds at closing anyway). Covered both refusal paths as separate, precise tests instead of forcing a misleading combined one.

129 tests passing.

## Session 9 — Dashboard (Goal 8)

### Prompt
Implement goal 8 only: the dashboard.

- Before building: decide and document in docs/decisions.md whether the
  dashboard is supervisor-only, or whether agents also get a version scoped
  to their own tickets (same assignee-or-collaborator scoping as the rest
  of the app). If agents get one, "breakdown by agent" doesn't make sense
  in their own scoped view (they'd only ever see themselves) — resolve what
  an agent's version actually shows before writing the query, don't build
  it ambiguously.
- Headline numbers: open tickets, tickets pending on customer, resolved this
  week, tickets currently breaching SLA. The "currently breaching" count
  must reuse the same breach-determination logic goal 7 already built for
  CSV export (elapsed_response_time_for_ticket + TARGET_RESPONSE_TIME), not
  a new or separate calculation.
- Breakdown by status and by agent (supervisor view — see the first bullet
  for what, if anything, an agent sees instead).
- A chart of tickets resolved per week over the last 8 weeks, rendered
  client-side with Chart.js fed by a small JSON endpoint.
- Tests: each headline number and breakdown number is correct against a
  seeded dataset with known values, and — if agents get a scoped dashboard —
  an agent's headline numbers only reflect their own tickets.

### What you got
Four decisions resolved before writing queries: dashboard available to both roles with identical scoping to the rest of the app; agent view omits the by-agent breakdown rather than inventing a substitute; "this week" defined as calendar week Monday-Sunday UTC, consistent between headline number and chart; "currently breaching" restricted to New/Open/Pending, reusing elapsed_response_time_for_ticket + TARGET_RESPONSE_TIME directly. matching_ticket_ids promoted from private to public since dashboard_service is now a third caller alongside search_tickets/all_matching_tickets, so viewer-scoping lives in exactly one place. Tested against seeded data throughout: headline counts, status breakdown, agent breakdown (including a zero-ticket agent, confirming LEFT JOIN not inner join), 8-week chart bucketing (including a 9-weeks-ago ticket that must not appear in any bucket), and agent-vs-supervisor scoping for headline numbers. 138 tests passing. Committed as c62c857.

### What you corrected
Real prerequisite gap, not optional scope: nothing tracked when a ticket became Resolved, so "resolved this week" was uncomputable. Added Ticket.resolved_at, set by lifecycle_service.transition() on every entry into Resolved, overwritten on re-resolution after a reopen cycle, so it always reflects the most recent one.

Real bug, not invented: the Chart.js CDN URL first written (4.4.4) 404s, since that patch version was never published to cdnjs. Caught by actually curling it rather than trusting a plausible looking version string, pinned to 4.4.1 after confirming it's a real ~200KB UMD bundle.


## Session 10 — Immutable timeline (Goal 9)

### Prompt
Implement goal 9 only: history you cannot rewrite.

- A timeline/audit table recording every status change (old + new status, who),
  every reassignment, and every reply (internal or customer-visible), each
  timestamped.
- These records are created only as a side effect of the real actions — there
  must be no update or delete endpoint for timeline entries, for any role,
  including supervisors.
- Ticket detail page renders this as one chronological timeline. Decide
  explicitly how this coexists with the reply thread goal 3 already built —
  either the timeline replaces the reply list as the single history view
  (it now covers replies plus status changes and reassignments), or the two
  stay visually distinct with a clear reason why. Don't let the same replies
  render twice in two separate, redundant lists. Whichever you pick,
  preserve the internal/customer-visible visual distinction for reply
  entries.
- Tests: each action creates the correct timeline row, and confirm there is
  genuinely no route capable of mutating a timeline row once created.

### What you got
Design decision: timeline replaces the reply list as the single history view, since the README describes one unified timeline including replies, avoiding the same replies rendering twice. Internal/customer-visible badge styling carries over for reply entries; status-change/reassignment entries are new, distinctly-styled rows interleaved chronologically (verified visually: reply → status change → reply → reassignment, in order, correct badges). Immutability enforced structurally: history_service.py exposes only record_status_change/record_reassignment/record_reply/list_timeline, no update/delete function exists anywhere for this table; no router touches it directly; every row is written as a side effect inside the same transaction as the real action. Reassignment recording wired into _apply_reassignment (already shared between update_ticket and bulk reassign since goal 7), so bulk reassign got correct history tracking for free, confirmed with its own test. Immutability tested from three angles: route introspection (no PUT/PATCH/DELETE on any history/timeline path), structural (no update/delete/edit/remove-named function exists in history_service), and behavioral (guessed mutation URLs 404/405, row confirmed byte-for-byte unchanged). 149 tests passing. Committed as 1007994.

### What you corrected
Bug in my own test, not the app: a test simulated an unchecked reply checkbox by sending is_internal="", which Pydantic can't parse as a bool. Verified this directly before concluding it wasn't an app bug (real browsers omit the field entirely when unchecked). Fixed the test, not the app.

Addendum — Four item field level check requested separately (commit e04630f):

1. Status change field assertions: already covered, no gap.
2. Reassignment field assertions: already covered, no gap.
3. Reply FK linkage: real gap, fixed. Added event.reply_id == reply.id assertion against an independently-queried Reply row, plus a second test with two replies proving each history row links to its own reply rather than both coincidentally pointing at the same one (unprovable with a single-reply test).
4. Goal 3 test preservation: verified by reading test_replies_shown_in_chronological_order_and_distinguish_internal's actual assertions (badge text/classes, chronological order), not assumed from it passing. Confirmed still valid against the unified timeline since the rendering contract for reply entries is unchanged.

150 tests passing.


## Session 11 — SLA alerts (Goal 10)

### Prompt
Implement goal 10 only: SLA alerts. Re-read the README's exact wording on the
reappearance rule before coding — it's easy to get subtly wrong.

- Any ticket whose response clock has passed its target, or is within a short
  configurable window of doing so (document the window in docs/decisions.md),
  appears in an alerts list, with a count badge in the nav. Reuse goal 8's
  active-ticket scoping (New/Open/Pending only — Resolved/Closed tickets
  never appear) and the existing breach-determination logic
  (elapsed_response_time_for_ticket + TARGET_RESPONSE_TIME); don't recompute
  either from scratch.
- Alert visibility: supervisors see all breaching/at-risk tickets; agents see
  only tickets where they're primary assignee or a collaborator — reuse the
  same viewer-scoping already established since goal 5, don't build a
  parallel version.
- An agent or collaborator can acknowledge an alert for a ticket they're
  assigned to or collaborating on — same rights as the primary assignee, per
  the earlier decision — clearing it from their list.
- If that ticket is later reopened and breaches its target again, the alert
  must return — so "acknowledged" needs to be scoped to a specific breach
  instance, not a permanent flag on the ticket, or it will never reappear.
- Tests: a ticket nearing/breaching its target appears in alerts (and a
  Resolved/Closed ticket that would otherwise qualify does not), a
  collaborator can acknowledge the same as the primary assignee, an agent's
  alert list excludes tickets outside their scope, acknowledging clears it,
  and reopening + re-breaching brings it back. Write that last test
  explicitly — it's the one most likely to be silently wrong.

### What you got
ACTIVE_STATUSES promoted out of dashboard_service into sla_service so both share the identical constant. list_alerts calls elapsed_response_time_for_ticket/TARGET_RESPONSE_TIME directly and scopes visibility through matching_ticket_ids, same as every list since goal 5, no parallel scoping logic. Reappearance: acknowledgment keyed by (ticket_id, user_id, breach_epoch), where breach_epoch counts TicketClosedPeriod rows with reopened_at set, reusing goal 4's reopen log rather than a new counter. Reopening increments the epoch; an old acknowledgment tied to the previous epoch stops matching, so the alert reappears. The elapse time value itself doesn't need to reset for this to work. Tested through two full breach→ack→close→reopen cycles, not one, since a single cycle could hide an off-by-one in epoch advancement. Explicitly tested that a Pending cycle (not a Closed→Open reopen) leaves an acknowledgment intact, since only reopening should advance the epoch. Added get_current_user_optional so the nav alert badge works on pages that don't require login instead of 401ing. Manually verified end-to-end on the live server: backdated a ticket to force a real breach, confirmed nav badge, alerts page listing, and acknowledge clearing all matched. 162 tests passing. Committed as eac2749.

### What you corrected
Nothing corrected this session, reappearance logic verified correct through the two cycle test rather than found broken.

Flagged, not yet resolved: elapsed_response_time_for_ticket excludes Pending and Closed time but not time spent Resolved before Closed, which could inflate elapsed time on a reopened ticket that sat in Resolved for a while before closing. Folded into the goal 12 review pass prompt to be fixed or explicitly documented, see decisions.md once resolved.


## Session 12 — Review pass

### Prompt
Do a review pass, not new features.

- Run the full pytest suite and fix anything failing.
- Re-check every "must be enforced on the server" and "must be rejected by the
  server" requirement in the README against the actual route/service code, not
  the UI.
- Confirm every role check happens in a dependency or service function, not
  just conditional rendering in a template.
- Specific check: elapsed_response_time_for_ticket excludes time spent
  Pending and time spent Closed, but not time spent Resolved-but-not-yet-
  Closed. Trace through what that means: a ticket resolved quickly but left
  sitting in Resolved for a long stretch before being closed, then later
  reopened, would show inflated elapsed time on reopen, even though the
  actual response was fast. Either fix it (a TicketResolvedPeriod table,
  symmetric to the existing two) or explicitly document it as a known
  limitation in docs/decisions.md with the reasoning above — don't leave it
  silently uncaught either way.
- Flag anything else you're not fully confident about instead of silently
  leaving it.

### What you got
Full test suite: 166 passed on the initial run, no pre existing failures. Server side enforcement rechecked: walked every mutating route across tickets.py, collaborators.py, replies.py, and alerts.py, confirming each calls a service function that independently revalidates rather than trusting the caller. Audited every raise HTTPException (29 sites) for a specific, non generic message. Verified no unauthenticated bypass across all seven routers except the three genuinely public routes. Role checks rechecked in every template: confirmed each conditional gates a UI convenience on top of an already enforced server check, never the only check. No template only enforcement found anywhere.

### What you corrected
Real bug, confirmed not theoretical: reproduced the Resolved but not closed elapsed time gap concretely (30 minute resolution, 10 days sitting Resolved, ~10 days elapsed shown on reopen), already silently affecting the shipped goal 7 CSV breach_status column. Fixed with TicketResolvedPeriod, symmetric to the existing period tables. Changed one existing test's expected value (5h→3h, corrected math shown inline as a comment) and added three new tests for the full cycle.

Three items proactively flagged, not asked for by name. First, the JWT secret had a hardcoded fallback that would silently accept a well known string if unset in production, resolved in a follow up, see addendum. Second, the auth cookie wasn't secure=True, also resolved in a followup, see addendum. Third, pip audit found 26 known vulnerabilities across 7 dependencies,  traced the most severe against actual usage and declined to upgrade, see decisions.md.

Addendum — JWT secret and cookie Secure flag fixes (commit c2c925d):

1. JWT secret: jwt_secret_key now has no default in Settings. The app fails to start with pydantic.ValidationError if JWT_SECRET_KEY isn't set. Local dev is unaffected since .env sets it explicitly.
2. Auth cookie Secure flag: added Settings.environment ("development" default / "production") and an is_production property, auth.py sets secure=settings.is_production. Rejected hardcoding secure=True (breaks local dev) and scheme-sniffing via request.url.scheme (unreliable behind a reverse proxy without explicit X Forwarded Proto trust).

166 tests passing, same as before the fix, confirming nothing broke. Verified more rigorously than a grep: searched tests/ for any reference to JWT_SECRET_KEY (zero matches), then moved .env aside and ran the suite directly. It failed at collection time (pydantic.ValidationError), since Settings() instantiates at module import. Distinguished precisely: no test relies on the old hardcoded fallback (a different, real value loads from .env, not the code-level default), but the suite does depend on .env existing at the repo root, already true before this change (e.g. for DATABASE_URL). The only new behavior is that a missing JWT_SECRET_KEY now fails loudly at import instead of silently working with a well known string. .env.example already has a working placeholder (JWT_SECRET_KEY=change-me) for this.


## Session 13 — Seed data and deployment config

### Prompt
Prepare for deployment.

- A seed script producing realistic demo data: the demo users from goal 1, at
  least 20–30 tickets spread across statuses/priorities/categories, some
  archived, some with collaborators, some breaching SLA — not an empty
  database.
- Confirm DATABASE_URL from pydantic-settings works against both SQLite (local)
  and a Postgres connection string (production) with no code changes.
- Add a render.yaml (or equivalent) config: uvicorn web service,
  DATABASE_URL, JWT_SECRET_KEY, and ENVIRONMENT=production as environment
  variables (never hardcoded), Alembic migration run as part of the
  build/start step. Confirm the app actually fails to start on the deployed
  host if JWT_SECRET_KEY is missing, matching the review-pass fix — don't
  just assume the local behavior carries over.
- Confirm .env is never committed and update .env.example with variable
  names only (including ENVIRONMENT), no real values.

### What you got
Seed data expanded from 3 bare users to 27 realistic tickets, built through the actual service layer (create_ticket, lifecycle_service.transition, add_reply, add_collaborator, archive_ticket) rather than raw row inserts, so history/period/resolved_at tracking is genuinely exercised. Spread across all 5 statuses, 4 priorities, 4 categories, 2 archived, 3 collaborator relationships, 11 mixed internal/customer-visible replies. Verified against a fresh database by calling the real alerts_service/dashboard_service functions: two backdated breaching tickets and one at-risk ticket showed up correctly, dashboard headlines were sensible. Idempotent, skips ticket seeding if any ticket already exists. render.yaml: web service + managed Postgres, DATABASE_URL wired from the database resource, JWT_SECRET_KEY via generateValue, ENVIRONMENT=production, Alembic migration + seed script in buildCommand. Confirmed fail-fast behavior concretely: ran the actual production start command with .env absent and no JWT_SECRET_KEY set, matching Render's filesystem, and confirmed it exits 1 before binding a port. .env confirmed never committed via git log --all -- .env (empty history). 166 tests passing. Committed as fe51f70.

### What you corrected
No live Postgres was available in this environment to test an actual connection end-to-end, flagged explicitly rather than overclaimed. Verified instead: psycopg2 imports and a postgresql:// engine constructs cleanly, the app's most complex queries (viewer-scoped search/filter, the priority CASE sort, the dashboard's compound-join aggregate) compile correctly under the real postgresql dialect, with ILIKE switching to the native operator, no SQLite-specific code exists outside the one intentional connect_args branch. Added a defensive postgres://→postgresql:// normalizer for a known SQLAlchemy 1.4+ gotcha (the exact issue that broke many Heroku deployments).

Caught at the documentation layer: .env.example previously listed JWT_SECRET_KEY=change-me, the exact copy pasteable looking safe value the code level fix was meant to eliminate. Updated to genuinely empty values for all variables, including ENVIRONMENT.

Addendum — deployment (commit f6e2684): 
first deploy attempt failed. Render defaulted to Python 3.14 (no PYTHON_VERSION pinned), which has no pre-built wheel for the pinned pydantic-core version. pip fell back to compiling it from source via maturin/Rust, which failed on Render's read-only filesystem. Fixed by pinning PYTHON_VERSION=3.12.14 in render.yaml, confirmed as the exact local dev interpreter version via python3.12 --version before using it, not guessed. Required a Blueprint "Manual Sync" (not "Manual Deploy") to actually pick up the new render.yaml env var, since Manual Deploy alone doesn't reread blueprint config for an already existing service. Deploy succeeded after both fixes.