"""
Phase 5 — Kafka Producer (updated for Docker)

Key change from Phase 4:
  bootstrap_servers now reads from KAFKA_BOOTSTRAP env var
  so it works both locally (localhost:9092) and in Docker (kafka:29092)
"""

import os
import json
import time
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

_producer = None
TOPIC = "click-events"
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")


def get_producer():
    global _producer
    if _producer is None:
        try:
            from kafka import KafkaProducer
            _producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                retries=3,
                request_timeout_ms=5000,
            )
            _producer.bootstrap_connected()
            log.info(f"✓ Kafka producer connected to {BOOTSTRAP}")
            print(f"✓ Kafka producer connected to {BOOTSTRAP}")
        except Exception as e:
            log.warning(f"⚠ Kafka not available ({BOOTSTRAP}): {e}")
            return None
    return _producer


def publish_click(
    slug: str,
    url_id: int,
    ip: str,
    user_agent: Optional[str] = None,
    referrer: Optional[str] = None,
):
    producer = get_producer()
    if not producer:
        return

    event = {
        "slug":       slug,
        "url_id":     url_id,
        "ip":         ip,
        "user_agent": user_agent or "",
        "referrer":   referrer or "",
        "timestamp":  int(time.time() * 1000),
    }

    try:
        producer.send(TOPIC, event)
    except Exception as e:
        log.warning(f"Failed to publish click event: {e}")