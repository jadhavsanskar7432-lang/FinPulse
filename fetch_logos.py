# -*- coding: utf-8 -*-
"""
Downloads official ticker logos into static/logos/ for Streamlit static serving.
Tries multiple URL sources per ticker. Run once; logos are cached locally.
"""
import requests, os, sys

os.makedirs("static/logos", exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Each ticker: list of URLs to try in order (first success wins)
LOGO_SOURCES = {
    "HDFCBANK":  [
        "https://www.google.com/s2/favicons?sz=128&domain=hdfcbank.com",
        "https://logo.clearbit.com/hdfcbank.com",
    ],
    "SBIN":  [
        "https://www.google.com/s2/favicons?sz=128&domain=sbi.co.in",
        "https://logo.clearbit.com/sbi.co.in",
    ],
    "TRENT": [
        "https://www.google.com/s2/favicons?sz=128&domain=trentlimited.com",
        "https://logo.clearbit.com/trentlimited.com",
    ],
    "DMART": [
        "https://www.google.com/s2/favicons?sz=128&domain=dmartindia.com",
        "https://logo.clearbit.com/dmartindia.com",
    ],
    "SIEMENS": [
        "https://www.google.com/s2/favicons?sz=128&domain=siemens.com",
        "https://logo.clearbit.com/siemens.com",
    ],
    "ABB": [
        "https://www.google.com/s2/favicons?sz=128&domain=abb.com",
        "https://logo.clearbit.com/abb.com",
    ],
    "MARUTI": [
        "https://www.google.com/s2/favicons?sz=128&domain=marutisuzuki.com",
        "https://logo.clearbit.com/marutisuzuki.com",
    ],
    "MM": [
        "https://www.google.com/s2/favicons?sz=128&domain=mahindra.com",
        "https://logo.clearbit.com/mahindra.com",
    ],
    "MSFT": [
        "https://www.google.com/s2/favicons?sz=128&domain=microsoft.com",
        "https://logo.clearbit.com/microsoft.com",
    ],
    "NVDA": [
        "https://www.google.com/s2/favicons?sz=128&domain=nvidia.com",
        "https://logo.clearbit.com/nvidia.com",
    ],
}

MIN_VALID_BYTES = 500  # anything smaller is a placeholder/error image

for name, urls in LOGO_SOURCES.items():
    out_path = f"static/logos/{name}.png"
    saved = False
    for url in urls:
        try:
            resp = requests.get(url, timeout=8, headers=HEADERS)
            if resp.status_code == 200 and len(resp.content) >= MIN_VALID_BYTES:
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                print(f"OK   {name}: {len(resp.content)} bytes  ({url})")
                saved = True
                break
            else:
                print(f"SKIP {name}: status={resp.status_code} size={len(resp.content)} ({url})")
        except Exception as e:
            print(f"ERR  {name}: {e} ({url})")
    if not saved:
        print(f"FAIL {name}: no valid source found")

print("\nDone. Files saved to static/logos/")
