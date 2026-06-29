import datetime
# pyrefly: ignore [missing-import]  
import requests
import urllib.parse
import os
import time
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
    
import database
from config import TICKERS

load_dotenv()

print("🕰️ INITIALIZING DEEP-TIME BACKFILL ENGINE...")

# Securely load API key from .env
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
if not NEWS_API_KEY:
    print("❌ FATAL ERROR: API Key missing. Please check your .env file.")
    exit()

conn = database.get_connection()
cursor = conn.cursor()
total_inserted = 0

for ticker, info in TICKERS.items():
    company_name = info["name"]
    print(f"\n📡 Deep-scanning archives for {ticker} ({company_name})...")

    raw_query = f'("{company_name}" OR "{ticker.replace(".NS", "")}") AND (stock OR shares OR earnings OR revenue OR dividend OR market)'
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

                valid_articles = 0
                for article in articles:
                    title = str(article.get("title", ""))
                    summary = str(article.get("description", ""))

                    search_pool = f"{title} {summary}".lower()

                    if company_name.lower() in search_pool or ticker.replace(".NS", "").lower() in search_pool:
                        raw_time = article.get("publishedAt", datetime.datetime.now().isoformat())
                        clean_time = raw_time.replace("T", " ").replace("Z", "")[:19]

                        cursor.execute('''
                            INSERT INTO market_news (ticker, title, summary, url, time_published, source)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (title) DO NOTHING
                        ''', (ticker, title, summary, article.get("url", ""), clean_time, "newsapi"))

                        if cursor.rowcount > 0:
                            total_inserted += 1
                            valid_articles += 1

                print(f"      -> Kept {valid_articles} relevant articles out of {len(articles)} fetched.")
            else:
                print(f"      ⚠️ API Error: {news_data.get('message')}")

        except Exception as e:
            print(f"      ❌ Network failure: {e}")

        time.sleep(2)

conn.commit()
conn.close()

print(f"\n✅ DEEP BACKFILL COMPLETE! Injected {total_inserted} high-quality historical records.")