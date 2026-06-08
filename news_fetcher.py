import json
import datetime
import random
import requests
import database  # Connects to your brand new database.py file

print("🌍 INGESTION FEED: Initializing Dual-Stream Pipeline...")

# 1. Configuration & Scope
tickers = {
    "AAPL": "Apple", 
    "MSFT": "Microsoft", 
    "TSLA": "Tesla", 
    "NVDA": "Nvidia", 
    "AMZN": "Amazon", 
    "KOTAKBANK.NS": "Kotak Mahindra"
}

# Pick a random ticker to update on this loop cycle
selected_ticker = random.choice(list(tickers.keys()))
company_name = tickers[selected_ticker]

# Replace this with your actual free API key from NewsAPI.org
NEWS_API_KEY = "93c030da0080476882719c144cce4013"

print(f"📡 API GATEWAY: Pinging NewsAPI for official [{company_name}] headlines...")

   
try:
    strict_query = f'"{company_name}"'
    
    url = f"https://newsapi.org/v2/everything?qInTitle={strict_query}&language=en&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    response = requests.get(url, timeout=5)
    news_data = response.json()
    
    if news_data.get("status") == "ok" and news_data.get("totalResults") > 0:
        articles_to_process = news_data["articles"][:10] 
        selected_stories = []
        for article in articles_to_process:
            raw_time = article.get("publishedAt", datetime.datetime.now().isoformat())
            clean_time = raw_time.replace("T", " ").replace("Z", "")[:19]

            selected_stories.append({
                "ticker": selected_ticker,
                "title": article.get("title", f"Latest corporate shift on {selected_ticker}"),
                "summary": article.get("description", "No summary text provided by publisher stream."),
                "url": article.get("url", f"https://finance.yahoo.com/quote/{selected_ticker}"),
                "time_published": clean_time
            })
    else:
        raise ValueError("NewsAPI returned empty news array or invalid schema response.")
        
except Exception as e:
    print(f"⚠️ API Fetch delayed or rate-limited. Injecting market pulse baseline...")
    selected_story = {
        "ticker": selected_ticker,
        "title": f"Live Tracking: {selected_ticker} liquidity metrics remaining stable.",
        "summary": "Awaiting fresh fundamental structural catalysts over the trading week.",
        "url": f"https://finance.yahoo.com/quote/{selected_ticker}",
        "time_published": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    selected_stories.append(selected_story)

try:
    conn = database.get_connection()
    cursor = conn.cursor()
    
    new_inserts = 0
    # Loop through our bulk list and insert them all
    for story in selected_stories:
        cursor.execute('''
            INSERT OR IGNORE INTO market_news (ticker, title, summary, url, time_published)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            story["ticker"], 
            story["title"], 
            story["summary"], 
            story["url"], 
            story["time_published"]
        ))
        if cursor.rowcount > 0:
            new_inserts += 1
            
    if new_inserts > 0:
        print(f"✅ SQLITE SUCCESS: Bulk committed {new_inserts} fresh records.")
    else:
        print(f"🔄 SQLITE SKIP: No new articles published since last check.")
        
    conn.commit()
    # Check if a new record was added or if it was blocked as a duplicate
    if cursor.rowcount > 0:
        print(f"✅ SQLITE SUCCESS: Committed fresh record to database row context.")
    else:
        print(f"🔄 SQLITE SKIP: Article duplicate intercepted by database constraints. Cache preserved.")
        
    conn.commit()
    
except Exception as db_err:
    print(f"❌ DATABASE EXCEPTION: Unable to commit transaction. Error: {db_err}")
finally:
    conn.close()

print(f"🏁 PIPELINE RUN COMPLETE: State tracking synchronized.")