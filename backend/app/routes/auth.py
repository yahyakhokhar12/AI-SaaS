import os
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import JWT_COOKIE_NAME, authenticate_user, create_access_token, get_current_user, hash_password
from app.db import get_db
from app.models import Subscription, Usage, User

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_RATE_LIMIT_WINDOW_SECONDS = 60
AUTH_RATE_LIMIT_MAX_ATTEMPTS = 10
_auth_attempts: Dict[str, List[datetime]] = {}

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")


def _is_rate_limited(identifier: str) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now.timestamp() - AUTH_RATE_LIMIT_WINDOW_SECONDS
    attempts = _auth_attempts.get(identifier, [])
    attempts = [attempt for attempt in attempts if attempt.timestamp() > window_start]
    if len(attempts) >= AUTH_RATE_LIMIT_MAX_ATTEMPTS:
        _auth_attempts[identifier] = attempts
        return True
    attempts.append(now)
    _auth_attempts[identifier] = attempts
    return False


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=JWT_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * 7,
        path="/",
    )


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    plan: str
    status: str
    requests_count: int


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    identifier = request.client.host if request.client else "anonymous"
    if _is_rate_limited(f"signup:{identifier}"):
        raise HTTPException(status_code=429, detail="Too many signup attempts. Please try again later.")

    existing_user = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email.lower(), hashed_password=hash_password(payload.password), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(Subscription(user_id=user.id, plan="free", status="active"))
    db.add(Usage(user_id=user.id, requests_count=0))
    db.commit()

    token = create_access_token(subject=user.email)
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    identifier = request.client.host if request.client else "anonymous"
    if _is_rate_limited(f"login:{identifier}"):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    user = authenticate_user(db, payload.email.lower(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(subject=user.email)
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=JWT_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserResponse:
    subscription = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    usage = db.query(Usage).filter(Usage.user_id == current_user.id).first()
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        plan=subscription.plan if subscription else "free",
        status=subscription.status if subscription else "active",
        requests_count=usage.requests_count if usage else 0,
    )
