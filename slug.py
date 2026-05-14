CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def base62_encode(num: int) -> str:
    if num <= 0:
        raise ValueError(f"Expected positive integer, got {num}")

    result = []
    while num:
        result.append(CHARS[num % 62])
        num //= 62
    return "".join(reversed(result))


def base62_decode(slug: str) -> int:
    result = 0
    for char in slug:
        result = result * 62 + CHARS.index(char)
    return result


# ── Validation ───────────────────────────────────────────────────────────────

RESERVED_SLUGS = {
    "api", "admin", "login", "logout", "signup", "register",
    "health", "metrics", "static", "favicon.ico", "robots.txt",
}

SLUG_MAX_LENGTH = 50
SLUG_ALLOWED_CHARS = set(CHARS + "-_")


def validate_custom_slug(slug: str) -> str:
    if not slug:
        raise ValueError("Slug cannot be empty")
    if len(slug) > SLUG_MAX_LENGTH:
        raise ValueError(f"Slug too long (max {SLUG_MAX_LENGTH} chars)")
    if slug.lower() in RESERVED_SLUGS:
        raise ValueError(f"'{slug}' is a reserved word")
    invalid = set(slug) - SLUG_ALLOWED_CHARS
    if invalid:
        raise ValueError(f"Invalid characters: {invalid}")
    return slug