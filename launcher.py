import subprocess
import time
import sys
import database

print("FINPULSE ENTERPRISE LAUNCHER INITIATED")
database.init_db()
print("🌐 Booting up Terminal UI...")
dashboard = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard.py"])
time.sleep(5)
try:
    while True:
        print("\n📥 SYSTEM: Triggering News Ingestion...")
        subprocess.run([sys.executable, "news_fetcher.py"])
        
        print(" SYSTEM: Triggering AI Sentiment Analysis...")
        subprocess.run([sys.executable, "sentiment_analyzer.py"])
        
        print(" SYSTEM: Pipeline resting for 60 seconds to respect API rate limits...")
        time.sleep(30)
        
except KeyboardInterrupt:
    print("\n SYSTEM: Shutting down FinPulse Terminal and background processes...")
    dashboard.terminate()
    sys.exit()