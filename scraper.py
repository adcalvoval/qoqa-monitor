import logging
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

QOQA_BASE = "https://www.qoqa.ch"


def fetch_offers(urls: list[str]) -> list[dict]:
    """
    Render qoqa.ch with a real browser (Playwright/Chromium) and extract all
    visible offer cards. Returns a deduplicated list of offer dicts.
    """
    all_offers = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for url in urls:
            try:
                logger.info(f"Fetching (browser): {url}")
                page.goto(url, wait_until="load", timeout=30000)
                # Wait for at least one offer card link to appear in the DOM
                try:
                    page.wait_for_selector(
                        "a[href*='/offers/']", timeout=15000
                    )
                except PWTimeout:
                    logger.warning(f"Offer cards did not appear within 15s at {url}")
                html = page.content()
                offers = parse_offers(html, url)
                all_offers.extend(offers)
                logger.info(f"Found {len(offers)} offer(s) at {url}")
            except PWTimeout:
                logger.error(f"Timeout loading {url}")
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {e}")

        browser.close()

    # Deduplicate by offer URL
    seen_urls = set()
    unique_offers = []
    for offer in all_offers:
        if offer["url"] not in seen_urls:
            seen_urls.add(offer["url"])
            unique_offers.append(offer)

    return unique_offers


def parse_offers(html: str, source_url: str) -> list[dict]:
    """
    Parse the rendered qoqa.ch HTML and extract individual offer cards.

    qoqa.ch offer cards are anchor tags whose href matches /fr/offers/<id>
    or /de/offers/<id>. Each card contains the brand, title, price, category
    and stock info as visible text.
    """
    soup = BeautifulSoup(html, "lxml")

    # Find all offer links: /fr/offers/12345 or /de/offers/12345
    offer_links = soup.find_all("a", href=re.compile(r"/?(?:fr|de)/offers/\d+"))

    offers = []
    seen_hrefs = set()

    for link in offer_links:
        href = link.get("href", "")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        full_url = QOQA_BASE + "/" + href.lstrip("/") if not href.startswith("http") else href
        raw_text = link.get_text(separator=" ", strip=True)

        if not raw_text:
            continue

        # First non-empty line is usually the brand; second is the title
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        # Fallback: split by multiple spaces
        if len(lines) <= 1:
            lines = [p.strip() for p in re.split(r"\s{2,}", raw_text) if p.strip()]

        brand = lines[0] if lines else ""
        title = lines[1] if len(lines) > 1 else brand

        offers.append({
            "title": f"{brand} — {title}" if brand != title else title,
            "description": raw_text,
            "url": full_url,
            "raw_text": raw_text,
            "source": source_url,
        })

    if not offers:
        logger.warning("No offer cards found — site structure may have changed.")

    return offers


def find_matching_offers(offers: list[dict], keywords: list[str]) -> list[dict]:
    """
    Return offers whose text contains at least one keyword (case-insensitive).
    Adds a 'matched_keywords' field to each returned offer.
    """
    keywords_lower = [kw.lower() for kw in keywords]
    matches = []

    for offer in offers:
        text = offer["raw_text"].lower()
        matched = [kw for kw in keywords_lower if kw in text]
        if matched:
            offer_copy = dict(offer)
            offer_copy["matched_keywords"] = matched
            matches.append(offer_copy)

    return matches
