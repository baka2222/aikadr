"""KADR API: PostgreSQL catalogue, uploads, subscriptions and creator accounting."""

import os
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg2
from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .db import all_rows, database, execute, init_database, one
from .auth import issue_challenge, normalize_email, throttle, verify_challenge
from .mail import validate_mail_config
from .payments import review_payment
from .security import clear_session, ensure_secret, hash_password, read_token, set_session, verify_password


DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
MEDIA_DIR = DATA_DIR / "media"
MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(2 * 1024**3)))
VIEW_QUALIFY_SECONDS = 30
CONTENT_MANAGERS = ("superadmin", "moderator")
EPISODE_SELECT = """SELECT e.id,e.series_id,e.season,e.number,e.title,e.description,e.duration,e.video_url,e.free_preview,
                    s.owner_id,s.is_published,v.id AS video_id,v.large_object_oid AS video_oid,
                    COALESCE(v.byte_size,0) AS video_size,v.mime_type AS video_mime
                    FROM episodes e JOIN series s ON s.id=e.series_id LEFT JOIN videos v ON v.episode_id=e.id"""
MEDIA_DIR.joinpath("covers").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_secret()
    validate_mail_config()
    init_database()
    yield


app = FastAPI(title="КАДР API", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
            return Response(status_code=403, content="Origin mismatch")
    return await call_next(request)


def clean_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return value
    if value.startswith("/media/") and not value.startswith("//"):
        return value
    raise ValueError("Укажите ссылку http(s) или путь /media/...")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(max_length=256)


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class Registration(Credentials):
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=256)


class CreateUser(Registration):
    role: str = Field(pattern="^(viewer|author|moderator|superadmin)$")
    storage_quota_gb: int = Field(default=10, ge=1, le=1000)


class VerifyEmailInput(BaseModel):
    challenge_id: str = Field(max_length=100)
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str | None = Field(default=None, min_length=12, max_length=256)


class ChallengeInput(BaseModel):
    challenge_id: str = Field(max_length=100)


class EmailInput(BaseModel):
    email: str = Field(max_length=254)


class UpdateUserInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(viewer|author|moderator|superadmin)$")
    is_active: bool
    storage_quota_gb: int | None = Field(default=None, ge=1, le=1000)


class SeriesInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=3000)
    category_id: str
    poster_url: str = ""
    year: int = Field(ge=1900, le=2100)
    rating: str = Field(default="12+", max_length=20)
    featured: bool = False
    popular: bool = False
    owner_id: str | None = None
    is_published: bool = True

    @field_validator("poster_url")
    @classmethod
    def valid_poster(cls, value):
        return clean_url(value)


class EpisodeInput(BaseModel):
    season: int = Field(ge=1, le=99)
    number: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=3000)
    duration: str = Field(default="", max_length=40)
    video_url: str = ""
    free_preview: bool = False

    @field_validator("video_url")
    @classmethod
    def valid_video(cls, value):
        return clean_url(value)


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PlanInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    price_som: int = Field(ge=0, le=10_000_000)
    duration_days: int = Field(ge=1, le=3650)
    active: bool = True
    sort_order: int = 0


class PaymentMethodInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    details: str = Field(min_length=5, max_length=1500)
    active: bool = True
    sort_order: int = 0


class ReviewInput(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(default="", max_length=1000)


class FinanceInput(BaseModel):
    revenue_override_som: int | None = Field(default=None, ge=0)
    author_percent: int = Field(ge=0, le=100)
    note: str = Field(default="", max_length=1000)


class PayoutInput(BaseModel):
    author_id: str
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    note: str = Field(default="", max_length=1000)


class SettingsInput(BaseModel):
    payment_instructions: str = Field(min_length=10, max_length=1500)
    default_author_percent: int = Field(ge=0, le=100)


class AppearanceInput(BaseModel):
    site_name: str = Field(default="aikadr", min_length=1, max_length=40)
    hero_kicker: str = Field(default="НОВЫЙ ВЗГЛЯД НА КИНО", max_length=90)
    hero_title: str = Field(default="Истории за гранью привычного", min_length=1, max_length=140)
    hero_subtitle: str = Field(default="Авторские ИИ-сериалы. Неожиданные миры. Ваше следующее открытие.", max_length=400)
    logo_url: str = "/brand/aikadr-square.png"
    hero_background_url: str = ""
    theme: str = Field(default="midnight", pattern="^(midnight|winter|aurora)$")
    accent_color: str = Field(default="#D8B66B", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("logo_url", "hero_background_url")
    @classmethod
    def valid_image(cls,value):
        if value.startswith("/brand/") and ".." not in value:
            return value
        return clean_url(value)


class ViewStartInput(BaseModel):
    episode_id: str


class ViewHeartbeatInput(BaseModel):
    session_id: str


class ViewStateInput(ViewHeartbeatInput):
    playing: bool


def safe_user(row):
    return {key: row[key] for key in ("id", "email", "full_name", "role", "is_active", "email_verified", "created_at")}


def author_storage_used(db, author_id):
    return one(db, """SELECT COALESCE(SUM(v.byte_size),0) AS bytes FROM videos v
                  JOIN episodes e ON e.id=v.episode_id JOIN series s ON s.id=e.series_id
                  WHERE s.owner_id=%s""", (author_id,))["bytes"]


def current_user(kadr_session: str | None = Cookie(default=None)):
    identity = read_token(kadr_session)
    if not identity:
        return None
    with database() as db:
        return one(db, """SELECT * FROM users WHERE id=%s AND session_version=%s AND is_active=TRUE
                      AND (role IN ('author','moderator','superadmin') OR email_verified=TRUE)""", identity)


def require_user(user=Depends(current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    return user


def require_staff(user=Depends(require_user)):
    if user["role"] not in ("author", "moderator", "superadmin"):
        raise HTTPException(status_code=403, detail="Доступ только для авторов и администрации")
    return user


def require_admin(user=Depends(require_user)):
    if user["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Нужны права супер-администратора")
    return user


def find_or_404(db, table, row_id):
    if table not in ("categories", "series", "episodes", "plans", "payment_methods", "users", "payment_requests"):
        raise ValueError("Invalid table")
    row = one(db, f"SELECT * FROM {table} WHERE id=%s", (row_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return row


def ensure_series_owner(series_row, user):
    if user["role"] not in CONTENT_MANAGERS and series_row["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Можно изменять только свои сериалы")


def active_subscription(db, user_id, now=None):
    return one(db, """SELECT s.*,p.title AS plan_title FROM subscriptions s
                      JOIN plans p ON p.id=s.plan_id WHERE s.user_id=%s AND s.ends_at>%s
                      ORDER BY s.ends_at DESC LIMIT 1""", (user_id, now or int(time.time())))


def can_watch(db, episode, user):
    if episode["free_preview"]:
        return True
    if not user:
        return False
    if user["role"] in CONTENT_MANAGERS or (user["role"] == "author" and episode["owner_id"] == user["id"]):
        return True
    return bool(active_subscription(db, user["id"]))


def series_rows(db, where="", params=(), order="s.created_at DESC"):
    return all_rows(db, f"""SELECT s.*, c.name AS genre, u.full_name AS author_name,
               (SELECT COUNT(*) FROM episodes e WHERE e.series_id=s.id) AS episode_count
               FROM series s JOIN categories c ON c.id=s.category_id
               LEFT JOIN users u ON u.id=s.owner_id {where} ORDER BY {order}""", params)


def detail_row(db, series_id, user=None):
    rows = series_rows(db, "WHERE s.id=%s", (series_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Сериал не найден")
    result = dict(rows[0])
    if not result["is_published"] and not (user and (user["role"] in CONTENT_MANAGERS or result["owner_id"] == user["id"])):
        raise HTTPException(status_code=404, detail="Сериал не найден")
    episodes = all_rows(db, EPISODE_SELECT + " WHERE e.series_id=%s ORDER BY e.season,e.number", (series_id,))
    result["episodes"] = []
    for episode in episodes:
        allowed = can_watch(db, episode, user)
        has_video = bool(episode["video_oid"] or episode["video_url"])
        result["episodes"].append({
            "id": episode["id"], "series_id": series_id, "season": episode["season"],
            "number": episode["number"], "title": episode["title"], "description": episode["description"],
            "duration": episode["duration"], "free_preview": episode["free_preview"],
            "has_video": has_video, "can_watch": allowed,
            "video_url": (f"/api/videos/{episode['id']}" if episode["video_oid"] else episode["video_url"]) if allowed else "",
            "source_video_url": episode["video_url"] if user and (user["role"] in CONTENT_MANAGERS or result["owner_id"] == user["id"]) else "",
            "video_size": episode["video_size"] if user and (user["role"] in CONTENT_MANAGERS or result["owner_id"] == user["id"]) else 0,
            "video_id": episode["video_id"],
        })
    return result


@app.get("/api/health")
def health():
    with database() as db:
        one(db, "SELECT 1")
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(payload: Registration, request: Request):
    email = normalize_email(payload.email)
    throttle(f"signup:{request.client.host}", limit=20, window=3600)
    with database() as db:
        if one(db, "SELECT id FROM users WHERE email=%s", (email,)):
            raise HTTPException(status_code=409, detail="Этот email уже зарегистрирован") from None
    return issue_challenge(email,"register",full_name=payload.full_name.strip(),password_hash=hash_password(payload.password))


@app.post("/api/auth/login")
@app.post("/api/admin/login")
def login(payload: Credentials, request: Request, response: Response):
    email = normalize_email(payload.email)
    throttle(f"login-ip:{request.client.host}",limit=40,window=900)
    throttle(f"login:{request.client.host}:{email}")
    with database() as db:
        row = one(db, "SELECT * FROM users WHERE email=%s AND is_active=TRUE", (email,))
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if request.url.path == "/api/admin/login":
        if row["role"] == "viewer":
            raise HTTPException(status_code=403, detail="Кабинет доступен авторам и администрации")
        set_session(response, row["id"], row["session_version"])
        return safe_user(row)
    if row["role"] != "viewer":
        raise HTTPException(status_code=403, detail="Для сотрудников вход через /admin")
    return issue_challenge(email,"login",user=row)


@app.post("/api/auth/verify-email")
def verify_email(payload: VerifyEmailInput, request: Request, response: Response):
    throttle(f"verify:{request.client.host}",limit=60,window=900)
    user = verify_challenge(payload.challenge_id,payload.code,payload.new_password)
    set_session(response,user["id"],user["session_version"])
    return safe_user(user)


@app.post("/api/auth/resend-code")
def resend_code(payload: ChallengeInput, request: Request):
    throttle(f"resend:{request.client.host}",limit=20,window=3600)
    with database() as db:
        row = one(db,"SELECT * FROM auth_challenges WHERE id=%s AND consumed_at IS NULL",(payload.challenge_id,))
        if not row or row["expires_at"] < int(time.time())-1800:
            raise HTTPException(status_code=400,detail="Начните вход или регистрацию заново")
        user = one(db,"SELECT * FROM users WHERE id=%s AND is_active=TRUE",(row["user_id"],)) if row["user_id"] else None
        if row["user_id"] and (not user or user["session_version"] != row["session_version"]):
            raise HTTPException(status_code=400,detail="Данные аккаунта изменились. Начните вход заново")
    return issue_challenge(row["email"],row["purpose"],user=user,full_name=row["full_name"],password_hash=row["password_hash"])


@app.post("/api/auth/reset-password")
def reset_password(payload: EmailInput, request: Request):
    email = normalize_email(payload.email)
    throttle(f"reset:{request.client.host}",limit=10,window=3600)
    with database() as db:
        user = one(db,"SELECT * FROM users WHERE email=%s AND is_active=TRUE",(email,))
    if user:
        return issue_challenge(email,"reset",user=user)
    return {"requires_verification":True,"challenge_id":str(uuid4()),"email":email,"expires_in":600,"resend_after":60,"purpose":"reset"}


@app.post("/api/auth/logout")
@app.post("/api/admin/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}


@app.post("/api/auth/change-password")
def change_password(payload: ChangePassword, response: Response, user=Depends(require_user)):
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Новый пароль должен отличаться от текущего")
    with database() as db:
        row = one(db, "SELECT password_hash,session_version FROM users WHERE id=%s FOR UPDATE", (user["id"],))
        if not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
        new_version = row["session_version"] + 1
        execute(db, "UPDATE users SET password_hash=%s,session_version=%s WHERE id=%s",
                (hash_password(payload.new_password), new_version, user["id"]))
    set_session(response, user["id"], new_version)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(require_user)):
    with database() as db:
        subscription = active_subscription(db, user["id"])
    return {**safe_user(user), "subscription": dict(subscription) if subscription else None}


@app.get("/api/admin/session")
def admin_session(user=Depends(require_staff)):
    return safe_user(user)


@app.get("/api/categories")
def list_categories():
    with database() as db:
        return all_rows(db, "SELECT * FROM categories ORDER BY name")


@app.get("/api/series")
def list_series(search: str = "", genre: str = "", sort: str = "new"):
    where = ["s.is_published=TRUE", "EXISTS (SELECT 1 FROM episodes e LEFT JOIN videos v ON v.episode_id=e.id WHERE e.series_id=s.id AND (v.id IS NOT NULL OR e.video_url<>''))"]
    params = []
    if genre.strip():
        where.append("c.name=%s")
        params.append(genre.strip())
    order = "s.popular DESC,s.created_at DESC" if sort == "popular" else "s.created_at DESC"
    with database() as db:
        rows = series_rows(db, "WHERE " + " AND ".join(where), params, order)
    needle = search.strip().casefold()
    return [row for row in rows if needle in f"{row['title']} {row['description']} {row['genre']}".casefold()] if needle else rows


@app.get("/api/series/{series_id}")
def get_series(series_id: str, user=Depends(current_user)):
    with database() as db:
        return detail_row(db, series_id, user)


@app.get("/api/plans")
def list_plans():
    with database() as db:
        return all_rows(db, "SELECT id,title,description,price_som,duration_days,sort_order FROM plans WHERE active=TRUE ORDER BY sort_order,price_som")


@app.get("/api/payment-instructions")
def payment_instructions():
    with database() as db:
        row = one(db, "SELECT value FROM settings WHERE key='payment_instructions'")
        ready = one(db, "SELECT value FROM settings WHERE key='payment_ready'")
        methods = all_rows(db, "SELECT id,title,details FROM payment_methods WHERE active=TRUE ORDER BY sort_order,created_at")
    return {"text": row["value"] if row and ready and ready["value"] == "true" else "",
            "ready": bool(ready and ready["value"] == "true" and methods), "methods": methods}


@app.post("/api/payments", status_code=201)
def create_payment_request(plan_id: str = Form(...), payment_method_id: str = Form(...), receipt: UploadFile = File(...), user=Depends(require_user)):
    if user["role"] != "viewer":
        raise HTTPException(status_code=403, detail="Подписку покупает аккаунт зрителя")
    allowed = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}
    if receipt.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Загрузите скриншот JPG, PNG или WebP")
    data = receipt.file.read(5 * 1024 * 1024 + 1)
    if not data or len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Чек должен быть не больше 5 МБ")
    if not data.startswith(allowed[receipt.content_type]) or (receipt.content_type == "image/webp" and data[8:12] != b"WEBP"):
        raise HTTPException(status_code=415, detail="Файл не соответствует формату изображения")
    with database() as db:
        ready = one(db, "SELECT value FROM settings WHERE key='payment_ready'")
        if not ready or ready["value"] != "true":
            raise HTTPException(status_code=409, detail="Реквизиты оплаты ещё не настроены")
        method = one(db, "SELECT * FROM payment_methods WHERE id=%s AND active=TRUE", (payment_method_id,))
        if not method:
            raise HTTPException(status_code=409, detail="Способ оплаты больше не доступен")
        plan = find_or_404(db, "plans", plan_id)
        if not plan["active"]:
            raise HTTPException(status_code=409, detail="Тариф больше не доступен")
        request_id = str(uuid4())
        execute(db, """INSERT INTO payment_requests (id,user_id,plan_id,payment_method_id,payment_method_title,price_som,duration_days,receipt,receipt_mime,receipt_size,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (request_id, user["id"], plan_id, method["id"], method["title"], plan["price_som"], plan["duration_days"], psycopg2.Binary(data), receipt.content_type, len(data), int(time.time())))
    try:
        from .telegram import notify_payment
        notify_payment(request_id, user["email"], plan["title"], plan["price_som"], data, receipt.content_type, method["title"])
    except Exception:
        pass  # The request remains in the admin queue.
    return {"id": request_id, "status": "pending"}


@app.get("/api/payments/mine")
def my_payments(user=Depends(require_user)):
    with database() as db:
        return all_rows(db, """SELECT p.id,p.price_som,p.status,p.created_at,p.reviewed_at,p.note,pl.title AS plan_title
                               FROM payment_requests p JOIN plans pl ON pl.id=p.plan_id
                               WHERE p.user_id=%s ORDER BY p.created_at DESC""", (user["id"],))


@app.get("/api/admin/payment-requests")
def admin_payments(user=Depends(require_admin)):
    with database() as db:
        return all_rows(db, """SELECT p.id,p.user_id,p.plan_id,p.payment_method_title,p.price_som,p.status,p.created_at,p.reviewed_at,p.note,
                               u.email,u.full_name,pl.title AS plan_title FROM payment_requests p
                               JOIN users u ON u.id=p.user_id JOIN plans pl ON pl.id=p.plan_id ORDER BY p.created_at DESC LIMIT 200""")


@app.get("/api/admin/payment-requests/{request_id}/receipt")
def get_receipt(request_id: str, user=Depends(require_admin)):
    with database() as db:
        row = find_or_404(db, "payment_requests", request_id)
    return Response(content=bytes(row["receipt"]), media_type=row["receipt_mime"],
                    headers={"Cache-Control": "private, no-store", "Content-Security-Policy": "default-src 'none'"})


@app.post("/api/admin/payment-requests/{request_id}/review")
def admin_review_payment(request_id: str, payload: ReviewInput, user=Depends(require_admin)):
    return review_payment(request_id, payload.decision, user["id"], payload.note)


@app.get("/api/admin/users")
def admin_users(user=Depends(require_admin)):
    with database() as db:
        rows = all_rows(db, """SELECT id,email,full_name,role,is_active,email_verified,storage_quota_bytes,created_at FROM users
                              ORDER BY CASE role WHEN 'superadmin' THEN 0 WHEN 'author' THEN 1 ELSE 2 END,created_at DESC""")
        for row in rows:
            row["storage_used_bytes"] = author_storage_used(db, row["id"]) if row["role"] == "author" else 0
        return rows


@app.post("/api/admin/users", status_code=201)
def admin_create_user(payload: CreateUser, user=Depends(require_admin)):
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Укажите корректный email")
    user_id = str(uuid4())
    with database() as db:
        try:
            execute(db, "INSERT INTO users (id,email,full_name,password_hash,role,storage_quota_bytes,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, email, payload.full_name.strip(), hash_password(payload.password), payload.role, payload.storage_quota_gb * 1024**3, int(time.time())))
        except psycopg2.IntegrityError:
            raise HTTPException(status_code=409, detail="Этот email уже зарегистрирован") from None
        return safe_user(find_or_404(db, "users", user_id))


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: str,payload: UpdateUserInput,user=Depends(require_admin)):
    with database() as db:
        execute(db,"LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
        old = find_or_404(db,"users",user_id)
        if user_id == user["id"] and (payload.role != "superadmin" or not payload.is_active):
            raise HTTPException(status_code=409,detail="Нельзя отключить свой доступ к управлению")
        if old["role"] == "superadmin" and (payload.role != "superadmin" or not payload.is_active):
            if one(db,"SELECT COUNT(*) AS n FROM users WHERE role='superadmin' AND is_active=TRUE")["n"] <= 1:
                raise HTTPException(status_code=409,detail="Должен остаться хотя бы один активный супер-администратор")
        if old["role"] == "author" and payload.role != "author" and (
            one(db,"SELECT 1 FROM series WHERE owner_id=%s LIMIT 1",(user_id,)) or
            one(db,"SELECT 1 FROM qualified_views WHERE author_id=%s LIMIT 1",(user_id,))):
            raise HTTPException(status_code=409,detail="У автора есть материалы или начисления. При необходимости отключите аккаунт, сохранив роль")
        changed_access = old["role"] != payload.role or old["is_active"] != payload.is_active
        quota_bytes = payload.storage_quota_gb * 1024**3 if payload.storage_quota_gb is not None else old["storage_quota_bytes"]
        if old["role"] == "author" and author_storage_used(db, user_id) > quota_bytes:
            raise HTTPException(status_code=409, detail="Новый лимит меньше уже занятого места")
        execute(db,"UPDATE users SET full_name=%s,role=%s,is_active=%s,storage_quota_bytes=%s,session_version=session_version+%s WHERE id=%s",
                (payload.full_name.strip(),payload.role,payload.is_active,quota_bytes,1 if changed_access else 0,user_id))
        return safe_user(find_or_404(db,"users",user_id))


@app.get("/api/admin/series")
def staff_series(user=Depends(require_staff)):
    where = "" if user["role"] in CONTENT_MANAGERS else "WHERE s.owner_id=%s"
    params = () if user["role"] in CONTENT_MANAGERS else (user["id"],)
    with database() as db:
        return series_rows(db, where, params)


@app.get("/api/admin/series/{series_id}")
def staff_series_detail(series_id: str, user=Depends(require_staff)):
    with database() as db:
        series = find_or_404(db, "series", series_id)
        ensure_series_owner(series, user)
        return detail_row(db, series_id, user)


@app.post("/api/admin/series", status_code=201)
def create_series(payload: SeriesInput, user=Depends(require_staff)):
    series_id = str(uuid4())
    owner_id = payload.owner_id if user["role"] == "superadmin" else (user["id"] if user["role"] == "author" else None)
    with database() as db:
        find_or_404(db, "categories", payload.category_id)
        if owner_id and find_or_404(db, "users", owner_id)["role"] != "author":
            raise HTTPException(status_code=422, detail="Владелец сериала должен быть автором")
        execute(db, """INSERT INTO series (id,title,description,category_id,poster_url,year,rating,featured,popular,created_at,owner_id,is_published)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (series_id, payload.title.strip(), payload.description.strip(), payload.category_id, payload.poster_url,
                 payload.year, payload.rating, payload.featured, payload.popular, int(time.time()), owner_id, payload.is_published))
        return detail_row(db, series_id, user)


@app.put("/api/admin/series/{series_id}")
def update_series(series_id: str, payload: SeriesInput, user=Depends(require_staff)):
    with database() as db:
        old = one(db, "SELECT * FROM series WHERE id=%s FOR UPDATE", (series_id,))
        if not old:
            raise HTTPException(status_code=404, detail="Сериал не найден")
        ensure_series_owner(old, user)
        find_or_404(db, "categories", payload.category_id)
        owner_id = old["owner_id"]
        if user["role"] == "superadmin":
            owner_id = payload.owner_id
            if owner_id and find_or_404(db, "users", owner_id)["role"] != "author":
                raise HTTPException(status_code=422, detail="Владелец сериала должен быть автором")
            if owner_id and owner_id != old["owner_id"]:
                owner = one(db, "SELECT storage_quota_bytes FROM users WHERE id=%s FOR UPDATE", (owner_id,))
                incoming = one(db, """SELECT COALESCE(SUM(v.byte_size),0) AS bytes FROM videos v
                                  JOIN episodes e ON e.id=v.episode_id WHERE e.series_id=%s""", (series_id,))["bytes"]
                if author_storage_used(db, owner_id) + incoming > owner["storage_quota_bytes"]:
                    raise HTTPException(status_code=409, detail="У автора недостаточно места для этого сериала")
        execute(db, """UPDATE series SET title=%s,description=%s,category_id=%s,poster_url=%s,year=%s,rating=%s,
                       featured=%s,popular=%s,owner_id=%s,is_published=%s WHERE id=%s""",
                (payload.title.strip(), payload.description.strip(), payload.category_id, payload.poster_url, payload.year,
                 payload.rating, payload.featured, payload.popular, owner_id, payload.is_published, series_id))
        return detail_row(db, series_id, user)


@app.delete("/api/admin/series/{series_id}", status_code=204)
def delete_series(series_id: str, user=Depends(require_staff)):
    with database() as db:
        series = find_or_404(db, "series", series_id)
        ensure_series_owner(series, user)
        execute(db, "DELETE FROM series WHERE id=%s", (series_id,))


def write_episode(db, payload, series_id, episode_id=None):
    if payload.video_url and not payload.free_preview:
        raise HTTPException(status_code=422, detail="Внешняя ссылка допустима только для бесплатной серии. Платное видео загрузите в PostgreSQL")
    try:
        if episode_id:
            execute(db, """UPDATE episodes SET season=%s,number=%s,title=%s,description=%s,duration=%s,
                           video_url=%s,free_preview=%s WHERE id=%s""",
                    (payload.season, payload.number, payload.title.strip(), payload.description.strip(),
                     payload.duration.strip(), payload.video_url, payload.free_preview, episode_id))
        else:
            episode_id = str(uuid4())
            execute(db, """INSERT INTO episodes (id,series_id,season,number,title,description,duration,video_url,free_preview)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (episode_id, series_id, payload.season, payload.number, payload.title.strip(), payload.description.strip(),
                     payload.duration.strip(), payload.video_url, payload.free_preview))
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=409, detail="Серия с таким сезоном и номером уже есть") from None
    return episode_id


@app.post("/api/admin/series/{series_id}/episodes", status_code=201)
def create_episode(series_id: str, payload: EpisodeInput, user=Depends(require_staff)):
    with database() as db:
        ensure_series_owner(find_or_404(db, "series", series_id), user)
        episode_id = write_episode(db, payload, series_id)
        return dict(find_or_404(db, "episodes", episode_id))


@app.put("/api/admin/episodes/{episode_id}")
def update_episode(episode_id: str, payload: EpisodeInput, user=Depends(require_staff)):
    with database() as db:
        episode = find_or_404(db, "episodes", episode_id)
        ensure_series_owner(find_or_404(db, "series", episode["series_id"]), user)
        write_episode(db, payload, episode["series_id"], episode_id)
        return dict(find_or_404(db, "episodes", episode_id))


@app.delete("/api/admin/episodes/{episode_id}", status_code=204)
def delete_episode(episode_id: str, user=Depends(require_staff)):
    with database() as db:
        episode = find_or_404(db, "episodes", episode_id)
        ensure_series_owner(find_or_404(db, "series", episode["series_id"]), user)
        execute(db, "DELETE FROM episodes WHERE id=%s", (episode_id,))


@app.get("/api/admin/episodes/{episode_id}/upload-info")
def upload_info(episode_id: str, user=Depends(require_staff)):
    with database() as db:
        episode = one(db, """SELECT e.id,e.title,e.season,e.number,s.id AS series_id,s.title AS series_title,
                         s.owner_id,COALESCE(v.byte_size,0) AS video_size FROM episodes e
                         JOIN series s ON s.id=e.series_id LEFT JOIN videos v ON v.episode_id=e.id
                         WHERE e.id=%s""", (episode_id,))
        if not episode:
            raise HTTPException(status_code=404, detail="Серия не найдена")
        ensure_series_owner(episode, user)
        owner = one(db, "SELECT storage_quota_bytes FROM users WHERE id=%s", (episode["owner_id"],)) if episode["owner_id"] else None
        return {**dict(episode), "storage_used_bytes": author_storage_used(db, episode["owner_id"]) if owner else 0,
                "storage_quota_bytes": owner["storage_quota_bytes"] if owner else None,
                "max_video_bytes": MAX_VIDEO_BYTES}


@app.post("/api/admin/episodes/{episode_id}/video")
def upload_video(episode_id: str, file: UploadFile = File(...), user=Depends(require_staff)):
    if file.content_type not in ("video/mp4", "video/webm"):
        raise HTTPException(status_code=415, detail="Нужен файл MP4 или WebM")
    first = file.file.read(12)
    if (file.content_type == "video/mp4" and first[4:8] != b"ftyp") or (
        file.content_type == "video/webm" and not first.startswith(b"\x1a\x45\xdf\xa3")
    ):
        raise HTTPException(status_code=415, detail="Файл не соответствует формату видео")
    file.file.seek(0)
    if file.size and file.size > MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail=f"Видео должно быть не больше {MAX_VIDEO_BYTES // 1024**2} МБ")
    with database() as db:
        episode = one(db,"SELECT * FROM episodes WHERE id=%s FOR UPDATE",(episode_id,))
        if not episode:
            raise HTTPException(status_code=404,detail="Серия не найдена")
        series = one(db, "SELECT * FROM series WHERE id=%s FOR UPDATE", (episode["series_id"],))
        ensure_series_owner(series, user)
        owner = one(db, "SELECT storage_quota_bytes FROM users WHERE id=%s FOR UPDATE", (series["owner_id"],)) if series["owner_id"] else None
        old = one(db,"SELECT id,large_object_oid,byte_size FROM videos WHERE episode_id=%s",(episode_id,))
        used = author_storage_used(db, series["owner_id"]) if owner else 0
        available = owner["storage_quota_bytes"] - used + (old["byte_size"] if old else 0) if owner else None
        if available is not None and file.size and file.size > available:
            raise HTTPException(status_code=413, detail="Недостаточно места у автора. Увеличьте лимит или удалите старое видео")
        large_object = db.lobject(0, "wb")
        total = 0
        while chunk := file.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_VIDEO_BYTES:
                raise HTTPException(status_code=413, detail=f"Видео должно быть не больше {MAX_VIDEO_BYTES // 1024**2} МБ")
            if available is not None and total > available:
                raise HTTPException(status_code=413, detail="Превышен лимит места автора")
            large_object.write(chunk)
        if not total:
            raise HTTPException(status_code=400, detail="Пустой файл")
        large_object.close()
        video_id = old["id"] if old else str(uuid4())
        execute(db,"""INSERT INTO videos (id,episode_id,large_object_oid,byte_size,mime_type,original_name,uploaded_by,created_at)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (episode_id) DO UPDATE SET
                      large_object_oid=EXCLUDED.large_object_oid,byte_size=EXCLUDED.byte_size,mime_type=EXCLUDED.mime_type,
                      original_name=EXCLUDED.original_name,uploaded_by=EXCLUDED.uploaded_by,created_at=EXCLUDED.created_at""",
                (video_id,episode_id,large_object.oid,total,file.content_type,Path(file.filename or "video").name[:255],user["id"],int(time.time())))
        execute(db,"UPDATE episodes SET video_url='' WHERE id=%s",(episode_id,))
    return {"id":video_id,"url": f"/api/videos/{episode_id}", "bytes": total}


@app.get("/api/admin/videos")
def list_uploaded_videos(user=Depends(require_staff)):
    with database() as db:
        return all_rows(db,"""SELECT v.id,v.episode_id,v.byte_size,v.mime_type,v.original_name,v.created_at,
                              e.title AS episode_title,e.season,e.number,s.title AS series_title,s.owner_id,
                              u.full_name AS author_name FROM videos v JOIN episodes e ON e.id=v.episode_id
                              JOIN series s ON s.id=e.series_id LEFT JOIN users u ON u.id=s.owner_id""" +
                        (" WHERE s.owner_id=%s" if user["role"]=="author" else "") + " ORDER BY v.created_at DESC",
                        (user["id"],) if user["role"]=="author" else ())


@app.delete("/api/admin/videos/{video_id}",status_code=204)
def delete_uploaded_video(video_id: str,user=Depends(require_staff)):
    with database() as db:
        # Use the same episode-first lock order as replacement uploads.
        episode = one(db,"SELECT e.* FROM episodes e JOIN videos v ON v.episode_id=e.id WHERE v.id=%s FOR UPDATE OF e",(video_id,))
        video = one(db,"SELECT * FROM videos WHERE id=%s FOR UPDATE",(video_id,))
        if not video:
            raise HTTPException(status_code=404,detail="Видео не найдено")
        ensure_series_owner(find_or_404(db,"series",episode["series_id"]),user)
        execute(db,"DELETE FROM videos WHERE id=%s",(video_id,))


def parse_range(value, size):
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()):
        raise HTTPException(status_code=416, detail="Некорректный диапазон", headers={"Content-Range": f"bytes */{size}"})
    left, right = match.groups()
    if left:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    else:
        length = int(right)
        start, end = max(0, size - length), size - 1
    if start >= size or end < start or (not left and not int(right)):
        raise HTTPException(status_code=416, detail="Диапазон вне файла", headers={"Content-Range": f"bytes */{size}"})
    return start, end, True


@app.get("/api/videos/{episode_id}")
def stream_video(episode_id: str, range_header: str | None = Header(default=None, alias="Range"), user=Depends(current_user)):
    with database() as db:
        episode = one(db, EPISODE_SELECT + " WHERE e.id=%s", (episode_id,))
        if not episode or not episode["video_oid"]:
            raise HTTPException(status_code=404, detail="Видео не найдено")
        if not episode["is_published"] and not (user and (user["role"] in CONTENT_MANAGERS or episode["owner_id"] == user["id"])):
            raise HTTPException(status_code=404, detail="Видео не найдено")
        if not can_watch(db, episode, user):
            raise HTTPException(status_code=403, detail="Нужна активная подписка")
    size = episode["video_size"]
    start, end, partial = parse_range(range_header, size)

    def chunks():
        with database() as db:
            large_object = db.lobject(episode["video_oid"], "rb")
            try:
                large_object.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = large_object.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                large_object.close()

    headers = {
        "Accept-Ranges": "bytes", "Content-Length": str(end - start + 1),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(chunks(), status_code=206 if partial else 200,
                             media_type=episode["video_mime"], headers=headers)


@app.post("/api/admin/covers", status_code=201)
def upload_cover(file: UploadFile = File(...), user=Depends(require_staff)):
    allowed = {"image/jpeg": (".jpg", b"\xff\xd8\xff"), "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
               "image/webp": (".webp", b"RIFF")}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Нужен JPG, PNG или WebP")
    data = file.file.read(3 * 1024 * 1024 + 1)
    if not data or len(data) > 3 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Обложка должна быть не больше 3 МБ")
    extension, signature = allowed[file.content_type]
    if not data.startswith(signature) or (file.content_type == "image/webp" and data[8:12] != b"WEBP"):
        raise HTTPException(status_code=415, detail="Файл не соответствует формату изображения")
    name = secrets.token_hex(16) + extension
    (MEDIA_DIR / "covers" / name).write_bytes(data)
    return {"url": f"/media/covers/{name}"}


@app.post("/api/admin/categories", status_code=201)
def create_category(payload: CategoryInput, user=Depends(require_admin)):
    category_id = str(uuid4())
    with database() as db:
        try:
            execute(db, "INSERT INTO categories (id,name) VALUES (%s,%s)", (category_id, payload.name.strip()))
        except psycopg2.IntegrityError:
            raise HTTPException(status_code=409, detail="Такой жанр уже есть") from None
        return dict(find_or_404(db, "categories", category_id))


@app.put("/api/admin/categories/{category_id}")
def update_category(category_id: str, payload: CategoryInput, user=Depends(require_admin)):
    with database() as db:
        find_or_404(db, "categories", category_id)
        try:
            execute(db, "UPDATE categories SET name=%s WHERE id=%s", (payload.name.strip(), category_id))
        except psycopg2.IntegrityError:
            raise HTTPException(status_code=409, detail="Такой жанр уже есть") from None
        return dict(find_or_404(db, "categories", category_id))


@app.delete("/api/admin/categories/{category_id}", status_code=204)
def delete_category(category_id: str, user=Depends(require_admin)):
    with database() as db:
        find_or_404(db, "categories", category_id)
        if one(db, "SELECT 1 FROM series WHERE category_id=%s LIMIT 1", (category_id,)):
            raise HTTPException(status_code=409, detail="Сначала перенесите сериалы в другой жанр")
        execute(db, "DELETE FROM categories WHERE id=%s", (category_id,))


@app.get("/api/admin/plans")
def admin_plans(user=Depends(require_admin)):
    with database() as db:
        return all_rows(db, "SELECT * FROM plans ORDER BY sort_order,price_som")


@app.post("/api/admin/plans", status_code=201)
def create_plan(payload: PlanInput, user=Depends(require_admin)):
    plan_id = str(uuid4())
    with database() as db:
        execute(db, """INSERT INTO plans (id,title,description,price_som,duration_days,active,sort_order,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (plan_id, payload.title.strip(), payload.description.strip(), payload.price_som, payload.duration_days,
                 payload.active, payload.sort_order, int(time.time())))
        return dict(find_or_404(db, "plans", plan_id))


@app.put("/api/admin/plans/{plan_id}")
def update_plan(plan_id: str, payload: PlanInput, user=Depends(require_admin)):
    with database() as db:
        find_or_404(db, "plans", plan_id)
        execute(db, """UPDATE plans SET title=%s,description=%s,price_som=%s,duration_days=%s,active=%s,sort_order=%s WHERE id=%s""",
                (payload.title.strip(), payload.description.strip(), payload.price_som, payload.duration_days,
                 payload.active, payload.sort_order, plan_id))
        return dict(find_or_404(db, "plans", plan_id))


@app.delete("/api/admin/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: str, user=Depends(require_admin)):
    with database() as db:
        find_or_404(db, "plans", plan_id)
        if one(db, "SELECT 1 FROM payment_requests WHERE plan_id=%s LIMIT 1", (plan_id,)):
            raise HTTPException(status_code=409, detail="Тариф с заявками нельзя удалить — отключите его")
        execute(db, "DELETE FROM plans WHERE id=%s", (plan_id,))


@app.get("/api/admin/payment-methods")
def admin_payment_methods(user=Depends(require_admin)):
    with database() as db:
        return all_rows(db, "SELECT * FROM payment_methods ORDER BY sort_order,created_at")


@app.post("/api/admin/payment-methods", status_code=201)
def create_payment_method(payload: PaymentMethodInput, user=Depends(require_admin)):
    method_id = str(uuid4())
    with database() as db:
        execute(db, """INSERT INTO payment_methods (id,title,details,active,sort_order,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (method_id, payload.title.strip(), payload.details.strip(), payload.active, payload.sort_order, int(time.time())))
        return dict(find_or_404(db, "payment_methods", method_id))


@app.put("/api/admin/payment-methods/{method_id}")
def update_payment_method(method_id: str, payload: PaymentMethodInput, user=Depends(require_admin)):
    with database() as db:
        find_or_404(db, "payment_methods", method_id)
        execute(db, "UPDATE payment_methods SET title=%s,details=%s,active=%s,sort_order=%s WHERE id=%s",
                (payload.title.strip(), payload.details.strip(), payload.active, payload.sort_order, method_id))
        return dict(find_or_404(db, "payment_methods", method_id))


@app.delete("/api/admin/payment-methods/{method_id}", status_code=204)
def delete_payment_method(method_id: str, user=Depends(require_admin)):
    with database() as db:
        find_or_404(db, "payment_methods", method_id)
        execute(db, "DELETE FROM payment_methods WHERE id=%s", (method_id,))


@app.get("/api/admin/settings")
def get_settings(user=Depends(require_admin)):
    with database() as db:
        return {row["key"]: row["value"] for row in all_rows(db, "SELECT key,value FROM settings")}


@app.put("/api/admin/settings")
def update_settings(payload: SettingsInput, user=Depends(require_admin)):
    with database() as db:
        for key, value in (("payment_instructions", payload.payment_instructions.strip()),
                           ("default_author_percent", str(payload.default_author_percent)),
                           ("payment_ready", "true")):
            execute(db, "INSERT INTO settings (key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (key, value))
    return {"ok": True}


@app.get("/api/site")
def site_appearance():
    with database() as db:
        row = one(db,"SELECT value FROM settings WHERE key='site_appearance'")
    return AppearanceInput(**json.loads(row["value"])).model_dump() if row else AppearanceInput().model_dump()


@app.put("/api/admin/appearance")
def update_appearance(payload: AppearanceInput,user=Depends(require_admin)):
    with database() as db:
        execute(db,"INSERT INTO settings (key,value) VALUES ('site_appearance',%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                (payload.model_dump_json(),))
    return payload.model_dump()


@app.post("/api/views/start")
def start_view(payload: ViewStartInput, user=Depends(require_user)):
    if user["role"] != "viewer":
        raise HTTPException(status_code=403, detail="Просмотры авторов и администрации не учитываются")
    with database() as db:
        episode = one(db, EPISODE_SELECT + " WHERE e.id=%s", (payload.episode_id,))
        if not episode or not (episode["video_oid"] or episode["video_url"]) or not episode["is_published"]:
            raise HTTPException(status_code=404, detail="Серия не найдена")
        if not active_subscription(db, user["id"]):
            raise HTTPException(status_code=403, detail="Нужна активная подписка")
        session_id = str(uuid4())
        now = int(time.time())
        execute(db, "INSERT INTO view_sessions (id,user_id,episode_id,started_at,last_heartbeat) VALUES (%s,%s,%s,%s,%s)",
                (session_id, user["id"], payload.episode_id, now, now))
    return {"session_id": session_id, "qualify_seconds": VIEW_QUALIFY_SECONDS}


def update_view_session(session_id, user_id, playing=None):
    with database() as db:
        session = one(db, "SELECT * FROM view_sessions WHERE id=%s AND user_id=%s FOR UPDATE", (session_id, user_id))
        if not session:
            raise HTTPException(status_code=404, detail="Сессия просмотра не найдена")
        now = int(time.time())
        elapsed = min(20, max(0, now - session["last_heartbeat"])) if session["is_playing"] else 0
        watched = session["watched_seconds"] + elapsed
        counted = session["counted"]
        if not counted and watched >= VIEW_QUALIFY_SECONDS:
            episode = one(db, "SELECT s.owner_id FROM episodes e JOIN series s ON s.id=e.series_id WHERE e.id=%s", (session["episode_id"],))
            day = datetime.fromtimestamp(now, timezone.utc).date()
            execute(db, """INSERT INTO qualified_views (id,user_id,episode_id,author_id,viewed_on,created_at)
                           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id,episode_id,viewed_on) DO NOTHING""",
                    (str(uuid4()), user_id, session["episode_id"], episode["owner_id"], day, now))
            counted = True
        execute(db, "UPDATE view_sessions SET last_heartbeat=%s,watched_seconds=%s,counted=%s,is_playing=%s WHERE id=%s",
                (now, watched, counted, session["is_playing"] if playing is None else playing, session["id"]))
        return {"watched_seconds": watched, "counted": counted}


@app.post("/api/views/heartbeat")
def heartbeat(payload: ViewHeartbeatInput, user=Depends(require_user)):
    return update_view_session(payload.session_id, user["id"])


@app.post("/api/views/state")
def view_state(payload: ViewStateInput, user=Depends(require_user)):
    return update_view_session(payload.session_id, user["id"], payload.playing)


def month_bounds(month):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=422, detail="Месяц укажите как ГГГГ-ММ")
    year, number = map(int, month.split("-"))
    if year < 2000 or year >= 9999:
        raise HTTPException(status_code=422, detail="Недопустимый год")
    start = int(datetime(year, number, 1, tzinfo=timezone.utc).timestamp())
    next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
    end = int(datetime(next_year, next_month, 1, tzinfo=timezone.utc).timestamp())
    return start, end


def finance_report(db, month):
    start, end = month_bounds(month)
    incoming = one(db, """SELECT COALESCE(SUM(price_som),0) AS amount FROM payment_requests
                          WHERE status='approved' AND reviewed_at >= %s AND reviewed_at < %s""", (start, end))["amount"]
    config = one(db, "SELECT * FROM monthly_finances WHERE month=%s", (month,))
    default = one(db, "SELECT value FROM settings WHERE key='default_author_percent'")
    percent = config["author_percent"] if config else int(default["value"] if default else 80)
    revenue = config["revenue_override_som"] if config and config["revenue_override_som"] is not None else incoming
    pool = revenue * percent // 100
    end_day = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d")
    counts = all_rows(db, """SELECT u.id AS author_id,u.full_name,u.email,COUNT(q.id)::int AS views
                             FROM users u LEFT JOIN qualified_views q ON q.author_id=u.id
                             AND q.viewed_on >= %s::date AND q.viewed_on < %s::date
                             WHERE u.role='author' GROUP BY u.id ORDER BY views DESC,u.full_name""",
                      (month + "-01", end_day))
    total = sum(row["views"] for row in counts)
    allocations = {row["author_id"]: (pool * row["views"] // total if total else 0) for row in counts}
    if total:
        remaining = pool - sum(allocations.values())
        ranked = sorted(counts, key=lambda row: (-(pool * row["views"] % total), row["author_id"]))
        for row in ranked[:remaining]:
            allocations[row["author_id"]] += 1
    payouts = {row["author_id"]: row for row in all_rows(db, "SELECT * FROM author_payouts WHERE month=%s", (month,))}
    authors = [{**dict(row), "earned_som": allocations[row["author_id"]],
                "payout": dict(payouts[row["author_id"]]) if row["author_id"] in payouts else None} for row in counts]
    return {"month": month, "actual_revenue_som": incoming, "revenue_som": revenue,
            "revenue_overridden": bool(config and config["revenue_override_som"] is not None),
            "author_percent": percent, "owner_percent": 100 - percent, "author_pool_som": pool,
            "owner_share_som": revenue - pool, "unallocated_som": pool if not total else 0,
            "total_views": total, "authors": authors,
            "note": config["note"] if config else ""}


@app.get("/api/admin/finance/{month}")
def admin_finance(month: str, user=Depends(require_admin)):
    with database() as db:
        return finance_report(db, month)


@app.put("/api/admin/finance/{month}")
def set_finance(month: str, payload: FinanceInput, user=Depends(require_admin)):
    month_bounds(month)
    with database() as db:
        execute(db, "SELECT pg_advisory_xact_lock(hashtext(%s))", ("finance:" + month,))
        if one(db, "SELECT 1 FROM author_payouts WHERE month=%s LIMIT 1", (month,)):
            raise HTTPException(status_code=409, detail="После первой выплаты расчёт месяца менять нельзя")
        execute(db, """INSERT INTO monthly_finances (month,revenue_override_som,author_percent,note,updated_at)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (month) DO UPDATE SET
                       revenue_override_som=EXCLUDED.revenue_override_som,author_percent=EXCLUDED.author_percent,
                       note=EXCLUDED.note,updated_at=EXCLUDED.updated_at""",
                (month, payload.revenue_override_som, payload.author_percent, payload.note.strip(), int(time.time())))
        return finance_report(db, month)


@app.post("/api/admin/payouts", status_code=201)
def mark_payout(payload: PayoutInput, user=Depends(require_admin)):
    if payload.month >= datetime.now(timezone.utc).strftime("%Y-%m"):
        raise HTTPException(status_code=409, detail="Выплату можно отметить после окончания месяца")
    with database() as db:
        execute(db, "SELECT pg_advisory_xact_lock(hashtext(%s))", ("finance:" + payload.month,))
        report = finance_report(db, payload.month)
        author = next((item for item in report["authors"] if item["author_id"] == payload.author_id), None)
        if not author:
            raise HTTPException(status_code=404, detail="Автор не найден")
        if author["payout"]:
            raise HTTPException(status_code=409, detail="Выплата уже отмечена")
        if author["earned_som"] <= 0:
            raise HTTPException(status_code=409, detail="У автора нет начислений за месяц")
        # Freeze revenue and percentage so later defaults cannot rewrite a paid month.
        if not one(db, "SELECT 1 FROM author_payouts WHERE month=%s LIMIT 1", (payload.month,)):
            execute(db, """INSERT INTO monthly_finances (month,revenue_override_som,author_percent,note,updated_at)
                           VALUES (%s,%s,%s,%s,%s) ON CONFLICT (month) DO UPDATE SET
                           revenue_override_som=EXCLUDED.revenue_override_som,
                           author_percent=EXCLUDED.author_percent,updated_at=EXCLUDED.updated_at""",
                    (payload.month,report["revenue_som"],report["author_percent"],report["note"],int(time.time())))
        payout_id = str(uuid4())
        execute(db, """INSERT INTO author_payouts (id,author_id,month,amount_som,paid_at,note,reviewer_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (payout_id, payload.author_id, payload.month, author["earned_som"], int(time.time()), payload.note.strip(), user["id"]))
        return {"id": payout_id, "amount_som": author["earned_som"]}


@app.get("/api/admin/dashboard")
def dashboard(month: str = "", user=Depends(require_staff)):
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    _, end = month_bounds(month)
    end_day = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d")
    with database() as db:
        if user["role"] == "moderator":
            return {"role":"moderator","month":month,
                    "series_count":one(db,"SELECT COUNT(*) AS n FROM series")["n"],
                    "video_count":one(db,"SELECT COUNT(*) AS n FROM videos")["n"],
                    "published_count":one(db,"SELECT COUNT(*) AS n FROM series WHERE is_published=TRUE")["n"]}
        report = finance_report(db, month)
        if user["role"] == "superadmin":
            series_count = one(db, "SELECT COUNT(*) AS n FROM series")["n"]
            pending = one(db, "SELECT COUNT(*) AS n FROM payment_requests WHERE status='pending'")["n"]
            daily = all_rows(db, """SELECT viewed_on::text AS day,COUNT(*)::int AS views FROM qualified_views
                                   WHERE viewed_on >= %s::date AND viewed_on < %s::date
                                   GROUP BY viewed_on ORDER BY viewed_on""", (month + "-01", end_day))
            return {"role": "superadmin", "month": month, "series_count": series_count, "pending_payments": pending,
                    "finance": report, "daily_views": daily}
        author = next((item for item in report["authors"] if item["author_id"] == user["id"]), None)
        series_count = one(db, "SELECT COUNT(*) AS n FROM series WHERE owner_id=%s", (user["id"],))["n"]
        daily = all_rows(db, """SELECT viewed_on::text AS day,COUNT(*)::int AS views FROM qualified_views
                               WHERE author_id=%s AND viewed_on >= %s::date AND viewed_on < %s::date
                               GROUP BY viewed_on ORDER BY viewed_on""", (user["id"], month + "-01", end_day))
        shows = all_rows(db, """SELECT s.id,s.title,COUNT(q.id)::int AS views FROM series s
                               LEFT JOIN episodes e ON e.series_id=s.id
                               LEFT JOIN qualified_views q ON q.episode_id=e.id AND q.viewed_on >= %s::date AND q.viewed_on < %s::date
                               WHERE s.owner_id=%s GROUP BY s.id ORDER BY views DESC,s.title""",
                         (month + "-01", end_day, user["id"]))
        return {"role": "author", "month": month, "series_count": series_count, "views": author["views"] if author else 0,
                "earned_som": author["earned_som"] if author else 0, "payout": author["payout"] if author else None,
                "daily_views": daily, "shows": shows}
