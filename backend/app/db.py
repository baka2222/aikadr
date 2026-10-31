"""PostgreSQL schema and small transaction helpers."""

import os
import time
from contextlib import contextmanager
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from .security import hash_password


DATABASE_URL = os.getenv("DATABASE_URL", "")


@contextmanager
def database():
    connection = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def one(db, query, params=()):
    with db.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


def all_rows(db, query, params=()):
    with db.cursor() as cur:
        cur.execute(query, params)
        return list(cur.fetchall())


def execute(db, query, params=()):
    with db.cursor() as cur:
        cur.execute(query, params)
        return cur.rowcount


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'author', 'moderator', 'superadmin')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    session_version INTEGER NOT NULL DEFAULT 0,
    storage_quota_bytes BIGINT NOT NULL DEFAULT 10737418240 CHECK (storage_quota_bytes >= 0),
    created_at BIGINT NOT NULL
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS storage_quota_bytes BIGINT NOT NULL DEFAULT 10737418240;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('viewer','author','moderator','superadmin'));
CREATE TABLE IF NOT EXISTS auth_challenges (
    id TEXT PRIMARY KEY, email TEXT NOT NULL, user_id TEXT REFERENCES users(id),
    purpose TEXT NOT NULL CHECK (purpose IN ('register','login','reset')),
    code_hash TEXT NOT NULL, password_hash TEXT, full_name TEXT NOT NULL DEFAULT '',
    session_version INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
    created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL, consumed_at BIGINT
);
CREATE INDEX IF NOT EXISTS auth_challenges_email_created ON auth_challenges(email,created_at DESC);
CREATE TABLE IF NOT EXISTS auth_rate_limits (
    bucket TEXT PRIMARY KEY, window_start BIGINT NOT NULL, hits INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category_id TEXT NOT NULL REFERENCES categories(id),
    poster_url TEXT NOT NULL DEFAULT '',
    year INTEGER NOT NULL,
    rating TEXT NOT NULL DEFAULT '12+',
    featured BOOLEAN NOT NULL DEFAULT FALSE,
    popular BOOLEAN NOT NULL DEFAULT FALSE,
    created_at BIGINT NOT NULL,
    owner_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    is_published BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    series_id TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    season INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    duration TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    video_oid OID,
    video_size BIGINT NOT NULL DEFAULT 0,
    video_mime TEXT NOT NULL DEFAULT '',
    free_preview BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (series_id, season, number)
);
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL UNIQUE REFERENCES episodes(id) ON DELETE CASCADE,
    large_object_oid OID NOT NULL UNIQUE,
    byte_size BIGINT NOT NULL CHECK (byte_size>0),
    mime_type TEXT NOT NULL,
    original_name TEXT NOT NULL DEFAULT '',
    uploaded_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at BIGINT NOT NULL
);
INSERT INTO videos (id,episode_id,large_object_oid,byte_size,mime_type,original_name,created_at)
SELECT id,id,video_oid,video_size,video_mime,'Импортированное видео',EXTRACT(EPOCH FROM NOW())::bigint
FROM episodes WHERE video_oid IS NOT NULL ON CONFLICT (episode_id) DO NOTHING;
UPDATE episodes SET video_oid=NULL,video_size=0,video_mime='' WHERE video_oid IS NOT NULL;
CREATE OR REPLACE FUNCTION cleanup_video_object() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN
        PERFORM lo_unlink(OLD.large_object_oid);
    ELSIF OLD.large_object_oid <> NEW.large_object_oid THEN
        PERFORM lo_unlink(OLD.large_object_oid);
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS videos_cleanup ON videos;
CREATE TRIGGER videos_cleanup AFTER UPDATE OR DELETE ON videos
FOR EACH ROW EXECUTE FUNCTION cleanup_video_object();
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price_som INTEGER NOT NULL CHECK (price_som >= 0),
    duration_days INTEGER NOT NULL CHECK (duration_days > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_methods (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    plan_id TEXT NOT NULL REFERENCES plans(id),
    payment_method_id TEXT REFERENCES payment_methods(id) ON DELETE SET NULL,
    payment_method_title TEXT NOT NULL DEFAULT '',
    price_som INTEGER NOT NULL,
    duration_days INTEGER,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    receipt BYTEA NOT NULL,
    receipt_mime TEXT NOT NULL,
    receipt_size INTEGER NOT NULL,
    created_at BIGINT NOT NULL,
    reviewed_at BIGINT,
    reviewer_id TEXT REFERENCES users(id),
    note TEXT NOT NULL DEFAULT ''
);
ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS payment_method_id TEXT REFERENCES payment_methods(id) ON DELETE SET NULL;
ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS payment_method_title TEXT NOT NULL DEFAULT '';
ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS duration_days INTEGER;
UPDATE payment_requests pr SET duration_days=pl.duration_days FROM plans pl
WHERE pr.plan_id=pl.id AND pr.duration_days IS NULL;
ALTER TABLE payment_requests ALTER COLUMN duration_days SET NOT NULL;
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    plan_id TEXT NOT NULL REFERENCES plans(id),
    payment_request_id TEXT NOT NULL UNIQUE REFERENCES payment_requests(id),
    starts_at BIGINT NOT NULL,
    ends_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS subscriptions_user_ends ON subscriptions(user_id, ends_at DESC);
CREATE TABLE IF NOT EXISTS view_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    started_at BIGINT NOT NULL,
    last_heartbeat BIGINT NOT NULL,
    watched_seconds INTEGER NOT NULL DEFAULT 0,
    counted BOOLEAN NOT NULL DEFAULT FALSE,
    is_playing BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS view_sessions_user ON view_sessions(user_id, started_at DESC);
CREATE TABLE IF NOT EXISTS qualified_views (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    episode_id TEXT REFERENCES episodes(id) ON DELETE SET NULL,
    author_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    viewed_on DATE NOT NULL,
    created_at BIGINT NOT NULL,
    UNIQUE (user_id, episode_id, viewed_on)
);
ALTER TABLE qualified_views ALTER COLUMN episode_id DROP NOT NULL;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='qualified_views'::regclass
               AND conname='qualified_views_episode_id_fkey' AND confdeltype <> 'n') THEN
        ALTER TABLE qualified_views DROP CONSTRAINT qualified_views_episode_id_fkey;
        ALTER TABLE qualified_views ADD CONSTRAINT qualified_views_episode_id_fkey
            FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS qualified_views_author_date ON qualified_views(author_id, viewed_on DESC);
CREATE TABLE IF NOT EXISTS monthly_finances (
    month TEXT PRIMARY KEY,
    revenue_override_som INTEGER CHECK (revenue_override_som >= 0),
    author_percent INTEGER NOT NULL DEFAULT 80 CHECK (author_percent BETWEEN 0 AND 100),
    note TEXT NOT NULL DEFAULT '',
    updated_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS author_payouts (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL REFERENCES users(id),
    month TEXT NOT NULL,
    amount_som INTEGER NOT NULL CHECK (amount_som >= 0),
    paid_at BIGINT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    UNIQUE (author_id, month)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"""


def init_database():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be set")
    with database() as db:
        with db.cursor() as cur:
            cur.execute(SCHEMA)
        admin_email = os.getenv("ADMIN_EMAIL", "admin@kadr.local").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        if not admin_password or len(admin_password) < 12:
            raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters")
        if not one(db, "SELECT id FROM users WHERE role='superadmin' LIMIT 1"):
            execute(db, "INSERT INTO users (id,email,full_name,password_hash,role,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (str(uuid4()), admin_email, "Главный администратор", hash_password(admin_password), "superadmin", int(time.time())))
        elif not admin_email.endswith("@kadr.local") and not one(db,"SELECT id FROM users WHERE email=%s",(admin_email,)):
            placeholder_admin = one(db,"SELECT id FROM users WHERE email='admin@kadr.local' AND role='superadmin'")
            if placeholder_admin:
                execute(db,"UPDATE users SET email=%s,email_verified=FALSE,session_version=session_version+1 WHERE id=%s",
                        (admin_email,placeholder_admin["id"]))
        execute(db, "INSERT INTO settings (key,value) VALUES ('default_author_percent','80') ON CONFLICT DO NOTHING")
        execute(db, "INSERT INTO settings (key,value) VALUES ('payment_instructions','') ON CONFLICT DO NOTHING")
        execute(db, "INSERT INTO settings (key,value) VALUES ('payment_ready','false') ON CONFLICT DO NOTHING")
        execute(db, """UPDATE settings SET value='' WHERE key='payment_instructions'
                       AND value='Переведите сумму по реквизитам, указанным администратором, и загрузите чек.'
                       AND EXISTS (SELECT 1 FROM settings WHERE key='payment_ready' AND value='false')""")
        if one(db, "SELECT id FROM categories LIMIT 1"):
            return
        names = ["Триллер", "Драма", "Фантастика", "Мелодрама", "Приключения", "Детектив", "Мистика"]
        category_ids = {name: str(uuid4()) for name in names}
        for name, category_id in category_ids.items():
            execute(db, "INSERT INTO categories (id,name) VALUES (%s,%s)", (category_id, name))
