import requests, base64

URLS = {
    "HDFCBANK.NS": "https://logo.clearbit.com/hdfcbank.com",
    "NVDA":        "https://logo.clearbit.com/nvidia.com",
    "MSFT":        "https://logo.clearbit.com/microsoft.com",
}

for ticker, url in URLS.items():
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        print(f"{ticker}: status={resp.status_code} content-type={resp.headers.get('Content-Type')} size={len(resp.content)} bytes")
        if resp.status_code == 200:
            b64 = base64.b64encode(resp.content).decode()
            print(f"  -> base64 OK, first 60 chars: {b64[:60]}")
        else:
            print(f"  -> FAILED: {resp.text[:200]}")
    except Exception as e:
        print(f"{ticker}: EXCEPTION -> {e}")
