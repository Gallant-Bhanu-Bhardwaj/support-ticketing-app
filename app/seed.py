"""Seed demo users. Run with: python -m app.seed"""

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole

DEMO_USERS = [
    ("supervisor@example.com", "password123", UserRole.SUPERVISOR),
    ("agent1@example.com", "password123", UserRole.AGENT),
    ("agent2@example.com", "password123", UserRole.AGENT),
]


def seed() -> None:
    db = SessionLocal()
    try:
        for email, password, role in DEMO_USERS:
            if db.query(User).filter(User.email == email).first():
                continue
            db.add(User(email=email, hashed_password=hash_password(password), role=role))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Seeded demo users:")
    for email, _, role in DEMO_USERS:
        print(f"  {email} ({role.value})")
