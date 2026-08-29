"""Seed demo users and a realistic ticket dataset. Run with: python -m app.seed

Idempotent at the top level: re-running skips user creation for existing
emails, and skips ticket creation entirely if any ticket already exists.
"""

from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.reply import ReplyCreate
from app.schemas.ticket import TicketCreate
from app.services import collaborator_service, lifecycle_service, reply_service, ticket_service

DEMO_USERS = [
    ("supervisor@example.com", "password123", UserRole.SUPERVISOR),
    ("agent1@example.com", "password123", UserRole.AGENT),
    ("agent2@example.com", "password123", UserRole.AGENT),
]

NEW, OPEN, PENDING, RESOLVED, CLOSED = "new", "open", "pending", "resolved", "closed"
URGENT, HIGH, NORMAL, LOW = (
    TicketPriority.URGENT,
    TicketPriority.HIGH,
    TicketPriority.NORMAL,
    TicketPriority.LOW,
)
BUG, BILLING, HOW_TO, FEATURE, OTHER = (
    TicketCategory.BUG,
    TicketCategory.BILLING,
    TicketCategory.HOW_TO,
    TicketCategory.FEATURE_REQUEST,
    TicketCategory.OTHER,
)

# Each dict describes one ticket's final state. `age` is how far back
# created_at is backdated from "now" -- for New/Open tickets this directly
# controls whether they show up breaching/at-risk (targets: urgent=4h,
# high=8h, normal=24h, low=72h), since neither status excludes any time.
TICKETS = [
    # -- New: two intentionally breaching/at-risk, rest fresh --
    dict(subject="Cannot log in after password reset", description="I reset my password but now I get an error saying my account is locked.", requester="jane.doe@example.com", category=BUG, priority=URGENT, assignee="agent1@example.com", status=NEW, age=timedelta(hours=10)),  # breaching (urgent target 4h)
    dict(subject="How do I export my data to CSV?", description="I need to export all our project data before our contract renewal review.", requester="ops@northwind.io", category=HOW_TO, priority=LOW, assignee="agent2@example.com", status=NEW, age=timedelta(hours=2)),
    dict(subject="Feature request: dark mode", description="Our team works late and would really appreciate a dark mode option.", requester="sara.lee@example.com", category=FEATURE, priority=LOW, assignee="agent1@example.com", status=NEW, age=timedelta(hours=1)),
    dict(subject="Please add SSO support", description="Our security team requires SSO before we can roll this out company-wide.", requester="it@globex.com", category=FEATURE, priority=NORMAL, assignee="agent2@example.com", status=NEW, age=timedelta(minutes=30)),
    dict(subject="How to set up recurring reports", description="I want a weekly summary emailed automatically.", requester="analytics@massive-dynamic.com", category=HOW_TO, priority=NORMAL, assignee="agent1@example.com", status=NEW, age=timedelta(hours=3)),

    # -- Open: one breaching, one at-risk, rest fresh --
    dict(subject="App crashes on startup on Windows 11", description="Since the last update the desktop app crashes immediately after the splash screen.", requester="d.chen@example.com", category=BUG, priority=HIGH, assignee="agent2@example.com", status=OPEN, age=timedelta(hours=9), replies=[dict(author="agent2@example.com", body="Thanks for the report -- can you send us the crash log from %AppData%/Logs?")]),  # breaching (high target 8h)
    dict(subject="Slow performance on large projects", description="Projects with over 500 tasks take a very long time to load.", requester="pm@wayne-ent.com", category=BUG, priority=NORMAL, assignee="agent1@example.com", status=OPEN, age=timedelta(hours=22), replies=[dict(author="agent1@example.com", body="Looking into this -- seems related to how we paginate the task list.")]),  # at-risk (normal target 24h)
    dict(subject="Duplicate charge on my card", description="I was charged twice for my monthly subscription this billing cycle.", requester="m.patel@example.com", category=BILLING, priority=HIGH, assignee="agent2@example.com", status=OPEN, age=timedelta(hours=1), collaborator="agent1@example.com"),
    dict(subject="Two-factor authentication not working", description="I can't complete 2FA setup, the QR code never loads.", requester="security@umbrella.co", category=BUG, priority=URGENT, assignee="agent1@example.com", status=OPEN, age=timedelta(hours=1), replies=[dict(author="agent1@example.com", body="Can you confirm which authenticator app you're using?")]),
    dict(subject="Broken link in welcome email", description="The 'Get Started' link in the onboarding email 404s.", requester="newuser@soylent.com", category=BUG, priority=LOW, assignee="agent2@example.com", status=OPEN, age=timedelta(hours=4)),

    # -- Pending: currently waiting on the customer --
    dict(subject="Invoice discrepancy for March", description="The March invoice shows a charge for a plan we downgraded from in February.", requester="billing@acme-corp.com", category=BILLING, priority=NORMAL, assignee="agent1@example.com", status=PENDING, age=timedelta(days=1), replies=[dict(author="agent1@example.com", body="Could you send over your account ID so we can check the billing history?")]),
    dict(subject="Refund request for unused seats", description="We removed 5 seats last month but were still billed for them.", requester="finance@initech.com", category=BILLING, priority=NORMAL, assignee="agent2@example.com", status=PENDING, age=timedelta(hours=6), collaborator="agent1@example.com"),
    dict(subject="Cannot cancel subscription", description="The cancel button on the billing page is greyed out.", requester="billing@pied-piper.com", category=BILLING, priority=HIGH, assignee="agent1@example.com", status=PENDING, age=timedelta(hours=12)),
    dict(subject="Mobile app notifications delayed", description="Push notifications sometimes arrive hours late on iOS.", requester="user@aviato.com", category=BUG, priority=NORMAL, assignee="agent2@example.com", status=PENDING, age=timedelta(days=2), replies=[dict(author="agent2@example.com", body="We've asked our mobile team to check APNs delivery -- will follow up.", internal=True)]),
    dict(subject="Cannot upload files larger than 10MB", description="Getting a generic error uploading a 15MB PDF.", requester="docs@gringotts.co", category=BUG, priority=LOW, assignee="agent1@example.com", status=PENDING, age=timedelta(hours=8)),

    # -- Resolved: spread across past weeks so the dashboard chart has data --
    dict(subject="How to add a teammate to my workspace", description="I can't find where to invite new members to my workspace.", requester="team@brightpath.co", category=HOW_TO, priority=LOW, assignee="agent2@example.com", status=RESOLVED, age=timedelta(hours=5), resolved_after=timedelta(hours=1), replies=[dict(author="agent2@example.com", body="You can invite teammates from Settings > Members > Invite.")]),
    dict(subject="How do I change my billing email?", description="Our accounts payable email changed and I need to update it.", requester="ap@stark-industries.com", category=HOW_TO, priority=LOW, assignee="agent1@example.com", status=RESOLVED, age=timedelta(days=3), resolved_after=timedelta(hours=2), replies=[dict(author="agent1@example.com", body="Updated -- you should see the new email reflected on your next invoice.")]),
    dict(subject="Overcharged after downgrade", description="We downgraded plans but were charged at the old rate.", requester="billing@oscorp.com", category=BILLING, priority=HIGH, assignee="agent2@example.com", status=RESOLVED, age=timedelta(days=8), resolved_after=timedelta(hours=3), replies=[dict(author="agent2@example.com", body="Issued a credit for the difference -- apologies for the trouble.")]),
    dict(subject="How do I reset a teammate's password?", description="One of our admins is locked out and I need to help them in.", requester="admin@monsters-inc.com", category=HOW_TO, priority=NORMAL, assignee="agent1@example.com", status=RESOLVED, age=timedelta(days=10), resolved_after=timedelta(hours=4)),
    dict(subject="How to bulk import contacts", description="Is there a way to import contacts from a CSV file?", requester="sales@pearson-hardman.com", category=HOW_TO, priority=LOW, assignee="agent2@example.com", status=RESOLVED, age=timedelta(days=15), resolved_after=timedelta(hours=1), replies=[dict(author="agent2@example.com", body="Yes -- use the Import Contacts button on the Contacts page.")]),
    dict(subject="Search results are inaccurate", description="Searching for exact phrases still returns unrelated results.", requester="support@abstergo.com", category=BUG, priority=NORMAL, assignee="agent1@example.com", status=RESOLVED, age=timedelta(days=20), resolved_after=timedelta(hours=6)),
    dict(subject="Dashboard widgets not saving layout", description="Every time I log back in my custom dashboard layout resets.", requester="ux@dunder-mifflin.com", category=BUG, priority=NORMAL, assignee="agent2@example.com", status=RESOLVED, age=timedelta(days=4), resolved_after=timedelta(hours=2)),

    # -- Closed: some archived --
    dict(subject="Tax invoice missing VAT number", description="Our VAT number isn't showing on the generated invoice PDF.", requester="accounts@bluth-company.com", category=BILLING, priority=NORMAL, assignee="agent1@example.com", status=CLOSED, age=timedelta(days=12), resolved_after=timedelta(hours=3), closed_after=timedelta(hours=1), archived=True, replies=[dict(author="agent1@example.com", body="Added your VAT number to the account -- future invoices will include it.")]),
    dict(subject="Add support for custom domains", description="We'd like to use our own domain for the customer portal.", requester="webmaster@cyberdyne.com", category=FEATURE, priority=LOW, assignee="agent2@example.com", status=CLOSED, age=timedelta(days=25), resolved_after=timedelta(hours=5), closed_after=timedelta(hours=2)),
    dict(subject="Request: bulk tag editing", description="It would help a lot to edit tags on many items at once.", requester="ops@hooli.com", category=FEATURE, priority=LOW, assignee="agent1@example.com", status=CLOSED, age=timedelta(days=18), resolved_after=timedelta(hours=2), closed_after=timedelta(hours=1), archived=True),
    dict(subject="Request: API rate limit increase", description="We're hitting rate limits during our nightly sync job.", requester="dev@wonka-industries.com", category=FEATURE, priority=HIGH, assignee="agent2@example.com", status=CLOSED, age=timedelta(days=6), resolved_after=timedelta(hours=1), closed_after=timedelta(minutes=30), collaborator="agent1@example.com", replies=[dict(author="agent2@example.com", body="Bumped your rate limit to 500 req/min -- let us know if you need more.")]),
    dict(subject="Feature request: Slack integration", description="We'd love ticket updates posted directly to our Slack channel.", requester="ops@tyrell-corp.com", category=FEATURE, priority=NORMAL, assignee="agent1@example.com", status=CLOSED, age=timedelta(days=30), resolved_after=timedelta(hours=4), closed_after=timedelta(hours=1)),
]


def seed_users(db) -> dict[str, User]:
    users = {}
    for email, password, role in DEMO_USERS:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, hashed_password=hash_password(password), role=role)
            db.add(user)
            db.commit()
            db.refresh(user)
        users[email] = user
    return users


def seed_tickets(db, users: dict[str, User]) -> int:
    if db.query(Ticket).count() > 0:
        return 0

    supervisor = users["supervisor@example.com"]
    now = datetime.now(timezone.utc)

    for spec in TICKETS:
        assignee = users[spec["assignee"]]
        created_at = now - spec["age"]

        ticket = ticket_service.create_ticket(
            db,
            TicketCreate(
                subject=spec["subject"],
                description=spec["description"],
                requester=spec["requester"],
                priority=spec["priority"],
                category=spec["category"],
                primary_assignee_id=assignee.id,
            ),
            supervisor,
        )
        ticket.created_at = created_at
        db.commit()
        db.refresh(ticket)

        status = spec["status"]
        if status != NEW:
            open_at = created_at + min(spec["age"] * 0.1, timedelta(hours=1))
            lifecycle_service.transition(db, ticket, TicketStatus.OPEN, assignee, now=open_at)

            if status == PENDING:
                pending_at = open_at + min(spec["age"] * 0.2, timedelta(hours=2))
                lifecycle_service.transition(db, ticket, TicketStatus.PENDING, assignee, now=pending_at)

            elif status in (RESOLVED, CLOSED):
                resolved_at = min(open_at + spec.get("resolved_after", timedelta(hours=1)), now - timedelta(minutes=2))
                lifecycle_service.transition(db, ticket, TicketStatus.RESOLVED, assignee, now=resolved_at)

                if status == CLOSED:
                    closed_at = min(resolved_at + spec.get("closed_after", timedelta(hours=1)), now - timedelta(minutes=1))
                    lifecycle_service.transition(db, ticket, TicketStatus.CLOSED, supervisor, now=closed_at)

        if spec.get("archived"):
            ticket_service.archive_ticket(db, ticket, supervisor)

        if spec.get("collaborator"):
            collaborator = users[spec["collaborator"]]
            collaborator_service.add_collaborator(db, ticket, collaborator.id, supervisor)

        for reply_spec in spec.get("replies", []):
            author = users[reply_spec["author"]]
            reply_service.add_reply(
                db,
                ticket,
                author,
                ReplyCreate(body=reply_spec["body"], is_internal=reply_spec.get("internal", False)),
            )

    return len(TICKETS)


def seed() -> None:
    db = SessionLocal()
    try:
        users = seed_users(db)
        ticket_count = seed_tickets(db, users)
    finally:
        db.close()
    return ticket_count


if __name__ == "__main__":
    count = seed()
    print("Seeded demo users:")
    for email, _, role in DEMO_USERS:
        print(f"  {email} ({role.value})")
    if count:
        print(f"Seeded {count} demo tickets.")
    else:
        print("Tickets already present -- skipped ticket seeding.")
