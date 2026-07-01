import database
import os
# pyrefly: ignore [missing-import]
from transformers import pipeline   
# pyrefly: ignore [missing-import]
from transformers.utils import logging as hf_logging

# 🛑 CRITICAL WINDOWS FIX: Disable progress bars to prevent subprocess crashes
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
hf_logging.disable_progress_bar()

# ==========================================
# FINBERT SENTIMENT ENGINE
# ==========================================

print("🧠 NLP ENGINE: Loading FinBERT financial sentiment model...")
print("   (First run will download ~420MB model — cached for future runs)")

# Load FinBERT using HuggingFace pipeline — simplest and most reliable approach
finbert = pipeline(
    "sentiment-analysis",
    model="ProsusAI/finbert",
    tokenizer="ProsusAI/finbert",
    truncation=True,
    max_length=512
)

print("✅ NLP ENGINE: FinBERT model loaded successfully.")


def map_finbert_score(result):
    """
    Maps FinBERT output to a compound-style score.
    
    FinBERT returns: {'label': 'positive'|'negative'|'neutral', 'score': 0.0-1.0}
    
    Mapping:
      positive (conf 0.92) → score = +0.92, sentiment = "Positive"
      negative (conf 0.85) → score = -0.85, sentiment = "Negative"  
      neutral  (conf 0.78) → score =  0.00, sentiment = "Neutral"
    """
    label = result["label"].lower()
    confidence = round(result["score"], 4)

    if label == "positive":
        return "Positive", round(confidence, 2)
    elif label == "negative":
        return "Negative", round(-confidence, 2)
    else:
        return "Neutral", 0.0


def process_unscored_news():
    """Processes all unscored articles in the database using FinBERT."""
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

        print(f"⚙️ NLP ENGINE: Processing sentiment for {len(unscored_rows)} records with FinBERT...")

        # Process in batches of 16 for memory efficiency
        batch_size = 16
        total_processed = 0

        for i in range(0, len(unscored_rows), batch_size):
            batch = unscored_rows[i:i + batch_size]

            # Prepare texts for batch inference
            texts = []
            for row in batch:
                title = row['title'] if row['title'] else ""
                summary = row['summary'] if row['summary'] else ""
                full_text = f"{title}. {summary}".strip()
                # Ensure we have some text to analyze
                if not full_text or full_text == ".":
                    full_text = "Market update."
                texts.append(full_text)

            # Run FinBERT batch inference
            try:
                results = finbert(texts)
            except Exception as model_err:
                print(f"   ⚠️ FinBERT batch error: {model_err}")
                continue

            # Update database with results
            for row, result in zip(batch, results):
                sentiment_label, compound_score = map_finbert_score(result)

                cursor.execute('''
                    UPDATE market_news
                    SET sentiment = %s, score = %s
                    WHERE id = %s
                ''', (sentiment_label, compound_score, row['id']))

                total_processed += 1
                print(f"   🔹 ID {row['id']} → [{sentiment_label}] (Score: {compound_score:+.2f})")

            conn.commit()   # commit per batch -- a later failure won't lose earlier progress
            print(f"   📊 Batch {i // batch_size + 1} complete ({len(batch)} records)")

        print(f"✅ NLP ENGINE: FinBERT analysis complete. Scored {total_processed} records.")

    except Exception as e:
        import traceback
        print(f"❌ NLP ENGINE ERROR: {e}")
        traceback.print_exc()
        raise
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    process_unscored_news()

    # ── Auto-trigger validator after scoring ────────────────────
    # Reads freshly-scored articles from DB, validates each ticker
    # against Moneycontrol, Tickertape, TradingView, writes to
    # analyst_validation table for the dashboard to display.
    try:
        from validator import validate_all
        import database

        conn   = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ticker, score FROM market_news WHERE score IS NOT NULL"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        if rows:
            print(f"\n[Validator] Auto-triggering for {len(set(r['ticker'] for r in rows))} tickers...")
            validate_all(rows)
        else:
            print("[Validator] No scored rows found — skipping validation.")

    except Exception as val_err:
        print(f"[Validator] Auto-trigger error (non-fatal): {val_err}")