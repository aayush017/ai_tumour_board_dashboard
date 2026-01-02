"""
Authentication & authorization utilities.

Implements:
- Master (admin) email/password login using secure hashing
- Google OAuth (ID token) login for regular users with DB allow-list
- JWT-based access & refresh tokens stored in HTTP-only cookies
- Role-based access control helpers
- Audit logging helpers (login + route access)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import os
import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi import status
from fastapi.responses import Response
from passlib.context import CryptContext
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User, UserRole, AllowListedEmail, AuditLog


# Use PBKDF2-SHA256 to avoid system bcrypt issues while keeping strong security.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-prod")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return pwd_context.verify(password, password_hash)


def create_tokens(*, user: User, session_id: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Returns (access_token, refresh_token, session_id).
    """
    now = datetime.now(timezone.utc)
    if not session_id:
        session_id = str(uuid.uuid4())

    access_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role.value,
        "sid": session_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    refresh_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role.value,
        "sid": session_id,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_DAYS)).timestamp()),
    }

    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return access_token, refresh_token, session_id


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    cookie_domain = os.getenv("COOKIE_DOMAIN") or None

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=cookie_domain,
        max_age=ACCESS_TOKEN_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=cookie_domain,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_auth_cookies(response: Response):
    cookie_domain = os.getenv("COOKIE_DOMAIN") or None
    for name in ["access_token", "refresh_token"]:
        response.delete_cookie(
            key=name,
            path="/",
            domain=cookie_domain,
        )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


def get_client_ip(request: Request) -> str:
    xfwd = request.headers.get("x-forwarded-for")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def log_audit_event(
    db: Session,
    *,
    action: str,
    request: Optional[Request] = None,
    user: Optional[User] = None,
    role: Optional[str] = None,
    session_id: Optional[str] = None,
    success: bool = True,
    detail: Optional[str] = None,
):
    ip = get_client_ip(request) if request else None
    user_agent = request.headers.get("user-agent") if request else None
    route = request.url.path if request else None
    method = request.method if request else None

    log = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        role=role or (user.role.value if user else None),
        ip_address=ip,
        user_agent=user_agent,
        route=route,
        method=method,
        session_id=session_id,
        action=action,
        success=success,
        detail=detail,
    )
    db.add(log)
    db.commit()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Tuple[User, str, str]:
    """
    Extracts user from access_token cookie.
    Returns (user, role, session_id).
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token, expected_type="access")
    user_id = payload.get("sub")
    role = payload.get("role")
    session_id = payload.get("sid")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role.value != role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    # Per-request audit log of access
    log_audit_event(
        db,
        action="access",
        request=request,
        user=user,
        role=role,
        session_id=session_id,
        success=True,
    )

    return user, role, session_id


def require_user(
    user_ctx: Tuple[User, str, str] = Depends(get_current_user),
) -> Tuple[User, str, str]:
    user, role, sid = user_ctx
    if role not in (UserRole.user.value, UserRole.master.value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return user, role, sid


def require_master(
    user_ctx: Tuple[User, str, str] = Depends(get_current_user),
) -> Tuple[User, str, str]:
    user, role, sid = user_ctx
    if role != UserRole.master.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Master access required")
    return user, role, sid


def verify_google_id_token(id_token_str: str) -> str:
    """
    Verifies a Google ID token and returns the email if valid.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GOOGLE_CLIENT_ID is not configured on the server.",
        )
    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    email = idinfo.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not present in token")
    return email


