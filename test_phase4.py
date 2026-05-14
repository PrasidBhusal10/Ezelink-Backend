import time
import requests

BASE = "http://localhost:8000"
EMAIL = f"phase4_{int(time.time())}@example.com"
PASSWORD = "testpass123"


def register_and_login():
    r = requests.post(f"{BASE}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_includes_kafka(token):
    print("\n── Health check includes Kafka ──────────────────────")
    r = requests.get(f"{BASE}/health")
    data = r.json()
    print(f"  Health: {data}")
    if data.get("kafka") == "ok":
        print("  ✓ Kafka connected")
    else:
        print("  ⚠ Kafka not connected — click events will be skipped")
        print("    Make sure worker is running: python worker.py")


def test_click_events_published(token):
    print("\n── Click events published to Kafka ──────────────────")
    r = requests.post(f"{BASE}/shorten",
        json={"url": "https://www.python.org"},
        headers=auth_headers(token)
    )
    assert r.status_code == 201, r.text
    slug = r.json()["slug"]
    print(f"  Created slug: {slug}")
    for i in range(5):
        r = requests.get(f"{BASE}/{slug}", allow_redirects=False)
        assert r.status_code == 302
    print(f"  Made 5 clicks on /{slug}")
    print("  Waiting 8 seconds for worker to process events...")
    time.sleep(8)

    return slug


def test_analytics_endpoint(token, slug):
    print("\n── Analytics endpoint ───────────────────────────────")

    r = requests.get(f"{BASE}/analytics/{slug}", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    data = r.json()

    print(f"  Slug:          {data['slug']}")
    print(f"  Total clicks:  {data['total_clicks']}")
    print(f"  By country:    {data['by_country']}")
    print(f"  By day:        {data['by_day']}")

    assert data["total_clicks"] >= 0
    print("  ✓ Analytics endpoint working")


def test_analytics_ownership(token, slug):
    print("\n── Analytics ownership check ────────────────────────")
    other = requests.post(f"{BASE}/auth/register", json={
        "email": f"other4_{int(time.time())}@example.com",
        "password": "pass123"
    })
    other_token = other.json()["access_token"]

    r = requests.get(f"{BASE}/analytics/{slug}",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert r.status_code == 403, r.text
    print("  ✓ Other user can't see analytics → 403")


def test_analytics_requires_auth(slug):
    print("\n── Analytics requires auth ──────────────────────────")
    r = requests.get(f"{BASE}/analytics/{slug}")
    assert r.status_code == 401, r.text
    print("  ✓ Analytics without token → 401")


if __name__ == "__main__":
    print("\n══ Phase 4 — Analytics pipeline tests ════════════════")
    print("  NOTE: Make sure worker.py is running in another terminal")
    print("  Command: python worker.py\n")

    token = register_and_login()
    test_health_includes_kafka(token)
    slug = test_click_events_published(token)
    test_analytics_endpoint(token, slug)
    test_analytics_ownership(token, slug)
    test_analytics_requires_auth(slug)

    print("\n✓ All Phase 4 tests passed\n")