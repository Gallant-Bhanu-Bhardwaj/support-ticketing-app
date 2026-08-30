# Plan

Answer each of these, in your own words.

## How did you break the work into sessions?

One session per prompt, roughly matching the 10 goals, plus three
non-goal sessions, an initial scaffold session before any feature work,
a review pass after all 10 goals were done, and a final seed-data-and-
deployment session. For the two highest-risk goals (lifecycle/SLA in
goal 4, and SLA alerts in goal 10) and the collaborators retrofit in
goal 5, each session had two phases rather than one a design proposal
that got checked against the README and against earlier decisions
before any code was written, then a separate build/test/commit phase.

## What order did you build in, and why that order?

Roughly the README's own numbering, but the real constraint was data
dependency, not the list order. Accounts and roles came first since
every later goal's authorization depends on users existing. Tickets and
replies came next as the core entities, with no dependency on lifecycle
or ownership data yet. Lifecycle (goal 4) was tackled early on purpose,
while there was still slack to absorb design iteration, since it was
flagged as highest-risk from the start two real design gaps were
caught and fixed before implementation because of that timing.
Collaborators (goal 5) came right after, since it's the goal that
introduces real assignee data goals 2 through 4 had deliberately left
ownership checks unenforced because that data didn't exist yet, and
goal 5 retrofitted all of them at once. Everything from goal 6 onward
built directly on goal 5's viewer-scoping and goal 4's SLA calculation
rather than recomputing either. The immutable timeline (goal 9) came
after every goal that actually writes ticket history, so there was real
history to make immutable. The review pass came only once all 10 goals
existed to check. Deployment prep came last, since it depends on every
model being final.

## What did you estimate versus what it actually took?

I'd expected roughly 17-18 hours going in. Reconstructed from git commit
timestamps, actual work spanned from 12:00 on 2026-08-29 to 00:29 the next
morning — about 12.5 hours of calendar time, under the estimate. Goal-by-
goal implementation was consistently fast (15-25 minutes per goal, prompt
to committed and tested code) across all 10 goals. Two stretches account
for most of the gap between individual goal speed and the overall total, a
~3h45m period after goal 5 spent on review-pass follow-ups and backfilling
decisions.md, and a ~3h 50m gap before evening deployment work began. The
estimate undercounted how much time review and documentation discipline
would take relative to writing the code itself, not the other way around.


## What did you cut when you ran short?

- Dependency upgrades: pip-audit found 26 known vulnerabilities across 7
  packages during the review pass. Investigated the most severe one
  specifically rather than reacting to the CVSS score alone, then
  deliberately left the rest unfixed, since upgrading independently risked
  breaking the app given FastAPI's version pin see decisions.md.

- Performance work at scale: SLA breach/at-risk calculations recompute
  per-ticket in a Python loop in three places (alerts, dashboard headline
  counts, CSV export) instead of a single aggregate query; bulk actions
  process one ticket per DB roundtrip instead of a batched update; text
  search is a plain ILIKE with no supporting index; no composite indexes
  exist anywhere in the schema. All correct and fine at this data volume
  see schema.md's "what would break first at 100x the data" — but none of
  it would hold up unchanged at real production scale.

- Product features narrower than a real deployment would need, already
  reasoned about in architecture.md: no self-service registration or
  password reset, no JWT refresh/rotation, no real-time updates between two
  agents on the same ticket, no rate limiting on login, no background job
  or cache for SLA state.

- No literal TODO/FIXME comments anywhere confirmed by searching the
  codebase directly, not assumed.

