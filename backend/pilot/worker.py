"""Run with python -m pilot.worker; --once performs one bounded polling pass."""
import argparse
import logging
import os
import secrets
import time

from database import SessionLocal
from pilot.delivery import claim_events, deliver_one


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    worker_id = secrets.token_hex(16)
    logger = logging.getLogger("matchsho.worker")
    logging.basicConfig(level=logging.INFO)
    if os.getenv("NO_OUTBOUND_EMAIL", "false").lower() == "true":
        raise SystemExit("Outbound delivery is disabled for this environment")
    last_maintenance = 0.0
    while True:
        try:
            if time.monotonic() - last_maintenance >= 60:
                from pilot.maintenance import maintenance
                with SessionLocal() as db:
                    counts = maintenance(db)
                    db.commit()
                logger.info("maintenance_completed counts=%s", counts)
                last_maintenance = time.monotonic()
            # One event per claim keeps the lease ahead of SMTP's bounded timeout.
            for event_id in claim_events(worker_id, limit=1):
                status = deliver_one(event_id, worker_id)
                logger.info("delivery event=%s status=%s", event_id, status)
        except Exception as exc:
            # Never log exception text: SMTP providers may echo credentials or addresses.
            logger.error("worker_iteration_failed error_type=%s", type(exc).__name__)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
