# ⚡ EzeLink — URL Shortener

> A production-grade URL shortener built from scratch with FastAPI, PostgreSQL, Redis, and Kafka. Features JWT authentication, sliding window rate limiting, async analytics pipeline, and Redis cache-aside pattern. Fully Dockerised and deployed live.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-ezelink.netlify.app-blueviolet?style=for-the-badge)](https://ezelink.netlify.app)
[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger%20UI-orange?style=for-the-badge)](https://ezelink.up.railway.app/docs)
[![Backend](https://img.shields.io/badge/Backend-Railway-purple?style=for-the-badge)](https://ezelink.up.railway.app)

---

## 🌐 Live Demo

| Service | URL |
|---------|-----|
| Frontend | https://ezelink.netlify.app |
| Backend API | https://ezelink.up.railway.app |
| API Documentation | https://ezelink.up.railway.app/docs |

---

## 📸 Features

- **Instant URL shortening** — paste any URL and get a short link in under 1 second
- **Custom slugs** — create branded links like `ezelink.io/my-brand`
- **Link expiry** — set an expiration date on any link
- **Click analytics** — track clicks by country and date
- **JWT authentication** — secure accounts with stateless token-based auth
- **Rate limiting** — sliding window rate limiter prevents abuse
- **Redis caching** — cache-aside pattern serves redirects in under 1ms
- **Async analytics** — Kafka-powered click tracking never slows down redirects
- **Fully Dockerised** — one command starts the entire stack

---

## 🏗️ Architecture

```
Browser
   │
   ▼
Netlify (Frontend)
   │  HTML + CSS + JS
   │
   ▼
Railway (Backend API — FastAPI)
   │
   ├──► Redis         (cache-aside + rate limiting)
   ├──► PostgreSQL    (persistent storage)
   └──► Kafka         (async click events)
              │
              ▼
        Analytics Worker
              │
              ▼
        PostgreSQL (clicks table)
```

### Request lifecycle

**Redirect (GET /{slug}):**
```
1. Check Redis cache (~0.5ms)
   ├── HIT  → return 302 immediately
   └── MISS → query PostgreSQL (~10ms)
               → populate Redis cache
               → publish click event to Kafka (fire and forget)
               → return 302
```

**Analytics worker (separate process):**
```
Kafka topic → consume batch → GeoIP lookup → INSERT clicks → commit offset
```

---

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **FastAPI** | REST API framework |
| **PostgreSQL** | Primary database |
| **Redis** | Cache-aside + sliding window rate limiting |
| **Kafka** | Async click event streaming |
| **Docker** | Containerisation |
| **PyJWT** | JWT authentication |
| **psycopg2** | PostgreSQL driver |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **HTML5 / CSS3 / JavaScript** | No framework — pure web standards |
| **Chart.js** | Analytics charts |
| **Fetch API** | HTTP requests to backend |

### Infrastructure
| Service | Purpose |
|---------|---------|
| **Railway** | Backend + PostgreSQL + Redis hosting |
| **Netlify** | Frontend hosting |
| **GitHub** | Version control |

---

## 🔑 Key Concepts Implemented

### 1. Cache-aside pattern
Every redirect checks Redis first. On a miss, queries PostgreSQL and populates the cache with a TTL. Negative caching prevents DB hammering for non-existent slugs.

```python
cached = cache.get_url(slug)
if cached:
    return RedirectResponse(url=cached, status_code=302)

# Cache miss — query DB
row = db.execute("SELECT original_url FROM urls WHERE slug = %s", (slug,))
cache.set_url(slug, row.original_url)  # populate for next time
return RedirectResponse(url=row.original_url, status_code=302)
```

### 2. Sliding window rate limiting
Uses a Redis sorted set to track request timestamps. Unlike fixed windows, this prevents burst attacks at window boundaries.

```python
# Remove entries older than window_start
pipe.zremrangebyscore(key, 0, window_start)
# Count remaining (current window)
pipe.zcard(key)
# Add this request
pipe.zadd(key, {str(now): now})
```

### 3. Fire-and-forget analytics
Click events are published to Kafka before returning the redirect. The user never waits for analytics writes.

```python
# Fire and forget — never blocks the redirect
events.publish_click(slug=slug, url_id=url_id, ip=request.client.host)
return RedirectResponse(url=original_url, status_code=302)
```

### 4. Idempotent consumer
The analytics worker commits Kafka offsets only after a successful DB write. `ON CONFLICT DO NOTHING` makes duplicate processing safe.

```python
# DB write FIRST, then commit offset
flush_batch(batch)           # write to PostgreSQL
consumer.commit()            # only now tell Kafka we're done
```

### 5. JWT stateless authentication
No server-side sessions. The JWT payload carries user identity, verified by signature on every request.

```python
payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
# user_id and email extracted from token — no DB lookup needed
```

### 6. Base62 slug generation
Auto-increment database IDs encoded to base62 — guaranteed unique, no collision checking needed.

```python
CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def base62_encode(num: int) -> str:
    result = []
    while num:
        result.append(CHARS[num % 62])
        num //= 62
    return ''.join(reversed(result))
```

---

## 📁 Project Structure

```
url_backend/
├── main.py          # FastAPI app + all routes
├── database.py      # DB connection + schema init
├── auth.py          # JWT + password hashing
├── cache.py         # Redis cache-aside implementation
├── ratelimit.py     # Sliding window rate limiter
├── events.py        # Kafka producer (click events)
├── worker.py        # Kafka consumer (analytics worker)
├── slug.py          # Base62 encoding + slug validation
├── Dockerfile       # Two-stage Docker build
├── docker-compose.yml  # Full stack (API + Worker + DB + Redis + Kafka)
└── requirements.txt

url_frontend/
├── index.html       # Home page — URL shortener
├── login.html       # Login page
├── register.html    # Register page
├── dashboard.html   # Link management dashboard
├── analytics.html   # Click analytics with charts
├── style.css        # Shared styles (light theme)
└── app.js           # API client + shared utilities
```

---

## 🗄️ Database Schema

```sql
users
├── id            BIGINT PK
├── email         TEXT UNIQUE
├── password_hash TEXT
├── api_key       TEXT UNIQUE
└── created_at    TIMESTAMPTZ

urls
├── id           BIGINT PK
├── slug         TEXT UNIQUE    ← indexed for fast redirects
├── original_url TEXT
├── user_id      BIGINT FK → users
├── is_active    BOOLEAN        ← soft delete
├── expires_at   TIMESTAMPTZ    ← nullable, partial index
└── created_at   TIMESTAMPTZ

clicks
├── id          BIGINT PK
├── url_id      BIGINT FK → urls
├── country     CHAR(2)         ← ISO 3166 country code
├── device_type TEXT
├── referrer    TEXT
└── clicked_at  TIMESTAMPTZ     ← composite index with url_id
```

---

## 🚀 Running Locally

### Prerequisites
- Docker Desktop
- Python 3.12+
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/PrasidBhusal10/EzeLink.git
cd EzeLink

# Copy environment variables
cp .env.example .env

# Start all services (PostgreSQL, Redis, Kafka, API, Worker)
docker compose up --build

# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Environment Variables

```env
DB_HOST=db
DB_NAME=shortener
DB_USER=app
DB_PASSWORD=secret
DB_PORT=5432

REDIS_HOST=redis
REDIS_PORT=6379

KAFKA_BOOTSTRAP=kafka:29092

BASE_URL=http://localhost:8000
SECRET_KEY=your-secret-key-minimum-32-characters
```

### API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `POST` | `/auth/register` | Create account | No |
| `POST` | `/auth/login` | Get JWT token | No |
| `GET` | `/auth/me` | Current user info | Yes |
| `POST` | `/shorten` | Shorten a URL | Optional |
| `GET` | `/{slug}` | Redirect to original URL | No |
| `GET` | `/info/{slug}` | URL metadata + click count | No |
| `GET` | `/analytics/{slug}` | Full analytics data | Yes (owner) |
| `DELETE` | `/{slug}` | Deactivate a URL | Yes (owner) |
| `GET` | `/cache/stats` | Redis cache statistics | No |
| `GET` | `/health` | Health check | No |

---

## 📊 System Design Decisions

### Why Redis for caching?
Redirects are the most frequent operation. Redis serves cached slugs in under 1ms vs 10-20ms for a PostgreSQL query. At scale, this difference is enormous — 1 million redirects/day means 10,000 seconds saved per day.

### Why Kafka for analytics?
Writing click data synchronously inside the redirect endpoint would add 10-20ms to every redirect. Kafka decouples the redirect from analytics — the event is published in ~0.5ms and the worker processes it asynchronously. The redirect endpoint stays fast regardless of analytics load.

### Why JWT over sessions?
Sessions require server-side storage — every request needs a DB or Redis lookup to validate. JWT embeds the user identity in the token itself. The server just verifies the signature — no storage lookup needed. Scales horizontally without shared session state.

### Why soft deletes?
Hard-deleting a slug means anyone who bookmarked the short link gets a confusing 500 error. Soft deletes (`is_active = false`) return a clean 404 with a helpful message. Historical data is preserved for analytics.

### Why base62 encoding over random strings?
Random slugs require a uniqueness check (DB round trip). Base62 encoding of the auto-increment ID is mathematically guaranteed unique — ID 1 = "b", ID 1000 = "g8", no collisions ever. Keeps slugs short as the table grows.

---

## 🔒 Security

- Passwords hashed with **PBKDF2-SHA256** + random salt (100,000 iterations)
- JWT signed with **HS256** — tokens expire after 24 hours
- **Rate limiting** — 10 shortens/min per user, 60 redirects/min per IP
- **Ownership checks** — users can only delete/view analytics for their own links
- **Soft deletes** — deactivated links return 404, not server errors
- **Environment variables** — no secrets hardcoded anywhere
- **CORS** configured to allow only the frontend domain

---

## 📈 What I Learned

Building this project gave me hands-on experience with:

- **System design** — decoupling services, handling failures gracefully
- **Caching strategies** — cache-aside, TTL design, cache invalidation
- **Message queues** — Kafka producers/consumers, offset management, idempotency
- **Authentication** — JWT internals, password hashing, stateless auth
- **Database design** — indexing strategy, soft deletes, partial indexes
- **Rate limiting** — sliding window algorithm using Redis sorted sets
- **Docker** — multi-stage builds, service dependencies, health checks
- **Deployment** — Railway (backend), Netlify (frontend), environment configuration

---

## 🗺️ Roadmap

- [ ] Email verification on registration
- [ ] Password reset via email
- [ ] QR code generation for each link
- [ ] Link preview (title + favicon)
- [ ] Custom domain support
- [ ] Bulk URL shortening
- [ ] API key authentication for programmatic access
- [ ] Prometheus metrics + Grafana dashboard

---

## 👤 Author

**Prasid Bhusal**
- GitHub: [@PrasidBhusal10](https://github.com/PrasidBhusal10)
- Live project: [ezelink.netlify.app](https://ezelink.netlify.app)

---

## 📄 License

MIT License — feel free to use this project as a learning reference.

---

*Built from scratch as a full-stack system design learning project — every line of code written and understood personally.*
