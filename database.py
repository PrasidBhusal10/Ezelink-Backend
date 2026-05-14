import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    """Return a new database connection."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "shortener"),
        user=os.getenv("DB_USER", "app"),
        password=os.getenv("DB_PASSWORD", "secret"),
        port=int(os.getenv("DB_PORT", 5432)),
    )


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            api_key       TEXT UNIQUE DEFAULT gen_random_uuid()::text,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS urls (
            id           BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            slug         TEXT NOT NULL UNIQUE,
            original_url TEXT NOT NULL,
            user_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
            is_active    BOOLEAN NOT NULL DEFAULT true,
            expires_at   TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- The most important index: every redirect hits this
        CREATE UNIQUE INDEX IF NOT EXISTS idx_urls_slug
            ON urls(slug);

        -- For listing a user's URLs
        CREATE INDEX IF NOT EXISTS idx_urls_user_id
            ON urls(user_id);

        -- Partial index: only rows that actually expire (keeps it small)
        CREATE INDEX IF NOT EXISTS idx_urls_expires
            ON urls(expires_at)
            WHERE expires_at IS NOT NULL;

        CREATE TABLE IF NOT EXISTS clicks (
            id           BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            url_id       BIGINT NOT NULL REFERENCES urls(id) ON DELETE CASCADE,
            country      CHAR(2),          -- ISO 3166: "US", "GB"
            device_type  TEXT,             -- "mobile", "desktop", "tablet"
            referrer     TEXT,
            clicked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- For counting clicks per URL
        CREATE INDEX IF NOT EXISTS idx_clicks_url_id
            ON clicks(url_id);

        -- For time-range analytics queries (Phase 4)
        CREATE INDEX IF NOT EXISTS idx_clicks_url_time
            ON clicks(url_id, clicked_at DESC);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✓ Database initialised")