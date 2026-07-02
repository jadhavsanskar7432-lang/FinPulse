import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st
# pyrefly: ignore [missing-import]
import plotly.express as px
# pyrefly: ignore [missing-import]
import plotly.graph_objects as go
# pyrefly: ignore [missing-import]
import time
# pyrefly: ignore [missing-import]
import subprocess
# pyrefly: ignore [missing-import]
import sys
# pyrefly: ignore [missing-import]
import io
import os
import base64
import requests
# pyrefly: ignore [missing-import]
import yfinance as yf

import database
from validator import get_validation_summary, validate_all
from config import TICKERS, SECTORS, ALL_TICKER_SYMBOLS, SECTOR_ICONS, get_display_name, get_company_name, get_logo_url
from logo_data import get_ticker_logo_html

# ==========================================
# FIX: Disable ALL progress bars before any model imports.
# ==========================================
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_TQDM"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

st.set_page_config(
    page_title="FinPulse Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)
debug_conn = database.get_connection()
debug_cursor = debug_conn.cursor()
debug_cursor.execute("SELECT current_database(), inet_server_addr(), (SELECT COUNT(*) FROM market_news)")
result = debug_cursor.fetchone()
print(f"🔍 DEBUG DB CHECK: {result}", flush=True)
debug_conn.close()
def silent_flush():
    sys.stderr.flush()

# ==========================================
# 1. THEME ENGINE & STATE PERSISTENCE
# ==========================================
if 'theme' in st.query_params:
    saved_theme = st.query_params['theme']
else:
    saved_theme = 'dark'

if 'theme' not in st.session_state:
    st.session_state.theme = saved_theme
    st.query_params['theme'] = saved_theme

def toggle_theme():
    st.session_state.theme = 'light' if st.session_state.theme == 'dark' else 'dark'
    st.query_params['theme'] = st.session_state.theme

if st.session_state.theme == 'dark':
    c_bg = "#050505"; c_card = "#0a0a0a"; c_text = "#ffffff"; c_subtext = "#a3a3a3"
    c_border = "#262626"; c_header = "linear-gradient(145deg, #0a0a0a 0%, #000000 100%)"
    c_grid = "#171717"; c_btn_hover_bg = "#ffffff"; c_btn_hover_txt = "#000000"; c_gauge_bg = "#1f1f1f"
else:
    c_bg = "#f4f4f5"; c_card = "#ffffff"; c_text = "#000000"; c_subtext = "#52525b"
    c_border = "#d4d4d8"; c_header = "linear-gradient(145deg, #ffffff 0%, #f4f4f5 100%)"
    c_grid = "#e4e4e7"; c_btn_hover_bg = "#000000"; c_btn_hover_txt = "#ffffff"; c_gauge_bg = "#e4e4e7"

# ==========================================
# FIX 1: Split CSS and HTML into separate st.markdown calls to prevent leaking
# ==========================================
st.markdown(
    f"""
    <style>
    [data-testid="stSidebar"], [data-testid="stSidebarNav"], [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
    .stApp {{ background-color: {c_bg} !important; color: {c_text} !important; }}
    [data-testid="stHeader"] {{ background-color: transparent !important; }}
    label[data-testid="stWidgetLabel"] p {{ color: {c_text} !important; font-weight: 700 !important; font-size: 13px !important; }}
    div[data-baseweb="select"] > div {{ background-color: {c_card} !important; border: 1px solid {c_border} !important; }}
    div[data-baseweb="select"] span {{ color: {c_text} !important; }}
    div[data-baseweb="select"] div {{ color: {c_text} !important; }}
    div[data-baseweb="popover"] > div {{ background-color: {c_card} !important; }}
    ul[data-baseweb="menu"] {{ background-color: {c_card} !important; border: 1px solid {c_border} !important; }}
    li[data-baseweb="option"] {{ color: {c_text} !important; background-color: transparent !important; }}
    li[data-baseweb="option"]:hover {{ background-color: {c_bg} !important; }}
    span[data-baseweb="tag"] {{ background-color: {c_bg} !important; border: 1px solid {c_border} !important; }}
    span[data-baseweb="tag"] span {{ color: {c_text} !important; font-weight: 700 !important; }}
    [data-testid="stMetricValue"] > div {{ color: {c_text} !important; }}
    [data-testid="stMetricLabel"] p {{ color: {c_subtext} !important; font-weight: bold !important; }}
    [data-testid="stMetric"] {{ background: rgba(255,255,255,0.03) !important; backdrop-filter: blur(12px) !important; -webkit-backdrop-filter: blur(12px) !important; border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 10px !important; padding: 16px !important; }}
    @keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .terminal-card {{ background-color: {c_card}; border: 1px solid {c_border}; border-radius: 8px; padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05); animation: fadeInUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) both; transition: transform 0.2s ease, border-color 0.2s ease; }}
    .terminal-card:hover {{ transform: translateY(-2px); border-color: {c_text}; }}
    .divergence-card {{ background: rgba(255,255,255,0.03); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px; margin-bottom: 10px; box-shadow: 0 4px 24px rgba(0,0,0,0.2); display: flex; flex-direction: column; gap: 4px; transition: transform 0.2s ease, border-color 0.2s ease; }}
    .divergence-card:hover {{ transform: translateY(-2px); border-color: rgba(255,255,255,0.2); }}
    .clickable-headline {{ color: {c_text} !important; text-decoration: none !important; transition: color 0.15s ease !important; }}
    .clickable-headline:hover {{ color: {c_subtext} !important; text-decoration: underline !important; }}
    .stButton > button {{ background: rgba(255,255,255,0.05) !important; color: {c_text} !important; font-weight: 700 !important; border: 1px solid rgba(255,255,255,0.1) !important; border-radius: 6px !important; padding: 10px 18px !important; transition: all 0.2s ease !important; width: 100%; backdrop-filter: blur(8px); }}
    .stButton > button:hover {{ background-color: {c_btn_hover_bg} !important; color: {c_btn_hover_txt} !important; }}
    div[data-testid="stTabs"] {{ background: rgba(255,255,255,0.03); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); padding: 4px 16px 0px 16px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08); margin-bottom: 25px; }}
    div[data-testid="stTabs"] button [data-testid="stMarkdownContainer"] p {{ font-size: 13px; font-weight: 700; letter-spacing: 0.75px; text-transform: uppercase; color: {c_subtext} !important; }}
    div[data-testid="stTabs"] button[aria-selected="true"] p {{ color: {c_text} !important; }}
    div[data-testid="stTabs"] [data-baseweb="tab-highlight-bar"] {{ background-color: {c_text} !important; height: 3px !important; }}
    [data-baseweb="tab-highlight"] {{ background-color: {c_text} !important; }}
    [data-baseweb="tab-border"] {{ background-color: {c_border} !important; }}
    .brand-header {{ background: linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.02) 100%); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); padding: 30px 35px; border-radius: 16px; margin-bottom: 25px; border: 1px solid rgba(255,255,255,0.1); border-left: 6px solid {c_text}; box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 1px rgba(255,255,255,0.05); position: relative; overflow: hidden; }}
    .brand-title {{ margin: 0; font-size: 34px; font-weight: 900; letter-spacing: 2.5px; color: {c_text}; }}
    .brand-subtitle {{ color: {c_subtext}; margin: 10px 0 0 0; font-size: 12px; text-transform: uppercase; font-weight: 700; letter-spacing: 3px; display: flex; align-items: center; gap: 10px; }}
    .status-dot {{ height: 8px; width: 8px; background-color: #10b981; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #10b981; animation: pulse 2s infinite ease-in-out; }}
    @keyframes pulse {{ 0% {{ opacity: 1; box-shadow: 0 0 8px #10b981; }} 50% {{ opacity: 0.3; box-shadow: 0 0 2px #10b981; }} 100% {{ opacity: 1; box-shadow: 0 0 8px #10b981; }} }}
    .source-badge {{ display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; margin-left: 8px; }}
    .source-newsapi {{ background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); }}
    .source-yahoo {{ background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.3); }}
    .source-cnbc {{ background: rgba(234, 179, 8, 0.15); color: #eab308; border: 1px solid rgba(234, 179, 8, 0.3); }}
    .sector-label {{ color: {c_subtext}; font-size: 13px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 8px; margin-top: 16px; }}
    .glass-card {{ background: rgba(255,255,255,0.04); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.25), inset 0 1px 1px rgba(255,255,255,0.05); transition: transform 0.2s ease, border-color 0.2s ease; }}
    .glass-card:hover {{ transform: translateY(-2px); border-color: rgba(255,255,255,0.18); }}
    div[data-testid="stCheckbox"] label p {{ color: {c_text} !important; font-weight: 700 !important; font-size: 13px !important; }}
    </style>
    """,
    unsafe_allow_html=True
)

# FIX 1: Brand header in its own separate st.markdown call
st.markdown(
    f"""
    <div class="brand-header">
        <h1 class="brand-title">FINPULSE</h1>
        <p class="brand-subtitle"><span class="status-dot"></span>SYSTEM STATE: ACTIVE ENTERPRISE ENGINE</p>
    </div>
    """,
    unsafe_allow_html=True
)

# ==========================================
# 2. CACHING & DEEP LEARNING ENGINE
# ==========================================
@st.cache_data(ttl=300)
def fetch_validation_data():
    return get_validation_summary()


@st.cache_data(ttl=30)
def fetch_database_records():
    local_articles = []
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, title, summary, url, time_published, sentiment, score, source FROM market_news ORDER BY id DESC")
        rows = cursor.fetchall()
        for row in rows:
            local_articles.append(dict(row))
        conn.close()
    except Exception as e:
        st.error(f"Database error: {e}")
    return local_articles

def get_trade_signal(sentiment, price_diff):
    if sentiment > 0.3 and price_diff < -1.0: return "STRONG BUY", "#10b981", "High positive news volume, but price is dipping (Value Buy)."
    elif sentiment > 0.15: return "BUY", "#34d399", "General positive market sentiment trending upward."
    elif sentiment < -0.3 and price_diff > 1.0: return "STRONG SELL", "#ef4444", "Heavy negative news, but price is artificially high (Correction imminent)."
    elif sentiment < -0.15: return "SELL", "#f87171", "Negative sentiment accumulation detected."
    else: return "HOLD", "#c8ff00", "Insufficient signal divergence. Await clearer data."

# FIX 2: Daily timeframe uses period="5d" to avoid empty data after market close
@st.cache_data(ttl=60)
def fetch_stock_history(ticker, period="2d", interval="1d"):
    try:
        stock = yf.Ticker(ticker)
        return stock.history(period=period, interval=interval, prepost=True)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_fundamentals(ticker):
    try:
        info = yf.Ticker(ticker).info
        is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")
        currency_sym = "₹" if is_indian else "$"

        market_cap_raw = info.get("marketCap")
        if market_cap_raw:
            if market_cap_raw >= 1_000_000_000_000:
                market_cap = f"{currency_sym}{market_cap_raw / 1_000_000_000_000:.2f}T"
            elif market_cap_raw >= 1_000_000_000:
                market_cap = f"{currency_sym}{market_cap_raw / 1_000_000_000:.2f}B"
            elif market_cap_raw >= 1_000_000:
                market_cap = f"{currency_sym}{market_cap_raw / 1_000_000:.2f}M"
            else:
                market_cap = f"{currency_sym}{market_cap_raw:,.0f}"
        else:
            market_cap = "N/A"

        eps = info.get("trailingEps")
        eps_str = f"{currency_sym}{eps:.2f}" if eps is not None else "N/A"

        roe = info.get("returnOnEquity")
        roe_str = f"{roe * 100:.2f}%" if roe is not None else "N/A"

        pb = info.get("priceToBook")
        pb_str = f"{pb:.2f}" if pb is not None else "N/A"

        pe = info.get("trailingPE")
        pe_str = f"{pe:.2f}" if pe is not None else "N/A"

        div_yield = info.get("dividendYield")
        div_str = f"{div_yield * 100:.2f}%" if div_yield is not None else "N/A"

        return {
            "Market Cap":        market_cap,
            "EPS (TTM)":         eps_str,
            "ROE":               roe_str,
            "P/B Ratio":         pb_str,
            "P/E Ratio (TTM)":   pe_str,
            "Dividend Yield":    div_str,
        }
    except Exception:
        return {
            "Market Cap": "N/A", "EPS (TTM)": "N/A", "ROE": "N/A",
            "P/B Ratio": "N/A", "P/E Ratio (TTM)": "N/A", "Dividend Yield": "N/A",
        }

def get_source_badge(source):
    badges = {
        "newsapi": '<span class="source-badge source-newsapi">📡 NewsAPI</span>',
        "yahoo": '<span class="source-badge source-yahoo">📊 Yahoo</span>',
        "cnbc": '<span class="source-badge source-cnbc">📺 CNBC</span>',
    }
    return badges.get(source, f'<span class="source-badge">{source}</span>')

def _norm(sig: str) -> str:
    if not sig or sig == "N/A": return None
    s = sig.upper()
    if any(k in s for k in ["BUY", "BULLISH", "LONG", "OUTPERFORM"]): return "BULLISH"
    if any(k in s for k in ["SELL", "BEARISH", "SHORT", "UNDERPERFORM"]): return "BEARISH"
    return "NEUTRAL"

def render_validation_tab(articles, c_bg, c_card, c_text, c_subtext, c_border, c_grid):
    def render_html(raw_html):
        clean_html = " ".join(raw_html.split())
        st.markdown(clean_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    render_html(f"""
    <div style="background:{c_card}; border:1px solid {c_border}; border-radius:8px; padding:16px 24px; margin:10px 0 20px 0;">
        <div style="color:{c_subtext}; font-size:10px; font-weight:800; letter-spacing:2px; text-transform:uppercase; margin-bottom:12px;">Signal Legend</div>
        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:10px;">
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #10b981; border-radius:6px; padding:10px 14px;">
                <div style="color:#10b981; font-size:13px; font-weight:800; margin-bottom:3px;">● BULLISH</div>
                <div style="color:{c_subtext}; font-size:11px;">Analysts expect price to rise</div>
            </div>
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #ef4444; border-radius:6px; padding:10px 14px;">
                <div style="color:#ef4444; font-size:13px; font-weight:800; margin-bottom:3px;">● BEARISH</div>
                <div style="color:{c_subtext}; font-size:11px;">Analysts expect price to fall</div>
            </div>
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #f59e0b; border-radius:6px; padding:10px 14px;">
                <div style="color:#f59e0b; font-size:13px; font-weight:800; margin-bottom:3px;">● NEUTRAL</div>
                <div style="color:{c_subtext}; font-size:11px;">No strong directional signal</div>
            </div>
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #10b981; border-radius:6px; padding:10px 14px;">
                <div style="color:#10b981; font-size:13px; font-weight:800; margin-bottom:3px;">✅ CONFIRMED</div>
                <div style="color:{c_subtext}; font-size:11px;">AI and analysts agree</div>
            </div>
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #f59e0b; border-radius:6px; padding:10px 14px;">
                <div style="color:#f59e0b; font-size:13px; font-weight:800; margin-bottom:3px;">⚠️ CONFLICTED</div>
                <div style="color:{c_subtext}; font-size:11px;">Mixed signals — wait for clarity</div>
            </div>
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #ef4444; border-radius:6px; padding:10px 14px;">
                <div style="color:#ef4444; font-size:13px; font-weight:800; margin-bottom:3px;">🔴 REVERSED</div>
                <div style="color:{c_subtext}; font-size:11px;">AI is wrong — trust analysts</div>
            </div>
            <div style="background:{c_bg}; border:1px solid {c_border}; border-left:3px solid #6b7280; border-radius:6px; padding:10px 14px;">
                <div style="color:#6b7280; font-size:13px; font-weight:800; margin-bottom:3px;">❓ UNVERIFIED</div>
                <div style="color:{c_subtext}; font-size:11px;">No analyst data available yet</div>
            </div>
        </div>
    </div>
""")

    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])
    with ctrl1:
        filter_status = st.selectbox("FILTER BY CONFLICT STATUS:", ["ALL", "⚠️ CONFLICTED", "🔴 REVERSED", "✅ CONFIRMED", "❓ UNVERIFIED"], key="val_filter_status")
    with ctrl2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("RE-VALIDATE ALL", key="btn_revalidate"):
            with st.spinner("Running full validator across all tickers..."):
                validate_all(articles)
            st.cache_data.clear()
            st.success("Validation complete! Refreshing...")
            st.rerun()
    with ctrl3:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        # FIX 3: Checkbox label visibility via CSS already handled globally above
        auto_refresh = st.checkbox("Auto-refresh (5 min)", value=False, key="val_auto")

    st.markdown("---")
    val_rows = fetch_validation_data()

    if not val_rows:
        st.info("No validation data yet. Click **RE-VALIDATE ALL** above to run the first check.")
        return

    total       = len(val_rows)
    confirmed   = sum(1 for r in val_rows if r["conflict_status"] == "CONFIRMED")
    conflicted  = sum(1 for r in val_rows if r["conflict_status"] == "CONFLICTED")
    reversed_   = sum(1 for r in val_rows if r["conflict_status"] == "REVERSED")
    unverified  = sum(1 for r in val_rows if r["conflict_status"] == "UNVERIFIED")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("✅ CONFIRMED",  confirmed,  help="FinBERT agrees with trusted analysts")
    k2.metric("⚠️ CONFLICTED", conflicted, help="Partial disagreement — review manually")
    k3.metric("🔴 REVERSED",   reversed_,  help="FinBERT is OPPOSITE to analyst consensus")
    k4.metric("Total Tickers", total)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    status_map = {
        "ALL":            val_rows,
        "⚠️ CONFLICTED":  [r for r in val_rows if r["conflict_status"] == "CONFLICTED"],
        "🔴 REVERSED":    [r for r in val_rows if r["conflict_status"] == "REVERSED"],
        "✅ CONFIRMED":   [r for r in val_rows if r["conflict_status"] == "CONFIRMED"],
        "❓ UNVERIFIED":  [r for r in val_rows if r["conflict_status"] == "UNVERIFIED"],
    }
    display_rows = status_map.get(filter_status, val_rows)

    if not display_rows:
        st.warning(f"No tickers match filter: {filter_status}")
        return

    render_html(f"<span style='color:{c_subtext}; font-size:12px; font-weight:bold;'>SHOWING {len(display_rows)} TICKER(S)</span>")
    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

    STATUS_COLORS = {"CONFIRMED": "#10b981", "CONFLICTED": "#f59e0b", "REVERSED": "#ef4444", "UNVERIFIED": "#6b7280"}
    STATUS_ICONS = {"CONFIRMED": "✅", "CONFLICTED": "⚠️", "REVERSED": "🔴", "UNVERIFIED": "❓"}
    SIGNAL_COLORS = {"BULLISH": "#10b981", "BEARISH": "#ef4444", "NEUTRAL": "#c8ff00", None: "#6b7280"}

    for row in display_rows:
        status      = row.get("conflict_status", "UNVERIFIED")
        border_color = STATUS_COLORS.get(status, "#6b7280")
        icon        = STATUS_ICONS.get(status, "❓")
        ticker      = row.get("ticker", "")
        company     = row.get("company_name", ticker)
        fb_score    = row.get("finbert_score")
        fb_sig      = row.get("finbert_signal", "NEUTRAL")
        consensus   = row.get("consensus_signal", "NEUTRAL")
        agreement   = row.get("source_agreement", 0)
        updated     = row.get("last_updated", "")

        fb_color     = SIGNAL_COLORS.get(fb_sig, "#6b7280")
        cons_color   = SIGNAL_COLORS.get(consensus, "#6b7280")

        mc_sig  = row.get("mc_signal")  or "N/A"
        tt_sig  = row.get("tt_signal")  or "N/A"
        tv_sig  = row.get("tv_signal")  or "N/A"

        is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")

        mc_buys  = row.get("mc_buy_count")
        mc_holds = row.get("mc_hold_count")
        mc_sells = row.get("mc_sell_count")
        mc_tp    = row.get("mc_target_price")
        tt_rat   = row.get("tt_analyst_rating") or "N/A"
        tt_mom   = row.get("tt_momentum") or "N/A"
        tv_osc   = row.get("tv_oscillators") or "N/A"
        tv_ma    = row.get("tv_moving_avgs") or "N/A"

        mc_analyst_line = ""
        if mc_buys is not None:
            mc_analyst_line = f"<span style='color:#10b981;'>{mc_buys} Buy</span> · <span style='color:{c_subtext};'>{mc_holds} Hold</span> · <span style='color:#ef4444;'>{mc_sells} Sell</span>"
            if mc_tp: mc_analyst_line += f" · <span style='color:{c_subtext};'>Target ₹{mc_tp:,.0f}</span>"

        recommendation_box = ""
        if status == "REVERSED":
            recommendation_box = f"<div style='background:rgba(239,68,68,0.08); border:1px solid #ef4444; border-radius:6px; padding:10px 14px; margin-top:10px;'><span style='color:#ef4444; font-size:12px; font-weight:800;'>🔴 ACTION REQUIRED: FinBERT is OPPOSITE to analyst consensus. Trust the analysts — override AI signal with: <b>{consensus}</b></span></div>"
        elif status == "CONFLICTED":
            recommendation_box = f"<div style='background:rgba(245,158,11,0.08); border:1px solid #f59e0b; border-radius:6px; padding:10px 14px; margin-top:10px;'><span style='color:#f59e0b; font-size:12px; font-weight:800;'>⚠️ MIXED SIGNALS: AI and analysts partially disagree. Recommended action: <b>HOLD / Wait for clarity.</b> Consensus points to <b>{consensus}</b>.</span></div>"

        logo_html_v = get_ticker_logo_html(ticker, size=28)
        render_html(f"""
            <div style="background:{c_card}; border:1px solid {c_border}; border-left:5px solid {border_color}; border-radius:8px; padding:18px 22px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div style="display:flex; align-items:center;">{logo_html_v}<span style="color:{c_text}; font-size:16px; font-weight:800;">{icon} {company}</span><span style="color:{c_subtext}; font-size:12px; margin-left:10px;">{ticker}</span></div>
                    <div style="text-align:right;"><span style="color:{border_color}; font-size:13px; font-weight:800;">{status}</span><br><span style="color:{c_subtext}; font-size:10px;">{agreement}/3 sources agree · {str(updated)[:16]}</span></div>
                </div>
                <div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; margin-bottom:10px;">
                <div style="background:{c_bg}; border:1px solid {c_border}; border-radius:6px; padding:10px; text-align:center;"><div style="color:{c_subtext}; font-size:9px; font-weight:700; margin-bottom:4px;">🧠 FINBERT AI</div><div style="color:{fb_color}; font-size:14px; font-weight:900;">{fb_sig}</div><div style="color:{c_subtext}; font-size:10px;">{f'{fb_score:+.2f}' if fb_score is not None else 'N/A'}</div></div>
                <div style="background:{c_bg}; border:1px solid {c_border}; border-radius:6px; padding:10px; text-align:center;"><div style="color:{c_subtext}; font-size:9px; font-weight:700; margin-bottom:4px;">{'📊 MONEYCONTROL' if is_indian else '📊 YAHOO FINANCE'}</div><div style="color:{SIGNAL_COLORS.get(_norm(mc_sig), c_subtext)}; font-size:14px; font-weight:900;">{mc_sig}</div><div style="color:{c_subtext}; font-size:10px;">{mc_analyst_line if mc_analyst_line else '—'}</div></div>
                <div style="background:{c_bg}; border:1px solid {c_border}; border-radius:6px; padding:10px; text-align:center;"><div style="color:{c_subtext}; font-size:9px; font-weight:700; margin-bottom:4px;">{'🎯 TICKERTAPE' if is_indian else '🔍 STOCKANALYSIS'}</div><div style="color:{SIGNAL_COLORS.get(_norm(tt_sig), c_subtext)}; font-size:14px; font-weight:900;">{tt_sig}</div><div style="color:{c_subtext}; font-size:10px;">{'N/A for US stocks' if not is_indian and tt_sig == 'N/A' else f'{tt_rat} · {tt_mom}'}</div></div>
                <div style="background:{c_bg}; border:1px solid {c_border}; border-radius:6px; padding:10px; text-align:center;"><div style="color:{c_subtext}; font-size:9px; font-weight:700; margin-bottom:4px;">📈 TRADINGVIEW</div><div style="color:{SIGNAL_COLORS.get(_norm(tv_sig), c_subtext)}; font-size:14px; font-weight:900;">{tv_sig}</div><div style="color:{c_subtext}; font-size:10px;">OSC: {tv_osc} · MA: {tv_ma}</div></div>
                <div style="background:{c_bg}; border:2px solid {border_color}; border-radius:6px; padding:10px; text-align:center;"><div style="color:{c_subtext}; font-size:9px; font-weight:700; margin-bottom:4px;">🏆 CONSENSUS</div><div style="color:{cons_color}; font-size:14px; font-weight:900;">{consensus}</div><div style="color:{c_subtext}; font-size:10px;">{agreement}/3 agree</div></div>
                </div>
                {recommendation_box}
            </div>
        """)

    if len(val_rows) >= 3:
        st.markdown("---")
        st.markdown("##### 📊 Conflict Status Breakdown")

        status_counts = {"CONFIRMED": confirmed, "CONFLICTED": conflicted, "REVERSED": reversed_, "UNVERIFIED": unverified}
        labels  = [k for k, v in status_counts.items() if v > 0]
        values  = [v for k, v in status_counts.items() if v > 0]
        colors  = [STATUS_COLORS[k] for k in labels]

        fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.55, marker=dict(colors=colors, line=dict(color=c_bg, width=2)), textinfo="label+value", textfont=dict(color=c_text, size=12, family="Courier New"))])
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10, b=10, l=10, r=10), height=220, showlegend=False, annotations=[dict(text="SIGNAL<br>HEALTH", x=0.5, y=0.5, font_size=13, font_color=c_subtext, showarrow=False, font_family="Courier New")])

        col_chart, col_tip = st.columns([1, 2])
        with col_chart:
            st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})
        with col_tip:
            render_html(f"<div style='margin-top:40px; color:{c_subtext}; font-size:13px; line-height:2;'><b style='color:{c_text};'>How to use this:</b><br>✅ <b>CONFIRMED</b> — AI + analysts agree. Higher confidence to act.<br>⚠️ <b>CONFLICTED</b> — Mixed signals. Wait or reduce position size.<br>🔴 <b>REVERSED</b> — AI is wrong. Use the <b>Consensus signal</b> instead.<br>❓ <b>UNVERIFIED</b> — No analyst data scraped yet for this ticker.</div>")


articles = fetch_database_records()
all_trackers = ALL_TICKER_SYMBOLS
tab_home, tab_news, tab_analytics, tab_strategy, tab_validation = st.tabs([" HOME ", " NEWS ", " ANALYTICS ", " STRATEGY ", " VALIDATION "])

# ==========================================
# 3. HOME TAB
# ==========================================
with tab_home:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
    with ctrl_col1:
        selected_ticker = st.selectbox("TRACKING DATA FILTER", ["ALL Tickers"] + all_trackers, label_visibility="visible")
    with ctrl_col2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        st.button("THEME", on_click=toggle_theme, key="btn_theme")
    with ctrl_col3:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("RE-FETCH", key="btn_refetch"):
            st.cache_data.clear()
            subprocess.run([sys.executable, "news_fetcher.py", "--once"])
            st.rerun()

    st.markdown("---")
    filtered_articles = [a for a in articles if selected_ticker == "ALL Tickers" or a.get("ticker") == selected_ticker]
    scored_articles = [a for a in filtered_articles if a.get("score") is not None]
    total_news = len(filtered_articles)
    avg_score = sum([item.get("score", 0) for item in scored_articles]) / len(scored_articles) if scored_articles else 0.0

    # ── Sector Performance ────────────────────────────────────────────────────
    st.markdown("### Sector Performance — Last 7 Days")
    st.markdown(f"<span style='color:{c_subtext}; font-size:12px;'>Which sectors gained or lost the most this week.</span>", unsafe_allow_html=True)

    sector_perf = {}
    for sector_name, sector_tickers in SECTORS.items():
        changes = []
        for t in sector_tickers:
            hist = fetch_stock_history(t, period="7d", interval="1d")
            if not hist.empty and 'Close' in hist.columns:
                clean = hist.dropna(subset=['Close'])
                if len(clean) >= 2:
                    pct = ((clean['Close'].iloc[-1] - clean['Close'].iloc[0]) / clean['Close'].iloc[0]) * 100
                    changes.append(pct)
        sector_perf[sector_name] = sum(changes) / len(changes) if changes else 0.0

    sorted_sectors = sorted(sector_perf.items(), key=lambda x: x[1], reverse=True)
    sector_cols = st.columns(len(sorted_sectors))
    for idx, (sector_name, perf) in enumerate(sorted_sectors):
        with sector_cols[idx]:
            color = "#10b981" if perf > 0 else "#ef4444"
            sign = "+" if perf > 0 else ""
            rank = idx + 1
            rank_badge = "#1" if rank == 1 else ("#2" if rank == 2 else ("#3" if rank == 3 else f"#{rank}"))
            icon = SECTOR_ICONS.get(sector_name, "")
            st.markdown(f"""
                <div style="background:{c_card}; border:1px solid {c_border}; border-top:4px solid {color}; border-radius:8px; padding:16px; text-align:center;">
                    <div style="font-size:20px; margin-bottom:4px;">{rank_badge}</div>
                    <div style="color:{c_subtext}; font-size:10px; font-weight:800; letter-spacing:1px; text-transform:uppercase; margin-bottom:6px;">{icon} {sector_name}</div>
                    <div style="color:{color}; font-size:24px; font-weight:900;">{sign}{perf:.2f}%</div>
                    <div style="color:{c_subtext}; font-size:10px; margin-top:4px;">7-day avg return</div>
                </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)

    # ── KPI Row ───────────────────────────────────────────────────────────────
    kpi_left, kpi_right = st.columns([2.5, 1.5])
    with kpi_left:
        st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
        sub_kpi1, sub_kpi2 = st.columns(2)
        sub_kpi1.metric(label="HEADLINES PROCESSED", value=total_news)
        sub_kpi2.metric(label="ACTIVE TARGET TICKER", value=get_display_name(selected_ticker) if selected_ticker != "ALL Tickers" else "ALL")

        st.markdown("<div style='margin-top:25px;'></div>", unsafe_allow_html=True)
        sub_kpi3, sub_kpi4 = st.columns(2)

        if selected_ticker != "ALL Tickers":
            hist = fetch_stock_history(selected_ticker, period="5d", interval="1d")
            if not hist.empty and 'Close' in hist.columns:
                clean_hist = hist.dropna(subset=['Close'])
                if len(clean_hist) >= 2:
                    current_price = clean_hist['Close'].iloc[-1]
                    prev_close = clean_hist['Close'].iloc[-2]
                    price_change = current_price - prev_close
                    currency = "₹" if ".NS" in selected_ticker else "$"
                    sub_kpi3.metric(label="LIVE ASSET PRICE", value=f"{currency}{current_price:.2f}", delta=f"{currency}{price_change:.2f}")
                elif len(clean_hist) == 1:
                    current_price = clean_hist['Close'].iloc[-1]
                    currency = "₹" if ".NS" in selected_ticker else "$"
                    sub_kpi3.metric(label="LIVE ASSET PRICE", value=f"{currency}{current_price:.2f}")
                else:
                    sub_kpi3.metric(label="LIVE ASSET PRICE", value="AWAITING DATA")
            else:
                sub_kpi3.metric(label="LIVE ASSET PRICE", value="AWAITING DATA")
        else:
            sub_kpi3.metric(label="LIVE ASSET PRICE", value="-")

    with kpi_right:
        # ── Portfolio Weekly Change Gauge ───────────────────────────────────
        weekly_changes = {}
        for t in all_trackers:
            hist_w = fetch_stock_history(t, period="7d", interval="1d")
            if not hist_w.empty and 'Close' in hist_w.columns:
                clean_w = hist_w.dropna(subset=['Close'])
                if len(clean_w) >= 2:
                    pct_w = ((clean_w['Close'].iloc[-1] - clean_w['Close'].iloc[0]) / clean_w['Close'].iloc[0]) * 100
                    weekly_changes[t] = float(pct_w)

        if weekly_changes:
            portfolio_avg = sum(weekly_changes.values()) / len(weekly_changes)
        else:
            portfolio_avg = 0.0

        portfolio_avg = round(portfolio_avg, 2)
        gauge_range = round(max(10, min(20, abs(portfolio_avg) * 2 + 5)), 2)

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=portfolio_avg, domain={'x': [0, 1], 'y': [0, 1]},
            number={'font': {'color': c_text, 'family': 'Courier New', 'size': 24}, 'valueformat': "+.2f", 'suffix': "%"},
            gauge={
                'axis': {
                    'range': [-gauge_range, gauge_range],
                    'tickwidth': 1,
                    'tickcolor': c_subtext,
                    'tickfont': {'color': c_text, 'size': 11},
                    'tickvals': [-gauge_range, -gauge_range/2, 0, gauge_range/2, gauge_range],
                    'ticktext': ['BEAR', 'WEAK', 'FLAT', 'STRONG', 'BULL']
                },
                'bar': {'color': c_text, 'thickness': 0.25}, 'bgcolor': c_gauge_bg, 'borderwidth': 1, 'bordercolor': c_border,
                'steps': [
                    {'range': [-gauge_range, -gauge_range * 0.15], 'color': 'rgba(239, 68, 68, 0.25)'},
                    {'range': [-gauge_range * 0.15, gauge_range * 0.15], 'color': 'rgba(200, 255, 0, 0.2)'},
                    {'range': [gauge_range * 0.15, gauge_range], 'color': 'rgba(83, 255, 4, 0.2)'}
                ]
            }
        ))
        fig_gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=10, b=10), height=160)
        st.plotly_chart(fig_gauge, use_container_width=True, config={'displayModeBar': False}, theme=None)

        st.markdown(
            f"<div style='text-align:center; color:{c_subtext}; font-size:11px; margin-top:-8px; margin-bottom:8px;'>"
            f"Average 7-day price change across your {len(weekly_changes)} tracked stocks. "
            f"Positive = portfolio gained this week, negative = portfolio lost value."
            f"</div>",
            unsafe_allow_html=True
        )

        if weekly_changes:
            best_t = max(weekly_changes, key=weekly_changes.get)
            worst_t = min(weekly_changes, key=weekly_changes.get)
            gl_col1, gl_col2 = st.columns(2)
            gl_col1.markdown(
                f"<div style='background:{c_card}; border:1px solid {c_border}; border-radius:8px; padding:10px 12px;'>"
                f"<div style='color:{c_subtext}; font-size:10px; font-weight:800; letter-spacing:1px; text-transform:uppercase;'>Top gainer (7d)</div>"
                f"<div style='color:{c_text}; font-size:14px; font-weight:900;'>{get_display_name(best_t)} "
                f"<span style='color:#10b981;'>{'+' if weekly_changes[best_t] >= 0 else ''}{weekly_changes[best_t]:.2f}%</span></div></div>",
                unsafe_allow_html=True
            )
            gl_col2.markdown(
                f"<div style='background:{c_card}; border:1px solid {c_border}; border-radius:8px; padding:10px 12px;'>"
                f"<div style='color:{c_subtext}; font-size:10px; font-weight:800; letter-spacing:1px; text-transform:uppercase;'>Top loser (7d)</div>"
                f"<div style='color:{c_text}; font-size:14px; font-weight:900;'>{get_display_name(worst_t)} "
                f"<span style='color:#ef4444;'>{weekly_changes[worst_t]:.2f}%</span></div></div>",
                unsafe_allow_html=True
            )

    st.markdown("---")

    # ── Sentiment vs Price Divergence ─────────────────────────────────────────
    st.markdown("### Sentiment vs Price Divergence")
    st.markdown(f"<span style='color: {c_subtext}; font-size: 12px;'>Scans for contradictory market action where live price deviates from media sentiment.</span>", unsafe_allow_html=True)
    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)

    for sector_name, sector_tickers in SECTORS.items():
        sector_icon = SECTOR_ICONS.get(sector_name, "📊")
        st.markdown(f'<div class="sector-label">{sector_icon} {sector_name}</div>', unsafe_allow_html=True)
        tape_cols = st.columns(len(sector_tickers))
        for idx, t in enumerate(sector_tickers):
            with tape_cols[idx]:
                t_arts = [a for a in articles if a.get("ticker") == t and a.get("score") is not None]
                t_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
                stock_data = fetch_stock_history(t, period="5d", interval="1d")

                c_val, pct_diff = 0.0, 0.0
                price_display, pct_display = "N/A", f"<span style='color: {c_subtext};'>--%</span>"

                if not stock_data.empty and 'Close' in stock_data.columns:
                    clean_data = stock_data.dropna(subset=['Close'])
                    if len(clean_data) >= 2:
                        c_val = clean_data['Close'].iloc[-1]
                        p_val = clean_data['Close'].iloc[-2]
                        pct_diff = ((c_val - p_val) / p_val) * 100
                        cur = "₹" if ".NS" in t else "$"
                        price_display = f"{cur}{c_val:.2f}"
                        pct_color = "#10b981" if pct_diff > 0 else "#ef4444"
                        pct_sign = "+" if pct_diff > 0 else ""
                        pct_display = f"<span style='color: {pct_color}; font-weight:bold; font-size:14px;'>{pct_sign}{pct_diff:.2f}%</span>"

                sent_color = "#10b981" if t_sent > 0 else ("#ef4444" if t_sent < 0 else c_subtext)
                sent_sign = "+" if t_sent > 0 else ""

                warning_html = ""
                if pct_diff < -0.5 and t_sent > 0.15:
                    warning_html = "<div style='border: 1px solid #eab308; color: #eab308; background: rgba(234, 179, 8, 0.05); font-size: 10px; font-weight: bold; padding: 4px; margin-top: 8px; border-radius: 4px; text-align: center;'>⚠️ News positive, price falling</div>"
                elif pct_diff > 0.5 and t_sent < -0.15:
                    warning_html = "<div style='border: 1px solid #eab308; color: #eab308; background: rgba(234, 179, 8, 0.05); font-size: 10px; font-weight: bold; padding: 4px; margin-top: 8px; border-radius: 4px; text-align: center;'>⚠️ News negative, price rising</div>"

                logo_tag = get_ticker_logo_html(t, size=26)
                disp_name = get_display_name(t)
                st.markdown(
                    f"""
                    <div class="divergence-card">
                        <div style="display:flex; align-items:center;">{logo_tag}<span style="font-size:14px; font-weight:800; color:{c_text};">{disp_name}</span></div>
                        <span style="font-size: 18px; font-weight: 700; color: {c_text};">{price_display}</span>
                        {pct_display}
                        <span style="font-size: 11px; color: {sent_color}; margin-top: 2px;">sentiment {sent_sign}{t_sent:.2f}</span>
                        {warning_html}
                    </div>
                    """, unsafe_allow_html=True
                )

    st.markdown("---")

    # ── Anomalies Matrix ──────────────────────────────────────────────────────
    st.markdown(f"### Anomalies Matrix")
    if not filtered_articles:
        st.info("No active records.")
    else:
        for item in filtered_articles[:3]:
            raw_score = item.get("score")
            is_scored = raw_score is not None
            score = raw_score if is_scored else 0.0
            color = "#53ff04" if score > 0.05 else ("#ef4444" if score < -0.05 else "#c8ff00")
            score_label = f"{score:+.2f}" if is_scored else "PENDING"
            source_badge = get_source_badge(item.get("source", ""))
            st.markdown(
                f"""
                <div class="terminal-card" style="border-left: 4px solid {color} !important;">
                    <span style="color:{color}; font-size:11px; font-weight:bold;">SCORE: {score_label} | {item.get('ticker')}</span>{source_badge}
                    <h5 style="margin-top:5px; margin-bottom:0px;"><a class="clickable-headline" href="{item.get('url', '#')}" target="_blank">{item.get('title')}</a></h5>
                </div>
                """, unsafe_allow_html=True
            )

# ==========================================
# 4. NEWS TAB
# ==========================================
with tab_news:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    if not articles:
        st.info("Awaiting background ingestion...")
    else:
        try:
            article_dates = [pd.to_datetime(a['time_published']).date() for a in articles if a.get('time_published')]
            db_min_date = min(article_dates) if article_dates else pd.Timestamp.now().date()
            db_max_date = max(article_dates) if article_dates else pd.Timestamp.now().date()
        except:
            db_min_date = pd.Timestamp.now().date()
            db_max_date = pd.Timestamp.now().date()

        news_col1, news_col2, news_col3 = st.columns([2, 1, 1])
        with news_col1:
            news_ticker = st.selectbox("FILTER BY TICKER:", ["ALL Tickers"] + all_trackers, key="news_tab_ticker")
        with news_col2:
            start_date = st.date_input("START DATE", value=db_min_date, min_value=db_min_date, max_value=db_max_date, key="news_start")
        with news_col3:
            end_date = st.date_input("END DATE", value=db_max_date, min_value=db_min_date, max_value=db_max_date, key="news_end")

        st.markdown("---")
        filtered_news_tab = []
        for item in articles:
            match_ticker = (news_ticker == "ALL Tickers") or (item.get("ticker") == news_ticker)
            match_date = True
            if item.get("time_published"):
                try:
                    item_date = pd.to_datetime(item["time_published"]).date()
                    match_date = (start_date <= item_date <= end_date)
                except:
                    pass
            if match_ticker and match_date:
                filtered_news_tab.append(item)

        if not filtered_news_tab:
            st.warning("No articles match your current filter criteria.")
        else:
            st.markdown(f"<span style='color:{c_subtext}; font-size:12px; font-weight:bold;'>SHOWING {len(filtered_news_tab)} RESULT(S)</span>", unsafe_allow_html=True)
            st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
            for item in filtered_news_tab:
                score = item.get("score", 0) if item.get("score") is not None else 0.0
                color = "#53ff04" if score > 0.05 else ("#ef4444" if score < -0.05 else "#c8ff00")
                source_badge = get_source_badge(item.get("source", ""))
                st.markdown(
                    f"""
                    <div class="terminal-card" style="border-left: 5px solid {color} !important;">
                        <span style="color:{color}; font-size:11px; font-weight:bold;">FINBERT SCORING: {score:.2f} | {item.get('ticker')}</span>{source_badge}
                        <h4 style="margin-top:5px;"><a class="clickable-headline" href="{item.get('url', '#')}" target="_blank">{item.get('title')}</a></h4>
                        <p style="color:{c_subtext}; font-size:13px; line-height:1.5;">{item.get('summary', '')}</p>
                        <span style="color:{c_subtext}; font-size:11px;">⏱️ {item.get('time_published')}</span>
                    </div>
                    """, unsafe_allow_html=True
                )

# ==========================================
# 5. ANALYTICS TAB
# ==========================================
with tab_analytics:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        search_ticker = st.selectbox("SELECT TARGET ASSET:", all_trackers)
    with col_t2:
        selected_timeframe = st.selectbox(
            "SELECT TIMEFRAME:",
            options=["Daily", "Weekly", "Monthly", "3 Months", "6 Months", "12 Months"],
            index=1
        )

    # FIX 2: Daily uses period="5d" + interval="15m" to avoid empty chart after market close
    timeframe_map = {
        "Daily":     {"period": "5d",  "interval": "15m", "days_back": 1,   "resample": "15min"},
        "Weekly":    {"period": "5d",  "interval": "1h",  "days_back": 5,   "resample": "h"},
        "Monthly":   {"period": "1mo", "interval": "1d",  "days_back": 30,  "resample": "D"},
        "3 Months":  {"period": "3mo", "interval": "1d",  "days_back": 90,  "resample": "D"},
        "6 Months":  {"period": "6mo", "interval": "1d",  "days_back": 180, "resample": "D"},
        "12 Months": {"period": "1y",  "interval": "1d",  "days_back": 365, "resample": "D"}
    }

    tf_config = timeframe_map[selected_timeframe]

    if search_ticker:
        ticker_articles = [a for a in articles if a.get("ticker") == search_ticker and a.get("score") is not None]

        if len(ticker_articles) < 2:
            st.info("Awaiting more database records to populate sentiment visuals.")
        else:
            hist = fetch_stock_history(search_ticker, period=tf_config["period"], interval=tf_config["interval"])

            if hist.empty:
                st.warning("Live market data temporarily unavailable from Yahoo Finance API.")
            else:
                hist.reset_index(inplace=True)
                time_col = 'Datetime' if 'Datetime' in hist.columns else 'Date'
                if hist[time_col].dt.tz is not None:
                    hist[time_col] = hist[time_col].dt.tz_localize(None)

                chronological_data = sorted(ticker_articles, key=lambda x: str(x.get("time_published", "")))
                raw_df = pd.DataFrame({
                    "Time": pd.to_datetime([item.get("time_published") for item in chronological_data], errors="coerce"),
                    "Sentiment Index": [item.get("score", 0) for item in chronological_data]
                }).dropna(subset=["Time"])

                if raw_df['Time'].dt.tz is not None:
                    raw_df['Time'] = raw_df['Time'].dt.tz_localize(None)

                alignment_df = raw_df.groupby(raw_df['Time'].dt.floor(tf_config["resample"]))['Sentiment Index'].mean().reset_index()
                alignment_df['Smoothed Sentiment'] = alignment_df['Sentiment Index'].rolling(window=3, min_periods=1).mean()

                now = pd.Timestamp.utcnow().tz_localize(None)

                # FIX 4: Daily needs a wider window to catch last trading session
                if selected_timeframe == "Daily":
                    start_time = now - pd.Timedelta(days=2)
                else:
                    start_time = now - pd.Timedelta(days=tf_config["days_back"])

                # FIX 4: Do NOT filter alignment_df by start_time — let Plotly handle axis range
                alignment_df = alignment_df[(alignment_df['Time'] >= start_time)]
                hist = hist[(hist[time_col] >= start_time)]
                master_x_range = [start_time, now]
                c1, c2 = st.columns(2)

                with c1:
                    st.markdown(f"##### 📊 AGGREGATED SENTIMENT INDEX")
                    fig1 = go.Figure()
                    fig1.add_trace(go.Scatter(x=alignment_df["Time"], y=alignment_df["Sentiment Index"], mode='lines', name='Raw Pulse', line=dict(color=c_subtext, width=1, dash='dot', shape='spline')))
                    fig1.add_trace(go.Scatter(x=alignment_df["Time"], y=alignment_df["Smoothed Sentiment"], mode='lines', name='3-Pd Trend', line=dict(color=c_text, width=3, shape='spline'), fill='tozeroy', fillcolor='rgba(128, 128, 128, 0.05)'))
                    fig1.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=c_text, size=12, family="Courier New, monospace"),
                        margin=dict(l=40, r=40, t=20, b=40),
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        xaxis=dict(autorange=True)
                    )
                    fig1.update_xaxes(range=master_x_range, showgrid=False, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    fig1.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False}, theme=None)

                with c2:
                    st.markdown(f"##### 💹 REAL-TIME PRICE ACTION (OHLC)")
                    hist_clean = hist.dropna(subset=['Open', 'High', 'Low', 'Close'])
                    x_labels = hist_clean[time_col].dt.strftime('%b %d %H:%M') if selected_timeframe == "Daily" else hist_clean[time_col].dt.strftime('%b %d')
                    fig2 = go.Figure(data=[go.Candlestick(x=x_labels, open=hist_clean['Open'], high=hist_clean['High'], low=hist_clean['Low'], close=hist_clean['Close'], increasing_line_color='#10b981', decreasing_line_color='#ef4444')])
                    fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=c_text, size=12, family="Courier New, monospace"), margin=dict(l=40, r=40, t=20, b=40), xaxis_rangeslider_visible=False)
                    fig2.update_xaxes(showgrid=False, tickfont=dict(color=c_text), title_font=dict(color=c_text), type='category', tickangle=-45, nticks=10)
                    fig2.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False}, theme=None)
                st.markdown("---")
                st.markdown(f"##### 📈 Relative Performance Comparison (Normalized %)")

                compare_tickers = st.multiselect("Select assets to overlay:", options=all_trackers, default=[search_ticker] if search_ticker else [], key="compare_multiselect")

                if compare_tickers:
                    fig_comp = go.Figure()
                    for ct in compare_tickers:
                        hist_comp = fetch_stock_history(ct, period=tf_config["period"], interval=tf_config["interval"])
                        if not hist_comp.empty and len(hist_comp) > 0:
                            hist_comp.reset_index(inplace=True)
                            time_col_c = 'Datetime' if 'Datetime' in hist_comp.columns else 'Date'
                            if hist_comp[time_col_c].dt.tz is not None:
                                hist_comp[time_col_c] = hist_comp[time_col_c].dt.tz_localize(None)
                            first_price = hist_comp['Close'].iloc[0]
                            hist_comp['Pct_Change'] = ((hist_comp['Close'] - first_price) / first_price) * 100
                            mask = (hist_comp[time_col_c] >= start_time)
                            fig_comp.add_trace(go.Scatter(x=hist_comp.loc[mask, time_col_c], y=hist_comp.loc[mask, 'Pct_Change'], mode='lines', name=get_display_name(ct), line=dict(width=2, shape='spline')))

                    fig_comp.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=c_text, size=12, family="Courier New, monospace"), margin=dict(l=40, r=40, t=20, b=40), hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    fig_comp.update_xaxes(showgrid=False, tickfont=dict(color=c_text))
                    fig_comp.update_yaxes(title="Gain / Loss (%)", showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_subtext, size=11), zeroline=True, zerolinecolor=c_subtext, zerolinewidth=1)
                    st.plotly_chart(fig_comp, use_container_width=True, config={'displayModeBar': False}, theme=None)

# ==========================================
# 6. STRATEGY TAB
# ==========================================
with tab_strategy:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    st.markdown("### Algorithmic Decision Support")

    signal_counts = {"STRONG BUY": 0, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG SELL": 0}
    for t in all_trackers:
        t_arts = [a for a in articles if a.get("ticker") == t and a.get("score") is not None]
        curr_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
        hist_agg = fetch_stock_history(t, period="5d", interval="1d")
        if not hist_agg.empty and 'Close' in hist_agg.columns:
            clean_agg = hist_agg.dropna(subset=['Close'])
            if len(clean_agg) >= 2:
                c_val_agg = clean_agg['Close'].iloc[-1]
                p_val_agg = clean_agg['Close'].iloc[-2]
                pct_diff_agg = ((c_val_agg - p_val_agg) / p_val_agg) * 100
                sig_agg, _, _ = get_trade_signal(curr_sent, pct_diff_agg)
                signal_counts[sig_agg] += 1
            else:
                signal_counts["HOLD"] += 1
        else:
            signal_counts["HOLD"] += 1

    labels = [k for k, v in signal_counts.items() if v > 0]
    values = [v for k, v in signal_counts.items() if v > 0]
    color_map = {"STRONG BUY": "#10b981", "BUY": "#34d399", "HOLD": "#a3a3a3", "SELL": "#f87171", "STRONG SELL": "#ef4444"}
    pie_colors = [color_map[l] for l in labels]

    col_pie, col_desc = st.columns([1.5, 2])
    if labels:
        with col_pie:
            fig_donut = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.6, marker=dict(colors=pie_colors, line=dict(color=c_bg, width=2)), textinfo='label+percent', textfont=dict(color=c_text, size=12, family="Courier New"))])
            fig_donut.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=20, b=20, l=20, r=20), height=250, showlegend=False, annotations=[dict(text='MARKET<br>BREADTH', x=0.5, y=0.5, font_size=14, font_color=c_subtext, showarrow=False, font_family="Courier New")])
            st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})

    with col_desc:
        st.markdown("<div style='margin-top:40px;'></div>", unsafe_allow_html=True)
        st.markdown(f"**Total Tracked Assets:** {len(all_trackers)}")
        st.markdown(f"<span style='color:#10b981; font-weight:bold;'>🛒 Accumulate (Buy):</span> {signal_counts['STRONG BUY'] + signal_counts['BUY']} Assets", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#a3a3a3; font-weight:bold;'>⚖️ Maintain (Hold):</span> {signal_counts['HOLD']} Assets", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#ef4444; font-weight:bold;'>📉 Liquidate (Sell):</span> {signal_counts['STRONG SELL'] + signal_counts['SELL']} Assets", unsafe_allow_html=True)

    st.markdown("---")
    target = st.selectbox("Select Asset for Signal Analysis:", all_trackers, key="strat_ticker")
    if target:
        t_arts = [a for a in articles if a.get("ticker") == target and a.get("score") is not None]
        curr_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
        hist = fetch_stock_history(target, period="5d", interval="1d")

        if not hist.empty and 'Close' in hist.columns:
            clean_hist = hist.dropna(subset=['Close'])
            if len(clean_hist) >= 2:
                c_val = clean_hist['Close'].iloc[-1]
                p_val = clean_hist['Close'].iloc[-2]
                pct_diff = ((c_val - p_val) / p_val) * 100
                signal, color, reasoning = get_trade_signal(curr_sent, pct_diff)

                strat_logo_html = get_ticker_logo_html(target, size=36)
                st.markdown(
                    f"""
                    <div style="background-color: {c_card}; border-left: 8px solid {color}; border-radius: 8px; padding: 25px; margin-bottom: 25px; border-top: 1px solid {c_border}; border-right: 1px solid {c_border}; border-bottom: 1px solid {c_border}; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                        <div style="display:flex; align-items:center; margin-bottom:6px;">{strat_logo_html}<h5 style="color: {c_subtext}; margin: 0; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">SYSTEM RECOMMENDATION — {get_company_name(target)}</h5></div>
                        <h1 style="color: {color}; margin: 5px 0; font-size: 42px; font-weight: 900;">{signal}</h1>
                        <p style="color: {c_text}; margin: 10px 0 0 0; font-size: 16px;"><strong>Logic:</strong> {reasoning}</p>
                    </div>
                    """, unsafe_allow_html=True
                )

                col_s1, col_s2, col_s3 = st.columns(3)
                col_s1.metric("Current Sentiment", f"{curr_sent:.2f}")
                col_s2.metric("24h Price Action", f"{pct_diff:.2f}%")
                col_s3.metric("Data Volume (Confidence)", f"{len(t_arts)} headlines")

                # ── Fundamentals Panel ─────────────────────────────────────
                st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
                st.markdown("##### 🏦 Key Fundamentals")

                fundamentals = fetch_fundamentals(target)

                # FIX 5: Market Cap hero card — large, prominent, uses signal color accent
                mkt_cap_val = fundamentals["Market Cap"]
                st.markdown(
                    f"""
                    <div style="
                        background:{c_card};
                        border:1px solid {c_border};
                        border-left:6px solid {color};
                        border-radius:10px;
                        padding:20px 24px;
                        margin-bottom:16px;
                    ">
                        <div style="color:{c_subtext}; font-size:10px; font-weight:800;
                                    letter-spacing:2px; text-transform:uppercase; margin-bottom:6px;">
                            MARKET CAPITALISATION — {get_display_name(target)}
                        </div>
                        <div style="color:{c_text}; font-size:38px; font-weight:900;
                                    font-family:'Courier New', monospace; letter-spacing:1px;">
                            {mkt_cap_val}
                        </div>
                        <div style="color:{c_subtext}; font-size:11px; margin-top:6px;">
                            Total market value of all outstanding shares
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Remaining 5 fundamentals in a row
                fund_items = [
                    ("EPS (TTM)",       fundamentals["EPS (TTM)"],       "Earnings per share — trailing 12 months"),
                    ("ROE",             fundamentals["ROE"],             "Return on equity"),
                    ("P/B Ratio",       fundamentals["P/B Ratio"],       "Price-to-book ratio"),
                    ("P/E Ratio (TTM)", fundamentals["P/E Ratio (TTM)"], "Price-to-earnings — trailing 12 months"),
                    ("Dividend Yield",  fundamentals["Dividend Yield"],  "Annual dividend as % of price"),
                ]

                fund_cols = st.columns(len(fund_items))
                for i, (label, value, tooltip) in enumerate(fund_items):
                    with fund_cols[i]:
                        st.markdown(
                            f"""
                            <div title="{tooltip}" style="
                                background:{c_card};
                                border:1px solid {c_border};
                                border-top:3px solid {c_border};
                                border-radius:8px;
                                padding:14px 16px;
                                margin-bottom:12px;
                            ">
                                <div style="color:{c_subtext}; font-size:10px; font-weight:800;
                                            letter-spacing:1.5px; text-transform:uppercase;
                                            margin-bottom:6px;">{label}</div>
                                <div style="color:{c_text}; font-size:20px; font-weight:900;
                                            font-family:'Courier New', monospace;">{value}</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                st.markdown("---")
                st.markdown("##### 📈 Signal Validation Chart")

                clean_hist.reset_index(inplace=True)
                time_col = 'Datetime' if 'Datetime' in clean_hist.columns else 'Date'
                if clean_hist[time_col].dt.tz is not None:
                    clean_hist[time_col] = clean_hist[time_col].dt.tz_localize(None)

                fig_strat = go.Figure(data=[go.Candlestick(x=clean_hist[time_col], open=clean_hist['Open'], high=clean_hist['High'], low=clean_hist['Low'], close=clean_hist['Close'], increasing_line_color='#10b981', decreasing_line_color='#ef4444', name='Price Action')])
                fig_strat.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=c_text, size=12, family="Courier New, monospace"), margin=dict(l=40, r=40, t=20, b=40), xaxis_rangeslider_visible=False, height=350, title=dict(text=f"{get_display_name(target)} - 5 Day Price Action", font=dict(color=c_subtext, size=14)))
                fig_strat.update_xaxes(showgrid=False, tickfont=dict(color=c_text))
                fig_strat.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text))
                st.plotly_chart(fig_strat, use_container_width=True, config={'displayModeBar': False})
            else:
                st.warning("Insufficient clean market data to generate a signal.")
        else:
            st.warning("Insufficient market data to generate a signal.")

# ==========================================
# 7. VALIDATION TAB
# ==========================================
with tab_validation:
    render_validation_tab(articles, c_bg, c_card, c_text, c_subtext, c_border, c_grid)

# ==========================================
# 8. GLOBAL FOOTER
# ==========================================
st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="glass-card" style="border-left:5px solid {c_border}; padding:18px 22px; margin-bottom:14px;">
        <span style="color: {c_subtext}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;">
            DISCLAIMER: THIS DASHBOARD IS STRICTLY A PROTOTYPE FOR EDUCATIONAL AND INTERNSHIP EVALUATION PURPOSES. <br>
            THE AI SENTIMENT SCORING AND MARKET DATA PROVIDED DO NOT CONSTITUTE PROFESSIONAL FINANCIAL OR TRADING ADVICE.
        </span>
    </div>
    <div style="text-align: center; margin-top: 25px; margin-bottom: 20px;">
        <span style="color: {c_subtext}; font-size: 13px; font-weight: 500; letter-spacing: 1.5px;">
            &copy; 2026 Sanskar Jadhav
        </span>
    </div>
    """,
    unsafe_allow_html=True
)
