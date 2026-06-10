import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import time
import subprocess
import sys
import database
import yfinance as yf

st.set_page_config(
    page_title="FinPulse Terminal", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

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
    @keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .terminal-card {{ background-color: {c_card}; border: 1px solid {c_border}; border-radius: 8px; padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05); animation: fadeInUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) both; transition: transform 0.2s ease, border-color 0.2s ease; }}
    .terminal-card:hover {{ transform: translateY(-2px); border-color: {c_text}; }}
    .divergence-card {{ background-color: {c_card}; border: 1px solid {c_border}; border-radius: 8px; padding: 12px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05); display: flex; flex-direction: column; gap: 4px; }}
    .clickable-headline {{ color: {c_text} !important; text-decoration: none !important; transition: color 0.15s ease !important; }}
    .clickable-headline:hover {{ color: {c_subtext} !important; text-decoration: underline !important; }}
    .stButton > button {{ background-color: {c_card} !important; color: {c_text} !important; font-weight: 700 !important; border: 1px solid {c_border} !important; border-radius: 6px !important; padding: 10px 18px !important; transition: all 0.2s ease !important; width: 100%; }}
    .stButton > button:hover {{ background-color: {c_btn_hover_bg} !important; color: {c_btn_hover_txt} !important; }}
    div[data-testid="stTabs"] {{ background-color: {c_card}; padding: 4px 16px 0px 16px; border-radius: 8px; border: 1px solid {c_border}; margin-bottom: 25px; }}
    div[data-testid="stTabs"] button [data-testid="stMarkdownContainer"] p {{ font-size: 13px; font-weight: 700; letter-spacing: 0.75px; text-transform: uppercase; color: {c_subtext} !important; }}
    div[data-testid="stTabs"] button[aria-selected="true"] p {{ color: {c_text} !important; }}
    div[data-testid="stTabs"] [data-baseweb="tab-highlight-bar"] {{ background-color: {c_text} !important; }}
    .brand-header {{ background: {c_header}; padding: 30px 35px; border-radius: 12px; margin-bottom: 25px; border: 1px solid {c_border}; border-left: 6px solid {c_text}; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05), inset 0 1px 1px rgba(255, 255, 255, 0.05); position: relative; overflow: hidden; }}
    .brand-title {{ margin: 0; font-size: 34px; font-weight: 900; letter-spacing: 2.5px; color: {c_text}; }}
    .brand-subtitle {{ color: {c_subtext}; margin: 10px 0 0 0; font-size: 12px; text-transform: uppercase; font-weight: 700; letter-spacing: 3px; display: flex; align-items: center; gap: 10px; }}
    .status-dot {{ height: 8px; width: 8px; background-color: #10b981; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #10b981; animation: pulse 2s infinite ease-in-out; }}
    @keyframes pulse {{ 0% {{ opacity: 1; box-shadow: 0 0 8px #10b981; }} 50% {{ opacity: 0.3; box-shadow: 0 0 2px #10b981; }} 100% {{ opacity: 1; box-shadow: 0 0 8px #10b981; }} }}
    </style>

    <div class="brand-header">
        <h1 class="brand-title">FINPULSE</h1>
        <p class="brand-subtitle"><span class="status-dot"></span>SYSTEM STATE: ACTIVE ENTERPRISE ENGINE</p>
    </div>
    """, 
    unsafe_allow_html=True
)

# ==========================================
# 2. CACHING ENGINE (SPEED OPTIMIZATION)
# ==========================================

@st.cache_data(ttl=30)
def fetch_database_records():
    """Caches local SQLite fetch for 30 seconds."""
    local_articles = []
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, title, summary, url, time_published, sentiment, score FROM market_news ORDER BY id DESC")
        rows = cursor.fetchall()
        for row in rows:
            local_articles.append(dict(row))
        conn.close()
    except Exception as e:
        st.error(f"Database error: {e}")
    return local_articles
def get_trade_signal(sentiment, price_diff):
    """Evaluates raw data and outputs a trading signal, color, and confidence reason."""
    if sentiment > 0.3 and price_diff < -1.0:
        return "STRONG BUY", "#10b981", "High positive news volume, but price is dipping (Value Buy)."
    elif sentiment > 0.15:
        return "BUY", "#34d399", "General positive market sentiment trending upward."
    elif sentiment < -0.3 and price_diff > 1.0:
        return "STRONG SELL", "#ef4444", "Heavy negative news, but price is artificially high (Correction imminent)."
    elif sentiment < -0.15:
        return "SELL", "#f87171", "Negative sentiment accumulation detected."
    else:
        return "HOLD", "#c8ff00", "Insufficient signal divergence. Await clearer data."

@st.cache_data(ttl=60)
def fetch_stock_history(ticker, period="2d", interval="1d"):
    """Caches Yahoo Finance API calls for 60 seconds to prevent IP bans."""
    try:
        stock = yf.Ticker(ticker)
        return stock.history(period=period, interval=interval, prepost=True)
    except Exception:
        return pd.DataFrame()


# Initialize data using cached functions
articles = fetch_database_records()
all_trackers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "KOTAKBANK.NS"]

tab_home, tab_news, tab_analytics, tab_strategy = st.tabs([" HOME ", " NEWS ", " ANALYTICS ", " STRATEGY "])

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
            # Clear caches to force a fresh pull when the user manually clicks re-fetch
            st.cache_data.clear() 
            subprocess.run([sys.executable, "news_fetcher.py"])
            subprocess.run([sys.executable, "sentiment_analyzer.py"])
            st.rerun()

    st.markdown("---")
    filtered_articles = [a for a in articles if selected_ticker == "ALL Tickers" or a.get("ticker") == selected_ticker]
    scored_articles = [a for a in filtered_articles if a.get("score") is not None]
    total_news = len(filtered_articles)
    avg_score = sum([item.get("score", 0) for item in scored_articles]) / len(scored_articles) if scored_articles else 0.0

    kpi_left, kpi_right = st.columns([2.5, 1.5])
    
    with kpi_left:
        st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
        sub_kpi1, sub_kpi2 = st.columns(2)
        sub_kpi1.metric(label="HEADLINES PROCESSED", value=total_news)
        sub_kpi2.metric(label="ACTIVE TARGET TICKER", value=selected_ticker)
        
        st.markdown("<div style='margin-top:25px;'></div>", unsafe_allow_html=True)
        sub_kpi3, sub_kpi4 = st.columns(2)
        sub_kpi3.metric(label="MARKET PULSE SCORE", value=f"{avg_score:.2f}", delta="📈 BULLISH" if avg_score > 0.05 else "📉 BEARISH")
        
        if selected_ticker != "ALL Tickers":
            hist = fetch_stock_history(selected_ticker, period="2d", interval="1d")
            if not hist.empty and len(hist) >= 2:
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2]
                price_change = current_price - prev_close
                currency = "₹" if ".NS" in selected_ticker else "$"
                sub_kpi4.metric(label="LIVE ASSET PRICE", value=f"{currency}{current_price:.2f}", delta=f"{currency}{price_change:.2f}")
            elif not hist.empty and len(hist) == 1:
                current_price = hist['Close'].iloc[-1]
                sub_kpi4.metric(label="LIVE ASSET PRICE", value=f"{current_price:.2f}")
            else:
                sub_kpi4.metric(label="LIVE ASSET PRICE", value="AWAITING DATA")
        else:
            sub_kpi4.metric(label="LIVE ASSET PRICE", value="-")

    with kpi_right:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=avg_score, domain={'x': [0, 1], 'y': [0, 1]},
            number={'font': {'color': c_text, 'family': 'Courier New', 'size': 24}, 'valueformat': ".2f"},
            gauge={
                'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': c_subtext, 'tickvals': [-1, -0.5, 0, 0.5, 1], 'ticktext': ['BEAR', 'SHORT', 'NEUTRAL', 'LONG', 'BULL']},
                'bar': {'color': c_text, 'thickness': 0.25}, 'bgcolor': c_gauge_bg, 'borderwidth': 1, 'bordercolor': c_border,
                'steps': [
                    {'range': [-1, -0.15], 'color': 'rgba(239, 68, 68, 0.25)'},
                    {'range': [-0.15, 0.15], 'color': 'rgba(200, 255, 0, 0.2)'},
                    {'range': [0.15, 1], 'color': 'rgba(83, 255, 4, 0.2)'} 
                ]
            }
        ))
        fig_gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=10, b=10), height=160)
        st.plotly_chart(fig_gauge, use_container_width=True, config={'displayModeBar': False}, theme=None)

    st.markdown("---")
    st.markdown("### Sentiment vs Price Divergence")
    st.markdown(f"<span style='color: {c_subtext}; font-size: 12px;'>Scans for contradictory market action where live price deviates from media sentiment.</span>", unsafe_allow_html=True)
    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
    
    tape_cols = st.columns(len(all_trackers))
    
    for idx, t in enumerate(all_trackers):
        with tape_cols[idx]:
            t_arts = [a for a in articles if a.get("ticker") == t and a.get("score") is not None]
            t_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
            
            stock_data = fetch_stock_history(t, period="5d", interval="1d")
            if not stock_data.empty and len(stock_data) >= 2:
                c_val = stock_data['Close'].iloc[-1]
                p_val = stock_data['Close'].iloc[-2]
                pct_diff = ((c_val - p_val) / p_val) * 100
                cur = "₹" if ".NS" in t else "$"
                price_display = f"{cur}{c_val:.2f}"
                pct_color = "#10b981" if pct_diff > 0 else "#ef4444"
                pct_sign = "+" if pct_diff > 0 else ""
                pct_display = f"<span style='color: {pct_color}; font-weight:bold; font-size:14px;'>{pct_sign}{pct_diff:.2f}%</span>"
            else:
                price_display = "N/A"
                pct_display = f"<span style='color: {c_subtext};'>--%</span>"
                pct_diff = 0.0

            sent_color = "#10b981" if t_sent > 0 else ("#ef4444" if t_sent < 0 else c_subtext)
            sent_sign = "+" if t_sent > 0 else ""
            
            warning_html = ""
            if pct_diff < -0.5 and t_sent > 0.15:
                warning_html = "<div style='border: 1px solid #eab308; color: #eab308; background: rgba(234, 179, 8, 0.05); font-size: 10px; font-weight: bold; padding: 4px; margin-top: 8px; border-radius: 4px; text-align: center;'>⚠️ News positive, price falling</div>"
            elif pct_diff > 0.5 and t_sent < -0.15:
                warning_html = "<div style='border: 1px solid #eab308; color: #eab308; background: rgba(234, 179, 8, 0.05); font-size: 10px; font-weight: bold; padding: 4px; margin-top: 8px; border-radius: 4px; text-align: center;'>⚠️ News negative, price rising</div>"

            st.markdown(
                f"""
                <div class="divergence-card">
                    <span style="font-size: 14px; font-weight: 800; color: {c_text};">{t.replace('.NS', '')}</span>
                    <span style="font-size: 18px; font-weight: 700; color: {c_text};">{price_display}</span>
                    {pct_display}
                    <span style="font-size: 11px; color: {sent_color}; margin-top: 2px;">sentiment {sent_sign}{t_sent:.2f}</span>
                    {warning_html}
                </div>
                """, unsafe_allow_html=True
            )

    st.markdown("---")
    left_panel, right_panel = st.columns([2, 1])
    with left_panel:
        st.markdown(f"### Anomalies Matrix")
        if not filtered_articles:
            st.info("No active records.")
        else:
            for item in filtered_articles[:3]:
                score = item.get("score", 0) if item.get("score") is not None else 0.0
                color = "#53ff04" if score > 0.05 else ("#ef4444" if score < -0.05 else "#c8ff00")
                st.markdown(
                    f"""
                    <div class="terminal-card" style="border-left: 4px solid {color} !important;">
                        <span style="color:{color}; font-size:11px; font-weight:bold;">SCORE: {score:.2f} | {item.get('ticker')}</span>
                        <h5 style="margin-top:5px; margin-bottom:0px;"><a class="clickable-headline" href="{item.get('url', '#')}" target="_blank">{item.get('title')}</a></h5>
                    </div>
                    """, unsafe_allow_html=True
                )
    with right_panel:
        st.markdown(f"### Audit Ledger")
        if filtered_articles:
            df_ledger = pd.DataFrame(filtered_articles)[["sentiment", "score", "time_published"]]
            styled_ledger = df_ledger.style.set_properties(**{
                'background-color': c_card, 'color': c_text, 'border-color': c_border
            }).set_table_styles([
                {'selector': 'th', 'props': [('background-color', c_bg), ('color', c_subtext), ('font-weight', 'bold')]}
            ])
            st.dataframe(styled_ledger, use_container_width=True)

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
                st.markdown(
                    f"""
                    <div class="terminal-card" style="border-left: 5px solid {color} !important;">
                        <span style="color:{color}; font-size:11px; font-weight:bold;">VADER SCORING: {score:.2f} | {item.get('ticker')}</span>
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
        search_ticker = st.selectbox("SELECT TARGET ASSET:", ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "KOTAKBANK.NS"])
    with col_t2:
        selected_timeframe = st.selectbox(
            "SELECT TIMEFRAME:", 
            options=["Daily", "Weekly", "Monthly", "3 Months", "6 Months", "12 Months"],
            index=1
        )
        
    timeframe_map = {
        "Daily": {"period": "1d", "interval": "5m", "days_back": 1, "resample": "5min"},
        "Weekly": {"period": "5d", "interval": "1h", "days_back": 5, "resample": "h"},
        "Monthly": {"period": "1mo", "interval": "1d", "days_back": 30, "resample": "D"},
        "3 Months": {"period": "3mo", "interval": "1d", "days_back": 90, "resample": "D"},
        "6 Months": {"period": "6mo", "interval": "1d", "days_back": 180, "resample": "D"},
        "12 Months": {"period": "1y", "interval": "1d", "days_back": 365, "resample": "D"}
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
                start_time = now - pd.Timedelta(days=tf_config["days_back"])
                
                alignment_df = alignment_df[(alignment_df['Time'] >= start_time)]
                hist = hist[(hist[time_col] >= start_time)]
                master_x_range = [start_time, now]

                c1, c2 = st.columns(2)
                
                with c1:
                    st.markdown(f"##### 📊 AGGREGATED SENTIMENT INDEX")
                    fig1 = go.Figure()
                    fig1.add_trace(go.Scatter(
                        x=alignment_df["Time"], y=alignment_df["Sentiment Index"], mode='lines', name='Raw Pulse',
                        line=dict(color=c_subtext, width=1, dash='dot', shape='spline')
                    ))
                    fig1.add_trace(go.Scatter(
                        x=alignment_df["Time"], y=alignment_df["Smoothed Sentiment"], mode='lines', name='3-Pd Trend',
                        line=dict(color=c_text, width=3, shape='spline'), fill='tozeroy', fillcolor='rgba(128, 128, 128, 0.05)'
                    ))
                    fig1.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                        font=dict(color=c_text, size=12, family="Courier New, monospace"),
                        margin=dict(l=40, r=40, t=20, b=40), showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    fig1.update_xaxes(range=master_x_range, showgrid=False, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    fig1.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False}, theme=None)
                    
                with c2:
                    st.markdown(f"##### 💹 REAL-TIME PRICE ACTION (OHLC)")
                    fig2 = go.Figure(data=[go.Candlestick(
                        x=hist[time_col], open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                        increasing_line_color='#10b981', decreasing_line_color='#ef4444'
                    )])
                    fig2.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                        font=dict(color=c_text, size=12, family="Courier New, monospace"),
                        margin=dict(l=40, r=40, t=20, b=40), xaxis_rangeslider_visible=False
                    )
                    fig2.update_xaxes(range=master_x_range, showgrid=False, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    fig2.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                    st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False}, theme=None)
                    st.markdown("---")
                st.markdown(f"##### 📈 Relative Performance Comparison (Normalized %)")
                
                # 1. Multi-select for comparison
                compare_tickers = st.multiselect(
                    "Select assets to overlay:", 
                    options=all_trackers, 
                    default=[search_ticker] if search_ticker else [],
                    key="compare_multiselect"
                )
                
                if compare_tickers:
                    fig_comp = go.Figure()
                    
                    for ct in compare_tickers:
                        hist_comp = fetch_stock_history(ct, period=tf_config["period"], interval=tf_config["interval"])
                        
                        if not hist_comp.empty and len(hist_comp) > 0:
                            # 1. Reset the index FIRST
                            hist_comp.reset_index(inplace=True)
                            time_col_c = 'Datetime' if 'Datetime' in hist_comp.columns else 'Date'
                            
                            if hist_comp[time_col_c].dt.tz is not None:
                                hist_comp[time_col_c] = hist_comp[time_col_c].dt.tz_localize(None)
                                
                            # 2. Calculate Percentage Change AFTER the reset so they share the same row numbers
                            first_price = hist_comp['Close'].iloc[0]
                            hist_comp['Pct_Change'] = ((hist_comp['Close'] - first_price) / first_price) * 100
                            
                            # 3. Filter to master time range
                            mask = (hist_comp[time_col_c] >= start_time)
                            
                            fig_comp.add_trace(go.Scatter(
                                x=hist_comp.loc[mask, time_col_c], 
                                y=hist_comp.loc[mask, 'Pct_Change'], 
                                mode='lines', 
                                name=ct.replace('.NS', ''),
                                line=dict(width=2, shape='spline')
                            ))
                            
                    # 3. Style the unified chart
                    fig_comp.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                        font=dict(color=c_text, size=12, family="Courier New, monospace"),
                        margin=dict(l=40, r=40, t=20, b=40), hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    fig_comp.update_xaxes(showgrid=False, tickfont=dict(color=c_text))
                    fig_comp.update_yaxes(
                        title="Gain / Loss (%)", showgrid=True, gridcolor=c_grid, 
                        tickfont=dict(color=c_text), title_font=dict(color=c_subtext, size=11),
                        zeroline=True, zerolinecolor=c_subtext, zerolinewidth=1
                    )
                    
                    st.plotly_chart(fig_comp, use_container_width=True, config={'displayModeBar': False}, theme=None)
# ==========================================
# 6. STRATEGY TAB
# ==========================================
with tab_strategy:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    
    st.markdown("### Algorithmic Decision Support")
    # --- PORTFOLIO AGGREGATION ENGINE ---
    signal_counts = {"STRONG BUY": 0, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG SELL": 0}
    
    for t in all_trackers:
        t_arts = [a for a in articles if a.get("ticker") == t and a.get("score") is not None]
        curr_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
        hist_agg = fetch_stock_history(t, period="5d", interval="1d")
        
        if not hist_agg.empty and len(hist_agg) >= 2:
            c_val_agg = hist_agg['Close'].iloc[-1]
            p_val_agg = hist_agg['Close'].iloc[-2]
            pct_diff_agg = ((c_val_agg - p_val_agg) / p_val_agg) * 100
            sig_agg, _, _ = get_trade_signal(curr_sent, pct_diff_agg)
            signal_counts[sig_agg] += 1
        else:
            signal_counts["HOLD"] += 1 # Default to hold if API data is missing

    # Filter out empty categories for a cleaner chart
    labels = [k for k, v in signal_counts.items() if v > 0]
    values = [v for k, v in signal_counts.items() if v > 0]
    color_map = {"STRONG BUY": "#10b981", "BUY": "#34d399", "HOLD": "#a3a3a3", "SELL": "#f87171", "STRONG SELL": "#ef4444"}
    pie_colors = [color_map[l] for l in labels]

    col_pie, col_desc = st.columns([1.5, 2])
    
    with col_pie:
        fig_donut = go.Figure(data=[go.Pie(
            labels=labels, values=values, hole=0.6, 
            marker=dict(colors=pie_colors, line=dict(color=c_bg, width=2)),
            textinfo='label+percent', textfont=dict(color=c_text, size=12, family="Courier New")
        )])
        fig_donut.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20, l=20, r=20), height=250, showlegend=False,
            annotations=[dict(text='MARKET<br>BREADTH', x=0.5, y=0.5, font_size=14, font_color=c_subtext, showarrow=False, font_family="Courier New")]
        )
        st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})
        
    with col_desc:
        st.markdown("<div style='margin-top:40px;'></div>", unsafe_allow_html=True)
        st.markdown(f"**Total Tracked Assets:** {len(all_trackers)}")
        st.markdown(f"<span style='color:#10b981; font-weight:bold;'>🛒 Accumulate (Buy):</span> {signal_counts['STRONG BUY'] + signal_counts['BUY']} Assets", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#a3a3a3; font-weight:bold;'>⚖️ Maintain (Hold):</span> {signal_counts['HOLD']} Assets", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#ef4444; font-weight:bold;'>📉 Liquidate (Sell):</span> {signal_counts['STRONG SELL'] + signal_counts['SELL']} Assets", unsafe_allow_html=True)

    st.markdown("---")
    # ------------------------------------
    target = st.selectbox("Select Asset for Signal Analysis:", all_trackers, key="strat_ticker")
    
    if target:
        # Grab the data
        t_arts = [a for a in articles if a.get("ticker") == target and a.get("score") is not None]
        curr_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
        
        hist = fetch_stock_history(target, period="5d", interval="1d")
        
        if not hist.empty and len(hist) >= 2:
            c_val = hist['Close'].iloc[-1]
            p_val = hist['Close'].iloc[-2]
            pct_diff = ((c_val - p_val) / p_val) * 100
            
            # Run the Engine
            signal, color, reasoning = get_trade_signal(curr_sent, pct_diff)
            
            # Build the UI
            st.markdown(
                f"""
                <div style="background-color: {c_card}; border-left: 8px solid {color}; border-radius: 8px; padding: 25px; margin-bottom: 25px; border-top: 1px solid {c_border}; border-right: 1px solid {c_border}; border-bottom: 1px solid {c_border}; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                    <h5 style="color: {c_subtext}; margin: 0; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">SYSTEM RECOMMENDATION</h5>
                    <h1 style="color: {color}; margin: 5px 0; font-size: 42px; font-weight: 900;">{signal}</h1>
                    <p style="color: {c_text}; margin: 10px 0 0 0; font-size: 16px;"><strong>Logic:</strong> {reasoning}</p>
                </div>
                """, unsafe_allow_html=True
            )
            st.markdown("##### 📈 Signal Validation Chart")
            
            # 1. Format the time column to prevent timezone errors
            hist.reset_index(inplace=True)
            time_col = 'Datetime' if 'Datetime' in hist.columns else 'Date'
            if hist[time_col].dt.tz is not None:
                hist[time_col] = hist[time_col].dt.tz_localize(None)

            # 2. Build the Terminal-Themed Candlestick Chart
            fig_strat = go.Figure(data=[go.Candlestick(
                x=hist[time_col], open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                increasing_line_color='#10b981', decreasing_line_color='#ef4444',
                name='Price Action'
            )])

            # 3. Apply the custom UI styling
            fig_strat.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                font=dict(color=c_text, size=12, family="Courier New, monospace"),
                margin=dict(l=40, r=40, t=20, b=40), xaxis_rangeslider_visible=False,
                height=350,
                title=dict(text=f"{target} - 5 Day Price Action", font=dict(color=c_subtext, size=14))
            )
            fig_strat.update_xaxes(showgrid=False, tickfont=dict(color=c_text))
            fig_strat.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text))
            
            # 4. Render it flawlessly
            st.plotly_chart(fig_strat, use_container_width=True, config={'displayModeBar': False})
            
            # The Data Breakdown
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("Current Sentiment", f"{curr_sent:.2f}")
            col_s2.metric("24h Price Action", f"{pct_diff:.2f}%")
            col_s3.metric("Data Volume (Confidence)", f"{len(t_arts)} headlines")
            
        else:
            st.warning("Insufficient market data to generate a signal.")
# ==========================================
# 7. GLOBAL FOOTER & SYSTEM REFRESH
# ==========================================
st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div style="background-color: {c_card}; border: 1px solid {c_border}; border-radius: 6px; padding: 14px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
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

time.sleep(10)
st.rerun()
