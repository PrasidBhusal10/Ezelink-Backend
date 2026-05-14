import os        
import json
import time
import signal
import logging
import requests
from typing import Optional

import database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [worker] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)
TOPIC          = os.getenv("KAFKA_TOPIC", "click-events")
GROUP_ID       = os.getenv("KAFKA_GROUP_ID", "analytics-workers")
BATCH_SIZE     = int(os.getenv("BATCH_SIZE", "100"))
FLUSH_INTERVAL = int(os.getenv("FLUSH_INTERVAL", "5"))
BOOTSTRAP      = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
def get_country(ip: str) -> Optional[str]:
    """Resolve an IP address to a 2-letter country code."""
    if not ip or ip.startswith(("127.", "192.168.", "10.", "172.")):
        log.debug(f"Skipping private IP: {ip}")
        return None

    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            timeout=2,
            params={"fields": "countryCode,status"}
        )
        data = r.json()
        if data.get("status") == "success":
            return data.get("countryCode")
    except Exception as e:
        log.warning(f"GeoIP lookup failed for {ip}: {e}")

    return None
def flush_batch(batch: list) -> bool:
    """Write a batch of enriched click events to the database."""
    if not batch:
        return True

    conn = database.get_conn()
    cur = conn.cursor()

    try:
        cur.executemany("""
            INSERT INTO clicks (url_id, country, clicked_at)
            VALUES (%(url_id)s, %(country)s, to_timestamp(%(timestamp)s / 1000.0))
            ON CONFLICT DO NOTHING
        """, batch)

        conn.commit()
        log.info(f"✓ Flushed {len(batch)} clicks to DB")
        return True

    except Exception as e:
        conn.rollback()
        log.error(f"DB write failed: {e}")
        return False

    finally:
        cur.close()
        conn.close()
def run():
    """Main consumer loop — runs forever until CTRL+C."""
    from kafka import KafkaConsumer
    from kafka.errors import CommitFailedError

    log.info(f"Starting analytics worker, consuming from '{TOPIC}'...")
    log.info(f"Connecting to bootstrap server: {BOOTSTRAP}")

    try:
        consumer = KafkaConsumer(
            TOPIC,
            bootstrap_servers=BOOTSTRAP,
            group_id=GROUP_ID,
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=lambda b: json.loads(b.decode('utf-8')),
            consumer_timeout_ms=1000,
        )
    except Exception as e:
        log.error(f"Failed to initialize Kafka consumer: {e}")
        return

    log.info(f"✓ Connected to Kafka, group_id='{GROUP_ID}'")

    batch = []
    last_flush = time.time()
    running = True
    def shutdown(sig, frame):
        nonlocal running
        log.info("Shutting down worker...")
        running = False
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while running:
        try:
            records = consumer.poll(timeout_ms=1000)

            for topic_partition, messages in records.items():
                for message in messages:
                    event = message.value
                    log.info(f"  Received: slug={event.get('slug')} ip={event.get('ip')}")

                    country = get_country(event.get('ip', ''))

                    batch.append({
                        'url_id':    event.get('url_id'),
                        'country':   country,
                        'timestamp': event.get('timestamp', int(time.time() * 1000)),
                    })

            now = time.time()
            should_flush = (
                len(batch) >= BATCH_SIZE or
                (batch and now - last_flush >= FLUSH_INTERVAL)
            )

            if should_flush:
                success = flush_batch(batch)

                if success:
                    try:
                        consumer.commit()
                        log.info(f"✓ Committed Kafka offset")
                    except CommitFailedError:
                        log.warning("Offset commit failed — will reprocess on restart")

                    batch = []
                    last_flush = now
                else:
                    log.error("Batch flush failed — keeping messages for retry")

        except Exception as e:
            log.error(f"Worker error: {e}")
            time.sleep(1)

    if batch:
        log.info(f"Flushing {len(batch)} remaining events before shutdown...")
        if flush_batch(batch):
            consumer.commit()

    consumer.close()
    log.info("Worker stopped.")


if __name__ == "__main__":
    run()