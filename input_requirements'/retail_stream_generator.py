"""
retail_stream_generator.py — Simulates a live POS terminal sending events to Azure Event Hubs.
Sends 1 order event per second. Press Ctrl+C to stop cleanly.

CREDENTIAL SETUP
─────────────────────────────────────────────────────────────────────────────────
Create a file called `.env` in the same directory as this script with:

    EH_CONNECTION_STRING=Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<YOUR_EH_SHARED_ACCESS_KEY>

OR export it as a shell environment variable before running:

    export EH_CONNECTION_STRING="Endpoint=sb://evhns-retail-stream..."
    python retail_stream_generator.py

Full credential reference:
    BOOTSTRAP_SERVERS : evhns-retail-stream.servicebus.windows.net:9093
    TOPIC_NAME        : retail-stream
    CONNECTION_STRING : (see .env / environment variable above — includes SharedAccessKey)

DEPENDENCIES
─────────────────────────────────────────────────────────────────────────────────
    pip install kafka-python python-dotenv
"""

import json
import os
import random
import sys
import time
from datetime import datetime

# ── Load .env file if present (local development) ─────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on environment variables only

from kafka import KafkaProducer
from kafka.errors import KafkaError

# =============================================================================
# CONFIGURATION — loaded from environment, never hardcoded
# =============================================================================
BOOTSTRAP_SERVERS = "evhns-retail-stream.servicebus.windows.net:9093"
TOPIC_NAME        = "retail-stream"

CONNECTION_STRING = os.environ.get("EH_CONNECTION_STRING")
if not CONNECTION_STRING:
    print(
        "ERROR: EH_CONNECTION_STRING environment variable is not set.\n"
        "Create a .env file or export the variable before running.\n"
        "See the module docstring for full instructions."
    )
    sys.exit(1)

# =============================================================================
# PRODUCER SETUP
# =============================================================================
print("Connecting to Event Hubs...")
producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    security_protocol="SASL_SSL",
    sasl_mechanism="PLAIN",
    sasl_plain_username="$ConnectionString",
    sasl_plain_password=CONNECTION_STRING,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    request_timeout_ms=30000,
    retries=3,
)
print("✅ Connected to Event Hubs namespace: evhns-retail-stream")

# =============================================================================
# SAMPLE DATA
# =============================================================================
products        = ["Laptop", "Mobile", "Tablet", "Headphones", "TV"]
cities          = ["Bangalore", "Delhi", "Mumbai", "Chennai", "Hyderabad"]
payment_methods = ["UPI", "Credit Card", "Debit Card"]


# =============================================================================
# EVENT GENERATOR
# =============================================================================
def generate_event(i: int) -> dict:
    price    = random.randint(1000, 50000)
    quantity = random.randint(1, 3)
    return {
        "order_id":       f"S{i:06d}",           # S = stream, avoids clash with batch O####
        "product":        random.choice(products),
        "price":          price,
        "quantity":       quantity,
        "total_amount":   price * quantity,
        "city":           random.choice(cities),
        "payment_method": random.choice(payment_methods),
        "event_time":     datetime.utcnow().isoformat(),
    }


# =============================================================================
# STREAM LOOP
# =============================================================================
def stream_data():
    print(f"Streaming started → topic: {TOPIC_NAME}   Press Ctrl+C to stop\n")
    i = 1
    try:
        while True:
            event = generate_event(i)
            future = producer.send(TOPIC_NAME, event)

            # Block until the message is acknowledged (or raises on error)
            try:
                future.get(timeout=10)
            except KafkaError as e:
                print(f"⚠️  Send failed for event {i}: {e}")

            print(f"[{i:05d}] Sent: {event}")
            i += 1
            time.sleep(1)  # 1 event/second — matches case study requirement

    except KeyboardInterrupt:
        print("\n\nCtrl+C received — flushing and closing producer...")
        producer.flush()
        producer.close()
        print(f"✅ Stream stopped cleanly after {i - 1} events.")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    stream_data()
