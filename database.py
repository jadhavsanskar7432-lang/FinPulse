import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
load_dotenv()
# PostgreSQL connection configuration loaded from .env
DB_CONFIG = {
    "host":     os.getenv("PG_HOST", "localhost"),
    "port":     os.getenv("PG_PORT", "5432"),
    "dbname":   os.getenv("PG_DATABASE", "finpulse"),
    "user":     os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", ""),
    "sslmode":  os.getenv("PG_SSLMODE", "prefer"),
}
def get_connection():
    """Returns a new PostgreSQL connection with RealDictCursor for dict-style row access."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    return conn
def init_db():
    """Creates the market_news table if it doesn't exist."""
    print("🗄️ DATABASE SYSTEM: Initializing PostgreSQL Schema...")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_news (
            id SERIAL PRIMARY KEY,
            ticker TEXT,
            title TEXT UNIQUE,
            summary TEXT,
            url TEXT,
            time_published TIMESTAMP,
            sentiment TEXT,
            score REAL,
            source TEXT DEFAULT 'newsapi'
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ DATABASE SYSTEM: 'market_news' table is ready on PostgreSQL.")
if __name__ == "__main__":
    init_db()