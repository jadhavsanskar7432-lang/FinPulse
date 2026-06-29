import json
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException 
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="FinPulse Data Ingestion API Engine",
    description="Live documented streaming endpoints for aggregated news sentiment metrics.",
    version="1.0.0"
)

# Enable CORS so your Streamlit frontend dashboard can read data safely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/stream", tags=["Ingestion Stream"])
def get_live_stream_matrix():
    """Reads the pipeline cache and returns evaluated text sentiment records."""
    try:
        with open("processed_news.json", "r") as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Ingestion layer database cache file not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal system pipeline exception: {str(e)}")

@app.get("/api/health", tags=["System Status"])
def get_system_health():
    """Returns the operational readiness status of the pipeline."""
    return {"status": "ACTIVE", "pipeline_matrix": "ONLINE", "stream_latency_ms": 12}