from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.core.database import get_db
from app.core.dependencies import get_current_user_optional


def _inject_current_user(request: Request) -> dict:
    """Every template needs current_user for the sidebar (who's signed in,
    role-conditional nav) even on routes that don't otherwise depend on it.
    Reuses the exact same cookie/JWT resolution the nav's alert badge
    already relies on (get_current_user_optional) rather than a second
    implementation of "who is this" -- called directly with our own
    short-lived session, since a Jinja2 context processor only ever
    receives the Request, not FastAPI's dependency-injection system.

    Resolves the DB session through request.app.dependency_overrides
    rather than importing SessionLocal directly, so this respects the
    same test-database override the rest of the app's dependencies do --
    otherwise tests would silently look up the user in the real app.db
    instead of the test database."""
    db_dependency = request.app.dependency_overrides.get(get_db, get_db)
    db_generator = db_dependency()
    db = next(db_generator)
    try:
        return {"current_user": get_current_user_optional(request, db)}
    finally:
        db_generator.close()


templates = Jinja2Templates(directory="app/templates", context_processors=[_inject_current_user])
