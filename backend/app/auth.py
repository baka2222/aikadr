"""Single-use email challenges with transactional verification and rate limits."""

import hashlib
import hmac
import os
import re
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException

from .db import database, execute, one
from .mail import send_code_email
from .security import hash_password

CODE_TTL = 600
MAX_ATTEMPTS = 5


def normalize_email(value):
    email = value.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Укажите корректный email")
    return email


def code_digest(challenge_id, code):
    return hmac.new(os.environ["SESSION_SECRET"].encode(), f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def throttle(identity, limit=15, window=900):
    now = int(time.time())
    bucket = hashlib.sha256(identity.encode()).hexdigest()
    with database() as db:
        row = one(db, """INSERT INTO auth_rate_limits (bucket,window_start,hits) VALUES (%s,%s,1)
                          ON CONFLICT (bucket) DO UPDATE SET
                          hits=CASE WHEN auth_rate_limits.window_start < %s THEN 1 ELSE auth_rate_limits.hits+1 END,
                          window_start=CASE WHEN auth_rate_limits.window_start < %s THEN %s ELSE auth_rate_limits.window_start END
                          RETURNING hits,window_start""", (bucket, now, now-window, now-window, now))
        execute(db, "DELETE FROM auth_rate_limits WHERE window_start<%s", (now-86400,))
    if row["hits"] > limit:
        raise HTTPException(status_code=429, detail="Слишком много попыток. Повторите позже", headers={"Retry-After": str(window)})


def issue_challenge(email, purpose, *, user=None, full_name="", password_hash=None):
    now = int(time.time())
    challenge_id = str(uuid4())
    code = f"{secrets.randbelow(1_000_000):06d}"
    with database() as db:
        # A per-email transaction lock also serializes concurrent resend requests.
        execute(db, "SELECT pg_advisory_xact_lock(hashtext(%s))", (email,))
        recent = one(db, "SELECT created_at FROM auth_challenges WHERE email=%s ORDER BY created_at DESC LIMIT 1", (email,))
        if recent and now-recent["created_at"] < 60:
            raise HTTPException(status_code=429, detail="Следующий код можно запросить через минуту", headers={"Retry-After": str(60-(now-recent["created_at"]))})
        count = one(db, "SELECT COUNT(*) AS n FROM auth_challenges WHERE email=%s AND created_at>%s", (email, now-3600))["n"]
        if count >= 8:
            raise HTTPException(status_code=429, detail="Лимит писем на час исчерпан. Попробуйте позже")
        execute(db, "UPDATE auth_challenges SET consumed_at=%s WHERE email=%s AND purpose=%s AND consumed_at IS NULL", (now,email,purpose))
        execute(db, """INSERT INTO auth_challenges (id,email,user_id,purpose,code_hash,password_hash,full_name,
                        session_version,created_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (challenge_id,email,user["id"] if user else None,purpose,code_digest(challenge_id,code),password_hash,
                 user["full_name"] if user else full_name,user["session_version"] if user else 0,now,now+CODE_TTL))
        send_code_email(email, user["full_name"] if user else full_name, code, purpose)
        execute(db, "DELETE FROM auth_challenges WHERE expires_at<%s", (now-86400,))
    return {"requires_verification": True, "challenge_id": challenge_id, "email": email,
            "expires_in": CODE_TTL, "resend_after": 60, "purpose": purpose}


def verify_challenge(challenge_id, code, new_password=None):
    now = int(time.time())
    error = None
    user = None
    with database() as db:
        target = one(db, "SELECT email FROM auth_challenges WHERE id=%s", (challenge_id,))
        if target:
            execute(db, "SELECT pg_advisory_xact_lock(hashtext(%s))", (target["email"],))
        row = one(db, "SELECT * FROM auth_challenges WHERE id=%s FOR UPDATE", (challenge_id,))
        if not row or row["consumed_at"] or row["expires_at"] <= now:
            error = "Код истёк или уже использован. Запросите новый"
        elif row["attempts"] >= MAX_ATTEMPTS:
            error = "Превышено число попыток. Запросите новый код"
        elif not hmac.compare_digest(row["code_hash"], code_digest(challenge_id,code)):
            execute(db, "UPDATE auth_challenges SET attempts=attempts+1 WHERE id=%s", (challenge_id,))
            error = "Неверный код"
        elif row["purpose"] == "register":
            if one(db, "SELECT id FROM users WHERE email=%s", (row["email"],)):
                error = "Аккаунт уже существует. Войдите с паролем"
            else:
                user = one(db, """INSERT INTO users (id,email,full_name,password_hash,role,email_verified,created_at)
                                VALUES (%s,%s,%s,%s,'viewer',TRUE,%s) RETURNING *""",
                           (str(uuid4()),row["email"],row["full_name"],row["password_hash"],now))
        else:
            user = one(db, "SELECT * FROM users WHERE id=%s AND is_active=TRUE FOR UPDATE", (row["user_id"],))
            if not user or user["session_version"] != row["session_version"]:
                user = None
                error = "Данные аккаунта изменились. Начните вход заново"
            elif row["purpose"] == "reset":
                if not new_password or not 12 <= len(new_password) <= 256:
                    error = "Новый пароль должен содержать от 12 до 256 символов"
                else:
                    user = one(db, """UPDATE users SET password_hash=%s,session_version=session_version+1,email_verified=TRUE
                                      WHERE id=%s RETURNING *""", (hash_password(new_password),user["id"]))
            else:
                user = one(db, "UPDATE users SET email_verified=TRUE WHERE id=%s RETURNING *", (user["id"],))
        if not error:
            execute(db, "UPDATE auth_challenges SET consumed_at=%s,password_hash=NULL WHERE id=%s", (now,challenge_id))
    if error:
        raise HTTPException(status_code=400, detail=error)
    return user
