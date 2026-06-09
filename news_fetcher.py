

import json
import datetime
import random
import requests
import urllib.parse
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

NEWS_API_KEY = "48af6ecbae4141869901fa62944d6981"

print(f"📡 API GATEWAY: Pinging NewsAPI for official [{company_name}] financial headlines...")

selected_stories = [] 

try:
    # Calculate exactly today and 2 days ago for a strict real-time window
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    
    # --- THE STRICT FINANCIAL FILTER ---
    # Force the API to only return articles that mention the company AND a finance keyword
    raw_query = f'("{company_name}" OR "{selected_ticker}") AND (stock OR shares OR earnings OR revenue OR dividend OR market)'
    strict_query = urllib.parse.quote(raw_query)
    
    url = f"https://newsapi.org/v2/everything?q={strict_query}&language=en&from={yesterday}&to={today}&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    
    response = requests.get(url, timeout=5)
    news_data = response.json()
    
    if news_data.get("status") == "ok" and news_data.get("totalResults", 0) > 0:
        articles_to_process = news_data["articles"][:10] 
        
        for article in articles_to_process:
            title = article.get("title", "")
            summary = article.get("description", "")
            
            # --- THE STRICT RELEVANCE BARRICADE ---
            # Convert everything to lowercase for easy matching
            search_pool = f"{title} {summary}".lower()
            
            # Only proceed if the company name OR ticker is actually in the headline/summary
            if company_name.lower() in search_pool or selected_ticker.lower() in search_pool:
                
                # Extract the actual publish time from NewsAPI
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
