import json
import datetime
import random
import requests
import urllib.parse
import os                      # <-- NEW: Allows computer to read system variables
from dotenv import load_dotenv # <-- NEW: Loads your hidden .env file
import database

# 1. Load the hidden environment variables
load_dotenv()

print("🌍 INGESTION FEED: Initializing Dual-Stream Pipeline...")

# Configuration & Scope
tickers = {
    "AAPL": "Apple", 
    "MSFT": "Microsoft", 
    "TSLA": "Tesla", 
    "NVDA": "Nvidia", 
    "AMZN": "Amazon", 
    "KOTAKBANK.NS": "Kotak Mahindra"
}

selected_ticker = random.choice(list(tickers.keys()))
company_name = tickers[selected_ticker]

# 2. Grab the key securely from the .env file instead of hardcoding it
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

if not NEWS_API_KEY:
    print("❌ FATAL ERROR: API Key missing. Please check your .env file.")
    exit()

print(f"📡 API GATEWAY: Pinging NewsAPI for official [{company_name}] financial headlines...")

selected_stories = [] 

try:
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    trusted_domains = "finance.yahoo.com,reuters.com,cnbc.com,marketwatch.com,bloomberg.com,seekingalpha.com,fool.com,investors.com,wsj.com,ft.com"
    raw_query = f'("{company_name}" OR "{selected_ticker}") AND (stock OR shares OR earnings OR revenue OR dividend) -deal -sale -discount -coupon -shipping'
    strict_query = urllib.parse.quote(raw_query)
    
    # 3. BUG FIX: Merged the two URLs into one master query that respects domains AND dates
    url = f"https://newsapi.org/v2/everything?q={strict_query}&domains={trusted_domains}&language=en&from={yesterday}&to={today}&sortBy=publishedAt&pageSize=20&apiKey={NEWS_API_KEY}"
    
    response = requests.get(url, timeout=5)
    news_data = response.json()
    
    if news_data.get("status") == "ok" and news_data.get("totalResults", 0) > 0:
        articles_to_process = news_data["articles"][:10] 
        
        for article in articles_to_process:
            title = article.get("title", "")
            summary = article.get("description", "")
            
            # --- THE STRICT RELEVANCE BARRICADE ---
            search_pool = f"{title} {summary}".lower()
            
            if company_name.lower() in search_pool or selected_ticker.lower() in search_pool:
                raw_time = article.get("publishedAt", datetime.datetime.now().isoformat())
                clean_time = raw_time.replace("T", " ").replace("Z", "")[:19]

                selected_stories.append({
                    "ticker": selected_ticker,
                    "title": title if title else f"Latest corporate shift on {selected_ticker}",
                    "summary": summary if summary else "No summary text provided by publisher stream.",
                    "url": article.get("url", f"https://finance.yahoo.com/quote/{selected_ticker}"),
                    "time_published": clean_time
                })
            else:
                print(f"Filtered out irrelevant article: {title[:30]}...")
    else:
        raise ValueError("NewsAPI returned empty news array or no financial matches found.")
        
except Exception as e:
    print(f"⚠️ API Fetch delayed or rate-limited ({e}). Injecting market pulse baseline...")
    selected_story = {
        "ticker": selected_ticker,
        "title": f"Live Tracking: {selected_ticker} liquidity metrics remaining stable.",
        "summary": "Awaiting fresh fundamental structural catalysts over the trading week.",
        "url": f"https://finance.yahoo.com/quote/{selected_ticker}",
        "time_published": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    selected_stories.append(selected_story)

# Database Injection Phase
try:
    conn = database.get_connection()
    cursor = conn.cursor()
    
    new_inserts = 0
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
            
    conn.commit()
    
    if new_inserts > 0:
        print(f"✅ SQLITE SUCCESS: Bulk committed {new_inserts} fresh records.")
    else:
        print(f"🔄 SQLITE SKIP: No new articles published since last check. Cache preserved.")
        
except Exception as db_err:
    print(f"❌ DATABASE EXCEPTION: Unable to commit transaction. Error: {db_err}")
finally:
    if 'conn' in locals():
        conn.close()

print(f"🏁 PIPELINE RUN COMPLETE: State tracking synchronized.")
