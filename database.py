import sqlite3
def get_connection():
    conn = sqlite3.connect('finpulse.db')
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    print("🗄️ DATABASE SYSTEM: Initializing SQLite Schema...")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            title TEXT UNIQUE,
            summary TEXT,
            url TEXT,
            time_published TEXT,
            sentiment TEXT,
            score REAL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("DATABASE SYSTEM: 'market_news' table is ready.")
if __name__ == "__main__":
    init_db()