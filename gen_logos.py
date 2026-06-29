"""
Generate SVG letter-badge logos for all tickers and save as base64 data URIs.
No internet required — all generated from pure SVG.
"""
import base64, os

# Each ticker: (display_label, background_color, text_color)
TICKER_BADGES = {
    "HDFCBANK.NS": ("HB",  "#004C8F", "#ffffff"),  # HDFC blue
    "SBIN.NS":     ("SBI", "#22409A", "#ffffff"),  # SBI blue
    "TRENT.NS":    ("TR",  "#8B1A1A", "#ffffff"),  # Trent maroon
    "DMART.NS":    ("DM",  "#E31837", "#ffffff"),  # DMart red
    "SIEMENS.NS":  ("SI",  "#009999", "#ffffff"),  # Siemens teal
    "ABB.NS":      ("ABB", "#FF0000", "#ffffff"),  # ABB red
    "MARUTI.NS":   ("MA",  "#1B3A6B", "#ffffff"),  # Maruti dark blue
    "M&M.NS":      ("MM",  "#CC0000", "#ffffff"),  # M&M red
    "MSFT":        ("MS",  "#00A4EF", "#ffffff"),  # Microsoft blue
    "NVDA":        ("NV",  "#76B900", "#ffffff"),  # Nvidia green
}

def make_svg_badge(label, bg, fg):
    font_size = 11 if len(label) >= 3 else 13
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
  <rect width="28" height="28" rx="6" fill="{bg}"/>
  <text x="14" y="19" font-family="Arial,sans-serif" font-size="{font_size}" font-weight="bold"
        fill="{fg}" text-anchor="middle" dominant-baseline="auto">{label}</text>
</svg>'''

def svg_to_data_uri(svg_str):
    b64 = base64.b64encode(svg_str.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"

os.makedirs("logos", exist_ok=True)

results = {}
for ticker, (label, bg, fg) in TICKER_BADGES.items():
    svg = make_svg_badge(label, bg, fg)
    uri = svg_to_data_uri(svg)
    # Save SVG file too for inspection
    safe = ticker.replace("&", "").replace(".", "_")
    with open(f"logos/{safe}.svg", "w") as f:
        f.write(svg)
    results[ticker] = uri
    print(f"OK  {ticker}: data URI length={len(uri)}")

# Write a Python file that can be imported directly
lines = ["# -*- coding: utf-8 -*-\n",
         "# Auto-generated SVG badge logos - no network needed\n",
         "LOGO_DATA_URIS = {\n"]
for ticker, uri in results.items():
    lines.append(f'    {repr(ticker)}: {repr(uri)},\n')
lines.append("}\n")

with open("logo_data.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("\nlogo_data.py written successfully.")
