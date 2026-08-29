# Decisions

Real decisions made while building this, in the order they happened —
including one deliberately left open until it's actually built (SLA alert
scope, goal 10).

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

---

*Still to come as later goals land: SLA alert scope (supervisors see all
breaching tickets, agents see only their own) and collaborator acknowledge
rights (goal 10) — both already decided, logged here once goal 10 is
actually built.*
