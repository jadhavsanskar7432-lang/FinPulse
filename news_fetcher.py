"""
news_fetcher.py — FinPulse Hybrid Ingestion Pipeline
=====================================================
SOURCES (9 total, hybrid API + scrape):
  API layer:
    1. NewsAPI       — Reuters, Bloomberg, WSJ, MarketWatch, FT, etc.
                       Paginated (up to 3 pages x 100), configurable date range.
    2. yfinance      — Yahoo Finance per-ticker .news (up to 50). RSS fallback on 404.
    3. GDELT         — Free, no API key, supports 3+ months of history.
                       Disk-cached (6hr TTL) to avoid 429s. Exponential backoff.
    4. Finnhub       — Free tier, /company-news with full date range support.
    5. MediaStack    — Free 500 req/month, good financial coverage.

  Scrape layer (via web_scraper.py):
    6. Yahoo Finance — HTML scrape of /quote/{ticker}/news/
    7. Reuters RSS   — 4 topic feeds, keyword-filtered
    8. CNBC RSS      — 8 channel feeds, keyword-filtered
    9. Google News   — per-ticker RSS search queries

NORMALIZATION:
  All articles pass through normalize_all() before DB insertion:
    - Timestamp coercion  (all formats -> "YYYY-MM-DD HH:MM:SS")
    - Junk title filtering ("[Removed]", source-name-only, too-short, etc.)
    - HTML entity decoding & encoding cleanup
    - Relevance check     (title/summary/URL must mention ticker or company)
    - URL fingerprint dedup (catches same story from multiple sources)
    - Title-based dedup   (fallback for articles without stable URLs)

RATE LIMIT HANDLING:
  - 2-second sleep between tickers to avoid burst throttling
  - GDELT responses cached to /tmp for 6 hours (no re-fetch for same ticker+window)
  - GDELT exponential backoff on 429: 5s -> 10s -> 20s -> give up
  - MediaStack and Finnhub have generous free limits; no special handling needed

SCHEDULING:
  Runs automatically every 15 minutes using APScheduler (BlockingScheduler).
  Each run: fetch -> scrape -> normalize -> deduplicate -> DB upsert -> sentiment_analyzer.py

MODES:
  python news_fetcher.py              <- run once then start 15-min schedule
  python news_fetcher.py --once       <- single live run, then exit
  python news_fetcher.py --backfill   <- one-time 90-day historical fetch

SETUP (.env keys):
  NEWS_API_KEY       (NewsAPI      -- required for source 1)
  FINNHUB_API_KEY    (Finnhub      -- optional, adds source 4)
  MEDIASTACK_API_KEY (MediaStack   -- optional, adds source 5)
"""

# ══════════════════════════════════════════════
# IMPORTS
# ══════════════════════════════════════════════

import hashlib
import html as html_module
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from urllib.parse import urlparse

# Fix Windows cp1252 console encoding — allows emoji in print() on all terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# pyrefly: ignore [missing-import]
import feedparser   
import requests
# pyrefly: ignore [missing-import]
import yfinance as yf
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database
from config import TICKERS, ALL_TICKER_SYMBOLS
from web_scraper import run_scraper


# ══════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════

load_dotenv()

print("INGESTION FEED: Initializing Hybrid Multi-Source Pipeline...")

NEWS_API_KEY      = os.getenv("NEWS_API_KEY")
FINNHUB_KEY       = os.getenv("FINNHUB_API_KEY")
MEDIASTACK_KEY    = os.getenv("MEDIASTACK_API_KEY")
POLYGON_KEY       = os.getenv("POLYGON_API_KEY")

if not NEWS_API_KEY:
    print("WARNING: NEWS_API_KEY missing from .env -- NewsAPI source will be skipped.")
if not FINNHUB_KEY:
    print("WARNING: FINNHUB_API_KEY missing from .env -- Finnhub source will be skipped.")
if not MEDIASTACK_KEY:
    print("WARNING: MEDIASTACK_API_KEY missing from .env -- MediaStack source will be skipped.")
if not POLYGON_KEY:
    print("WARNING: POLYGON_API_KEY missing from .env -- Polygon.io source will be skipped.")

# Delay between tickers to avoid burst rate-limiting across all sources
INTER_TICKER_DELAY = 2   # seconds

# GDELT disk cache TTL
GDELT_CACHE_TTL = 6 * 3600   # 6 hours in seconds


# ══════════════════════════════════════════════
# NORMALIZER
# ══════════════════════════════════════════════

JUNK_PATTERNS = [
    r'^\[removed\]$',
    r'^$',
    r'^null$',
    r'^none$',
    r'^\s*$',
    r'^https?://',
    r'^(cnbc|reuters|bloomberg|yahoo finance|marketwatch|google news)\s*$',
]
JUNK_RE = re.compile('|'.join(JUNK_PATTERNS), re.IGNORECASE)

MIN_TITLE_WORDS = 4
MAX_TITLE_LEN   = 500
MAX_SUMMARY_LEN = 2000

TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y%m%dT%H%M%SZ",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S GMT",
    "%Y-%m-%d",
]


def _parse_timestamp(raw) -> str:
    """Coerce any timestamp format -> 'YYYY-MM-DD HH:MM:SS' UTC. Falls back to now()."""
    if raw is None:
        return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(raw, (int, float)):
        try:
            return datetime.datetime.utcfromtimestamp(raw).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    raw = str(raw).strip()

    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    # Last resort: strip T/Z and truncate
    cleaned = raw.replace("T", " ").replace("Z", "")[:19]
    try:
        datetime.datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
        return cleaned
    except ValueError:
        return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _clean_text(text: str, max_len: int) -> str:
    """Decode HTML entities, fix mangled UTF-8, strip trailing source attributions."""
    if not text:
        return ""

    # Decode HTML entities: &amp; -> &, &#39; -> ', etc.
    text = html_module.unescape(text)

    # Fix mangled UTF-8 (RSS feeds decoded as latin-1 instead of UTF-8)
    try:
        text = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass  # already valid UTF-8

    # Strip trailing " - SourceName" attribution
    text = re.sub(
        r'\s*[-]\s*(Reuters|Bloomberg|CNBC|AP|AFP|MarketWatch)$', '', text
    )
    # Strip NewsAPI truncation artifact "[+1234 chars]"
    text = re.sub(r'\s*\[\+\d+ chars?\]$', '', text)
    # Strip trailing ellipsis
    text = re.sub(r'\s*\.\.\.$', '', text).strip()
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text[:max_len]


def _url_fingerprint(url: str) -> str:
    """MD5 of canonical URL (no query string/fragment) for cross-source dedup."""
    if not url:
        return ""
    try:
        parsed    = urlparse(url.lower().strip())
        canonical = f"{parsed.netloc}{parsed.path}".rstrip("/")
        return hashlib.md5(canonical.encode()).hexdigest()
    except Exception:
        return hashlib.md5(url.encode()).hexdigest()


# Tickers whose bare symbol/company_name collides with common English words,
# place names, unrelated people's names, or other entities. For these, a bare
# ticker or company_name match is NOT enough — we additionally require the
# ticker word to co-occur with finance/business context, since company_name
# in config is often just the bare word (e.g. "Trent") with no disambiguating
# suffix like "Ltd". Add to this dict as new false-positive collisions turn up.
AMBIGUOUS_TICKER_CONTEXT = {
    "trent": [
        # generic finance/market vocabulary
        "share", "shares", "stock", "stocks", "nse", "bse", "revenue",
        "profit", "dividend", "bonus", "quarter", "q1", "q2", "q3", "q4",
        "results", "earnings", "ipo", "pat", "ebitda", "market cap",
        "brokerage", "target price", "price target", "52-week", "52 week", "ex-dividend",
        "ex-bonus", "ltd", "limited", "sensex", "nifty",
        # Trent Ltd's own retail brands / parent group — near-zero false
        # positive risk since unrelated "Trent" mentions never include these
        "zudio", "westside", "tata group", "noel tata", "growth", "retailer", "apparel",
    ],
    "abb": ["share", "shares", "stock", "nse", "bse", "revenue", "profit",
            "dividend", "quarter", "results", "earnings", "ltd", "limited",
            "india", "target price", "price target", "index", "buy call",
            "sell call", "buy rating", "sell rating", "upgrade", "downgrade",
            "bullish", "bearish", "brokerage", "partnership"],
}
AMBIGUOUS_TICKERS = set(AMBIGUOUS_TICKER_CONTEXT.keys())
EXCLUSION_KEYWORDS = {
    "m&m": ["m&m's", "m&ms candy"],
}


# Brand names that are distinctive enough (long, unambiguous) that matching them
# as a prefix — even with a foreign-language suffix glued on, e.g. "Microsofttan",
# "Microsoftov", "Nvidiaya" — carries negligible false-positive risk.
SUFFIX_TOLERANT_BRANDS = {"microsoft", "nvidia"}

def _word_in_text(word: str, text: str) -> bool:
    """Whole-word (word-boundary) match — avoids matching substrings inside other words.
    For a curated set of distinctive brand names, also matches when a foreign-language
    suffix is glued directly onto the brand with no space (e.g. "Microsofttan")."""
    if not word:
        return False
    if re.search(r'\b' + re.escape(word) + r'\b', text) is not None:
        return True
    if word.lower() in SUFFIX_TOLERANT_BRANDS:
        return re.search(r'\b' + re.escape(word) + r'[a-zA-ZğüşıöçĞÜŞİÖÇ]*\b', text) is not None
    return False
def _is_relevant(story: dict) -> bool:
    """
    Returns True if the article actually relates to the ticker/company.
    Checks title, summary, AND URL to catch articles where the ticker
    appears in the URL but not the body (common with Yahoo/Finnhub).

    Uses word-boundary matching (not bare substring) to avoid partial-word
    false positives. For tickers in AMBIGUOUS_TICKER_CONTEXT (short/common
    symbols like "TRENT" that collide with unrelated nouns, place names, or
    people's names), a bare ticker/company_name match is not trusted alone —
    the ticker word must additionally co-occur with finance/business context
    (e.g. "shares", "revenue", "Q4 results") or one of the company's known
    brand names. This is necessary because company_name in config is often
    just the bare word (e.g. "Trent") with no disambiguating suffix, so it
    can't be used as a standalone discriminator for these tickers.

    Additionally, for tickers in EXCLUSION_KEYWORDS, a hard override drops
    the story if an unrelated-brand phrase is present (e.g. "M&M's" the
    candy vs. "M&M" the stock ticker), regardless of any other context.
    """
    raw_ticker  = story.get("ticker", "").replace(".NS", "").replace(".BO", "").lower()
    company     = story.get("company_name", "").lower().strip()
    search_pool = (
        f"{story.get('title', '')} {story.get('summary', '')}".lower()
    )
    url = story.get("url", "").lower()

    # Hard override: unrelated brand/entity collision. Checked before anything
    # else — a story matching an exclusion phrase is dropped regardless of
    # what else it contains.
    if raw_ticker in EXCLUSION_KEYWORDS:
        if any(phrase in search_pool for phrase in EXCLUSION_KEYWORDS[raw_ticker]):
            return False

    ticker_matches_text  = _word_in_text(raw_ticker, search_pool)
    company_matches_text = bool(company) and _word_in_text(company, search_pool)
    ticker_matches_url   = _word_in_text(raw_ticker, url)

    if raw_ticker in AMBIGUOUS_TICKERS:
        base_mentioned = ticker_matches_text or company_matches_text or ticker_matches_url
        if not base_mentioned:
            return False
        context_words = AMBIGUOUS_TICKER_CONTEXT[raw_ticker]
        return any(_word_in_text(kw, search_pool) for kw in context_words)

    return ticker_matches_text or company_matches_text or ticker_matches_url

def _normalize_one(story: dict) -> dict | None:
    """
    Normalize a single raw story dict.
    Returns a clean dict ready for DB insertion, or None if it should be dropped.
    """
    title   = _clean_text(story.get("title",   ""), MAX_TITLE_LEN)
    summary = _clean_text(story.get("summary", ""), MAX_SUMMARY_LEN)

    if not title or JUNK_RE.match(title):
        return None
    if len(title.split()) < MIN_TITLE_WORDS:
        return None
    if not _is_relevant({**story, "title": title, "summary": summary}):
        return None

    return {
        "ticker":          story.get("ticker", ""),
        "title":           title,
        "summary":         summary or "No summary available.",
        "url":             story.get("url", ""),
        "time_published":  _parse_timestamp(story.get("time_published")),
        "source":          story.get("source", "unknown"),
        "url_fingerprint": _url_fingerprint(story.get("url", "")),
    }


def normalize_all(stories: list[dict]) -> list[dict]:
    """
    Normalize + deduplicate an entire batch of raw story dicts.
    Dedup priority: URL fingerprint first, title-key fallback.
    """
    cleaned     = []
    seen_urls   = set()
    seen_titles = set()

    for raw in stories:
        result = _normalize_one(raw)
        if result is None:
            continue

        fp = result["url_fingerprint"]
        if fp:
            if fp in seen_urls:
                continue
            seen_urls.add(fp)

        title_key = result["title"].lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        cleaned.append(result)

    return cleaned


# ══════════════════════════════════════════════
# SOURCE 1: NewsAPI — paginated, configurable date window
# ══════════════════════════════════════════════

def fetch_from_newsapi(ticker: str, company_name: str, days_back: int = 2) -> list[dict]:
    """
    Fetches from NewsAPI with pagination (up to 3 pages x 100 results).

    Auto-detects Indian stocks (.NS / .BO suffix) and:
      - Switches domains to Indian financial sites (ET, Moneycontrol, Mint, etc.)
      - Removes the US-centric keyword filter since Indian headlines don't
        reliably use words like "stock/shares/earnings"
      - Runs two queries: company name + short ticker symbol separately,
        because Indian outlets use both (e.g. "Reliance Industries" AND "RELIANCE")
    """
    stories = []
    if not NEWS_API_KEY:
        return stories

    is_indian    = ticker.endswith(".NS") or ticker.endswith(".BO")
    short_ticker = ticker.replace(".NS", "").replace(".BO", "")

    # Indian sites actually index NSE/BSE stocks well
    indian_domains = (
        "economictimes.indiatimes.com,moneycontrol.com,livemint.com,"
        "business-standard.com,businesstoday.in,financialexpress.com,"
        "ndtvprofit.com,zeebiz.com,thehindubusinessline.com,"
        "reuters.com,bloomberg.com"
    )
    global_domains = (
        "finance.yahoo.com,reuters.com,cnbc.com,marketwatch.com,"
        "bloomberg.com,seekingalpha.com,fool.com,investors.com,"
        "wsj.com,ft.com,economictimes.indiatimes.com,moneycontrol.com,livemint.com"
    )

    domains = indian_domains if is_indian else global_domains

    # For Indian stocks: two separate simple queries work much better than
    # one complex query with AND/OR + keyword filters
    if is_indian:
        queries = [
            f'"{company_name}"',
            f'"{short_ticker}"',
        ]
    else:
        queries = [
            f'("{company_name}" OR "{short_ticker}")'
            f' AND (stock OR shares OR earnings OR revenue OR market)'
        ]

    try:
        to_date   = datetime.datetime.now()
        from_date = to_date - datetime.timedelta(days=days_back)

        for raw_query in queries:
            encoded_query = urllib.parse.quote(raw_query)

            for page in range(1, 4):   # pages 1-3, 100 results each
                url = (
                    f"https://newsapi.org/v2/everything"
                    f"?q={encoded_query}"
                    f"&domains={domains}"
                    f"&language=en"
                    f"&from={from_date.strftime('%Y-%m-%d')}"
                    f"&to={to_date.strftime('%Y-%m-%d')}"
                    f"&sortBy=publishedAt"
                    f"&pageSize=100"
                    f"&page={page}"
                    f"&apiKey={NEWS_API_KEY}"
                )

                response  = requests.get(url, timeout=10)
                news_data = response.json()

                if news_data.get("status") != "ok":
                    err_msg = news_data.get("message", "unknown error")
                    print(f"   WARNING: NewsAPI [{company_name}]: {err_msg}")
                    break

                batch = news_data.get("articles", [])
                if not batch:
                    break

                for article in batch:
                    title   = article.get("title",       "")
                    summary = article.get("description", "")
                    if not title:
                        continue

                    raw_time   = article.get("publishedAt", datetime.datetime.now().isoformat())
                    clean_time = raw_time.replace("T", " ").replace("Z", "")[:19]

                    stories.append({
                        "ticker":         ticker,
                        "company_name":   company_name,
                        "title":          title,
                        "summary":        summary or "No summary provided by publisher.",
                        "url":            article.get("url", f"https://finance.yahoo.com/quote/{ticker}"),
                        "time_published": clean_time,
                        "source":         "newsapi",
                    })

                total_results = news_data.get("totalResults", 0)
                if len(stories) >= total_results:
                    break   # no more pages

        print(f"   [NewsAPI]     {len(stories):>4} articles for {company_name} (last {days_back}d)")

    except Exception as e:
        print(f"   WARNING: NewsAPI error for {company_name}: {e}")

    return stories


# ══════════════════════════════════════════════
# SOURCE 2: yfinance — with RSS fallback on 404
# ══════════════════════════════════════════════

def fetch_from_yahoo(ticker: str, company_name: str) -> list[dict]:
    """
    Fetches per-ticker news using yfinance .news (up to 50 items).
    Yahoo frequently returns 404/changes its API -- automatically falls
    back to Yahoo Finance RSS feed if yfinance fails.
    """
    stories = []

    # Attempt 1: yfinance .news property
    try:
        stock      = yf.Ticker(ticker)
        news_items = stock.news or []

        for item in news_items[:50]:
            content  = item.get("content", {})
            title    = content.get("title", "")
            pub_date = content.get("pubDate", "")

            if not title:
                continue

            clean_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if pub_date:
                try:
                    parsed     = datetime.datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ")
                    clean_time = parsed.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    clean_time = pub_date.replace("T", " ").replace("Z", "")[:19]

            url = ""
            click_through = content.get("clickThroughUrl", {})
            if isinstance(click_through, dict):
                url = click_through.get("url", "")
            elif isinstance(click_through, str):
                url = click_through
            if not url:
                canonical = content.get("canonicalUrl", {})
                if isinstance(canonical, dict):
                    url = canonical.get("url", "")
                elif isinstance(canonical, str):
                    url = canonical
            if not url:
                url = f"https://finance.yahoo.com/quote/{ticker}"

            provider      = content.get("provider", {})
            provider_name = (
                provider.get("displayName", "Yahoo Finance")
                if isinstance(provider, dict) else "Yahoo Finance"
            )
            summary = content.get("summary", f"Via {provider_name}")

            stories.append({
                "ticker":         ticker,
                "company_name":   company_name,
                "title":          title,
                "summary":        summary or f"Financial update via {provider_name}",
                "url":            url,
                "time_published": clean_time,
                "source":         "yahoo",
            })

        if stories:
            print(f"   [Yahoo API]   {len(stories):>4} articles for {ticker}")
            return stories

    except Exception as e:
        print(f"   WARNING: Yahoo API error for {ticker} (trying RSS fallback): {e}")

    # Attempt 2: Yahoo Finance RSS fallback
    try:
        short   = ticker.replace(".NS", "").replace(".BO", "")
        rss_url = (
            f"https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={short}&region=US&lang=en-US"
        )
        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:30]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            try:
                clean_time = datetime.datetime(
                    *entry.published_parsed[:6]
                ).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                clean_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            stories.append({
                "ticker":         ticker,
                "company_name":   company_name,
                "title":          title,
                "summary":        entry.get("summary", "Via Yahoo Finance RSS"),
                "url":            entry.get("link", f"https://finance.yahoo.com/quote/{short}"),
                "time_published": clean_time,
                "source":         "yahoo",
            })

        print(f"   [Yahoo RSS]   {len(stories):>4} articles for {ticker} (RSS fallback)")

    except Exception as e:
        print(f"   WARNING: Yahoo RSS fallback also failed for {ticker}: {e}")

    return stories


# ══════════════════════════════════════════════

# ══════════════════════════════════════════════
# SOURCE: Polygon.io — 2 years history, paginated, reliable
# ══════════════════════════════════════════════

def fetch_from_polygon(ticker: str, company_name: str, days_back: int = 7) -> list[dict]:
    """
    Polygon.io /v2/reference/news endpoint.
    Free tier: unlimited requests, 2 years of history, 1000 articles per call.
    Sign up free at https://polygon.io/ -- no credit card needed.

    This is the most reliable high-volume source in the pipeline.
    Automatically handles pagination to pull all available articles.
    Works for both US (MSFT, AAPL) and Indian stocks (use NSE symbol without .NS).
    """
    stories = []
    if not POLYGON_KEY:
        return stories

    short_ticker = ticker.replace(".NS", "").replace(".BO", "")
    end_date     = datetime.date.today()
    start_date   = end_date - datetime.timedelta(days=days_back)

    try:
        next_url = (
            f"https://api.polygon.io/v2/reference/news"
            f"?ticker={short_ticker}"
            f"&published_utc.gte={start_date}"
            f"&published_utc.lte={end_date}"
            f"&order=desc"
            f"&limit=1000"
            f"&apiKey={POLYGON_KEY}"
        )

        page_count = 0
        max_pages  = 5   # up to 5000 articles per ticker per run

        while next_url and page_count < max_pages:
            resp = requests.get(next_url, timeout=20)

            if resp.status_code == 429:
                print(f"   WARNING: Polygon rate-limit for {ticker} -- waiting 60s")
                time.sleep(60)
                resp = requests.get(next_url, timeout=20)

            if resp.status_code != 200:
                print(f"   WARNING: Polygon HTTP {resp.status_code} for {ticker}")
                break

            data     = resp.json()
            articles = data.get("results", [])

            for art in articles:
                title   = (art.get("title") or "").strip()
                summary = (art.get("description") or "").strip()
                if not title:
                    continue

                raw_time   = art.get("published_utc", "")
                clean_time = (
                    raw_time.replace("T", " ").replace("Z", "")[:19]
                    if raw_time else
                    datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                )

                article_url = art.get("article_url", f"https://finance.yahoo.com/quote/{ticker}")
                publisher   = art.get("publisher", {})
                source_name = publisher.get("name", "Polygon") if isinstance(publisher, dict) else "Polygon"

                stories.append({
                    "ticker":         ticker,
                    "company_name":   company_name,
                    "title":          title,
                    "summary":        summary or f"Via {source_name}",
                    "url":            article_url,
                    "time_published": clean_time,
                    "source":         "polygon",
                })

            next_url = data.get("next_url")
            if next_url:
                next_url = f"{next_url}&apiKey={POLYGON_KEY}"
            page_count += 1

        print(f"   [Polygon]     {len(stories):>4} articles for {company_name} (last {days_back}d)")

    except Exception as e:
        print(f"   WARNING: Polygon error for {company_name}: {e}")

    return stories

# SOURCE 4: GDELT (fallback) — cached + exponential backoff
# ══════════════════════════════════════════════

def _gdelt_cache_path(ticker: str, days_back: int) -> str:
    key = hashlib.md5(f"{ticker}{days_back}".encode()).hexdigest()
    return f"/tmp/gdelt_cache_{key}.json"


def fetch_from_gdelt(ticker: str, company_name: str, days_back: int = 7) -> list[dict]:
    """
    GDELT DOC 2.0 API -- free, no API key, supports date ranges back to 2015.
    Returns up to 250 articles per query.
    Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

    Disk-cached (6hr TTL) to avoid hammering the shared public API.
    Exponential backoff on 429: 5s -> 10s -> 20s -> give up.
    """
    # Check disk cache first
    cache_file = _gdelt_cache_path(ticker, days_back)
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < GDELT_CACHE_TTL:
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                print(f"   [GDELT cache] {len(cached):>4} articles for {company_name} (cached)")
                return cached
            except Exception:
                pass  # corrupted cache — re-fetch

    stories    = []
    max_tries  = 4
    base_delay = 5   # doubles each retry: 5 -> 10 -> 20 -> give up

    try:
        end_date   = datetime.datetime.utcnow()
        start_date = end_date - datetime.timedelta(days=days_back)
        fmt        = "%Y%m%d%H%M%S"

        query_term = urllib.parse.quote(f'"{company_name}"')

        url = (
            f"https://api.gdeltproject.org/api/v2/doc/doc"
            f"?query={query_term}"
            f"&mode=artlist"
            f"&maxrecords=250"
            f"&startdatetime={start_date.strftime(fmt)}"
            f"&enddatetime={end_date.strftime(fmt)}"
            f"&sort=DateDesc"
            f"&format=json"
        )

        resp = None
        for attempt in range(1, max_tries + 1):
            resp = requests.get(url, timeout=25)

            if resp.status_code == 200:
                break
            elif resp.status_code == 429:
                wait = base_delay * (2 ** (attempt - 1))
                print(f"   GDELT 429 for {company_name} -- waiting {wait}s "
                      f"(attempt {attempt}/{max_tries})")
                time.sleep(wait)
            else:
                print(f"   WARNING: GDELT HTTP {resp.status_code} for {company_name}")
                return stories

        if resp is None or resp.status_code != 200:
            print(f"   WARNING: GDELT gave up after {max_tries} attempts for {company_name}")
            return stories

        data     = resp.json()
        articles = data.get("articles", [])

        for art in articles:
            title = art.get("title", "").strip()
            if not title:
                continue

            seendate = art.get("seendate", "")
            try:
                clean_time = datetime.datetime.strptime(
                    seendate, "%Y%m%dT%H%M%SZ"
                ).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                clean_time = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            stories.append({
                "ticker":         ticker,
                "company_name":   company_name,
                "title":          title,
                "summary":        art.get("domain", "Via GDELT"),
                "url":            art.get("url", f"https://finance.yahoo.com/quote/{ticker}"),
                "time_published": clean_time,
                "source":         "gdelt",
            })

        # Save to disk cache
        try:
            with open(cache_file, "w") as f:
                json.dump(stories, f)
        except Exception:
            pass

        print(f"   [GDELT]       {len(stories):>4} articles for {company_name} (last {days_back}d)")

    except Exception as e:
        print(f"   WARNING: GDELT error for {company_name}: {e}")

    return stories


# ══════════════════════════════════════════════
# SOURCE 4: Finnhub — free tier, full date range
# ══════════════════════════════════════════════

def fetch_from_finnhub(ticker: str, company_name: str, days_back: int = 7) -> list[dict]:
    """
    Finnhub /company-news endpoint -- free tier supports 1 year of history.
    Requires FINNHUB_API_KEY in .env. Sign up free at https://finnhub.io/
    """
    stories = []
    if not FINNHUB_KEY:
        return stories

    try:
        end_date   = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        # Finnhub uses plain symbol without exchange suffix
        fh_ticker = ticker.replace(".NS", "").replace(".BO", "")

        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={fh_ticker}"
            f"&from={start_date}"
            f"&to={end_date}"
            f"&token={FINNHUB_KEY}"
        )

        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"   WARNING: Finnhub HTTP {resp.status_code} for {ticker}")
            return stories

        articles = resp.json()
        if not isinstance(articles, list):
            return stories

        for art in articles:
            title   = art.get("headline", "").strip()
            summary = art.get("summary",  "").strip()
            if not title:
                continue

            unix_ts    = art.get("datetime", 0)
            clean_time = (
                datetime.datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S")
                if unix_ts else
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            stories.append({
                "ticker":         ticker,
                "company_name":   company_name,
                "title":          title,
                "summary":        summary or "Via Finnhub",
                "url":            art.get("url", f"https://finance.yahoo.com/quote/{ticker}"),
                "time_published": clean_time,
                "source":         "finnhub",
            })

        print(f"   [Finnhub]     {len(stories):>4} articles for {company_name} (last {days_back}d)")

    except Exception as e:
        print(f"   WARNING: Finnhub error for {company_name}: {e}")

    return stories


# ══════════════════════════════════════════════
# SOURCE 5: MediaStack — free 500 req/month
# ══════════════════════════════════════════════

def fetch_from_mediastack(ticker: str, company_name: str, days_back: int = 7) -> list[dict]:
    """
    MediaStack /news endpoint -- 500 free requests/month, good financial coverage.
    Sign up free at https://mediastack.com/
    Requires MEDIASTACK_API_KEY in .env.
    """
    stories = []
    if not MEDIASTACK_KEY:
        return stories

    try:
        end_date   = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        url = (
            f"http://api.mediastack.com/v1/news"
            f"?access_key={MEDIASTACK_KEY}"
            f"&keywords={urllib.parse.quote(company_name)}"
            f"&date={start_date},{end_date}"
            f"&languages=en"
            f"&limit=100"
            f"&sort=published_desc"
        )

        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"   WARNING: MediaStack HTTP {resp.status_code} for {company_name}")
            return stories

        data = resp.json()
        for art in data.get("data", []):
            title   = (art.get("title") or "").strip()
            summary = (art.get("description") or "").strip()
            if not title:
                continue

            raw_time = art.get("published_at", "")
            clean_time = raw_time[:19].replace("T", " ") if raw_time else \
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            stories.append({
                "ticker":         ticker,
                "company_name":   company_name,
                "title":          title,
                "summary":        summary or "Via MediaStack",
                "url":            art.get("url", f"https://finance.yahoo.com/quote/{ticker}"),
                "time_published": clean_time,
                "source":         "mediastack",
            })

        print(f"   [MediaStack]  {len(stories):>4} articles for {company_name} (last {days_back}d)")

    except Exception as e:
        print(f"   WARNING: MediaStack error for {company_name}: {e}")

    return stories



# ══════════════════════════════════════════════
# SOURCE 7: Economic Times RSS — best Indian stock coverage
# ══════════════════════════════════════════════

def fetch_from_economic_times(ticker: str, company_name: str) -> list[dict]:
    """
    Economic Times has dedicated RSS feeds for every major NSE/BSE stock.
    No API key, no rate limits, updated every 15 minutes.
    Feed URL pattern: https://economictimes.indiatimes.com/[company-slug]/stocks/rss.cms
    Falls back to the general markets feed if per-stock feed returns nothing.
    """
    stories      = []
    short_ticker = ticker.replace(".NS", "").replace(".BO", "")

    # ET per-stock feed uses a slug derived from company name
    # e.g. "Reliance Industries" -> "reliance-industries"
    slug = re.sub(r'[^a-z0-9]+', '-', company_name.lower()).strip('-')

    feeds_to_try = [
        f"https://economictimes.indiatimes.com/{slug}/stocks/rss.cms",
        f"https://economictimes.indiatimes.com/markets/stocks/rss.cms",   # fallback
        f"https://economictimes.indiatimes.com/markets/rss.cms",          # broad fallback
    ]

    for feed_url in feeds_to_try:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                continue

            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Only keep entries that mention the company/ticker
                pool = f"{title} {entry.get('summary', '')}".lower()
                if (company_name.lower() not in pool
                        and short_ticker.lower() not in pool):
                    continue

                try:
                    clean_time = datetime.datetime(
                        *entry.published_parsed[:6]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    clean_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                stories.append({
                    "ticker":         ticker,
                    "company_name":   company_name,
                    "title":          title,
                    "summary":        entry.get("summary", "Via Economic Times"),
                    "url":            entry.get("link", "https://economictimes.indiatimes.com"),
                    "time_published": clean_time,
                    "source":         "economic_times",
                })

            if stories:
                break   # got results from this feed, stop trying fallbacks

        except Exception as e:
            print(f"   WARNING: ET RSS error ({feed_url}): {e}")
            continue

    print(f"   [Econ Times]  {len(stories):>4} articles for {company_name}")
    return stories


# ══════════════════════════════════════════════
# SOURCE 8: Moneycontrol RSS — real-time Indian market news
# ══════════════════════════════════════════════

def fetch_from_moneycontrol(ticker: str, company_name: str) -> list[dict]:
    """
    Moneycontrol RSS feeds — best real-time coverage of Indian stocks.
    No API key required. Multiple topic feeds are checked and filtered
    by company name / ticker mention.
    """
    stories      = []
    short_ticker = ticker.replace(".NS", "").replace(".BO", "")

    mc_feeds = [
        "https://www.moneycontrol.com/rss/marketreports.xml",
        "https://www.moneycontrol.com/rss/latestnews.xml",
        "https://www.moneycontrol.com/rss/results.xml",
        "https://www.moneycontrol.com/rss/business.xml",
    ]

    for feed_url in mc_feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:40]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                pool = f"{title} {entry.get('summary', '')}".lower()
                if (company_name.lower() not in pool
                        and short_ticker.lower() not in pool):
                    continue

                try:
                    clean_time = datetime.datetime(
                        *entry.published_parsed[:6]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    clean_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                stories.append({
                    "ticker":         ticker,
                    "company_name":   company_name,
                    "title":          title,
                    "summary":        entry.get("summary", "Via Moneycontrol"),
                    "url":            entry.get("link", "https://moneycontrol.com"),
                    "time_published": clean_time,
                    "source":         "moneycontrol",
                })

        except Exception as e:
            print(f"   WARNING: Moneycontrol RSS error ({feed_url}): {e}")
            continue

    print(f"   [Moneycontrol]{len(stories):>4} articles for {company_name}")
    return stories


# ══════════════════════════════════════════════
# SOURCE 9: Business Standard RSS — strong NSE/BSE coverage
# ══════════════════════════════════════════════

def fetch_from_business_standard(ticker: str, company_name: str) -> list[dict]:
    """
    Business Standard RSS -- strong NSE/BSE coverage, no auth needed.
    """
    stories      = []
    short_ticker = ticker.replace(".NS", "").replace(".BO", "")

    bs_feeds = [
        "https://www.business-standard.com/rss/markets-106.rss",
        "https://www.business-standard.com/rss/finance-103.rss",
        "https://www.business-standard.com/rss/economy-policy-102.rss",
    ]

    for feed_url in bs_feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:40]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                pool = f"{title} {entry.get('summary', '')}".lower()
                if (company_name.lower() not in pool
                        and short_ticker.lower() not in pool):
                    continue

                try:
                    clean_time = datetime.datetime(
                        *entry.published_parsed[:6]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    clean_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                stories.append({
                    "ticker":         ticker,
                    "company_name":   company_name,
                    "title":          title,
                    "summary":        entry.get("summary", "Via Business Standard"),
                    "url":            entry.get("link", "https://business-standard.com"),
                    "time_published": clean_time,
                    "source":         "business_standard",
                })

        except Exception as e:
            print(f"   WARNING: Business Standard RSS error ({feed_url}): {e}")
            continue

    print(f"   [Biz Standard]{len(stories):>4} articles for {company_name}")
    return stories

# ══════════════════════════════════════════════
# SOURCE 6: CNBC RSS (legacy stub -- scraper handles it)
# ══════════════════════════════════════════════

def fetch_from_cnbc(ticker: str, company_name: str) -> list[dict]:
    """
    Legacy CNBC RSS stub -- kept for API compatibility.
    web_scraper.py handles the full 8-feed CNBC scrape.
    Returns empty list to avoid duplicate insertions.
    """
    return []


# ══════════════════════════════════════════════
# DB INSERTION HELPER
# ══════════════════════════════════════════════

def insert_articles(stories: list[dict]) -> int:
    """
    Upserts normalized stories into market_news.
    Returns the count of newly inserted rows.

    Required DB migration (run once):
      ALTER TABLE market_news ADD COLUMN IF NOT EXISTS url_fingerprint VARCHAR(32);
      CREATE UNIQUE INDEX IF NOT EXISTS idx_url_fingerprint
          ON market_news(url_fingerprint) WHERE url_fingerprint IS NOT NULL;
    """
    new_inserts = 0
    try:
        conn   = database.get_connection()
        cursor = conn.cursor()

        for story in stories:
            cursor.execute(
                '''
                INSERT INTO market_news
                    (ticker, title, summary, url, time_published, source, url_fingerprint)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (title) DO NOTHING
                ''',
                (
                    story["ticker"],
                    story["title"],
                    story["summary"],
                    story["url"],
                    story["time_published"],
                    story["source"],
                    story.get("url_fingerprint", ""),
                )
            )
            if cursor.rowcount > 0:
                new_inserts += 1

        conn.commit()

        if new_inserts > 0:
            print(f"POSTGRESQL: Committed {new_inserts} fresh records.")
        else:
            print("POSTGRESQL: No new articles since last run. Cache preserved.")

    except Exception as db_err:
        print(f"DATABASE EXCEPTION: {db_err}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return new_inserts


# ══════════════════════════════════════════════
# MAIN PIPELINE ORCHESTRATOR
# ══════════════════════════════════════════════

def _fetch_all_for_ticker(args: tuple) -> list[dict]:
    """
    Fetches all sources for a single ticker.
    Designed to run inside a ThreadPoolExecutor worker.
    Returns combined list of raw stories from all sources.
    """
    ticker, info, news_days, gdelt_days, fh_days, ms_days = args
    company_name = info["name"]
    stories      = []

    try:
        stories.extend(fetch_from_newsapi(ticker, company_name, days_back=news_days))
        stories.extend(fetch_from_yahoo(ticker, company_name))
        stories.extend(fetch_from_polygon(ticker, company_name, days_back=gdelt_days))
        stories.extend(fetch_from_gdelt(ticker, company_name, days_back=gdelt_days))
        stories.extend(fetch_from_finnhub(ticker, company_name, days_back=fh_days))
        stories.extend(fetch_from_mediastack(ticker, company_name, days_back=ms_days))
        stories.extend(fetch_from_economic_times(ticker, company_name))
        stories.extend(fetch_from_moneycontrol(ticker, company_name))
        stories.extend(fetch_from_business_standard(ticker, company_name))
    except Exception as e:
        print(f"   WARNING: Unhandled error fetching {ticker}: {e}")

    print(f"  [{ticker}] done -- {len(stories)} raw articles")
    return stories


def run_pipeline(backfill: bool = False):
    """
    Full hybrid pipeline run.

    backfill=True  -> pulls 90 days of history via Polygon + GDELT + NewsAPI + Finnhub.
    backfill=False -> live mode: 2-day NewsAPI window, 7-day Polygon/GDELT/Finnhub top-up.

    Flow:
      1. API layer  -- all sources fetched in PARALLEL using ThreadPoolExecutor
                       (all tickers run simultaneously -- 10x faster than sequential)
      2. Scrape layer -- Yahoo HTML + Reuters RSS + CNBC RSS + Google News (live only)
      3. normalize_all() -- clean, deduplicate
      4. DB upsert
      5. Trigger sentiment_analyzer.py for unscored rows

    Threading: MAX_WORKERS controls parallelism. Default 5 means 5 tickers fetch
    simultaneously. Increase carefully -- too high will trigger rate limits.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    MAX_WORKERS = 5   # 5 tickers in parallel -- safe for all sources

    MAX_HISTORY_DAYS = 365   # global cap -- no source fetches beyond 1 year

    news_days  = min(365, 365) if backfill else 2    # NewsAPI: 30 on dev plan, 365 on business
    gdelt_days = min(365, 365) if backfill else 7
    fh_days    = min(365, 365) if backfill else 7    # Finnhub free supports 1 year
    ms_days    = min(365,  30) if backfill else 7    # MediaStack free caps at 30 days

    mode_label = "BACKFILL 1-YEAR" if backfill else "LIVE"

    print(f"\n{'=' * 60}")
    print(f"PIPELINE START [{mode_label}]: "
          f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Max parallel workers: {MAX_WORKERS}")
    print(f"{'=' * 60}")

    all_stories: list[dict] = []
    tickers_list = list(TICKERS.items())

    # Build args list for each ticker worker
    worker_args = [
        (ticker, info, news_days, gdelt_days, fh_days, ms_days)
        for ticker, info in tickers_list
    ]

    # API layer -- parallel fetch
    print(f"\nAPI LAYER: Fetching {len(tickers_list)} tickers in parallel (workers={MAX_WORKERS})...")
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_all_for_ticker, args): args[0]
            for args in worker_args
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                all_stories.extend(result)
            except Exception as e:
                print(f"   WARNING: Worker for {ticker} raised: {e}")

    elapsed = time.time() - t_start
    print(f"\nAPI layer done in {elapsed:.1f}s  (was ~{len(tickers_list) * 12}s sequential)")

    # Scrape layer (live only -- RSS/HTML has no historical mode)
    if not backfill:
        print("\nSCRAPE LAYER: Yahoo HTML + Reuters RSS + CNBC RSS + Google News")
        scraped_stories = run_scraper()
        all_stories.extend(scraped_stories)
        print(f"   [Scraper]     {len(scraped_stories):>4} articles")
    else:
        print("\nSCRAPE LAYER skipped in backfill mode (no historical RSS support).")

    # Normalize + deduplicate
    print(f"\nRaw articles collected:  {len(all_stories)}")
    normalized = normalize_all(all_stories)
    dropped    = len(all_stories) - len(normalized)
    print(f"After normalization:     {len(normalized)}  ({dropped} dropped -- junk/dupes/off-topic)")

    # Purge articles older than 1 year to keep DB lean
    try:
        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM market_news
            WHERE time_published < NOW() - INTERVAL '1 year'
        """)
        purged = cursor.rowcount
        conn.commit()
        conn.close()
        if purged > 0:
            print(f"Purged {purged} articles older than 1 year.")
    except Exception as e:
        print(f"WARNING: Purge failed: {e}")

    # Insert
    new_inserts = insert_articles(normalized)

    # Trigger sentiment scoring
    if new_inserts > 0:
        print(f"\nTriggering FinBERT sentiment scoring for {new_inserts} new article(s)...")
        try:
            subprocess.run([sys.executable, "sentiment_analyzer.py"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"   WARNING: sentiment_analyzer.py exited with error: {e}")
        except FileNotFoundError:
            print("   WARNING: sentiment_analyzer.py not found -- skipping auto-score.")
    else:
        print("\nNo new articles -- skipping sentiment re-score.")

    print(f"\nPIPELINE COMPLETE: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")


# ══════════════════════════════════════════════
# SCHEDULER (15-minute auto-run)
# ══════════════════════════════════════════════

def start_scheduler():
    """
    Runs the pipeline once immediately (live mode), then every 15 minutes.
    Uses APScheduler's BlockingScheduler -- process stays alive until Ctrl+C.
    Install: pip install apscheduler
    """
    try:
        # pyrefly: ignore [missing-import]
        from apscheduler.schedulers.blocking import BlockingScheduler
        # pyrefly: ignore [missing-import]
        from apscheduler.triggers.interval   import IntervalTrigger
    except ImportError:
        print("APScheduler not installed. Run: pip install apscheduler")
        print("Falling back to single run...")
        run_pipeline()
        return

    run_pipeline()   # immediate run on startup

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        func=run_pipeline,
        trigger=IntervalTrigger(minutes=15),
        id="finpulse_pipeline",
        name="FinPulse 15-min hybrid ingestion",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    next_run = datetime.datetime.now() + datetime.timedelta(minutes=15)
    print(f"SCHEDULER ACTIVE -- next run at {next_run.strftime('%H:%M:%S IST')}")
    print("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        print("\nScheduler stopped cleanly.")


# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    if "--backfill" in sys.argv:
        print("BACKFILL MODE -- fetching 90 days of history via GDELT + NewsAPI + Finnhub")
        print("This may take several minutes depending on ticker count.\n")
        run_pipeline(backfill=True)

    elif "--once" in sys.argv:
        print("Single-run mode (--once flag detected)")
        run_pipeline(backfill=False)

    else:
        start_scheduler()