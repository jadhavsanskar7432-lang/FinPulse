import sqlite3
import database
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    print("📥 NLP ENGINE: Downloading VADER Lexicon files...")
    nltk.download('vader_lexicon', quiet=True)

sia = SentimentIntensityAnalyzer()
print("🧠 NLP ENGINE: VADER Context Matrix initialized successfully.")

def process_unscored_news():
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, summary FROM market_news 
            WHERE score IS NULL
        ''')
        unscored_rows = cursor.fetchall()
        
        if not unscored_rows:
            print("🔄 NLP ENGINE: Idle. Zero unscored database rows located.")
            return
            
        print(f"⚙️ NLP ENGINE: Processing sentiment vectors for {len(unscored_rows)} records...")
        
        for row in unscored_rows:
            row_id = row['id']
            title = row['title']
            summary = row['summary'] if row['summary'] else ""
            
            full_text = f"{title}. {summary}"
            
            scores = sia.polarity_scores(full_text)
            compound_score = round(scores['compound'], 2)
            
            if compound_score >= 0.05:
                sentiment_label = "Positive"
            elif compound_score <= -0.05:
                sentiment_label = "Negative"
            else:
                sentiment_label = "Neutral"
                
            cursor.execute('''
                UPDATE market_news
                SET sentiment = ?, score = ?
                WHERE id = ?
            ''', (sentiment_label, compound_score, row_id))
            
            print(f"   🔹 ID {row_id} analyzed -> [{sentiment_label}] (Score: {compound_score})")
            
        conn.commit()
        print(f"✅ NLP ENGINE: Transaction committed. Cleaned and saved {len(unscored_rows)} records.")
        
    except Exception as e:
        print(f"❌ NLP ENGINE ERROR: Transaction rolled back. Details: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    process_unscored_news()
