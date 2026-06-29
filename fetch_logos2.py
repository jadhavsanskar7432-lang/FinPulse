# -*- coding: utf-8 -*-
"""
Fetches logos directly from company websites' standard favicon/logo paths.
Also tries Wikipedia API for official logos.
"""
import requests, os

os.makedirs("static/logos", exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Multiple direct sources per ticker
SOURCES = {
    "SBIN": [
        "https://sbi.co.in/favicon.ico",
        "https://www.onlinesbi.sbi/favicon.ico",
        "https://sbionline.sbi/favicon.ico",
    ],
    "TRENT": [
        "https://www.trentlimited.com/favicon.ico",
        "https://tatatrend.com/favicon.ico",
    ],
    "MARUTI": [
        "https://www.marutisuzuki.com/favicon.ico",
        "https://marutisuzuki.com/favicon.ico",
    ],
    "MM": [
        "https://www.mahindra.com/favicon.ico",
        "https://mahindra.com/favicon.ico",
    ],
    "MSFT": [
        "https://www.microsoft.com/favicon.ico",
        "https://microsoft.com/favicon.ico",
    ],
}

MIN_BYTES = 100  # favicons can be small but still valid

for name, urls in SOURCES.items():
    out_path = f"static/logos/{name}.png"
    if os.path.exists(out_path):
        print(f"SKIP {name}: already downloaded")
        continue
    saved = False
    for url in urls:
        try:
            resp = requests.get(url, timeout=8, headers=HEADERS, allow_redirects=True)
            ct = resp.headers.get("Content-Type", "")
            print(f"  {name}: status={resp.status_code} size={len(resp.content)} ct={ct} ({url})")
            if resp.status_code == 200 and len(resp.content) >= MIN_BYTES and "text/html" not in ct:
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                print(f"  OK {name}: saved {len(resp.content)} bytes")
                saved = True
                break
        except Exception as e:
            print(f"  ERR {name}: {e}")
    if not saved:
        print(f"  FAIL {name}: no source worked")

print("\nDone.")
