# Decisions

Real decisions made while building this, in the order they happened.

## Decision — Auth error status codes (Goal 1)

- **Chose:** Uniform 403 for every auth failure — missing token, invalid
  token, wrong role.

- **Rejected:** The conventional split — 401 for missing/invalid token, 403
  for wrong role.

- **Why:** Simpler at the time — one check, one response path.

- **Later reversed:** Switched to the conventional 401/403 split (commit
  7e6dec6), since a reviewer reading the code would expect standard REST
  semantics, and the split cost almost nothing to make once the codebase
  existed to check it against.




## Decision — When ownership enforcement started (Goals 2, 3, 5)

- **Chose:** For goals 2 and 3, ticket edit/archive/restore/reply were open
  to any authenticated agent or supervisor, with no ownership check.

- **Rejected:** Restricting these to the primary assignee/collaborator from
  the start.

- **Why:** `primary_assignee_id` and collaborator data didn't exist until
  goal 5; adding a placeholder assignee field early would have been scope
  creep ahead of its own goal.

- **Later reversed:** Goal 5 retrofitted `permissions.can_act_on_ticket`
  across `ticket_service`, `reply_service`, `lifecycle_service`, and
  `collaborator_service` once the data existed (commit 46417d3).




## Decision — Requester field format (Goal 2)

- **Chose:** `requester` as a single free-text string.

- **Rejected:** A structured requester — separate name/email fields, or a
  foreign key to a contact record.

- **Why:** The brief specifies "a requester" as one attribute; splitting it
  would add structure beyond what was asked.

## Decision — Archived-tickets view (Goal 2)

- **Chose:** Added a dedicated `/tickets/archived` view, not explicitly
  requested by the brief.

- **Rejected:** Leaving archived tickets reachable only by navigating
  directly to a known ticket ID.

- **Why:** Restore needs somewhere to be triggered from in the UI once a
  ticket leaves the default list — without it, restore would only be
  reachable by guessing a ticket ID.




## Decision — Per-priority SLA targets (Goal 4)

- **Chose:** urgent = 4h, high = 8h, normal = 24h, low = 72h.

- **Why:** The brief requires a target response time per priority without
  specifying numbers; these are a reasonable, easily-adjustable default
  stored as plain config, not hardcoded per ticket.

## Decision — Reopen window (Goal 4)

- **Chose:** 7 days after closing.

- **Why:** The brief requires "a fixed window" without specifying a length;
  7 days is a common, defensible support-industry default.

## Decision — No Resolved → Open transition (Goal 4)

- **Chose:** Resolved tickets can only move forward to Closed. Reopening
  only exists via Closed → Open, within the 7-day window.

- **Rejected:** Allowing a Resolved ticket to reopen directly (e.g. on new
  activity) before it's even Closed.

- **Why:** The brief specifies clock behavior for Pending → Open and
  Closed → Open explicitly, but never for Resolved → Open — treated as one
  of the "other moves" the brief says must be rejected, rather than
  inventing an unstated transition.

## Decision — Pending → Open trigger is manual only (Goal 4)

- **Chose:** Pending → Open is a manual action only.

- **Rejected:** Automatically transitioning a ticket out of Pending whenever
  a customer-visible reply is added.

- **Why:** Every reply in the system — internal or customer-visible — is
  authored by an agent or supervisor; there's no customer account, so a
  customer-visible reply isn't reliable evidence the customer actually
  replied. It could just as easily be an agent's own outbound follow-up
  sent while still waiting on the customer, and auto-resuming the clock in
  that case would defeat the point of Pending protecting the agent.

## Decision — Closed-time excluded from the SLA clock (Goal 4)

- **Chose:** Added a `TicketClosedPeriod` table, symmetric to
  `TicketPendingPeriod`, and excluded time spent Closed from
  `elapsed_response_time()`.

- **Rejected:** Leaving Closed time counted in the elapsed calculation.

- **Why:** Since Closed → Open is legal, a ticket reopened after sitting
  Closed for days or weeks would otherwise show as instantly, massively
  breaching the moment it reopened.

## Decision — Deriving `closed_at` instead of storing it (Goal 4)

- **Chose:** Derive a ticket's closed timestamp from the open
  `TicketClosedPeriod` row instead of a separate `Ticket.closed_at` column.

- **Rejected:** Keeping a standalone `closed_at` column alongside the
  period table.

- **Why:** One source of truth feeding both the reopen-window guard and the
  elapsed-time exclusion, instead of two fields that could drift apart.

## Decision — Which lifecycle actions are supervisor-gated (Goal 4)

- **Chose:** Only Resolved → Closed requires
  `permissions.can_close_ticket`; every other transition, including the
  reopen, is open to any agent or supervisor for now.

- **Why:** The brief calls out "close tickets" as the one lifecycle action
  specific to supervisors; nothing else in the brief is stated as
  supervisor-only.




## Decision — Agent-submitted assignee override (Goal 5)

- **Chose:** Agents can never set `primary_assignee_id` to someone other
  than themselves, at creation or edit.

- **Rejected:** Allowing agents to pick any assignee.

- **Why:** Consistent with agents never being able to reassign a ticket at
  all, per the brief.
- **Later reversed (enforcement, not the rule):** Initially, a different
  submitted assignee was silently overwritten with the agent's own ID. This
  contradicted the brief's own acceptance criteria for goal 1 — "Agent
  attempting to reassign a ticket away from themselves → rejected by the
  API, with a clear error." Changed to explicitly reject with 403 and a
  clear message instead of silently overriding (commit 5bc25d3).

## Decision — Collaborators must be agents (Goal 5)

- **Chose:** Both primary assignee and collaborators must be users with the
  agent role; a supervisor can't be added as either.

- **Why:** The brief only ever describes supervisors reassigning tickets to
  agents, never being assignees themselves.

## Decision — Collaborator management permissions (Goal 5)

- **Chose:** Adding/removing collaborators is gated by the same
  `can_act_on_ticket` check as every other ticket action (edit, archive,
  reply, status transitions).

- **Rejected:** A narrower rule — e.g. only the primary assignee or a
  supervisor can manage collaborators.

- **Why:** Resolves a gap explicitly flagged in the original goal-1
  analysis ("add/remove collaborators... needs explicit decision"); one
  consistent permission check across all ticket actions is simpler to
  reason about and audit than a special case for this one action.

## Decision — Migration backfill for pre-existing tickets (Goal 5)

- **Chose:** Existing tickets (created before `primary_assignee_id`
  existed) were backfilled to the earliest-created agent.

- **Why:** The column is required, so every existing row needed a value.
  Explicitly documented in the migration's own comment as a placeholder,
  not a real triage strategy — this is dev/seed data, not production data
  needing a considered reassignment policy.

## Decision — Ticket-viewing scope (Goal 5 follow-up)

- **Chose:** Agents can only view tickets (list and detail) where they're
  primary assignee or collaborator; supervisors see everything. Enforced
  via `can_view_ticket` on `GET /tickets/{id}`, viewer-scoping built into
  `list_tickets` (inherited by `GET /tickets` and `GET /tickets/archived`),
  and `can_act_on_ticket` (stricter) on `GET /tickets/{id}/edit`.

- **Why:** Already specified in the original goal-1 analysis's roles table
  ("View entire queue — Agent: No, Supervisor: Yes") but unenforced from
  goal 2 through goal 5. Closed as soon as the gap was found rather than
  deferred to goal 6, since goal 6 only needed to add search/filter/sort on
  top of an already-scoped query.




## Decision — Priority sort ordering (Goal 6)

- **Chose:** An explicit CASE-based severity rank (low=1, normal=2, high=3,
  urgent=4) for "sort by priority."

- **Rejected:** A naive `ORDER BY priority` on the raw string column.

- **Why:** Priority is stored as a plain string, so alphabetical ordering
  produces `high, low, normal, urgent` — nonsense for a severity-based
  sort. Caught before committing, with a regression test
  (`test_sort_by_priority_uses_severity_order_not_alphabetical`) that fails
  against the naive version.

## Decision — Filter parameter parsing (Goal 6)

- **Chose:** Accept status/priority/category/assignee filters as raw query
  strings, parse them explicitly — empty string means "no filter," a
  genuinely invalid value is a real 422.

- **Rejected:** Typed `Optional[int]`/`Optional[Enum]` query parameters —
  FastAPI's default, more idiomatic approach.

- **Why:** Verified empirically that FastAPI can't parse `""` (what an
  unselected `<select>` sends) into `Optional[int]`/`Optional[Enum]`. The
  "default, idiomatic" approach would 422 the entire queue page the moment
  any filter was left on "Any..." — breaking the single most common case,
  no filters applied at all.




  ## Decision — Bulk endpoint authorization approach (Goal 7)

- **Chose:** No blanket role check on the bulk-reassign/bulk-close routes
  themselves; every ticket in a batch goes through the same
  `can_reassign_ticket`/`can_close_ticket` check as the single-ticket path.
  A batch submitted entirely by an unauthorized actor returns 200 with
  every item refused, not a blanket 403.

- **Rejected:** Gating the whole bulk endpoint to supervisors via a route-
  level role check.

- **Why:** One source of truth for "who can reassign/close a ticket,"
  instead of two rules — a route-level check and a per-ticket check — that
  could drift apart over time. Verified role-agnostic with a dedicated
  test.

## Decision — Bulk toolbar visibility (Goal 7)

- **Chose:** Hide the bulk-select checkboxes/toolbar from agents in the UI
  entirely.

- **Rejected:** Showing the bulk toolbar to everyone and letting the per-
  ticket refused-report explain why nothing happened.

- **Why:** `can_reassign_ticket` and `can_close_ticket` are both
  unconditionally supervisor-only, so an agent's bulk action would always
  come back 100% refused — a control that can never succeed has no value.

  ## Decision — CSV breach_status granularity (Goal 7)

- **Chose:** `breach_status` as a binary value (`breaching`/`on_track`) in
  the CSV export, computed via the existing
  `elapsed_response_time_for_ticket` + `TARGET_RESPONSE_TIME`.

- **Rejected:** A three-state value (`breaching`/`at-risk`/`on_track`)
  matching goal 10's eventual SLA alert model.

- **Why:** The "at-risk" threshold — how close to breaching counts as
  at-risk — is goal 10's design decision, not yet made. Computing a third
  state now would mean guessing at a number that hasn't been chosen, rather
  than reusing something already decided.




  ## Decision — Dashboard visibility (Goal 8)

- **Chose:** Dashboard is available to both roles, scoped identically to the
  rest of the app — agents see assignee-or-collaborator tickets only,
  supervisors see everything.
- **Rejected:** Making the dashboard supervisor-only.
- **Why:** Consistent with every other view in the app already respecting
  this scope; no reason for the dashboard to be the one exception.

## Decision — Agent dashboard's missing "breakdown by agent" (Goal 8)

- **Chose:** Simply omit the by-agent breakdown from an agent's dashboard
  view. Headline numbers, status breakdown, and the resolved/week chart are
  the full agent view.
- **Rejected:** Inventing a substitute dimension for agents in place of the
  by-agent breakdown.
- **Why:** A breakdown by agent only makes sense from a queue-wide view; an
  agent's own scoped view would only ever show themselves, so replacing it
  with something invented would add complexity the brief never asked for.

## Decision — "This week" definition (Goal 8)

- **Chose:** Calendar week, Monday–Sunday UTC, applied consistently to both
  the "resolved this week" headline number and the 8-week chart's bucketing.
- **Why:** The brief doesn't define the boundary; a fixed, consistent
  definition avoids the headline number and the chart silently disagreeing
  with each other over different week boundaries.

## Decision — Which statuses count as "currently breaching" (Goal 8)

- **Chose:** Only New, Open, and Pending tickets are eligible; Resolved and
  Closed tickets are never counted, regardless of their elapsed response
  time.
- **Why:** "Currently breaching" implies an active, ongoing state — a
  Resolved or Closed ticket isn't currently doing anything an agent needs
  to act on.


  ## Decision — Timeline replaces the reply list (Goal 9)

- **Chose:** The unified timeline replaces the standalone reply list from
  goal 3 as the single history view on the ticket detail page.
- **Rejected:** Keeping both — a separate reply thread alongside the new
  timeline.
- **Why:** The README describes one timeline that includes replies
  alongside status changes and reassignments; keeping a separate reply
  section would render the same replies twice. Internal/customer-visible
  badge styling carries over unchanged for reply entries within the
  unified view.


## Decision — SLA alert visibility scope (Goal 10)

- **Chose:** Supervisors see all breaching/at-risk tickets in alerts;
  agents see only tickets where they're primary assignee or collaborator.
- **Rejected:** A single shared alerts view identical for both roles.
- **Why:** Consistent with the original goal-1 roles table ("View entire
  queue — Agent: No, Supervisor: Yes") and the same viewer-scoping already
  established since goal 5 — reused directly for alerts rather than
  building parallel logic.


  ## Decision — SLA at-risk window (Goal 10)

- **Chose:** At-risk = elapsed time within 90% of the priority's target — a
  percentage, not a fixed duration.
- **Rejected:** A fixed duration window (e.g., "within 2 hours of
  breaching") applied uniformly across all priorities.
- **Why:** Targets range from 4h (urgent) to 72h (low). A fixed duration
  would be nearly meaningless for a 4h target and barely noticeable for a
  72h one; a percentage scales proportionally to each priority's own
  target.

## Decision — Acknowledgment is per-viewer (Goal 10)

- **Chose:** Acknowledgment keyed by (ticket_id, user_id, breach_epoch) —
  each viewer (primary assignee, each collaborator, each supervisor) tracks
  their own acknowledgment independently.
- **Rejected:** A single ticket-level acknowledgment clearing the alert for
  everyone once any one person acknowledges it.
- **Why:** The brief's own wording — "clearing it from their list" —
  implies a personal list; one collaborator dismissing an alert shouldn't
  hide it from the primary assignee or a supervisor who hasn't seen it yet.


  ## Decision — Resolved-period elapsed-time exclusion (Review pass)

- **Chose:** Added `TicketResolvedPeriod`, symmetric to
  `TicketPendingPeriod`/`TicketClosedPeriod`, excluding time spent
  Resolved-but-not-yet-Closed from `elapsed_response_time_for_ticket`.
- **Rejected:** Leaving Resolved-period time counted toward elapsed, the
  original goal-4 design.
- **Why:** Confirmed as a real, reproducible bug during the review pass — a
  ticket resolved in 30 minutes but left sitting Resolved for 10 days
  before being closed showed ~10 days elapsed on reopen. This had already
  silently affected the shipped CSV `breach_status` column from goal 7, not
  just a theoretical future scenario.

## Decision — Dependency vulnerabilities, accepted for now (Review pass)

- **Chose:** Did not upgrade any of the 26 known vulnerabilities pip-audit
  found across 7 packages.
- **Rejected:** Upgrading starlette (and its dependents) to a fixed
  version.
- **Why:** Starlette's available fixes are on a major version line FastAPI
  0.115.6 wasn't built against; upgrading independently risks breaking the
  app in ways outside a review pass's scope. Investigated the most severe
  finding specifically — python-jose's algorithm-confusion CVE-2024-33663
  (CVSS 9.3) — against actual usage: `decode_access_token` pins
  `algorithms=["HS256"]` explicitly, and the app never uses asymmetric keys
  or JWE, which both that CVE and its DoS sibling depend on — so it doesn't
  appear directly exploitable here. Accepted as a known, documented risk;
  a real production deployment would warrant a proper dependency upgrade
  pass beyond this project's scope.
  
  ## Decision — JWT secret required, no fallback (Review pass)

- **Chose:** `jwt_secret_key: str` with no default in `Settings` — the app
  fails to start (`pydantic.ValidationError`) if `JWT_SECRET_KEY` isn't set
  via environment or `.env`.
- **Rejected:** Keeping the `"dev-secret-change-me"` default.
- **Why:** A misconfigured deployment missing the env var would otherwise
  silently sign and accept tokens with a well-known secret instead of
  failing loudly. Local dev is unaffected — `.env` already sets it
  explicitly.

## Decision — Auth cookie `Secure` flag driven by environment (Review pass)

- **Chose:** Added `Settings.environment` (`"development"` default /
  `"production"`) and a computed `is_production` property; `auth.py` sets
  `secure=settings.is_production` on the login cookie.
- **Rejected:** Hardcoding `secure=True` (breaks local HTTP dev) or
  deriving it from `request.url.scheme` (unreliable behind a reverse proxy
  unless `X-Forwarded-Proto` is explicitly trusted).
- **Why:** The cookie must never be sent over plain HTTP in production, but
  must still work locally over `http://localhost`. An explicit environment
  flag is simpler and more predictable than scheme-sniffing.

## Decision — "View tickets" link removed from logged-out home page

- **Chose:** Removed the "View tickets" link entirely from the
  unauthenticated landing page; "Sign in" is the sole call to action.
- **Rejected:** Leaving it pointing at GET /tickets.
- **Why:** Same principle as goal 7's bulk-toolbar decision — the link
  could never succeed for a logged-out visitor (every route requires
  auth, there's no public ticket view), so showing it had no value.
  Discovered by actually clicking it, not caught in review.
