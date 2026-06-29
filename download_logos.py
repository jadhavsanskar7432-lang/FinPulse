"""
One-time script to download ticker logos and save them locally in a logos/ folder.
Uses Google's favicon service + direct company URLs as fallbacks.
"""
import requests, os, base64

LOGO_SOURCES = {
    "HDFCBANK": "https://www.google.com/s2/favicons?sz=64&domain=hdfcbank.com",
    "SBIN":     "https://www.google.com/s2/favicons?sz=64&domain=sbi.co.in",
    "TRENT":    "https://www.google.com/s2/favicons?sz=64&domain=trentlimited.com",
    "DMART":    "https://www.google.com/s2/favicons?sz=64&domain=dmartindia.com",
    "SIEMENS":  "https://www.google.com/s2/favicons?sz=64&domain=siemens.com",
    "ABB":      "https://www.google.com/s2/favicons?sz=64&domain=abb.com",
    "MARUTI":   "https://www.google.com/s2/favicons?sz=64&domain=marutisuzuki.com",
    "MM":       "https://www.google.com/s2/favicons?sz=64&domain=mahindra.com",
    "MSFT":     "https://www.google.com/s2/favicons?sz=64&domain=microsoft.com",
    "NVDA":     "https://www.google.com/s2/favicons?sz=64&domain=nvidia.com",
}

os.makedirs("logos", exist_ok=True)

for name, url in LOGO_SOURCES.items():
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and len(resp.content) > 500:
            path = f"logos/{name}.png"
            with open(path, "wb") as f:
                f.write(resp.content)
            print(f"OK  {name}: {len(resp.content)} bytes -> {path}")
        else:
            print(f"FAIL {name}: status={resp.status_code} size={len(resp.content)}")
    except Exception as e:
        print(f"ERR  {name}: {e}")
