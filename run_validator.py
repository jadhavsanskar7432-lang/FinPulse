from validator import validate_all
import database
conn = database.get_connection()
cursor = conn.cursor()
cursor.execute("SELECT ticker, title, score FROM market_news")
rows = [dict(r) for r in cursor.fetchall()]
conn.close()
validate_all(rows)