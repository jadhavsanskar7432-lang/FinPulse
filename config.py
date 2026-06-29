# ==========================================
# FINPULSE CONFIGURATION — SINGLE SOURCE OF TRUTH
# ==========================================
# All ticker, sector, and display data lives here.
# Every other module imports from this file.

TICKERS = {
    "HDFCBANK.NS": {"name": "HDFC Bank",          "sector": "Banking"},
    "SBIN.NS":     {"name": "State Bank of India", "sector": "Banking"},
    "TRENT.NS":    {"name": "Trent",               "sector": "Retail"},
    "DMART.NS":    {"name": "Avenue Supermarts",    "sector": "Retail"},
    "SIEMENS.NS":  {"name": "Siemens India",       "sector": "Manufacturing"},
    "ABB.NS":      {"name": "ABB India",           "sector": "Manufacturing"},
    "MARUTI.NS":   {"name": "Maruti Suzuki",       "sector": "Automobile"},
    "M&M.NS":      {"name": "Mahindra & Mahindra", "sector": "Automobile"},
    "MSFT":        {"name": "Microsoft",           "sector": "Global"},
    "NVDA":        {"name": "Nvidia",              "sector": "Global"},
}

# Auto-generate sector groupings preserving insertion order
SECTORS = {}
for _ticker, _info in TICKERS.items():
    _sector = _info["sector"]
    if _sector not in SECTORS:
        SECTORS[_sector] = []
    SECTORS[_sector].append(_ticker)

# Flat list of all ticker symbols
ALL_TICKER_SYMBOLS = list(TICKERS.keys())

# Sector display icons for the dashboard UI
SECTOR_ICONS = {
    "Banking":       "🏦",
    "Retail":        "🛒",
    "Manufacturing": "🏭",
    "Automobile":    "🚗",
    "Global":        "🌐",
}


# Ticker logo URLs — uses Clearbit Domains API (reliable, no auth needed)
TICKER_LOGOS = {
    "HDFCBANK.NS": "https://logo.clearbit.com/hdfcbank.com",
    "SBIN.NS":     "https://logo.clearbit.com/sbi.co.in",
    "TRENT.NS":    "https://logo.clearbit.com/trentlimited.com",
    "DMART.NS":    "https://logo.clearbit.com/dmartindia.com",
    "SIEMENS.NS":  "https://logo.clearbit.com/siemens.com",
    "ABB.NS":      "https://logo.clearbit.com/abb.com",
    "MARUTI.NS":   "https://logo.clearbit.com/marutisuzuki.com",
    "M&M.NS":      "https://logo.clearbit.com/mahindra.com",
    "MSFT":        "https://logo.clearbit.com/microsoft.com",
    "NVDA":        "https://logo.clearbit.com/nvidia.com",
}


def get_logo_url(ticker):
    """Returns a logo image URL for a given ticker symbol."""
    return TICKER_LOGOS.get(ticker, "")


def get_display_name(ticker):
    """Returns a clean display name (strips .NS suffix for Indian stocks)."""
    return ticker.replace(".NS", "")


def get_company_name(ticker):
    """Returns the full company name for a given ticker symbol."""
    info = TICKERS.get(ticker)
    return info["name"] if info else ticker


def get_sector(ticker):
    """Returns the sector for a given ticker symbol."""
    info = TICKERS.get(ticker)
    return info["sector"] if info else "Unknown"
