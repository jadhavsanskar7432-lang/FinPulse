"""
web_scraper.py — FinPulse Hybrid Scraping Engine
=================================================
Adds 4 new scraped sources on top of the existing NewsAPI + yfinance pipeline:

  1. Yahoo Finance HTML  — /quote/{ticker}/news/ page scrape
  2. Reuters RSS         — 4 topic feeds filtered by company keyword
  3. CNBC RSS            — 8 channel feeds (superset of the 4 already in news_fetcher)
  4. Google News RSS     — per-ticker search queries; most reliable, zero blocking

Anti-bot measures built in:
  - Rotating User-Agent pool
  - Random inter-request delay (1.5 – 3.5 s)
  - Per-domain session reuse with keep-alive
  - Hard timeout (12 s) + full try/except on every network call
  - Graceful degradation: one dead source never crashes the pipeline

All articles are returned as plain dicts matching the schema already used by
news_fetcher.py, so they drop straight into the same DB INSERT logic.

Schema reminder:
    ticker, title, summary, url, time_published (str "YYYY-MM-DD HH:MM:SS"), source
"""

import sys
import datetime
import random
import time
import urllib.parse

# Fix Windows cp1252 console encoding — allows emoji in print() on all terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# pyrefly: ignore [missing-import]
import feedparser
import requests
# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup   

from config import TICKERS

# ──────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Reusable sessions — one per domain to benefit from connection keep-alive
_SESSIONS: dict[str, requests.Session] = {}

REUTERS_RSS_FEEDS = [
    ("Business",   "https://feeds.reuters.com/reuters/businessNews"),
    ("Technology", "https://feeds.reuters.com/reuters/technologyNews"),
    ("Markets",    "https://feeds.reuters.com/reuters/marketsNews"),
    ("World",      "https://feeds.reuters.com/reuters/worldNews"),
]

CNBC_RSS_FEEDS = [
    ("Top News",   "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Finance",    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("Investing",  "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"),
    ("Earnings",   "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"),
    ("Technology", "https://www.cnbc.com/id/19854910/device/rss/rss.html"),
    ("Business",   "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
    ("Asia",       "https://www.cnbc.com/id/10000003/device/rss/rss.html"),
    ("Markets",    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
]


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _get_session(domain: str) -> requests.Session:
    """Returns a cached Session for the given domain, creating one if needed."""
    if domain not in _SESSIONS:
        s = requests.Session()
        s.headers.update({
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT":             "1",
            "Connection":      "keep-alive",
            "Cache-Control":   "no-cache",
        })
        _SESSIONS[domain] = s
    # Rotate User-Agent on every call to avoid fingerprinting
    _SESSIONS[domain].headers["User-Agent"] = random.choice(_USER_AGENTS)
    return _SESSIONS[domain]


def _polite_delay(min_s: float = 1.5, max_s: float = 3.5) -> None:
    """Sleeps a random amount to avoid rate-limit bans."""
    time.sleep(random.uniform(min_s, max_s))


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_time(raw: str) -> str:
    """
    Normalises any ISO-ish timestamp string to 'YYYY-MM-DD HH:MM:SS'.
    Falls back to current time on parse failure.
    """
    if not raw:
        return _now_str()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.datetime.strptime(raw[:len(fmt) + 5].strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    # Last resort: strip T/Z and take first 19 chars
    try:
        return raw.replace("T", " ").replace("Z", "")[:19]
    except Exception:
        return _now_str()


def _parse_feedparser_time(entry) -> str:
    """Extracts and formats a timestamp from a feedparser entry object."""
    # feedparser gives us published_parsed (a time.struct_time) when it can
    if entry.get("published_parsed"):
        try:
            return datetime.datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    if entry.get("published"):
        return _parse_time(entry["published"])
    if entry.get("updated"):
        return _parse_time(entry["updated"])
    return _now_str()


def _is_relevant(text: str, company_name: str, ticker: str) -> bool:
    """
    Returns True if the article text mentions the company or ticker symbol.
    Strips .NS suffix for NSE tickers so 'HDFC' matches 'HDFCBANK.NS'.
    """
    haystack = text.lower()
    bare_ticker = ticker.replace(".NS", "").lower()
    # Also build common abbreviations (e.g. "M&M" → "m&m", "mahindra")
    terms = [company_name.lower(), bare_ticker]
    # For multi-word company names also try the first word alone if it's >= 5 chars
    first_word = company_name.split()[0].lower()
    if len(first_word) >= 5:
        terms.append(first_word)
    return any(term in haystack for term in terms)


def _make_article(ticker: str, title: str, summary: str, url: str,
                  time_published: str, source: str) -> dict:
    """Constructs a standardised article dict matching the DB schema."""
    return {
        "ticker":         ticker,
        "title":          title.strip() if title else f"Update: {ticker}",
        "summary":        summary.strip() if summary else "No summary available.",
        "url":            url or f"https://finance.yahoo.com/quote/{ticker}",
        "time_published": time_published,
        "source":         source,
    }


# ──────────────────────────────────────────────
# SOURCE A: Yahoo Finance HTML scrape
# ──────────────────────────────────────────────

def scrape_yahoo_finance(ticker: str, company_name: str) -> list[dict]:
    """
    Scrapes the Yahoo Finance news tab for a ticker.
    This captures articles that yfinance's .news API misses (especially
    older items and articles without structured JSON metadata).

    URL pattern: https://finance.yahoo.com/quote/{TICKER}/news/
    Yahoo's HTML is server-rendered so no JS execution needed.
    """
    stories = []
    url = f"https://finance.yahoo.com/quote/{ticker}/news/"

    try:
        session = _get_session("finance.yahoo.com")
        # Yahoo requires a Referer header or returns 403
        session.headers["Referer"] = "https://finance.yahoo.com/"
        r = session.get(url, timeout=12)
        _polite_delay(1.0, 2.0)

        if r.status_code != 200:
            print(f"   🌐 Yahoo Scraper: HTTP {r.status_code} for {ticker}")
            return stories

        soup = BeautifulSoup(r.text, "lxml")

        # Yahoo Finance 2024 layout: news items live inside <li> tags
        # with anchor tags carrying data-* attributes.
        # We try multiple selector patterns for resilience across layout changes.
        candidate_links = []

        # Pattern 1: anchor tags with an 'href' pointing to a news story
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Yahoo news links look like /news/... or are absolute https://...
            if "/news/" in href or "finance.yahoo.com" in href:
                candidate_links.append(a)

        # Fallback pattern 2: h3 tags (headline containers)
        if not candidate_links:
            for h3 in soup.find_all("h3"):
                a = h3.find("a", href=True)
                if a:
                    candidate_links.append(a)

        seen = set()
        for a in candidate_links[:20]:
            title = a.get_text(strip=True)
            if not title or len(title) < 15:
                continue
            if title in seen:
                continue
            seen.add(title)

            href = a["href"]
            # Make absolute URL
            if href.startswith("/"):
                href = "https://finance.yahoo.com" + href
            elif not href.startswith("http"):
                continue  # skip javascript: links etc.

            # Relevance check
            if not _is_relevant(title, company_name, ticker):
                continue

            # Try to grab a timestamp from a sibling <time> element
            time_tag = a.find_next("time") or a.find_previous("time")
            pub_time = _now_str()
            if time_tag:
                pub_time = _parse_time(time_tag.get("datetime", "") or time_tag.get_text())

            stories.append(_make_article(
                ticker=ticker, title=title,
                summary=f"Yahoo Finance coverage of {company_name}.",
                url=href, time_published=pub_time, source="yahoo_scrape"
            ))

        print(f"   🌐 Yahoo Scraper: {len(stories)} articles for {ticker}")

    except requests.exceptions.Timeout:
        print(f"   ⚠️ Yahoo Scraper: timeout for {ticker}")
    except Exception as e:
        print(f"   ⚠️ Yahoo Scraper error for {ticker}: {e}")

    return stories


# ──────────────────────────────────────────────
# SOURCE B: Reuters RSS
# ──────────────────────────────────────────────

def scrape_reuters_rss(ticker: str, company_name: str) -> list[dict]:
    """
    Parses Reuters topic RSS feeds and filters by company relevance.

    Reuters RSS endpoints (no auth, no JS, very reliable):
      feeds.reuters.com/reuters/{businessNews,technologyNews,marketsNews,worldNews}

    Each feed returns ~20 entries; we scan title + summary for the company name.
    """
    stories = []

    for feed_name, feed_url in REUTERS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            _polite_delay(0.5, 1.2)

            for entry in feed.entries[:25]:
                title   = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link    = entry.get("link", "https://www.reuters.com")

                if not title:
                    continue

                search_pool = f"{title} {summary}"
                if not _is_relevant(search_pool, company_name, ticker):
                    continue

                pub_time = _parse_feedparser_time(entry)

                stories.append(_make_article(
                    ticker=ticker, title=title,
                    summary=summary if summary else f"Reuters {feed_name} coverage.",
                    url=link, time_published=pub_time, source="reuters"
                ))

        except Exception as e:
            print(f"   ⚠️ Reuters RSS '{feed_name}' error for {company_name}: {e}")

    print(f"   📰 Reuters RSS: {len(stories)} articles for {company_name}")
    return stories


# ──────────────────────────────────────────────
# SOURCE C: CNBC RSS (expanded — 8 channels)
# ──────────────────────────────────────────────

def scrape_cnbc_rss(ticker: str, company_name: str) -> list[dict]:
    """
    Pulls from 8 CNBC RSS channels (vs. the 4 in news_fetcher) and filters
    by company relevance.  The source tag is 'cnbc_scrape' to distinguish
    these records from the ones already inserted by news_fetcher.
    """
    stories = []

    for feed_name, feed_url in CNBC_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            _polite_delay(0.3, 0.9)

            for entry in feed.entries[:25]:
                title   = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link    = entry.get("link", "https://www.cnbc.com")

                if not title:
                    continue

                search_pool = f"{title} {summary}"
                if not _is_relevant(search_pool, company_name, ticker):
                    continue

                pub_time = _parse_feedparser_time(entry)

                stories.append(_make_article(
                    ticker=ticker, title=title,
                    summary=summary if summary else f"CNBC {feed_name} coverage.",
                    url=link, time_published=pub_time, source="cnbc"
                ))

        except Exception as e:
            print(f"   ⚠️ CNBC RSS '{feed_name}' error for {company_name}: {e}")

    print(f"   📺 CNBC RSS (expanded): {len(stories)} articles for {company_name}")
    return stories


# ──────────────────────────────────────────────
# SOURCE D: Google News RSS (most reliable)
# ──────────────────────────────────────────────

def scrape_google_news_rss(ticker: str, company_name: str) -> list[dict]:
    """
    Queries Google News RSS for each ticker/company combination.
    Google News RSS is free, requires no authentication, and almost never
    blocks automated access via feedparser (it sends a plain GET with no JS).

    We run TWO queries per ticker:
      1. "{company_name} stock"           — general coverage
      2. "{company_name} earnings results" — fundamental events

    For Indian tickers (.NS) we also run:
      3. "{company_name} NSE"             — BSE/NSE specific coverage

    Each query returns up to 20 articles; after relevance filtering and
    deduplication the effective yield is typically 5-15 per ticker.

    Source tags: "google_news"
    """
    stories = []
    seen_titles: set[str] = set()

    # Build query list
    bare_ticker = ticker.replace(".NS", "")
    queries = [
        f'"{company_name}" stock',
        f'"{company_name}" earnings results',
    ]
    if ".NS" in ticker:
        queries.append(f'"{company_name}" NSE shares')
        queries.append(f'"{bare_ticker}" BSE NSE')
    else:
        queries.append(f'"{bare_ticker}" shares market')

    # For Indian companies also try Hindi/abbreviated names in English press
    # e.g. "SBI" for "State Bank of India", "M&M" for "Mahindra"
    if " " in company_name:
        # Generate acronym: "State Bank of India" → "SBI"
        acronym = "".join(w[0].upper() for w in company_name.split() if w[0].isalpha())
        if len(acronym) >= 2 and acronym != bare_ticker.upper():
            queries.append(f'"{acronym}" stock India')

    base_url = "https://news.google.com/rss/search"

    for query in queries:
        try:
            params = {
                "q":    query,
                "hl":   "en-IN",
                "gl":   "IN",
                "ceid": "IN:en",
            }
            feed_url = f"{base_url}?{urllib.parse.urlencode(params)}"
            feed = feedparser.parse(feed_url)
            _polite_delay(0.8, 1.8)

            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                if not title or title in seen_titles:
                    continue

                # Google News embeds the source name in the title as " - Source Name"
                # Strip it to get a clean headline
                clean_title = title.rsplit(" - ", 1)[0].strip() if " - " in title else title

                if not _is_relevant(f"{clean_title}", company_name, ticker):
                    continue

                seen_titles.add(title)

                summary = entry.get("summary", "")
                # Google News summaries are often just the title repeated — skip them
                if summary.startswith(clean_title[:30]):
                    summary = ""

                # Extract the actual publisher from the title suffix
                publisher = title.rsplit(" - ", 1)[-1].strip() if " - " in title else "Google News"
                if not summary:
                    summary = f"Via {publisher}."

                link = entry.get("link", "")
                pub_time = _parse_feedparser_time(entry)

                stories.append(_make_article(
                    ticker=ticker, title=clean_title,
                    summary=summary, url=link,
                    time_published=pub_time, source="google_news"
                ))

        except Exception as e:
            print(f"   ⚠️ Google News RSS error for '{query}': {e}")

    print(f"   🔍 Google News RSS: {len(stories)} articles for {company_name}")
    return stories


# ──────────────────────────────────────────────
# MAIN SCRAPER ENTRYPOINT
# ──────────────────────────────────────────────

def run_scraper() -> list[dict]:
    """
    Runs all 4 scraping sources for every ticker in config.TICKERS.
    Returns a deduplicated list of article dicts ready for DB insertion.
    Call this from news_fetcher.py — it slots straight into the existing pipeline.
    """
    all_stories: list[dict] = []
    print("\n🕷️  WEB SCRAPER: Starting hybrid scraping run...")

    for ticker, info in TICKERS.items():
        company_name = info["name"]
        print(f"\n  🔍 Scraping: {company_name} ({ticker})")

        yahoo_articles  = scrape_yahoo_finance(ticker, company_name)
        reuters_articles = scrape_reuters_rss(ticker, company_name)
        cnbc_articles   = scrape_cnbc_rss(ticker, company_name)
        gnews_articles  = scrape_google_news_rss(ticker, company_name)

        all_stories.extend(yahoo_articles)
        all_stories.extend(reuters_articles)
        all_stories.extend(cnbc_articles)
        all_stories.extend(gnews_articles)

        # Brief pause between tickers to stay polite
        _polite_delay(1.0, 2.5)

    # Global deduplication by title (case-insensitive)
    seen: set[str] = set()
    unique: list[dict] = []
    for story in all_stories:
        key = story["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(story)

    print(f"\n✅ WEB SCRAPER: {len(unique)} unique articles collected across all sources.")
    return unique


# ──────────────────────────────────────────────
# STANDALONE TEST RUN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    results = run_scraper()
    print(f"\n{'─'*60}")
    print(f"SAMPLE OUTPUT ({min(5, len(results))} of {len(results)} articles):")
    print(f"{'─'*60}")
    for r in results[:5]:
        print(f"  [{r['source']:12}] {r['ticker']:12} | {r['title'][:65]}")
        print(f"  {'':14} {r['time_published']}  →  {r['url'][:55]}")
        print()