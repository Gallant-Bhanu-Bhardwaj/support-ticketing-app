from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User, UserRole

ACCESS_TOKEN_COOKIE = "access_token"


def _resolve_user_from_cookie(request: Request, db: Session) -> User | None:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        return None
    email = decode_access_token(token)
    if not email:
        return None
    return db.query(User).filter(User.email == email).first()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _resolve_user_from_cookie(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    """For the global nav's alert badge, which renders on pages that don't
    otherwise require a login (home, the login page itself) -- None means
    "not signed in," not an error."""
    return _resolve_user_from_cookie(request, db)


def require_role(*roles: UserRole):
    allowed = set(roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            allowed_names = ", ".join(role.value for role in allowed)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {allowed_names}",
            )
        return current_user

    return dependency
