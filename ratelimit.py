import time
from fastapi import HTTPException, Request
import cache
WINDOW_SECONDS = 60       # look-back window
STRICT_LIMIT   = 10       # authenticated users: 10 requests/min
ANON_LIMIT     = 10       # anonymous users:     10 requests/min (same, strict)
LIMITS = {
    "shorten":  10,   # 10 shortens/min — most restrictive
    "redirect": 60,   # 60 redirects/min — generous, it's the main use case
    "default":  30,   # everything else
}
def is_rate_limited(identifier: str, limit: int, window: int = WINDOW_SECONDS) -> dict:
    try:
        r = cache.get_redis()
        now = time.time()
        window_start = now - window
        key = f"ratelimit:{identifier}"

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        results = pipe.execute()
        current_count = results[1]

        if current_count >= limit:
            oldest = r.zrange(key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + window - now) + 1 if oldest else window
            return {
                "allowed": False,
                "count": current_count,
                "limit": limit,
                "remaining": 0,
                "retry_after": retry_after,
            }

        return {
            "allowed": True,
            "count": current_count + 1,
            "limit": limit,
            "remaining": limit - current_count - 1,
            "retry_after": 0,
        }
    except Exception as e:
        # Redis timeout or error — skip rate limiting, allow request
        import logging
        logging.warning(f"Rate limiting skipped: {e}")
        return {"allowed": True, "count": 0, "limit": limit, "remaining": limit, "retry_after": 0}

def get_identifier(request: Request, user: dict = None) -> str:
    if user:
        return f"user:{user['user_id']}"

    # Try to get real IP behind proxies/load balancers
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    return f"ip:{ip}"


def check_rate_limit(request: Request, user: dict = None, endpoint: str = "default"):
    # Temporarily disabled — Redis connection issues on Railway
    # TODO: re-enable when Redis is stable
    return {"allowed": True, "count": 0, "limit": 100, "remaining": 100, "retry_after": 0}