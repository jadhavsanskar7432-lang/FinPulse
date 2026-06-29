import database

conn   = database.get_connection()
cursor = conn.cursor()
cursor.execute("""
    ALTER TABLE market_news 
    ADD COLUMN IF NOT EXISTS url_fingerprint VARCHAR(32);
""")
conn.commit()
conn.close()
print("✅ Column added successfully.")