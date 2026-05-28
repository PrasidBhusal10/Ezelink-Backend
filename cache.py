import os
import redis
from dotenv import load_dotenv

load_dotenv()

_client = None

DEFAULT_TTL  = 3600
POPULAR_TTL  = 86400
NEGATIVE_TTL = 60


def get_redis() -> redis.Redis:
    # ← KEEP THIS EXACTLY AS IT IS
    global _client
    if _client is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            _client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=0.1,
                socket_connect_timeout=0.1,
            )
        else:
            _client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                password=os.getenv("REDIS_PASSWORD", None),
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
    return _client


def get_url(slug: str) -> str | None:
    try:
        r = get_redis()
        return r.get(f"slug:{slug}")
    except Exception:
        return None  # cache miss — fall through to DB

def set_url(slug: str, original_url: str, ttl: int = DEFAULT_TTL) -> None:
    try:
        r = get_redis()
        r.set(f"slug:{slug}", original_url, ex=ttl)
    except Exception:
        pass

def set_not_found(slug: str) -> None:
    try:
        r = get_redis()
        r.set(f"slug:{slug}", "__not_found__", ex=NEGATIVE_TTL)
    except Exception:
        pass

def evict(slug: str) -> None:
    try:
        r = get_redis()
        r.delete(f"slug:{slug}")
    except Exception:
        pass

def get_stats() -> dict:
    try:
        r = get_redis()
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
    except Exception as e:
        return {"error": str(e)}

def _hit_rate(info: dict) -> str:
    hits   = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total  = hits + misses
    if total == 0:
        return "0%"
    return f"{hits / total * 100:.1f}%"