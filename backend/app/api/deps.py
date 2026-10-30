from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.entities import Business, BusinessUser, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin role required")
    return user


def get_current_business(
    x_business_id: int | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Business:
    """Resolve the tenant the request acts on and verify membership.

    Multi-tenant isolation gate: every tenant-scoped router depends on this,
    so a user can only ever operate on a business they belong to.
    """
    if user.role == "platform_admin":
        if x_business_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Business-Id header required for admin")
        business = db.get(Business, x_business_id)
        if business is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
        return business

    query = (
        db.query(Business)
        .join(BusinessUser, BusinessUser.business_id == Business.id)
        .filter(BusinessUser.user_id == user.id)
    )
    if x_business_id is not None:
        query = query.filter(Business.id == x_business_id)
    business = query.order_by(Business.id).first()
    if business is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No business membership found for user")
    return business


def require_business_role(*roles: str):
    """Restrict an endpoint to specific business roles (e.g. owner)."""

    def checker(
        business: Business = Depends(get_current_business),
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Business:
        if user.role == "platform_admin":
            return business
        link = (
            db.query(BusinessUser)
            .filter(BusinessUser.business_id == business.id, BusinessUser.user_id == user.id)
            .first()
        )
        if link is None or (roles and link.role not in roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires business role: {', '.join(roles)}")
        return business

    return checker
