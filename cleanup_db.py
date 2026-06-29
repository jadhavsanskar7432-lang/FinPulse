import database
c = database.get_connection()
cur = c.cursor()
cur.execute("DELETE FROM market_news WHERE source='yahoo'")
c.commit()
print(f"Deleted {cur.rowcount} bad Yahoo news records.")
c.close()
