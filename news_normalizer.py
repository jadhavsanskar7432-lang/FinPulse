# news_normalizer.py
import re
import html
import hashlib
import datetime
from urllib.parse import urlparse
import html as html_module
from news_fetcher import _is_relevant
from utils import clean_text

# ── Junk title patterns ──────────────────────────────────────────
JUNK_PATTERNS = [
    r'^\[removed\]$',
    r'^…$',
    r'^null$',
    r'^none$',
    r'^\s*$',
    r'^https?://',              # URL stored as title
    r'^(cnbc|reuters|bloomberg|yahoo finance)\s*$',  # source name only
]
JUNK_RE = re.compile('|'.join(JUNK_PATTERNS), re.IGNORECASE)

MIN_TITLE_WORDS  = 4
MAX_TITLE_LEN    = 500
MAX_SUMMARY_LEN  = 2000


# ── Timestamp normalizer ─────────────────────────────────────────
TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",       # NewsAPI, yfinance
    "%Y-%m-%dT%H:%M:%S%z",      # ISO with tz offset
    "%Y-%m-%d %H:%M:%S",        # already clean
    "%Y%m%dT%H%M%SZ",           # GDELT
    "%a, %d %b %Y %H:%M:%S %z", # RSS (RFC 2822)
    "%a, %d %b %Y %H:%M:%S GMT",
    "%Y-%m-%d",                  # date only
]

def parse_timestamp(raw) -> str:
    """Coerce any timestamp format to 'YYYY-MM-DD HH:MM:SS'. Falls back to now()."""
    if raw is None:
        return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Unix integer/float
    if isinstance(raw, (int, float)):
        try:
            return datetime.datetime.utcfromtimestamp(raw).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    raw = str(raw).strip()

    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            # Strip tz and return as UTC string
            return dt.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    # Last resort: strip T and Z and truncate
    cleaned = raw.replace("T", " ").replace("Z", "")[:19]
    try:
        datetime.datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
        return cleaned
    except ValueError:
        return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ── Text cleaner ────────────────────────────────────────────────
def _clean_text(text: str, max_len: int) -> str:
    """Decode HTML entities, fix mangled UTF-8, strip trailing source tags."""
    if not text:
        return ""

    # Decode HTML entities: &amp; -> &, &#39; -> ', etc.
    text = html_module.unescape(text)

    # Fix mangled UTF-8 (e.g. RSS feeds decoded as latin-1 instead of UTF-8)
    try:
        text = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass  # already valid UTF-8, skip

    # Strip trailing " - SourceName" attribution
    text = re.sub(r'\s*[-]\s*(Reuters|Bloomberg|CNBC|AP|AFP|MarketWatch)$', '', text)

    # Strip NewsAPI truncation artifact: "[+1234 chars]"
    text = re.sub(r'\s*\[\+\d+ chars?\]$', '', text)

    # Strip trailing ellipsis
    text = re.sub(r'\s*\.\.\.$', '', text).strip()

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text[:max_len]


# ── URL-based dedup key ─────────────────────────────────────────
def url_fingerprint(url: str) -> str:
    """
    Canonical URL fingerprint — strips tracking params, utm_, etc.
    so the same article from 2 sources resolves to one key.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.lower().strip())
        # Drop query string (tracking params) and fragment
        canonical = f"{parsed.netloc}{parsed.path}".rstrip("/")
        return hashlib.md5(canonical.encode()).hexdigest()
    except Exception:
        return hashlib.md5(url.encode()).hexdigest()


def _is_relevant(story: dict) -> bool:
    ticker      = story.get("ticker", "").replace(".NS", "").lower()
    company     = story.get("company_name", "").lower()
    search_pool = f"{story.get('title', '')} {story.get('summary', '')}".lower()
    
    # Also accept if ticker appears in the URL (common with Yahoo/Finnhub)
    url = story.get("url", "").lower()
    
    return (
        ticker in search_pool
        or (company and company in search_pool)
        or ticker in url
    )

# ── Main normalizer ─────────────────────────────────────────────
def normalize(story: dict) -> dict | None:
    """
    Takes a raw story dict from any source and returns a clean dict
    ready for DB insertion, or None if the article should be dropped.
    """
    title   = clean_text(story.get("title", ""), MAX_TITLE_LEN)
    summary = clean_text(story.get("summary", ""), MAX_SUMMARY_LEN)

    # Drop junk titles
    if not title or JUNK_RE.match(title):
        return None
    if len(title.split()) < MIN_TITLE_WORDS:
        return None

    # Drop irrelevant articles
    # (pass company_name in story dict from the pipeline for this to work)
    if not _is_relevant({**story, "title": title, "summary": summary}):
        return None

    return {
        "ticker":         story.get("ticker", ""),
        "title":          title,
        "summary":        summary or "No summary available.",
        "url":            story.get("url", ""),
        "time_published": parse_timestamp(story.get("time_published")),
        "source":         story.get("source", "unknown"),
        "url_fingerprint": url_fingerprint(story.get("url", "")),
    }


def normalize_all(stories: list[dict]) -> list[dict]:
    """Normalize + deduplicate a batch of raw stories."""
    cleaned    = []
    seen_urls  = set()
    seen_titles = set()

    for raw in stories:
        result = normalize(raw)
        if result is None:
            continue

        # URL-based dedup (catches same article from multiple sources)
        fp = result["url_fingerprint"]
        if fp and fp in seen_urls:
            continue
        if fp:
            seen_urls.add(fp)

        # Title-based dedup as fallback (for articles without a stable URL)
        title_key = result["title"].lower().strip()
        if title_key in seen_titles:
            continue  
        seen_titles.add(title_key)

        cleaned.append(result)

    return cleaned
def _normalize_one(story: dict) -> dict | None:
    title   = _clean_text(story.get("title",   ""), MAX_TITLE_LEN)
    summary = _clean_text(story.get("summary", ""), MAX_SUMMARY_LEN)

    if not title or JUNK_RE.match(title):
        print(f"   ❌ JUNK TITLE: {title[:60]}")
        return None
    if len(title.split()) < MIN_TITLE_WORDS:
        print(f"   ❌ TOO SHORT: {title}")
        return None
    if not _is_relevant({**story, "title": title, "summary": summary}):
        print(f"   ❌ NOT RELEVANT: {title[:60]}")
        return None

    return { ... }