# ⚡ FinPulse Terminal
**Democratizing Quant-Level Market Insights for the Retail Trader**

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B?style=for-the-badge&logo=streamlit)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite)
![NLTK](https://img.shields.io/badge/NLTK-VADER_Sentiment-brightgreen?style=for-the-badge)

FinPulse is a professional-grade, zero-latency financial terminal designed to bridge the information asymmetry gap in modern markets. It provides high-frequency news ingestion, live market pricing, and automated technical divergence detection within a sleek, terminal-style interface.

---

## 🚀 Core Features

### 1. Data Pipeline & Backend
* **Targeted Ingestion Engine:** Utilizes strict boolean query logic (`-sale -deal`) and domain whitelisting to block e-commerce noise and pull only high-value corporate news via REST APIs.
* **Zero-Latency RAM Caching:** Leverages Streamlit `@st.cache_data` with strict Time-To-Live (TTL) protocols to serve market data instantly from memory, bypassing API rate limits.
* **Asynchronous Dual-Stream Integration:** Seamlessly merges slow-moving textual data (NewsAPI/NewsData) with millisecond-live market tape (`yfinance`) into a persistent SQLite database.

### 2. AI & Sentiment Analytics
* **Lexicon-Based NLP Scoring:** Integrates NLTK's VADER sentiment reasoner for localized, high-speed scoring of short-form financial headlines, avoiding the latency and cost of cloud-based LLMs.
* **Algorithmic Trend Smoothing:** Applies a 3-period Rolling Moving Average (via Pandas) to raw sentiment scores to filter daily media noise and reveal macroscopic momentum.

### 3. Strategy & Decision Support
* **Rule-Based Decision Engine:** Evaluates price-to-sentiment divergence to generate actionable **STRONG BUY / HOLD / SELL** algorithmic signals.
* **Market Breadth Aggregation:** A dynamic portfolio-level engine that tallies active signals into a Donut Chart, providing an instant "Bird's Eye View" of macro market health.
* **Relative Performance Analysis:** A normalized multi-select charting tool that converts raw stock prices into Percentage Change, allowing accurate performance overlays across disparate assets.

### 4. Security & DevOps
* **Credential Decoupling:** API keys are isolated using `.env` environment variables.
* **Production-Ready Repo:** Strict `.gitignore` implementation prevents leakage of credentials and local database bloat.

---

## 🛠️ Technology Stack
* **Backend:** Python, SQLite3
* **Data Processing:** Pandas, NLTK (VADER), yfinance, Requests
* **Frontend / UI:** Streamlit, Plotly Express & Graph Objects, Custom CSS (Glassmorphism & Terminal Aesthetics)

---

## ⚙️ Installation & Setup

**1. Clone the Repository**
```bash
git clone [https://github.com/yourusername/finpulse-terminal.git](https://github.com/yourusername/finpulse-terminal.git)
cd finpulse-terminal
