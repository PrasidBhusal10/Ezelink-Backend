import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, EmailStr
from dotenv import load_dotenv

import database
import slug as slug_utils
import cache
import auth
import ratelimit
import events

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

app = FastAPI(
    title="URL Shortener",
    description="Kafka analytics pipeline",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.on_event("startup")
def startup():
    database.init_db()
    try:
        cache.get_redis().ping()
        print("✓ Redis connected")
    except Exception as e:
        print(f"⚠ Redis not reachable: {e}")
    events.get_producer()
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str

class ShortenRequest(BaseModel):
    url: HttpUrl
    custom_slug: Optional[str] = None
    expires_at: Optional[datetime] = None

class ShortenResponse(BaseModel):
    short_url: str
    slug: str
    original_url: str

class URLInfo(BaseModel):
    slug: str
    original_url: str
    is_active: bool
    created_at: datetime
    click_count: int
@app.post("/auth/register", status_code=201)
def register(req: RegisterRequest):
    user = auth.create_user(req.email, req.password)
    token = auth.create_access_token(user["user_id"], user["email"])
    return {
        "message": "Account created",
        "access_token": token,
        "token_type": "bearer",
        "email": user["email"],
        "api_key": user["api_key"],
    }
@app.post("/auth/login", response_model=LoginResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = auth.get_user_by_email(form.username)
    if not user or not auth.verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password",
                          headers={"WWW-Authenticate": "Bearer"})
    token = auth.create_access_token(user["user_id"], user["email"])
    return LoginResponse(access_token=token, email=user["email"])
@app.get("/auth/me")
def me(current_user: dict = Depends(auth.get_current_user)):
    return current_user
@app.get("/analytics/{slug}")
def analytics(
    slug: str,
    request: Request,
    current_user: dict = Depends(auth.get_current_user),
):
    conn = database.get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, original_url, created_at, user_id
        FROM urls WHERE slug = %s AND is_active = true
    """, (slug,))
    url_row = cur.fetchone()

    if not url_row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Slug not found")

    if url_row[3] != current_user["user_id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=403, detail="You don't own this URL")

    url_id = url_row[0]
    cur.execute("SELECT COUNT(*) FROM clicks WHERE url_id = %s", (url_id,))
    total_clicks = cur.fetchone()[0]
    cur.execute("""
        SELECT country, COUNT(*) as clicks
        FROM clicks
        WHERE url_id = %s AND country IS NOT NULL
        GROUP BY country
        ORDER BY clicks DESC
        LIMIT 10
    """, (url_id,))
    by_country = [
        {"country": row[0], "clicks": row[1]}
        for row in cur.fetchall()
    ]
    cur.execute("""
        SELECT
            date_trunc('day', clicked_at)::date AS day,
            COUNT(*) AS clicks
        FROM clicks
        WHERE url_id = %s
          AND clicked_at > now() - INTERVAL '30 days'
        GROUP BY day
        ORDER BY day DESC
    """, (url_id,))
    by_day = [
        {"day": str(row[0]), "clicks": row[1]}
        for row in cur.fetchall()
    ]

    cur.close()
    conn.close()

    return {
        "slug":         slug,
        "original_url": url_row[1],
        "created_at":   url_row[2],
        "total_clicks": total_clicks,
        "by_country":   by_country,
        "by_day":       by_day,
    }
@app.post("/shorten", response_model=ShortenResponse, status_code=201)
def shorten(
    req: ShortenRequest,
    request: Request,
    current_user: dict = Depends(auth.get_current_user),
):
    ratelimit.check_rate_limit(request, user=current_user, endpoint="shorten")

    conn = database.get_conn()
    cur = conn.cursor()

    try:
        if req.custom_slug:
            try:
                slug_utils.validate_custom_slug(req.custom_slug)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            cur.execute("""
                INSERT INTO urls (slug, original_url, user_id, expires_at)
                VALUES (%s, %s, %s, %s) RETURNING id, slug
            """, (req.custom_slug, str(req.url), current_user["user_id"], req.expires_at))
        else:
            cur.execute("""
                INSERT INTO urls (slug, original_url, user_id, expires_at)
                VALUES ('__placeholder__', %s, %s, %s) RETURNING id
            """, (str(req.url), current_user["user_id"], req.expires_at))

            row_id = cur.fetchone()[0]
            real_slug = slug_utils.base62_encode(row_id)

            cur.execute("""
                UPDATE urls SET slug = %s WHERE id = %s RETURNING id, slug
            """, (real_slug, row_id))

        result = cur.fetchone()
        if result is None:
            raise HTTPException(status_code=409, detail=f"Slug '{req.custom_slug}' is already taken")

        conn.commit()
        return ShortenResponse(
            short_url=f"{BASE_URL}/{result[1]}",
            slug=result[1],
            original_url=str(req.url),
        )

    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Slug '{req.custom_slug}' is already taken")
        raise
    finally:
        cur.close()
        conn.close()


@app.get("/cache/stats")
def cache_stats():
    return cache.get_stats()


@app.get("/info/{slug}", response_model=URLInfo)
def url_info(slug: str, request: Request):
    ratelimit.check_rate_limit(request, endpoint="default")

    conn = database.get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT u.slug, u.original_url, u.is_active, u.created_at,
               COUNT(c.id) AS click_count
        FROM urls u
        LEFT JOIN clicks c ON c.url_id = u.id
        WHERE u.slug = %s
        GROUP BY u.slug, u.original_url, u.is_active, u.created_at
    """, (slug,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Slug not found")

    return URLInfo(slug=row[0], original_url=row[1], is_active=row[2],
                   created_at=row[3], click_count=row[4])


@app.delete("/{slug}", status_code=204)
def deactivate(slug: str, current_user: dict = Depends(auth.get_current_user)):
    conn = database.get_conn()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM urls WHERE slug = %s AND is_active = true", (slug,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Slug not found")

    if row[0] != current_user["user_id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=403, detail="You don't own this URL")

    cur.execute("UPDATE urls SET is_active = false WHERE slug = %s RETURNING id", (slug,))
    conn.commit()
    cur.close()
    conn.close()
    cache.evict(slug)


@app.get("/health")
def health():
    status = {"db": "unreachable", "redis": "unreachable", "kafka": "unreachable"}
    code = 200

    try:
        conn = database.get_conn()
        conn.close()
        status["db"] = "ok"
    except Exception:
        code = 503

    try:
        cache.get_redis().ping()
        status["redis"] = "ok"
    except Exception:
        pass

    try:
        producer = events.get_producer()
        if producer:
            status["kafka"] = "ok"
    except Exception:
        pass

    status["status"] = "ok" if code == 200 else "degraded"
    return JSONResponse(status_code=code, content=status)


@app.get("/{slug}")
def redirect(slug: str, request: Request):
    ratelimit.check_rate_limit(request, endpoint="redirect")
    cached = cache.get_url(slug)

    if cached == "__not_found__":
        raise HTTPException(status_code=404, detail="Short URL not found")
    if cached:
        parts = cached.split("|", 1)
        if len(parts) == 2:
            url_id, original_url = int(parts[0]), parts[1]
        else:
            original_url = cached
            url_id = None
        if url_id:
            events.publish_click(
                slug=slug,
                url_id=url_id,
                ip=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("user-agent"),
                referrer=request.headers.get("referer"),
            )

        return RedirectResponse(url=original_url, status_code=302)
    conn = database.get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, original_url, expires_at
        FROM urls WHERE slug = %s AND is_active = true
    """, (slug,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        cache.set_not_found(slug)
        raise HTTPException(status_code=404, detail="Short URL not found")

    url_id, original_url, expires_at = row

    if expires_at and expires_at < datetime.utcnow().replace(tzinfo=expires_at.tzinfo):
        raise HTTPException(status_code=410, detail="This link has expired")
    cache.set_url(slug, f"{url_id}|{original_url}")
    events.publish_click(
        slug=slug,
        url_id=url_id,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
    )

    return RedirectResponse(url=original_url, status_code=302)