import database
c = database.get_connection()
cur = c.cursor()
cur.execute("SELECT title, url FROM market_news WHERE source='yahoo' LIMIT 10")
for r in cur.fetchall():
    print(f"Title: {r['title']}\nURL: {r['url']}\n")
