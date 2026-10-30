"""
QoQa Monitor — daily scraper for www.qoqa.ch
Checks for keyword matches in offers and sends a Gmail notification.

Usage:
    python main.py              # runs the scheduler (checks daily at time set in config.json)
    python main.py --now        # run a single check immediately (useful for testing)
"""

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import schedule
import time

from scraper import fetch_offers, find_matching_offers
from notifier import send_email

# ── Logging setup ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
LOG_PATH = BASE_DIR / "qoqa_monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH = BASE_DIR / "seen_offers.json"


def _flush_logs() -> None:
    """Flush all logging handlers to ensure logs are written to disk."""
    for handler in logging.root.handlers:
        handler.flush()


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.error(f"config.json not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Seen-offers tracking (avoid duplicate emails) ─────────────────────────────

def load_seen() -> dict:
    """Load the set of offer titles already notified, keyed by date."""
    if SEEN_PATH.exists():
        with open(SEEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen: dict) -> None:
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


def get_new_matches(matches: list[dict], seen: dict) -> list[dict]:
    """Filter out matches we've already sent an email about today."""
    today = str(date.today())
    today_seen = set(seen.get(today, []))
    new = [m for m in matches if m["title"] not in today_seen]
    return new


def mark_as_seen(matches: list[dict], seen: dict) -> dict:
    today = str(date.today())
    today_seen = set(seen.get(today, []))
    today_seen.update(m["title"] for m in matches)
    seen[today] = list(today_seen)
    # Keep only the last 7 days to avoid the file growing forever
    cutoff = sorted(seen.keys())[-7:]
    return {k: seen[k] for k in cutoff}


# ── Core check logic ──────────────────────────────────────────────────────────

def run_check() -> None:
    logger.info("=== Starting QoQa check ===")
    errors: list[str] = []

    try:
        config = load_config()

        keywords: list[str] = config.get("keywords", [])
        urls: list[str] = config.get("qoqa_urls", ["https://www.qoqa.ch"])

        # Get email credentials from environment variables
        sender = os.getenv("QOQA_EMAIL_SENDER")
        app_password = os.getenv("QOQA_EMAIL_PASSWORD")
        recipient = os.getenv("QOQA_EMAIL_RECIPIENT")

        if not keywords:
            logger.warning("No keywords configured in config.json — nothing to search for.")
            logger.info("=== Check SUCCEEDED ===")
            _flush_logs()
            return

        if not sender or not app_password or not recipient:
            logger.error("Missing email credentials. Set QOQA_EMAIL_SENDER, QOQA_EMAIL_PASSWORD, and QOQA_EMAIL_RECIPIENT environment variables.")
            sys.exit(1)

        logger.info(f"Keywords: {keywords}")

        offers = fetch_offers(urls)
        logger.info(f"Total unique offers fetched: {len(offers)}")

        matches = find_matching_offers(offers, keywords)
        logger.info(f"Keyword matches found: {len(matches)}")

        seen = load_seen()
        new_matches = get_new_matches(matches, seen) if matches else []

        if matches and not new_matches:
            logger.info("All matches already notified today — skipping email.")
            logger.info("=== Check SUCCEEDED ===")
            _flush_logs()
            return

        logger.info(f"New matches to notify: {len(new_matches)}")

        sent = send_email(
            sender=sender,
            app_password=app_password,
            recipient=recipient,
            matches=new_matches,
        )

        if not sent:
            errors.append("email notification failed")

        if sent and new_matches:
            seen = mark_as_seen(new_matches, seen)
            save_seen(seen)
            logger.info("Seen-offers file updated.")

    except Exception as e:
        errors.append(f"unexpected error: {e}")
        logger.exception("Unexpected error during check")

    if errors:
        logger.error(f"=== Check FAILED: {'; '.join(errors)} ===")
    else:
        logger.info("=== Check SUCCEEDED ===")

    _flush_logs()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="QoQa Monitor")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run a single check immediately instead of waiting for the scheduled time",
    )
    args = parser.parse_args()

    if args.now:
        run_check()
        return

    config = load_config()
    check_times = config.get("check_times", config.get("check_time", "10:00"))
    if isinstance(check_times, str):
        check_times = [check_times]

    logger.info(f"Scheduler started. Daily checks at {', '.join(check_times)}.")
    logger.info("Press Ctrl+C to stop.")

    for check_time in check_times:
        schedule.every().day.at(check_time).do(run_check)

    # Run once immediately on startup so you know it's working
    logger.info("Running initial check on startup...")
    run_check()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
