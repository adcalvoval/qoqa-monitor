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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("qoqa_monitor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH = BASE_DIR / "seen_offers.json"


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
    config = load_config()

    keywords: list[str] = config.get("keywords", [])
    urls: list[str] = config.get("qoqa_urls", ["https://www.qoqa.ch"])
    email_cfg: dict = config.get("email", {})

    if not keywords:
        logger.warning("No keywords configured in config.json — nothing to search for.")
        return

    logger.info(f"Keywords: {keywords}")

    offers = fetch_offers(urls)
    logger.info(f"Total unique offers fetched: {len(offers)}")

    matches = find_matching_offers(offers, keywords)
    logger.info(f"Keyword matches found: {len(matches)}")

    seen = load_seen()
    new_matches = get_new_matches(matches, seen) if matches else []

    if matches and not new_matches:
        logger.info("All matches already notified today — skipping email.")
        return

    logger.info(f"New matches to notify: {len(new_matches)}")

    sent = send_email(
        sender=email_cfg.get("sender", ""),
        app_password=email_cfg.get("app_password", ""),
        recipient=email_cfg.get("recipient", ""),
        matches=new_matches,
    )

    if sent and new_matches:
        seen = mark_as_seen(new_matches, seen)
        save_seen(seen)
        logger.info("Seen-offers file updated.")

    logger.info("=== Check complete ===")


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
    check_time: str = config.get("check_time", "08:00")

    logger.info(f"Scheduler started. Daily check at {check_time}.")
    logger.info("Press Ctrl+C to stop.")

    schedule.every().day.at(check_time).do(run_check)

    # Run once immediately on startup so you know it's working
    logger.info("Running initial check on startup...")
    run_check()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
