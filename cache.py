
import os
import redis
from dotenv import load_dotenv
 
load_dotenv()
 
# ── Connection ─────────────────────────────────────────────────────────────────
 
_client: redis.Redis | None = None
 
 
def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True,   # return str, not bytes
        )
    return _client
DEFAULT_TTL = 3600          # 1 hour — most slugs
POPULAR_TTL = 86400         # 24 hours — could use for high-traffic slugs
NEGATIVE_TTL = 60           # 1 min — cache "not found" to block DB hammering
 
 
# ── Cache operations ───────────────────────────────────────────────────────────
 
def get_url(slug: str) -> str | None:
    r = get_redis()
    try:
        return r.get(f"slug:{slug}")
    except redis.RedisError:
        return None
 
 
def set_url(slug: str, original_url: str, ttl: int = DEFAULT_TTL) -> None:
    r = get_redis()
    try:
        r.set(f"slug:{slug}", original_url, ex=ttl)
    except redis.RedisError:
        pass  # Cache write failure is non-fatal
 
 
def set_not_found(slug: str) -> None:
    r = get_redis()
    try:
        r.set(f"slug:{slug}", "__not_found__", ex=NEGATIVE_TTL)
    except redis.RedisError:
        pass
 
 
def evict(slug: str) -> None:
    r = get_redis()
    try:
        r.delete(f"slug:{slug}")
    except redis.RedisError:
        pass
 
 
def get_stats() -> dict:
 
    r = get_redis()
    try:
        info = r.info("stats")
        memory = r.info("memory")
        return {
            "hits":              info.get("keyspace_hits", 0),
            "misses":            info.get("keyspace_misses", 0),
            "hit_rate":          _hit_rate(info),
            "total_keys":        r.dbsize(),
            "used_memory_human": memory.get("used_memory_human"),
            "evicted_keys":      info.get("evicted_keys", 0),
        }
    except redis.RedisError as e:
        return {"error": str(e)}
 
 
def _hit_rate(info: dict) -> str:
    hits   = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total  = hits + misses
    if total == 0:
        return "0%"
    return f"{hits / total * 100:.1f}%"