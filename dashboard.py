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
    c_bg = "#050505"
    c_card = "#0a0a0a"
    c_text = "#ffffff"
    c_subtext = "#a3a3a3"
    c_border = "#262626"
    c_header = "linear-gradient(145deg, #0a0a0a 0%, #000000 100%)"
    c_grid = "#171717"
    c_btn_hover_bg = "#ffffff"
    c_btn_hover_txt = "#000000"
    c_gauge_bg = "#1f1f1f"
else:
    c_bg = "#f4f4f5"
    c_card = "#ffffff"
    c_text = "#000000"  
    c_subtext = "#52525b"
    c_border = "#d4d4d8"
    c_header = "linear-gradient(145deg, #ffffff 0%, #f4f4f5 100%)"
    c_grid = "#e4e4e7"
    c_btn_hover_bg = "#000000"
    c_btn_hover_txt = "#ffffff"
    c_gauge_bg = "#e4e4e7"

st.markdown(
    f"""
    <style>
    [data-testid="stSidebar"], [data-testid="stSidebarNav"], [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
    .stApp {{ background-color: {c_bg} !important; color: {c_text} !important; }}
    [data-testid="stHeader"] {{ background-color: transparent !important; }}
    
    label[data-testid="stWidgetLabel"] p {{ color: {c_text} !important; font-weight: 700 !important; font-size: 13px !important; }}
    
    div[data-baseweb="select"] > div {{
        background-color: {c_card} !important;
        border: 1px solid {c_border} !important;
    }}
    div[data-baseweb="select"] span {{ color: {c_text} !important; }}
    div[data-baseweb="select"] div {{ color: {c_text} !important; }}
    
    div[data-baseweb="popover"] > div {{ background-color: {c_card} !important; }}
    ul[data-baseweb="menu"] {{ background-color: {c_card} !important; border: 1px solid {c_border} !important; }}
    li[data-baseweb="option"] {{ color: {c_text} !important; background-color: transparent !important; }}
    li[data-baseweb="option"]:hover {{ background-color: {c_bg} !important; }}

    [data-testid="stMetricValue"] > div {{ color: {c_text} !important; }}
    [data-testid="stMetricLabel"] p {{ color: {c_subtext} !important; font-weight: bold !important; }}

    @keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    
    .terminal-card {{
        background-color: {c_card}; border: 1px solid {c_border}; border-radius: 8px;
        padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05);
        animation: fadeInUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) both; transition: transform 0.2s ease, border-color 0.2s ease;
    }}
    .terminal-card:hover {{ transform: translateY(-2px); border-color: {c_text}; }}

    .divergence-card {{
        background-color: {c_card}; border: 1px solid {c_border}; border-radius: 8px;
        padding: 12px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        display: flex; flex-direction: column; gap: 4px;
    }}
    
    .clickable-headline {{ color: {c_text} !important; text-decoration: none !important; transition: color 0.15s ease !important; }}
    .clickable-headline:hover {{ color: {c_subtext} !important; text-decoration: underline !important; }}
    
    .stButton > button {{
        background-color: {c_card} !important; color: {c_text} !important; font-weight: 700 !important;
        border: 1px solid {c_border} !important; border-radius: 6px !important; padding: 10px 18px !important;
        transition: all 0.2s ease !important; width: 100%;
    }}
    .stButton > button:hover {{ background-color: {c_btn_hover_bg} !important; color: {c_btn_hover_txt} !important; }}
    
    div[data-testid="stTabs"] {{ background-color: {c_card}; padding: 4px 16px 0px 16px; border-radius: 8px; border: 1px solid {c_border}; margin-bottom: 25px; }}
    div[data-testid="stTabs"] button [data-testid="stMarkdownContainer"] p {{ font-size: 13px; font-weight: 700; letter-spacing: 0.75px; text-transform: uppercase; color: {c_subtext} !important; }}
    div[data-testid="stTabs"] button[aria-selected="true"] p {{ color: {c_text} !important; }}
    div[data-testid="stTabs"] [data-baseweb="tab-highlight-bar"] {{ background-color: {c_text} !important; }}

    .brand-header {{
        background: {c_header}; padding: 30px 35px; border-radius: 12px; margin-bottom: 25px;
        border: 1px solid {c_border}; border-left: 6px solid {c_text};
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05), inset 0 1px 1px rgba(255, 255, 255, 0.05);
        position: relative; overflow: hidden;
    }}
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

articles = []
try:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, title, summary, url, time_published, sentiment, score FROM market_news ORDER BY id DESC")
    rows = cursor.fetchall()
    for row in rows:
        articles.append(dict(row))
    conn.close()
except Exception as e:
    st.error(f"Database error: {e}")

all_trackers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "KOTAKBANK.NS"]
tab_home, tab_news, tab_analytics = st.tabs([" HOME ", " NEWS ", " ANALYTICS "])

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
            try:
                stock = yf.Ticker(selected_ticker)
                hist = stock.history(period="2d") 
                if len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2]
                    price_change = current_price - prev_close
                    currency = "₹" if ".NS" in selected_ticker else "$"
                    sub_kpi4.metric(label="LIVE ASSET PRICE", value=f"{currency}{current_price:.2f}", delta=f"{currency}{price_change:.2f}")
                elif len(hist) == 1:
                    current_price = hist['Close'].iloc[-1]
                    sub_kpi4.metric(label="LIVE ASSET PRICE", value=f"{current_price:.2f}")
                else:
                    sub_kpi4.metric(label="LIVE ASSET PRICE", value="AWAITING DATA")
            except Exception:
                sub_kpi4.metric(label="LIVE ASSET PRICE", value="API ERROR")
        else:
            sub_kpi4.metric(label="LIVE ASSET PRICE", value="-")

    with kpi_right:
        # THE FIXED GAUGE SYNTAX
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=avg_score,
            domain={'x': [0, 1], 'y': [0, 1]},
            number={'font': {'color': c_text, 'family': 'Courier New', 'size': 24}, 'valueformat': ".2f"},
            gauge={
                'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': c_subtext, 'tickvals': [-1, -0.5, 0, 0.5, 1], 'ticktext': ['BEAR', 'SHORT', 'NEUTRAL', 'LONG', 'BULL']},
                'bar': {'color': c_text, 'thickness': 0.25},
                'bgcolor': c_gauge_bg,
                'borderwidth': 1,
                'bordercolor': c_border,
                'steps': [
                    {'range': [-1, -0.15], 'color': 'rgba(239, 68, 68, 0.25)'},
                    {'range': [-0.15, 0.15], 'color': 'rgba(200, 255, 0, 0.2)'},
                    {'range': [0.15, 1], 'color': 'rgba(83, 255, 4, 0.2)'}  # <-- FIXED LINE
                ]
            }
        ))
        fig_gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=10, b=10), height=160)
        st.plotly_chart(fig_gauge, use_container_width=True, config={'displayModeBar': False}, theme=None)

    # ==========================================
    # 🆕 THE DIVERGENCE TAPE SCANNER
    # ==========================================
    st.markdown("---")
    st.markdown("### Sentiment vs Price Divergence")
    st.markdown(f"<span style='color: {c_subtext}; font-size: 12px;'>Scans for contradictory market action where live price deviates from media sentiment.</span>", unsafe_allow_html=True)
    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
    
    # Create an evenly spaced row of columns for all our tickers
    tape_cols = st.columns(len(all_trackers))
    
    for idx, t in enumerate(all_trackers):
        with tape_cols[idx]:
            # 1. Calculate Average Sentiment for this specific ticker
            t_arts = [a for a in articles if a.get("ticker") == t and a.get("score") is not None]
            t_sent = sum(a['score'] for a in t_arts) / len(t_arts) if t_arts else 0.0
            
            # 2. Fetch live price data
            try:
                stock_data = yf.Ticker(t).history(period="2d")
                if len(stock_data) >= 2:
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
            except:
                price_display = "ERR"
                pct_display = f"<span style='color: {c_subtext};'>--%</span>"
                pct_diff = 0.0

            # 3. Formulate Sentiment Display
            sent_color = "#10b981" if t_sent > 0 else ("#ef4444" if t_sent < 0 else c_subtext)
            sent_sign = "+" if t_sent > 0 else ""
            
            # 4. Determine Divergence Warning Flag
            warning_html = ""
            # If price drops but sentiment is very positive
            if pct_diff < -0.5 and t_sent > 0.15:
                warning_html = "<div style='border: 1px solid #eab308; color: #eab308; background: rgba(234, 179, 8, 0.05); font-size: 10px; font-weight: bold; padding: 4px; margin-top: 8px; border-radius: 4px; text-align: center;'>⚠️ News positive, price falling</div>"
            # If price jumps but sentiment is very negative
            elif pct_diff > 0.5 and t_sent < -0.15:
                warning_html = "<div style='border: 1px solid #eab308; color: #eab308; background: rgba(234, 179, 8, 0.05); font-size: 10px; font-weight: bold; padding: 4px; margin-top: 8px; border-radius: 4px; text-align: center;'>⚠️ News negative, price rising</div>"

            # 5. Render HTML Card
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

with tab_news:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    
    if not articles:
        st.info("Awaiting background ingestion...")
    else:
        # 1. Determine the earliest and latest dates in our database for the calendar bounds
        try:
            article_dates = [pd.to_datetime(a['time_published']).date() for a in articles if a.get('time_published')]
            db_min_date = min(article_dates) if article_dates else pd.Timestamp.now().date()
            db_max_date = max(article_dates) if article_dates else pd.Timestamp.now().date()
        except:
            db_min_date = pd.Timestamp.now().date()
            db_max_date = pd.Timestamp.now().date()

        # 2. Build the Filter UI Row
        news_col1, news_col2, news_col3 = st.columns([2, 1, 1])
        
        with news_col1:
            news_ticker = st.selectbox("FILTER BY TICKER:", ["ALL Tickers"] + all_trackers, key="news_tab_ticker")
        with news_col2:
            start_date = st.date_input("START DATE", value=db_min_date, min_value=db_min_date, max_value=db_max_date, key="news_start")
        with news_col3:
            end_date = st.date_input("END DATE", value=db_max_date, min_value=db_min_date, max_value=db_max_date, key="news_end")

        st.markdown("---")

        # 3. Apply the Logic Filters
        filtered_news_tab = []
        for item in articles:
            # Check Ticker
            match_ticker = (news_ticker == "ALL Tickers") or (item.get("ticker") == news_ticker)
            
            # Check Date Range
            match_date = True
            if item.get("time_published"):
                try:
                    item_date = pd.to_datetime(item["time_published"]).date()
                    match_date = (start_date <= item_date <= end_date)
                except:
                    pass # Failsafe if a date string is corrupted
            
            # If it passes both filters, add it to our display list
            if match_ticker and match_date:
                filtered_news_tab.append(item)

        # 4. Render the Filtered Results
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
            try:
                stock = yf.Ticker(search_ticker)
                hist = stock.history(period=tf_config["period"], interval=tf_config["interval"], prepost=True)
                
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

                    now = pd.Timestamp.utcnow().tz_localize(None)
                    start_time = now - pd.Timedelta(days=tf_config["days_back"])
                    
                    alignment_df = alignment_df[(alignment_df['Time'] >= start_time)]
                    hist = hist[(hist[time_col] >= start_time)]
                    master_x_range = [start_time, now]

                    c1, c2 = st.columns(2)
                    
                    with c1:
                        st.markdown(f"##### 📊 AGGREGATED SENTIMENT INDEX")
                        fig1 = px.line(alignment_df, x="Time", y="Sentiment Index")
                        fig1.update_traces(line_shape='spline', line_color=c_text, line_width=3, fill='tozeroy', fillcolor='rgba(128, 128, 128, 0.05)')
                        fig1.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                            font=dict(color=c_text, size=12, family="Courier New, monospace"),
                            margin=dict(l=40, r=40, t=20, b=40)
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
                        
            except Exception as e:
                st.error("Failed to connect to real-time market data stream.")

# ==========================================
# 4. GLOBAL FOOTER & SYSTEM REFRESH
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
