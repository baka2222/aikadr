"""Password hashing and signed, HttpOnly account sessions."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Response


SECRET = os.getenv("SESSION_SECRET", "")
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() == "true"
SESSION_TTL = 14 * 86400
ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, expected = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def signed_token(user_id: str, session_version: int = 0) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"u": user_id, "v": session_version, "e": int(time.time()) + SESSION_TTL}, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_token(token: str | None) -> tuple[str, int] | None:
    if not token or not SECRET:
        return None
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["e"] < time.time():
            return None
        return data["u"], int(data.get("v", 0))
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError):
        return None


def set_session(response: Response, user_id: str, session_version: int = 0):
    response.set_cookie("kadr_session", signed_token(user_id, session_version), max_age=SESSION_TTL,
                        httponly=True, samesite="lax", secure=SECURE_COOKIES, path="/")


def clear_session(response: Response):
    response.delete_cookie("kadr_session", path="/")


def ensure_secret():
    if len(SECRET) < 32:
        raise RuntimeError("SESSION_SECRET must contain at least 32 characters")
