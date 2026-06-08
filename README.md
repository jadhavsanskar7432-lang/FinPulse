# ⚡ FinPulse Terminal Core
**High-Frequency Financial News Sentiment & Market Correlation Engine**

![System State](https://img.shields.io/badge/System%20State-Active%20Enterprise%20Engine-10b981?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B?style=for-the-badge)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge)

**Developer:** Sanskar Jadhav  
**Portfolio:** [Visit My Website](INSERT_YOUR_WEBSITE_LINK_HERE)

## 📖 Overview
FinPulse is a local, end-to-end data engineering pipeline and interactive terminal dashboard designed to ingest live global financial news, score it using Natural Language Processing (NLP), and visually correlate the resulting sentiment index against real-time stock market price action.

Built to handle live data streams, this project demonstrates full-stack data engineering capabilities including REST API integration, data cleaning, relational database architecture, local AI processing, and advanced UI/UX state management.

---

## 🛠️ Technology Stack
This project was built using a robust, data-driven Python stack focused on Object-Oriented principles and efficient exception handling:

* **Backend & Data Pipeline:** Python
* **Database:** SQLite (built-in relational data storage)
* **Frontend UI:** Streamlit (custom-styled with dynamic CSS)
* **Natural Language Processing (NLP):** NLTK (VADER Lexicon)
* **Data Visualization:** Plotly (Interactive Spline & Candlestick charts)
* **Market Data APIs:** `yfinance` (Yahoo Finance live OHLC data)
* **News Ingestion APIs:** NewsAPI (High-fidelity boolean queries)
* **Data Manipulation:** Pandas & NumPy

---

## 🚀 Key Engineering Features

### 1. Decoupled Pipeline Architecture
Instead of a single monolithic script, the system relies on a Master Launcher (`launcher.py`) that orchestrates parallel background processes. Data ingestion, AI processing, and the frontend UI operate independently, preventing UI freezing and ensuring continuous background data flows.

### 2. High-Fidelity Data Ingestion
Integrates with NewsAPI using strict boolean search logic and `qInTitle` parameters to completely eliminate "Full-Text Bleed" and data noise, ensuring target asset relevance. Includes automated bulk-loading for historical charting.

### 3. Enterprise Database Layer
Utilizes an SQLite relational database to enable ACID-compliant concurrent writes from the NLP worker and high-speed reads from the Streamlit dashboard via optimized SQL queries.

### 4. Local AI Sentiment Engine
Utilizes NLTK's VADER (Valence Aware Dictionary and sEntiment Reasoner). The engine parses complex sentence structures, understands negations, and applies mathematical heuristics to grade financial context entirely locally.

### 5. Reactive UI & State Persistence
Features a custom-styled, terminal-inspired interface. Includes a dynamic Light/Dark Mode engine that injects CSS directly into Pandas rendering and uses URL Query Parameters to persist UI state across hard browser reloads.

### 6. Real-Time Market Correlation
Integrates natively with the Yahoo Finance API to pull live OHLC (Open, High, Low, Close) candlestick data, plotted synchronously alongside the aggregated AI Sentiment Index.

---

## 🗂️ Project Structure

```text
📁 finpulse_project/
│
├── launcher.py               # Master orchestration script
├── news_fetcher.py           # Background REST API ingestion worker
├── sentiment_analyzer.py     # Local NLP VADER scoring worker
├── database.py               # SQLite connection and schema manager
├── dashboard.py              # Streamlit frontend & charting engine
├── README.md                 # Project documentation
└── finpulse.db               # Local SQLite database (Auto-generated on launch)
