import re
import time
import logging
import datetime
import requests
from collections import Counter
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry  # type: ignore[import]
# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup   
import database

# ══════════════════════════════════════════════
# LOGGER
# ══════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("validator.log", mode="a"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("validator")

# ══════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

REQUEST_TIMEOUT     = 15
INTER_REQUEST_DELAY = 1
VALIDATION_STALE_HOURS = 24   # skip re-validating a ticker if it was checked within this window

# Yahoo Finance analyst recommendation mean → label mapping
# Values from yfinance: 1.0=Strong Buy, 2.0=Buy, 3.0=Hold, 4.0=Sell, 5.0=Strong Sell
_YF_REC_MAP = {
    (1.0, 1.5): "STRONG_BUY",
    (1.5, 2.5): "BUY",
    (2.5, 3.5): "HOLD",
    (3.5, 4.5): "SELL",
    (4.5, 5.1): "STRONG_SELL",
}


# ══════════════════════════════════════════════
# SESSION
# ══════════════════════════════════════════════

def _make_session() -> requests.Session:
    session = requests.Session()
    retry   = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    session.headers.update(HEADERS)
    return session


SESSION = _make_session()


# ══════════════════════════════════════════════
# TICKER CLASSIFICATION
# ══════════════════════════════════════════════

def _is_indian(ticker: str) -> bool:
    return ticker.endswith(".NS") or ticker.endswith(".BO")


def _short(ticker: str) -> str:
    return ticker.replace(".NS", "").replace(".BO", "")


# ══════════════════════════════════════════════
# DB SETUP
# ══════════════════════════════════════════════

def ensure_validation_table():
    try:
        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyst_validation (
                id                  SERIAL PRIMARY KEY,
                ticker              VARCHAR(20)  NOT NULL,
                company_name        VARCHAR(100),
                finbert_score       FLOAT,
                finbert_signal      VARCHAR(10),
                mc_signal           VARCHAR(20),
                mc_buy_count        INT,
                mc_hold_count       INT,
                mc_sell_count       INT,
                mc_target_price     FLOAT,
                mc_current_price    FLOAT,
                tt_signal           VARCHAR(20),
                tt_analyst_rating   VARCHAR(20),
                tt_momentum         VARCHAR(20),
                tv_signal           VARCHAR(20),
                tv_oscillators      VARCHAR(20),
                tv_moving_avgs      VARCHAR(20),
                consensus_signal    VARCHAR(20),
                conflict_status     VARCHAR(15),
                source_agreement    INT,
                last_updated        TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_validation_ticker
            ON analyst_validation(ticker);
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"DB setup warning: {e}")


def _get_last_updated_map() -> dict:
    """Returns {ticker: last_updated datetime} for every ticker currently in analyst_validation."""
    try:
        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, last_updated FROM analyst_validation")
        rows = cursor.fetchall()
        conn.close()
        return {r["ticker"]: r["last_updated"] for r in rows}
    except Exception as e:
        log.warning(f"Could not fetch last_updated map: {e}")
        return {}


# ══════════════════════════════════════════════
# SIGNAL HELPERS
# ══════════════════════════════════════════════

def _normalize_signal(raw: str) -> str:
    if not raw:
        return "NEUTRAL"
    r = raw.upper().strip()
    bullish = ["BUY", "STRONG BUY", "STRONG_BUY", "OUTPERFORM", "OVERWEIGHT",
               "ACCUMULATE", "ADD", "POSITIVE", "BULLISH", "LONG"]
    bearish = ["SELL", "STRONG SELL", "STRONG_SELL", "UNDERPERFORM", "UNDERWEIGHT",
               "REDUCE", "NEGATIVE", "BEARISH", "SHORT"]
    for kw in bullish:
        if kw in r:
            return "BULLISH"
    for kw in bearish:
        if kw in r:
            return "BEARISH"
    return "NEUTRAL"


def _finbert_to_signal(score: float) -> str:
    if score is None: return "NEUTRAL"
    if score >  0.15: return "BULLISH"
    if score < -0.15: return "BEARISH"
    return "NEUTRAL"


# ══════════════════════════════════════════════
# SOURCE: YAHOO FINANCE  (US tickers only)
# Uses the unofficial query2 JSON API — no key needed.
# ══════════════════════════════════════════════

def fetch_yahoo_finance_signal(ticker: str) -> dict:
    """
    Fetches analyst recommendation and price target using yfinance library.
    More reliable than scraping query2 endpoint directly.
    """
    result = {
        "signal":        None,
        "rec_mean":      None,
        "rec_key":       None,
        "num_analysts":  None,
        "target_mean":   None,
        "target_high":   None,
        "target_low":    None,
        "current_price": None,
        "source_url":    f"https://finance.yahoo.com/quote/{ticker}/analysis",
    }

    try:
        # pyrefly: ignore [missing-import]
        import yfinance as yf   
        stock = yf.Ticker(ticker)
        info  = stock.info

        rec_key   = info.get("recommendationKey")       # "buy", "hold", etc.
        rec_mean  = info.get("recommendationMean")      # 1.0–5.0
        n_analysts = info.get("numberOfAnalystOpinions")
        target_mean = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        target_low  = info.get("targetLowPrice")
        cur_price   = info.get("currentPrice") or info.get("regularMarketPrice")

        result["rec_key"]       = rec_key
        result["rec_mean"]      = rec_mean
        result["num_analysts"]  = n_analysts
        result["target_mean"]   = target_mean
        result["target_high"]   = target_high
        result["target_low"]    = target_low
        result["current_price"] = cur_price

        if rec_key:
            result["signal"] = _normalize_signal(rec_key.replace("_", " "))

        if not result["signal"] and rec_mean is not None:
            for (lo, hi), label in _YF_REC_MAP.items():
                if lo <= rec_mean < hi:
                    result["signal"] = _normalize_signal(label)
                    break

        log.info(
            f"Yahoo Finance (yfinance): {ticker} → {result['signal']} "
            f"(rec={rec_key}, mean={rec_mean}, analysts={n_analysts})"
        )

    except Exception as e:
        log.error(f"yfinance error for {ticker}: {e}")

    return result


# ══════════════════════════════════════════════
# SOURCE: MONEYCONTROL  (Indian tickers only)
# ══════════════════════════════════════════════

def _get_moneycontrol_sc_id(sym: str) -> str | None:
    """Resolves internal Moneycontrol sc_id via their JSON autocomplete API."""
    auto_url = (
        "https://www.moneycontrol.com/mccode/common/autosuggestion/ajaxsearch.php"
        f"?classic=true&query={sym}&type=1&format=json"
    )
    try:
        resp = SESSION.get(auto_url, timeout=REQUEST_TIMEOUT)
        time.sleep(INTER_REQUEST_DELAY)
        if resp.status_code == 200:
            try:
                items = resp.json()
            except ValueError:
                items = []
            for item in items:
                sc_id = item.get("sc_id") or item.get("link_src", "")
                if sc_id:
                    log.info(f"MC sc_id: {sc_id} for {sym}")
                    return sc_id.strip()
    except Exception as e:
        log.warning(f"MC autocomplete error for {sym}: {e}")

    # Fallback: scrape search page
    try:
        search_url = (
            "https://www.moneycontrol.com/stocks/cptmarket/compsearchnew.php"
            f"?search_data={sym}&cid=&mbsearch_str=&topsearch_type=1&search_str={sym}"
        )
        resp2 = SESSION.get(search_url, timeout=REQUEST_TIMEOUT)
        time.sleep(INTER_REQUEST_DELAY)
        if resp2.status_code == 200:
            soup  = BeautifulSoup(resp2.text, "html.parser")
            links = soup.find_all("a", href=re.compile(r"/india/stockpricequote/"))
            for link in links:
                parts = [p for p in link.get("href", "").rstrip("/").split("/") if p]
                if parts and re.match(r'^[A-Z0-9]{3,10}$', parts[-1]):
                    log.info(f"MC sc_id via search page: {parts[-1]} for {sym}")
                    return parts[-1]
    except Exception as e:
        log.warning(f"MC search fallback error for {sym}: {e}")

    return None

def fetch_stockanalysis_signal(ticker: str) -> dict:
    """Fetches analyst rating from Zacks for US tickers."""
    result = {
        "signal": None,
        "source_url": f"https://www.zacks.com/stock/quote/{ticker}",
    }
    try:
        resp = SESSION.get(
            result["source_url"],
            headers={**HEADERS, "Referer": "https://www.zacks.com/"},
            timeout=REQUEST_TIMEOUT,
        )
        time.sleep(INTER_REQUEST_DELAY)
        if resp.status_code == 200:
            text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
            m = re.search(r'Zacks Rank[:\s#]*\d*\s*(Strong Buy|Buy|Hold|Sell|Strong Sell)', text, re.I)
            if m:
                result["signal"] = m.group(1)
                log.info(f"Zacks: {ticker} → {result['signal']}")
            else:
                log.warning(f"Zacks: no rating found for {ticker}")
        else:
            log.warning(f"Zacks: HTTP {resp.status_code} for {ticker}")
    except Exception as e:
        log.error(f"Zacks error for {ticker}: {e}")
    return result
def fetch_moneycontrol_signal(ticker: str, company_name: str) -> dict:
    result = {
        "signal": None, "buy_count": None, "hold_count": None,
        "sell_count": None, "target_price": None, "current_price": None,
        "source_url": "",
    }

    sym   = _short(ticker)
    sc_id = _get_moneycontrol_sc_id(sym) or sym
    url   = f"https://www.moneycontrol.com/stocks/company_info/analyst_views.php?sc_id={sc_id}"
    result["source_url"] = url

    try:
        resp = SESSION.get(url, headers={"Referer": "https://www.moneycontrol.com/"}, timeout=REQUEST_TIMEOUT)
        time.sleep(INTER_REQUEST_DELAY)

        if resp.status_code == 200:
            text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

            buy_m  = re.search(r'Buy[:\s]*(\d+)',  text, re.I)
            hold_m = re.search(r'Hold[:\s]*(\d+)', text, re.I)
            sell_m = re.search(r'Sell[:\s]*(\d+)', text, re.I)

            bc = int(buy_m.group(1))  if buy_m  else 0
            hc = int(hold_m.group(1)) if hold_m else 0
            sc = int(sell_m.group(1)) if sell_m else 0

            if bc + hc + sc > 0:
                result.update({"buy_count": bc, "hold_count": hc, "sell_count": sc})
                result["signal"] = "BUY" if bc > sc and bc > hc else ("SELL" if sc > bc and sc > hc else "HOLD")

            tp = re.search(r'[Tt]arget\s*[Pp]rice[:\s₹]*([0-9,]+\.?[0-9]*)', text)
            if tp:
                try: result["target_price"] = float(tp.group(1).replace(",", ""))
                except ValueError: pass

            cp = re.search(r'[Cc]urrent\s*[Pp]rice[:\s₹]*([0-9,]+\.?[0-9]*)', text)
            if cp:
                try: result["current_price"] = float(cp.group(1).replace(",", ""))
                except ValueError: pass

            if not result["signal"]:
                log.warning(f"MC: no analyst data for {sym} (sc_id={sc_id})")
        else:
            log.warning(f"MC: HTTP {resp.status_code} for {sym}")

    except Exception as e:
        log.error(f"MC error for {ticker}: {e}")

    return result

def fetch_screener_signal(ticker: str) -> dict:
    """Fetches analyst data from Screener.in for Indian stocks."""
    result = {
        "signal": None, "buy_count": None, "hold_count": None,
        "sell_count": None, "target_price": None, "current_price": None,
        "source_url": "",
    }
    sym = _short(ticker)
    url = f"https://www.screener.in/company/{sym}/consolidated/"
    result["source_url"] = url

    try:
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        time.sleep(INTER_REQUEST_DELAY)
        if resp.status_code == 200:
            text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
            buy_m  = re.search(r'Buy[:\s]*(\d+)',  text, re.I)
            hold_m = re.search(r'Hold[:\s]*(\d+)', text, re.I)
            sell_m = re.search(r'Sell[:\s]*(\d+)', text, re.I)
            bc = int(buy_m.group(1))  if buy_m  else 0
            hc = int(hold_m.group(1)) if hold_m else 0
            sc = int(sell_m.group(1)) if sell_m else 0
            if bc + hc + sc > 0:
                result["buy_count"]  = bc
                result["hold_count"] = hc
                result["sell_count"] = sc
                result["signal"] = "BUY" if bc > sc and bc > hc else ("SELL" if sc > bc and sc > hc else "HOLD")
                log.info(f"Screener: {sym} → {result['signal']} (B:{bc} H:{hc} S:{sc})")
            else:
                log.warning(f"Screener: no analyst counts for {sym}")
        else:
            log.warning(f"Screener: HTTP {resp.status_code} for {sym}")
    except Exception as e:
        log.error(f"Screener error for {ticker}: {e}")
    return result


# ══════════════════════════════════════════════
# SOURCE: TICKERTAPE  (Indian tickers only)
# ══════════════════════════════════════════════

_TT_STRIP = re.compile(
    r'\b(limited|ltd|technologies|technology|tech|industries|industry|'
    r'enterprises|corporation|corp|solutions|services|group|holdings|'
    r'india|indian|national|international|intl|and)\b',
    re.IGNORECASE,
)


def _tt_slugs(company_name: str, sym: str) -> list[str]:
    stripped = re.sub(r'-{2,}', '-', re.sub(r'[^a-z0-9]+', '-', _TT_STRIP.sub("", company_name).lower()).strip('-'))
    full     = re.sub(r'[^a-z0-9]+', '-', company_name.lower()).strip('-')
    seen, out = set(), []
    for s in [stripped, full, sym.lower()]:
        if s and s not in seen:
            seen.add(s); out.append(s)
    return out


def fetch_tickertape_signal(ticker: str, company_name: str) -> dict:
    result = {"signal": None, "analyst_rating": None, "momentum": None, "source_url": ""}
    sym    = _short(ticker)

    for slug in _tt_slugs(company_name, sym):
        url = f"https://www.tickertape.in/stocks/{slug}-{sym}"
        log.info(f"TT trying: {url}")
        try:
            resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
            time.sleep(INTER_REQUEST_DELAY)

            if resp.status_code == 404:
                continue
            if resp.status_code == 200:
                result["source_url"] = url
                text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

                for pat in [
                    r'(Strong\s+Buy|Strong\s+Sell|Buy|Sell|Hold)\s+\d+\s+analyst',
                    r'Analyst\s+Rating[:\s]*(Strong\s+Buy|Strong\s+Sell|Buy|Sell|Hold)',
                    r'(Strong\s+Buy|Strong\s+Sell|Buy|Sell|Hold)\s+consensus',
                    r'consensus[:\s]*(Strong\s+Buy|Strong\s+Sell|Buy|Sell|Hold)',
                ]:
                    m = re.search(pat, text, re.I)
                    if m:
                        result["analyst_rating"] = m.group(1)
                        result["signal"]         = m.group(1)
                        break

                mm = re.search(r'Momentum[:\s]*(Bullish|Bearish|Neutral|Strong|Weak)', text, re.I)
                if mm:
                    result["momentum"] = mm.group(1)

                if not result["signal"]:
                    for label in ["Strong Buy", "Strong Sell", "Buy", "Sell", "Hold"]:
                        if re.search(rf'\b{re.escape(label)}\b', text, re.I):
                            result["signal"] = label
                            break

                log.info(f"TT: {sym} → {result['signal']} (slug={slug})")
                break
        except Exception as e:
            log.error(f"TT error {ticker} slug={slug}: {e}")

    if not result["source_url"]:
        log.warning(f"TT: all slugs failed for {sym}")
    return result


# ══════════════════════════════════════════════
# SOURCE: TRADINGVIEW  (all tickers)
# ══════════════════════════════════════════════

def fetch_tradingview_signal(ticker: str) -> dict:
    result = {"signal": None, "oscillators": None, "moving_averages": None, "source_url": ""}

    sym       = _short(ticker)
    indian    = _is_indian(ticker)
    tv_symbol = f"NSE:{sym}" if indian else f"NASDAQ:{sym}"
    scan_url  = "https://scanner.tradingview.com/india/scan" if indian else "https://scanner.tradingview.com/america/scan"

    result["source_url"] = f"https://www.tradingview.com/symbols/{tv_symbol}"

    payload = {
        "symbols": {"tickers": [tv_symbol], "query": {"types": []}},
        "columns": ["Recommend.All", "Recommend.Other", "Recommend.MA", "close"],
        "filter":  [],
        "sort":    {"sortBy": "Recommend.All", "sortOrder": "desc"},
        "range":   [0, 1],
    }

    try:
        resp = SESSION.post(
            scan_url,
            json=payload,
            headers={**HEADERS, "Content-Type": "application/json", "Origin": "https://www.tradingview.com"},
            timeout=REQUEST_TIMEOUT,
        )
        time.sleep(INTER_REQUEST_DELAY)

        if resp.status_code == 200:
            rows = resp.json().get("data", [])
            if rows:
                vals = rows[0].get("d", [])
                if len(vals) >= 3:
                    def _lbl(v):
                        if v is None:  return "NEUTRAL"
                        if v >= 0.5:   return "STRONG_BUY"
                        if v >= 0.1:   return "BUY"
                        if v <= -0.5:  return "STRONG_SELL"
                        if v <= -0.1:  return "SELL"
                        return "NEUTRAL"
                    result["signal"]          = _lbl(vals[0])
                    result["oscillators"]     = _lbl(vals[1])
                    result["moving_averages"] = _lbl(vals[2])
                    log.info(f"TV: {tv_symbol} → {result['signal']}")
                else:
                    log.warning(f"TV: unexpected values for {tv_symbol}")
            else:
                log.warning(f"TV: empty data for {tv_symbol} — symbol not in scanner")
        else:
            log.warning(f"TV: HTTP {resp.status_code} for {tv_symbol}")

    except Exception as e:
        log.error(f"TV error for {ticker}: {e}")

    return result


# ══════════════════════════════════════════════
# AGGREGATE
# ══════════════════════════════════════════════

def _aggregate_consensus(finbert_sig: str, mc_sig, tt_sig, tv_sig) -> dict:
    trusted  = [s for s in [mc_sig, tt_sig, tv_sig] if s is not None]
    agree    = sum(1 for s in trusted if s == finbert_sig)
    all_sigs = [finbert_sig] + trusted
    consensus = Counter(all_sigs).most_common(1)[0][0]

    if not trusted:
        conflict = "UNVERIFIED"
    elif agree == len(trusted):
        conflict = "CONFIRMED"
    elif agree == 0:
        non_neutral = [s for s in trusted if s != "NEUTRAL"]
        opposite    = [s for s in non_neutral if
                       (finbert_sig == "BULLISH" and s == "BEARISH") or
                       (finbert_sig == "BEARISH" and s == "BULLISH")]
        conflict = "REVERSED" if (finbert_sig != "NEUTRAL" and non_neutral and len(opposite) == len(non_neutral)) else "CONFLICTED"
    else:
        conflict = "CONFLICTED"

    return {"consensus_signal": consensus, "conflict_status": conflict, "source_agreement": agree}


# ══════════════════════════════════════════════
# MAIN PUBLIC API
# ══════════════════════════════════════════════

def validate_ticker(ticker: str, company_name: str, finbert_score: float) -> dict:
    """
    Validates a single ticker. Routes US vs Indian tickers to the right sources.

    Indian (.NS/.BO): Moneycontrol + Tickertape + TradingView
    US (no suffix):   Yahoo Finance + TradingView  (MC/TT skipped — India only)
    """
    log.info(f"Validating {ticker} ({company_name}) | FinBERT: {finbert_score:+.3f}")

    finbert_sig = _finbert_to_signal(finbert_score)
    indian      = _is_indian(ticker)

    if indian:
        mc_raw = fetch_yahoo_finance_signal(ticker)
        tt_raw = fetch_tickertape_signal(ticker, company_name)
        tv_raw = fetch_tradingview_signal(ticker)
        yf_raw = {}  # not used

        mc_sig = _normalize_signal(mc_raw.get("signal")) if mc_raw.get("signal") else None
        tt_sig = _normalize_signal(tt_raw.get("signal")) if tt_raw.get("signal") else None
        tv_sig = _normalize_signal(tv_raw.get("signal")) if tv_raw.get("signal") else None

    else:
        log.info(f"{ticker} is a US ticker — using Yahoo Finance + StockAnalysis + TradingView")
        yf_raw = fetch_yahoo_finance_signal(ticker)
        sa_raw = fetch_stockanalysis_signal(ticker)   # ← add this
        tv_raw = fetch_tradingview_signal(ticker)
        mc_raw = {}  # not used
        tt_raw = {}
        mc_sig = _normalize_signal(yf_raw.get("signal")) if yf_raw.get("signal") else None
        tt_sig = _normalize_signal(sa_raw.get("signal")) if sa_raw.get("signal") else None  # ← add this
        tv_sig = _normalize_signal(tv_raw.get("signal")) if tv_raw.get("signal") else None

        # Map Yahoo Finance into the mc_ slot for DB consistency
        mc_sig = _normalize_signal(yf_raw.get("signal")) if yf_raw.get("signal") else None
        tt_sig = None  # not available for US stocks
        tv_sig = _normalize_signal(tv_raw.get("signal")) if tv_raw.get("signal") else None

    agg = _aggregate_consensus(finbert_sig, mc_sig, tt_sig, tv_sig)

    # For US tickers, populate mc_ fields with Yahoo Finance data
    mc_buy   = mc_raw.get("buy_count")   if indian else None
    mc_hold  = mc_raw.get("hold_count")  if indian else None
    mc_sell  = mc_raw.get("sell_count")  if indian else None
    mc_tp    = mc_raw.get("target_price")  if indian else yf_raw.get("target_mean")
    mc_cp    = mc_raw.get("current_price") if indian else yf_raw.get("current_price")
    mc_url   = mc_raw.get("source_url", "") if indian else yf_raw.get("source_url", "")

    result = {
        "ticker":            ticker,
        "company_name":      company_name,
        "finbert_score":     round(finbert_score, 4) if finbert_score is not None else None,
        "finbert_signal":    finbert_sig,
        "mc_signal":         mc_sig,
        "mc_buy_count":      mc_buy,
        "mc_hold_count":     mc_hold,
        "mc_sell_count":     mc_sell,
        "mc_target_price":   mc_tp,
        "mc_current_price":  mc_cp,
        "mc_source_url":     mc_url,
        "tt_signal":         tt_sig,
        "tt_analyst_rating": tt_raw.get("analyst_rating") if indian else "N/A (US stock)",
        "tt_momentum":       tt_raw.get("momentum"),
        "tt_source_url":     tt_raw.get("source_url", "") if indian else "",
        "tv_signal":         tv_sig,
        "tv_oscillators":    tv_raw.get("oscillators"),
        "tv_moving_avgs":    tv_raw.get("moving_averages"),
        "tv_source_url":     tv_raw.get("source_url", ""),
        "consensus_signal":  agg["consensus_signal"],
        "conflict_status":   agg["conflict_status"],
        "source_agreement":  agg["source_agreement"],
        "last_updated":      datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    icon = {"CONFIRMED": "✅", "CONFLICTED": "⚠️", "REVERSED": "🔴", "UNVERIFIED": "❓"}.get(agg["conflict_status"], "❓")
    log.info(
        f"{icon} [{agg['conflict_status']}] {ticker}: "
        f"FinBERT={finbert_sig} | src1={mc_sig} | TT={tt_sig} | TV={tv_sig} "
        f"→ Consensus: {agg['consensus_signal']}"
    )

    _upsert_validation(result)
    return result


def validate_all(articles: list[dict]) -> list[dict]:
    """
    Validates all tickers. Seeds from config.TICKERS first so all tickers
    appear even with zero scored articles.
    """
    ensure_validation_table()

    ticker_data: dict = {}

    # Seed ALL configured tickers first
    try:
        from config import TICKERS
        for t, info in TICKERS.items():
            ticker_data[t] = {"company_name": info.get("name", t), "scores": []}
        log.info(f"Seeded {len(ticker_data)} tickers from config.TICKERS")
    except ImportError:
        log.warning("config.TICKERS not found — building ticker list from articles only")

    # Merge article scores
    for art in articles:
        t     = art.get("ticker")
        score = art.get("score")
        if not t:
            continue
        if t not in ticker_data:
            cname = art.get("company_name") or art.get("name") or art.get("stock_name") or t
            ticker_data[t] = {"company_name": cname, "scores": []}
        if score is not None:
            ticker_data[t]["scores"].append(float(score))

    last_updated_map = _get_last_updated_map()
    stale_cutoff = datetime.datetime.now() - datetime.timedelta(hours=VALIDATION_STALE_HOURS)

    results = []
    skipped = 0
    total   = len(ticker_data)
    log.info(f"Starting validation for {total} tickers (staleness window: {VALIDATION_STALE_HOURS}h)...")

    for i, (ticker, data) in enumerate(ticker_data.items(), 1):
        last_checked = last_updated_map.get(ticker)
        if last_checked and last_checked > stale_cutoff:
            log.info(f"[{i}/{total}] {ticker} — skipped (last validated {last_checked}, still fresh)")
            skipped += 1
            continue

        scores    = data["scores"]
        avg_score = (sum(scores) / len(scores)) if scores else 0.0
        log.info(f"[{i}/{total}] {ticker} — avg FinBERT: {avg_score:+.3f} ({len(scores)} articles)")
        results.append(validate_ticker(ticker, data["company_name"], avg_score))
        if i < total:
            time.sleep(INTER_REQUEST_DELAY)

    log.info(f"Done. {len(results)}/{total} tickers validated ({skipped} skipped as still fresh).")
    return results


def get_validation_summary() -> list[dict]:
    rows = []
    try:
        ensure_validation_table()
        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                ticker, company_name,
                finbert_score, finbert_signal,
                mc_signal, mc_buy_count, mc_hold_count, mc_sell_count,
                mc_target_price, mc_current_price,
                tt_signal, tt_analyst_rating, tt_momentum,
                tv_signal, tv_oscillators, tv_moving_avgs,
                consensus_signal, conflict_status, source_agreement,
                last_updated
            FROM analyst_validation
            ORDER BY conflict_status DESC, ticker ASC
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
    except Exception as e:
        log.error(f"DB read error: {e}")
    return rows


# ══════════════════════════════════════════════
# DB UPSERT
# ══════════════════════════════════════════════

def _upsert_validation(data: dict):
    try:
        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analyst_validation (
                ticker, company_name,
                finbert_score, finbert_signal,
                mc_signal, mc_buy_count, mc_hold_count, mc_sell_count,
                mc_target_price, mc_current_price,
                tt_signal, tt_analyst_rating, tt_momentum,
                tv_signal, tv_oscillators, tv_moving_avgs,
                consensus_signal, conflict_status, source_agreement,
                last_updated
            ) VALUES (
                %(ticker)s, %(company_name)s,
                %(finbert_score)s, %(finbert_signal)s,
                %(mc_signal)s, %(mc_buy_count)s, %(mc_hold_count)s, %(mc_sell_count)s,
                %(mc_target_price)s, %(mc_current_price)s,
                %(tt_signal)s, %(tt_analyst_rating)s, %(tt_momentum)s,
                %(tv_signal)s, %(tv_oscillators)s, %(tv_moving_avgs)s,
                %(consensus_signal)s, %(conflict_status)s, %(source_agreement)s,
                %(last_updated)s
            )
            ON CONFLICT (ticker) DO UPDATE SET
                company_name       = EXCLUDED.company_name,
                finbert_score      = EXCLUDED.finbert_score,
                finbert_signal     = EXCLUDED.finbert_signal,
                mc_signal          = EXCLUDED.mc_signal,
                mc_buy_count       = EXCLUDED.mc_buy_count,
                mc_hold_count      = EXCLUDED.mc_hold_count,
                mc_sell_count      = EXCLUDED.mc_sell_count,
                mc_target_price    = EXCLUDED.mc_target_price,
                mc_current_price   = EXCLUDED.mc_current_price,
                tt_signal          = EXCLUDED.tt_signal,
                tt_analyst_rating  = EXCLUDED.tt_analyst_rating,
                tt_momentum        = EXCLUDED.tt_momentum,
                tv_signal          = EXCLUDED.tv_signal,
                tv_oscillators     = EXCLUDED.tv_oscillators,
                tv_moving_avgs     = EXCLUDED.tv_moving_avgs,
                consensus_signal   = EXCLUDED.consensus_signal,
                conflict_status    = EXCLUDED.conflict_status,
                source_agreement   = EXCLUDED.source_agreement,
                last_updated       = EXCLUDED.last_updated
        """, data)
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB upsert error: {e}")


# ══════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    ensure_validation_table()

    try:
        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, title, score FROM market_news")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
    except Exception as e:
        log.error(f"DB error on CLI run: {e}")
        rows = []

    log.info(f"Found {len(rows)} articles. Starting validation...")
    results = validate_all(rows)

    log.info("══ VALIDATION SUMMARY ══")
    for r in results:
        icon = {"CONFIRMED": "✅", "CONFLICTED": "⚠️", "REVERSED": "🔴", "UNVERIFIED": "❓"}.get(r["conflict_status"], "❓")
        log.info(
            f"  {icon} {r['ticker']:<14} | FinBERT: {r['finbert_signal']:<8} "
            f"| Consensus: {r['consensus_signal']:<8} | Status: {r['conflict_status']}"
        )