import time
import subprocess
import sys

# Track the exact Python 3.14 executable path
current_env_executable = sys.executable

print("⚡ FINPULSE BACKGROUND CONVEYOR RUNNING")
print(f"🎯 Target Engine Environment: {current_env_executable}")

while True:
    try:
        # Run scripts using the verified environment executable path
        subprocess.run([current_env_executable, "news_fetcher.py"], check=True)
        subprocess.run([current_env_executable, "sentiment_analyzer.py"], check=True)
        print("📁 JSON Data Matrix updated successfully. Waiting 30s...")
    except Exception as e:
        print(f"⚠️ Pipeline loop warning: {e}")
        
    time.sleep(30)