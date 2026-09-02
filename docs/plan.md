# Plan

## How did you break the work into sessions?

One session per prompt, roughly matching the 10 goals. Plus three sessions that weren't tied to a specific goal: an initial scaffold session before any feature work, a review pass once all 10 goals were done, and a final session for seed data and deployment.

For the two highest-risk goals (lifecycle and SLA in goal 4, SLA alerts in goal 10), and the goal 5 session that went back and added permission checks in, each one had two phases instead of one. First a design proposal, checked against the README and against earlier decisions before any code got written. Then a separate build, test, and commit phase.

## What order did you build in, and why that order?

Roughly the README own order, but the real constraint was data dependency, not the list order.

Accounts and roles came first, since every later goal's authorization depends on users existing. Tickets and replies came next as the core entities, with no dependency yet on lifecycle or ownership data.

Lifecycle (goal 4) came early on purpose, while there was still slack to absorb design iteration. It was flagged as highest risk from the start, and that timing paid off: two real design gaps got caught and fixed before implementation instead of after.

Collaborators (goal 5) came right after, since that's the goal that introduces real assignee data. Goals 2 through 4 had deliberately left ownership checks unenforced, because that data didn't exist yet, and goal 5 went back and added them all in at once.

Everything from goal 6 onward built directly on goal 5 viewer scoping and goal 4 SLA calculation, instead of recomputing either. The immutable timeline (goal 9) came after every goal that actually writes ticket history, so there was real history to make immutable by the time it existed. The review pass only made sense once all 10 goals were there to check. Deployment prep came last, since it depends on every model being final.

## What did you estimate versus what it actually took?

I expected this to take roughly 17-18 hours. Looking at the git commit timestamps, Goal by goal, the work was fast and consistent: 15-25 minutes per goal, from prompt to committed and tested code, across all 10 goals. Two stretches account for most of the gap between that per goal speed and the overall total. About 3 hours 45 minutes after goal 5, spent on review-pass follow-ups and catching up decisions.md. Then another roughly 3 hours 50 minutes before evening deployment work started. The estimate wasn't wrong about the code itself. It was wrong about how much time review and documentation discipline would take on top of it.


## What did you cut when you ran short?

- Dependency upgrades. pip-audit found 26 known vulnerabilities across 7 packages during the review pass. I looked into the worst one specifically, instead of just reacting to the CVSS score, and left the rest alone on purpose, since upgrading independently risked breaking the app given FastAPI version pin. More on that in decisions.md.

- Performance work at scale. SLA breach and at risk calculations recompute per ticket in a Python loop, in three places: alerts, dashboard headline counts, and CSV export, instead of one aggregate query. Bulk actions process one ticket per database round trip instead of a batched update. Text search is a plain `ILIKE` with no supporting index. No composite indexes exist anywhere in the schema. All of this is correct and fine at this data volume (see schema.md "what would break first at 100x the data"), but none of it would hold up unchanged at real production scale.

- Product features narrower than a real deployment would need, already covered in architecture.md: no self service registration or password reset, no JWT refresh or rotation, no real time updates between two agents on the same ticket, no rate limiting on login, no background job or cache for SLA state.