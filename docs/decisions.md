# Decisions

Real decisions made while building this, in the order they happened.

## Decision — Auth error status codes (Goal 1)

- **Chose:** A uniform 403 for every kind of auth failure, whether the token was missing, invalid, or just belonged to the wrong role.

- **Rejected:** The conventional split most APIs use, 401 for a missing or invalid token, 403 only when the token is valid but the role is wrong.

- **Why:** Early on, this felt like the simpler path. One check catches everything, and there's only one response path to write and test, instead of two separate cases to get right.

- **Later reversed:** I came back to this later and switched it to the standard 401/403 split (commit 405798a). The reasoning changed once there was more of the app to actually look at a reviewer reading through the codebase would expect the conventional REST behavior by default, and since the app already existed at that point, splitting the two cases apart cost almost nothing to do properly.


## Decision — Requester field format (Goal 2)

- **Chose:** `requester` as a single free text string.

- **Rejected:** A structured requester, split into separate name and email fields, or a proper foreign key to a real contact record.

- **Why:** The brief talks about "a requester" as if it's one piece of information, not a name plus an email plus whatever else a contact record might need. Building out a whole structured contact model would have meant designing something the brief never actually asked for, just because it felt like the more "correct" or complete way to model a real person. Since goal 2 doesn't need anything more than knowing who a ticket is for, a single free text field does exactly what's required without adding structure, and the maintenance that comes with it, that nothing in this project actually calls for.


## Decision — Per-priority SLA targets (Goal 4)

- **Chose:** urgent = 4 hours, high = 8 hours, normal = 24 hours, low = 72 hours.

- **Why:** The brief says every priority needs a target response time, but it doesn't say what the actual numbers should be, that part was left for me to decide. I picked values that scale reasonably with urgency, urgent tickets need attention fast, low priority ones can wait a few days. I stored these as plain configuration values rather than hardcoding them onto individual tickets, so if the numbers ever need to change, it's a one  line edit in a config file instead of a database migration or a change scattered across the codebase.

## Decision — No Resolved → Open transition (Goal 4)

- **Chose:** A Resolved ticket can only move forward to Closed. The only way to reopen a ticket at all is Closed → Open, and only within the 7-day window.

- **Rejected:** Letting a Resolved ticket reopen directly, say if there's new activity on it, before it's ever actually been Closed.

- **Why:** I went back to the brief specifically to check this, since it would have been easy to just assume a "reopen from Resolved" path made sense. The brief describes exact clock behavior for two transitions: Pending → Open, and Closed → Open. It never says anything about Resolved → Open. Given that the brief also states that any move it doesn't explicitly allow has to be rejected by the server with a reason, the safer and more faithful choice was to treat Resolved → Open as one of those "other moves" and reject it, rather than invent a transition the brief never actually described just because it seemed like it might be useful.


## Decision — Agent-submitted assignee override (Goal 5)

- **Chose:** Agents can never set `primary_assignee_id` to someone other than themselves, whether they're creating a new ticket or editing an existing one.

- **Rejected:** Letting agents pick any assignee they want.

- **Why:** The brief is explicit that agents can't reassign a ticket away from themselves. But if I'd let an agent freely choose the assignee when creating or editing a ticket, that would have been a quiet way around that exact rule, they could just set someone else as the primary assignee from the start, or switch it during an edit, without ever going through anything that looked like a "reassign" action. The restriction only really means something if it applies everywhere the assignee field can be touched, not just in one specific reassign endpoint. So I locked it down completely. no matter which route or form an agent uses, they can only ever end up as their own assignee.

- **Later reversed (enforcement, not the rule):** The rule itself never changed, but how it was enforced did. At first, if an agent submitted someone else's ID as the assignee, the code just quietly swapped it back to the agent's own ID and moved on, no error, no message. That technically prevented the wrong outcome, but it directly contradicted what the brief actually asked for in its goal-1 acceptance criteria: "Agent attempting to reassign a ticket away from themselves → rejected by the API, with a clear error." Silently correcting the value isn't the same as rejecting the request. Once I caught that mismatch, I changed the behavior to explicitly reject the submission with a 403 and a clear error message instead of fixing it behind the agent's back (commit 491cac0).

## Decision — Collaborators must be agents (Goal 5)

- **Chose:** Both the primary assignee and any collaborators have to be users with the agent role. A supervisor can't be set as either one.

- **Why:** Nowhere in the brief does a supervisor ever show up as someone a ticket gets assigned to. The only role the brief gives supervisors in relation to assignment is reassigning tickets to agents, they hand work off, they don't receive it. Since collaborators have essentially the same rights on a ticket as the primary assignee, it made sense to apply that same rule to both: if supervisors were never meant to be assignees, they shouldn't be able to sneak into that role through the collaborator list either.



## Decision — Priority sort ordering (Goal 6)

- **Chose:** An explicit CASE based severity rank (low=1, normal=2, high=3, urgent=4) for "sort by priority."

- **Rejected:** A naive `ORDER BY priority` on the raw string column.

- **Why:** Priority is stored as a plain string in the database, not a number. So a normal alphabetical sort just orders the text: "high" comes before "low," which comes before "normal," which comes before "urgent." That's completely backwards for what a priority sort should actually do, which is show urgent tickets first, then high, then normal, then low. I caught this before committing, but I didn't just fix it and move on. I wrote a test specifically designed to fail if someone (or some future version of this code) went back to a plain column sort. The test seeds tickets with all four priorities, sorts by priority, and checks the actual order that comes back. If it's ever alphabetical instead of severity based, the test fails loudly instead of the bug quietly coming back.

## Decision — Filter parameter parsing (Goal 6)

- **Chose:** Accept status/priority/category/assignee filters as raw query strings, and parse them explicitly. An empty string means "no filter." A genuinely invalid value gets a real 422.

- **Rejected:** Typed `Optional[int]`/`Optional[Enum]` query parameters, which is FastAPI's default and the more idiomatic approach.

- **Why:** I actually tested this rather than assuming. FastAPI can't parse `""`, which is exactly what an unselected `<select>` dropdown sends, into `Optional[int]` or `Optional[Enum]`. So the "correct, idiomatic" approach would have crashed the entire queue page with a 422 the moment someone left any filter on "Any..." — which is the single most common case there is: loading the page with no filters applied at all. Parsing the strings myself meant I could handle that case on purpose instead of accidentally breaking it.



## Decision — Bulk endpoint authorization approach (Goal 7)

- **Chose:** No blanket role check on the bulk-reassign / bulk-close routes themselves. Every ticket in a batch goes through the same `can_reassign_ticket`/`can_close_ticket` check as the single-ticket path. If someone submits a batch they're not authorized for at all, they get a 200 back with every single item marked refused, not a blanket 403 on the whole request.

- **Rejected:** Gating the whole bulk endpoint at the route level, so only supervisors could even hit it.

- **Why:** If I'd gated the route itself, I'd have ended up with two separate places that decide "who's allowed to reassign or close a ticket": the route-level check, and the per ticket check that already exists for the single ticket path. Two rules doing the same job always risk drifting apart over time, someone fixes one and forgets the other, and now the bulk and single ticket paths disagree about who's allowed to do what. Reusing the exact same per ticket check for both means there's only ever one place that answer lives. I confirmed this actually works the way I intended with a dedicated test, a crafted request from an unauthorized agent still gets a normal 200 response with a per-item refusal, not an unexpected 403 at the route level.

## Decision — Dashboard visibility (Goal 8)

- **Chose:** Dashboard is available to both roles, scoped identically to the rest of the app. Agents see only tickets where they're the assignee or a collaborator, supervisors see everything.

- **Rejected:** Making the dashboard supervisor only.

- **Why:** By the time I got to this goal, every other view in the app, the queue, search, ticket detail, all already respected this same scoping rule, agents see their own tickets, supervisors see all of them. Making the dashboard the one place that broke from that pattern would have been inconsistent for no real reason. There was no requirement anywhere saying agents shouldn't have dashboard access, so restricting it to supervisors only would have been me inventing a limitation the brief never asked for, just because it happened to be the last goal I was building.

## Decision — Agent dashboard's missing "breakdown by agent" (Goal 8)

- **Chose:** Simply leave out the by agent breakdown from an agent's dashboard view entirely. Headline numbers, status breakdown, and the resolved per week chart are the whole agent view.

- **Rejected:** Inventing some substitute dimension for agents, in place of the by agent breakdown they don't get.

- **Why:** The by agent breakdown only means anything from a queue wide view, where you're comparing how much work different agents are carrying. An agent looking at their own scoped dashboard would only ever see themselves in that breakdown, since they can't see anyone else's tickets. A "breakdown" of one person isn't a breakdown, it's just a number they already have. I could have tried to replace it with something else, some other chart or stat, but that would mean inventing a feature the brief never asked for just to fill a gap that didn't actually need filling. Leaving it out is the more honest choice, this widget genuinely doesn't apply here, so it doesn't show up.




## Decision — Timeline replaces the reply list (Goal 9)

- **Chose:** The unified timeline replaces the standalone reply list from goal 3 as the single history view on the ticket detail page.

- **Rejected:** Keeping both the old reply thread sitting alongside the new timeline as two separate sections.

- **Why:** The README describes one timeline that includes replies mixed in with status changes and reassignments, not a timeline plus a separate reply list next to it. If I'd kept both, every reply would show up twice on the same page, once in its original list from goal 3, and again inside the new timeline. That's confusing for anyone reading the ticket, and it's also just redundant code maintaining two views of the same data. Replacing the reply list with the timeline was the more faithful reading of what was actually asked for. The one thing I made sure not to lose in that switch was the internal versus customer visible badge styling on replies, since that distinction still matters and needed to carry over into the unified view exactly as it worked before.

## Decision — SLA alert visibility scope (Goal 10)

- **Chose:** Supervisors see every breaching and at risk ticket in the alerts view. Agents only see alerts for tickets where they're the primary assignee or a collaborator.

- **Rejected:** One shared alerts view that looks the same for both roles.

- **Why:** This wasn't a new decision so much as applying a rule that was already settled back in the goal 1 analysis, where the roles table explicitly said agents don't get to see the entire queue, only supervisors do. Alerts are really just another view into the same ticket data, so it would have been inconsistent to suddenly give agents full visibility here when every other screen in the app respects that boundary. Rather than writing a new scoping check just for alerts, I reused the exact same viewer scoping logic that's been in place since goal 5. That keeps the rule defined in one place instead of two, so if it ever needs to change, there's only one spot to update.


 ## Decision — SLA at-risk window (Goal 10)

- **Chose:** A ticket counts as "at risk" once it's used up 90% of its elapsed time against its priority's target. A percentage of the target, not a fixed amount of time.

- **Rejected:** A flat duration, like "within 2 hours of breaching," applied the same way to every priority.

- **Why:** The targets themselves are wildly different depending on priority, from 4 hours for urgent all the way up to 72 hours for low. A fixed 2 hour warning window would be almost the entire target for an urgent ticket, so it'd trigger almost immediately and not give much of a real warning. For a low priority ticket, that same 2 hours would be such a tiny sliver of the full 72 hour window that it'd barely register as a warning at all, you'd probably breach it before ever noticing the alert. A percentage-based threshold scales with each priority automatically, so "at-risk" means roughly the same thing, proportionally, no matter which priority a ticket has.


