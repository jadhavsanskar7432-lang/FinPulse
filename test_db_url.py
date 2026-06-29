import database
c = database.get_connection()
cur = c.cursor()
cur.execute("SELECT source, COUNT(*) as count, url FROM market_news GROUP BY source, url LIMIT 10")
for r in cur.fetchall():
    print(r)
