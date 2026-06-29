# -*- coding: utf-8 -*-
"""Bakes downloaded PNGs + SVG badges into logo_data.py as base64 data URIs."""
import base64, os

def svg_b64(label, bg, fg="#ffffff"):
    fs = 11 if len(label) >= 3 else 13
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">'
        f'<rect width="28" height="28" rx="6" fill="{bg}"/>'
        f'<text x="14" y="19" font-family="Arial,sans-serif" font-size="{fs}" font-weight="bold"'
        f' fill="{fg}" text-anchor="middle" dominant-baseline="auto">{label}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

# ticker -> (local png path or None, fallback label, fallback color)
TICKERS = {
    "HDFCBANK.NS": ("static/logos/HDFCBANK.png", "HB",  "#004C8F"),
    "SBIN.NS":     ("static/logos/SBIN.png",     "SBI", "#22409A"),
    "TRENT.NS":    (None,                         "TR",  "#8B1A1A"),
    "DMART.NS":    ("static/logos/DMART.png",    "DM",  "#E31837"),
    "SIEMENS.NS":  ("static/logos/SIEMENS.png",  "SI",  "#009999"),
    "ABB.NS":      ("static/logos/ABB.png",       "ABB", "#FF0000"),
    "MARUTI.NS":   (None,                         "MA",  "#1B3A6B"),
    "M&M.NS":      (None,                         "MM",  "#CC0000"),
    "MSFT":        ("static/logos/MSFT.png",     "MS",  "#00A4EF"),
    "NVDA":        ("static/logos/NVDA.png",     "NV",  "#76B900"),
}

lines = [
    "# -*- coding: utf-8 -*-\n",
    "# Auto-generated: base64 logos embedded directly - no network or static serving needed\n\n",
    "LOGO_URIS = {\n",
]

for ticker, (fpath, label, color) in TICKERS.items():
    if fpath and os.path.exists(fpath):
        with open(fpath, "rb") as f:
            data = f.read()
        uri = "data:image/png;base64," + base64.b64encode(data).decode()
        src = "PNG"
    else:
        uri = svg_b64(label, color)
        src = "SVG"
    lines.append(f"    {repr(ticker)}: {repr(uri)},  # {src}\n")
    print(f"  {src:3}  {ticker}: {len(uri)} chars")

lines.append("}\n\n\n")
lines.append(
    "def get_ticker_logo_html(ticker, size=26):\n"
    '    src = LOGO_URIS.get(ticker, "")\n'
    '    if not src:\n'
    '        return ""\n'
    "    return (\n"
    '        f\'<img src="{src}" width="{size}" height="{size}" \'\n'
    '        f\'style="border-radius:5px; object-fit:contain; background:white; \'\n'
    '        f\'padding:2px; margin-right:7px; flex-shrink:0; vertical-align:middle;"/>\'\n'
    "    )\n"
)

with open("logo_data.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("\nlogo_data.py written OK")
