# Decisions

Real decisions made while building this, in the order they happened.

## Decision — Auth error status codes (Goal 1)

- **Chose:** Uniform 403 for every auth failure missing token, invalid
  token, wrong role.

- **Rejected:** The conventional split 401 for missing/invalid token, 403
  for wrong role.

- **Why:** Simpler at the time one check, one response path.

- **Later reversed:** Switched to the conventional 401/403 split (commit
  7e6dec6), since a reviewer reading the code would expect standard REST
  semantics, and the split cost almost nothing to make once the codebase
  existed to check it against.



## Decision — Requester field format (Goal 2)

- **Chose:** `requester` as a single free-text string.

- **Rejected:** A structured requester separate name/email fields, or a
  foreign key to a contact record.

- **Why:** The brief specifies "a requester" as one attribute splitting it
  would add structure beyond what was asked.



## Decision — Per-priority SLA targets (Goal 4)

- **Chose:** urgent = 4h, high = 8h, normal = 24h, low = 72h.

- **Why:** The brief requires a target response time per priority without
  specifying numbers  these are a reasonable, easily adjustable default
  stored as plain config, not hardcoded per ticket.


## Decision — No Resolved → Open transition (Goal 4)

- **Chose:** Resolved tickets can only move forward to Closed. Reopening
  only exists via Closed → Open, within the 7 day window.

- **Rejected:** Allowing a Resolved ticket to reopen directly (e.g. on new
  activity) before it's even Closed.

- **Why:** The brief specifies clock behavior for Pending → Open and
  Closed → Open explicitly, but never for Resolved → Open  treated as one
  of the "other moves" the brief says must be rejected, rather than
  inventing an unstated transition.



## Decision — Agent-submitted assignee override (Goal 5)

- **Chose:** Agents can never set `primary_assignee_id` to someone other
  than themselves, at creation or edit.

- **Rejected:** Allowing agents to pick any assignee.

- **Why:** Consistent with agents never being able to reassign a ticket at
  all, per the brief.
- **Later reversed (enforcement, not the rule):** Initially, a different
  submitted assignee was silently overwritten with the agent's own ID. This
  contradicted the brief's own acceptance criteria for goal 1  "Agent
  attempting to reassign a ticket away from themselves → rejected by the
  API, with a clear error." Changed to explicitly reject with 403 and a
  clear message instead of silently overriding (commit 5bc25d3).

## Decision — Collaborators must be agents (Goal 5)

- **Chose:** Both primary assignee and collaborators must be users with the
  agent role, a supervisor can't be added as either.

- **Why:** The brief only ever describes supervisors reassigning tickets to
  agents, never being assignees themselves.




## Decision — Priority sort ordering (Goal 6)

- **Chose:** An explicit CASE-based severity rank (low=1, normal=2, high=3,
  urgent=4) for "sort by priority."

- **Rejected:** A naive `ORDER BY priority` on the raw string column.

- **Why:** Priority is stored as a plain string, so alphabetical ordering
  produces `high, low, normal, urgent` nonsense for a severity based
  sort. Caught before committing, with a regression test
  (`test_sort_by_priority_uses_severity_order_not_alphabetical`) that fails
  against the naive version.

## Decision — Filter parameter parsing (Goal 6)

- **Chose:** Accept status/priority/category/assignee filters as raw query
  strings, parse them explicitly empty string means "no filter," a
  genuinely invalid value is a real 422.

- **Rejected:** Typed `Optional[int]`/`Optional[Enum]` query parameters
  FastAPI's default, more idiomatic approach.

- **Why:** Verified empirically that FastAPI can't parse `""` (what an
  unselected `<select>` sends) into `Optional[int]`/`Optional[Enum]`. The
  "default, idiomatic" approach would 422 the entire queue page the moment
  any filter was left on "Any..."  breaking the single most common case,
  no filters applied at all.




  ## Decision — Bulk endpoint authorization approach (Goal 7)

- **Chose:** No blanket role check on the bulk-reassign/bulk-close routes
  themselves every ticket in a batch goes through the same
  `can_reassign_ticket`/`can_close_ticket` check as the single-ticket path.
  A batch submitted entirely by an unauthorized actor returns 200 with
  every item refused, not a blanket 403.

- **Rejected:** Gating the whole bulk endpoint to supervisors via a route
  level role check.

- **Why:** One source of truth for "who can reassign/close a ticket,"
  instead of two rules a route level check and a per ticket check that
  could drift apart over time. Verified role-agnostic with a dedicated
  test.



  ## Decision — Dashboard visibility (Goal 8)

- **Chose:** Dashboard is available to both roles, scoped identically to the
  rest of the app agents see assignee or collaborator tickets only,
  supervisors see everything.

- **Rejected:** Making the dashboard supervisor only.

- **Why:** Consistent with every other view in the app already respecting
  this scope; no reason for the dashboard to be the one exception.

## Decision — Agent dashboard's missing "breakdown by agent" (Goal 8)

- **Chose:** Simply omit the by agent breakdown from an agent's dashboard
  view. Headline numbers, status breakdown, and the resolved/week chart are
  the full agent view.

- **Rejected:** Inventing a substitute dimension for agents in place of the
  by-agent breakdown.

- **Why:** A breakdown by agent only makes sense from a queue wide view; an
  agent's own scoped view would only ever show themselves, so replacing it
  with something invented would add complexity the brief never asked for.




  ## Decision — Timeline replaces the reply list (Goal 9)

- **Chose:** The unified timeline replaces the standalone reply list from
  goal 3 as the single history view on the ticket detail page.

- **Rejected:** Keeping both a separate reply thread alongside the new
  timeline.

- **Why:** The README describes one timeline that includes replies
  alongside status changes and reassignments, keeping a separate reply
  section would render the same replies twice. Internal/customer visible
  badge styling carries over unchanged for reply entries within the
  unified view.


## Decision — SLA alert visibility scope (Goal 10)

- **Chose:** Supervisors see all breaching at risk tickets in alerts,
  agents see only tickets where they're primary assignee or collaborator.

- **Rejected:** A single shared alerts view identical for both roles.

- **Why:** Consistent with the original goal-1 roles table ("View entire
  queue Agent: No, Supervisor: Yes") and the same viewer scoping already
  established since goal 5 reused directly for alerts rather than
  building parallel logic.


  ## Decision — SLA at-risk window (Goal 10)

- **Chose:** At-risk = elapsed time within 90% of the priority's target  a
  percentage, not a fixed duration.

- **Rejected:** A fixed duration window (e.g., "within 2 hours of
  breaching") applied uniformly across all priorities.

- **Why:** Targets range from 4h (urgent) to 72h (low). A fixed duration
  would be nearly meaningless for a 4h target and barely noticeable for a
  72h one; a percentage scales proportionally to each priority's own
  target.


