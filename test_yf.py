import yfinance as yf
import json
print(json.dumps(yf.Ticker("NVDA").news[:2], indent=2))
