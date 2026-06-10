import datetime
import requests
import urllib.parse
import database
import time

print("🕰️ INITIALIZING STRICT DEEP-TIME BACKFILL ENGINE...")

tickers = {
    "AAPL": "Apple", "MSFT": "Microsoft", "TSLA": "Tesla", 
    "NVDA": "Nvidia", "AMZN": "Amazon", "KOTAKBANK.NS": "Kotak Mahindra"
}

# Your NewsAPI Key
NEWS_API_KEY = "699bf2aa98aa4c30b1de1f0a9e7635ac"

conn = database.get_connection()
cursor = conn.cursor()
total_inserted = 0

for ticker, company_name in tickers.items():
    print(f"\n📡 Deep-scanning archives for {ticker}...")
    
    raw_query = f'("{company_name}" OR "{ticker}") AND (stock OR shares OR earnings OR revenue OR dividend OR market)'
    strict_query = urllib.parse.quote(raw_query)
    
    for chunk in range(3):
        chunk_end = (datetime.datetime.now() - datetime.timedelta(days=(chunk * 10))).strftime('%Y-%m-%d')
        chunk_start = (datetime.datetime.now() - datetime.timedelta(days=((chunk + 1) * 10))).strftime('%Y-%m-%d')
        
        print(f"   ⏳ Querying window: {chunk_start} to {chunk_end}")
        url = f"https://newsapi.org/v2/everything?q={strict_query}&language=en&from={chunk_start}&to={chunk_end}&sortBy=publishedAt&pageSize=40&apiKey={NEWS_API_KEY}"
        
        try:
            response = requests.get(url, timeout=10)
            news_data = response.json()
            
            if news_data.get("status") == "ok":
                articles = news_data.get("articles", [])
                
                # --- 🚨 THE STRICT BOUNCER ADDED HERE 🚨 ---
                valid_articles = 0
                for article in articles:
                    title = str(article.get("title", ""))
                    summary = str(article.get("description", ""))
                    
                    # Create the lowercase search pool of just the headline and summary
                    search_pool = f"{title} {summary}".lower()
                    
                    # ONLY insert if the company name or ticker is actually in the title/summary
                    if company_name.lower() in search_pool or ticker.lower() in search_pool:
                        raw_time = article.get("publishedAt", datetime.datetime.now().isoformat())
                        clean_time = raw_time.replace("T", " ").replace("Z", "")[:19]
                        
                        cursor.execute('''
                            INSERT OR IGNORE INTO market_news (ticker, title, summary, url, time_published)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (ticker, title, summary, article.get("url", ""), clean_time))
                        
                        if cursor.rowcount > 0:
                            total_inserted += 1
                            valid_articles += 1
                            
                print(f"      -> Kept {valid_articles} strictly relevant articles out of {len(articles)} fetched.")
            else:
                print(f"      ⚠️ API Error: {news_data.get('message')}")
                
        except Exception as e:
            print(f"      ❌ Network failure: {e}")
        
        time.sleep(2) 

conn.commit()
conn.close()

print(f"\n✅ STRICT DEEP BACKFILL COMPLETE! Injected {total_inserted} high-quality historical records.")
