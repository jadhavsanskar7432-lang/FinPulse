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
# 1a. Read the browser's URL memory first
if 'theme' in st.query_params:
    saved_theme = st.query_params['theme']
else:
    saved_theme = 'dark'

# 1b. Initialize the session state with the URL memory
if 'theme' not in st.session_state:
    st.session_state.theme = saved_theme
    st.query_params['theme'] = saved_theme # Lock default into the URL

def toggle_theme():
    # Swap the theme variable
    st.session_state.theme = 'light' if st.session_state.theme == 'dark' else 'dark'
    # Force the browser URL to remember the new choice!
    st.query_params['theme'] = st.session_state.theme

# Apply the hex codes based on the locked state
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
    .brand-title {{
        margin: 0; font-size: 34px; font-weight: 900; letter-spacing: 2.5px; color: {c_text};
    }}
    .brand-subtitle {{ color: {c_subtext}; margin: 10px 0 0 0; font-size: 12px; text-transform: uppercase; font-weight: 700; letter-spacing: 3px; display: flex; align-items: center; gap: 10px; }}
    
    .status-dot {{ height: 8px; width: 8px; background-color: #10b981; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #10b981; animation: pulse 2s infinite ease-in-out; }}
    @keyframes pulse {{ 0% {{ opacity: 1; box-shadow: 0 0 8px #10b981; }} 50% {{ opacity: 0.3; box-shadow: 0 0 2px #10b981; }} 100% {{ opacity: 1; box-shadow: 0 0 8px #10b981; }} }}

    @media (max-width: 768px) {{
        .brand-header {{ padding: 20px; }}
        .brand-title {{ font-size: 20px; letter-spacing: 1px; }}
        .brand-subtitle {{ font-size: 9px; letter-spacing: 1px; }}
        div[data-testid="stTabs"] button [data-testid="stMarkdownContainer"] p {{ font-size: 10px; }}
        .terminal-card {{ padding: 15px; }}
    }}
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

tab_home, tab_news, tab_analytics = st.tabs([" HOME ", " NEWS ", " ANALYTICS "])

with tab_home:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.5, 1, 1, 1])
    
    with ctrl_col1:
        selected_ticker = st.selectbox("TRACKING DATA FILTER", ["ALL Tickers", "AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "KOTAKBANK.NS"], label_visibility="visible")
    with ctrl_col2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        st.button("THEME", on_click=toggle_theme, key="btn_theme")
    with ctrl_col3:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 RE-FETCH", key="btn_refetch"):
            subprocess.run([sys.executable, "news_fetcher.py"])
            subprocess.run([sys.executable, "sentiment_analyzer.py"])
            st.rerun()
    with ctrl_col4:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button(" SHOCK", key="btn_shock"):
            target_asset = "AAPL" if selected_ticker == "ALL Tickers" else selected_ticker
            try:
                conn = database.get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO market_news (ticker, title, summary, url, time_published, sentiment, score) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (target_asset, f" BREAKING: Regulatory shockwaves hit {target_asset}.", "Unexpected compliance reviews.", f"https://finance.yahoo.com/quote/{target_asset}", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), "Negative", -0.85)
                )
                conn.commit()
                conn.close()
                st.rerun()
            except Exception as e:
                pass

    st.markdown("---")
    filtered_articles = [a for a in articles if selected_ticker == "ALL Tickers" or a.get("ticker") == selected_ticker]
    scored_articles = [a for a in filtered_articles if a.get("score") is not None]
    total_news = len(filtered_articles)
    avg_score = sum([item.get("score", 0) for item in scored_articles]) / len(scored_articles) if scored_articles else 0.0

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="HEADLINES PROCESSED", value=total_news)
    kpi2.metric(label="MARKET PULSE SCORE", value=f"{avg_score:.2f}", delta="📈 BULLISH" if avg_score > 0.05 else "📉 BEARISH")
    kpi3.metric(label="ACTIVE TARGET", value=selected_ticker)

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
            # 1. Filter the columns cleanly
            df_ledger = pd.DataFrame(filtered_articles)[["sentiment", "score", "time_published"]]
            
            # 2. Use Pandas Styler to dynamically paint the Canvas cells to match your theme
            styled_ledger = df_ledger.style.set_properties(**{
                'background-color': c_card,
                'color': c_text,
                'border-color': c_border
            }).set_table_styles([
                {'selector': 'th', 'props': [('background-color', c_bg), ('color', c_subtext), ('font-weight', 'bold')]}
            ])
            
            # 3. Render the newly painted dataframe
            st.dataframe(styled_ledger, use_container_width=True)
with tab_news:
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    if not articles:
        st.info("Awaiting background ingestion...")
    else:
        for item in articles:
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
    search_ticker = st.selectbox("SELECT TARGET ASSET:", ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "KOTAKBANK.NS"])
    
    if search_ticker:
        ticker_articles = [a for a in articles if a.get("ticker") == search_ticker and a.get("score") is not None]
        if len(ticker_articles) < 2:
            st.info("Awaiting more database records to populate sentiment visuals.")
        else:
            chronological_data = sorted(ticker_articles, key=lambda x: str(x.get("time_published", "")))
            raw_df = pd.DataFrame({
                "Time": pd.to_datetime([item.get("time_published") for item in chronological_data], errors="coerce"),
                "Sentiment Index": [item.get("score", 0) for item in chronological_data]
            }).dropna(subset=["Time"])

            alignment_df = raw_df.groupby(raw_df['Time'].dt.floor('min'))['Sentiment Index'].mean().reset_index()
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"##### AGGREGATED SENTIMENT INDEX")
                fig1 = px.line(alignment_df, x="Time", y="Sentiment Index")
                fig1.update_traces(line_shape='spline', line_color=c_text, line_width=3, fill='tozeroy', fillcolor='rgba(128, 128, 128, 0.05)')
                fig1.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                    font=dict(color=c_text, size=12, family="Courier New, monospace"),
                    margin=dict(l=40, r=40, t=20, b=40)
                )
                fig1.update_xaxes(showgrid=False, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                fig1.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False}, theme=None)
                
            with c2:
                st.markdown(f"#####  REAL-TIME PRICE ACTION (OHLC)")
                try:
                    stock = yf.Ticker(search_ticker)
                    hist = stock.history(period="1mo")
                    
                    if not hist.empty:
                        hist.reset_index(inplace=True)
                        fig2 = go.Figure(data=[go.Candlestick(
                            x=hist['Date'], open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                            increasing_line_color='#10b981', decreasing_line_color='#ef4444'
                        )])
                        fig2.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                            font=dict(color=c_text, size=12, family="Courier New, monospace"),
                            margin=dict(l=40, r=40, t=20, b=40), xaxis_rangeslider_visible=False
                        )
                        fig2.update_xaxes(showgrid=False, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                        fig2.update_yaxes(showgrid=True, gridcolor=c_grid, tickfont=dict(color=c_text), title_font=dict(color=c_text))
                        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False}, theme=None)
                    else:
                        st.info("Live market data temporarily unavailable from Yahoo Finance API.")
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

# Auto-refresh loop
time.sleep(10)
st.rerun()