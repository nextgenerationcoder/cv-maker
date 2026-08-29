import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

import user_store

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Not a valid email address.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


def _generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(days=JWT_EXPIRE_DAYS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

    user = user_store.get_user_by_id(payload.get("sub", ""))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


@router.post("/signup")
def signup(body: SignupRequest):
    if user_store.get_user_by_email(body.email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = user_store.create_user(body.email, hash_password(body.password))
    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer", "email": user["email"]}


@router.post("/login")
def login(body: LoginRequest):
    user = user_store.get_user_by_email(body.email.strip().lower())
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer", "email": user["email"]}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "email": current_user["email"]}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    """No email sending is set up for this deployment, so this can't send a
    reset link — instead it generates a new temporary password and returns
    it directly. Anyone who knows an account's email can reset it this way;
    that's an accepted trade-off for a small self-hosted app with no email
    infrastructure, not a general-purpose reset flow. Change the password
    afterward from Settings."""
    user = user_store.get_user_by_email(body.email.strip().lower())
    if user is None:
        raise HTTPException(status_code=404, detail="No account with that email.")
    temp_password = _generate_temp_password()
    user_store.update_password(user["id"], hash_password(temp_password))
    return {"email": user["email"], "temporary_password": temp_password}


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    user = user_store.get_user_by_email(current_user["email"])
    if user is None or not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    user_store.update_password(current_user["id"], hash_password(body.new_password))
    return {"status": "changed"}
