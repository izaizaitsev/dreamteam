import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import User

def password_hash(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"legal-assistant-demo", 200_000).hex()

def token_for(user: User) -> str:
    payload = {"uid": user.id, "exp": int(time.time()) + 8 * 3600}
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(os.environ["AUTH_SECRET"].encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{signature}"

@dataclass(frozen=True)
class Actor:
    id: str
    organization_id: str
    username: str
    role: str

def get_actor(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Actor:
    try:
        scheme, token = authorization.split(" ", 1)
        data, signature = token.split(".", 1)
        expected = hmac.new(os.environ["AUTH_SECRET"].encode(), data.encode(), hashlib.sha256).hexdigest()
        if scheme.lower() != "bearer" or not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
        if payload["exp"] < time.time():
            raise ValueError()
        user = db.scalar(select(User).where(User.id == payload["uid"]))
        if user is None:
            raise ValueError()
        return Actor(user.id, user.organization_id, user.username, user.role)
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Требуется вход"}) from None

def require_role(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Недостаточно прав"})
