import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Ensure ai-service root is in sys.path so `src...` imports work from any working directory
AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(AI_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_DIR))

load_dotenv(AI_SERVICE_DIR / ".env")

from src.api.routers import energy, forecast, anomalies, copilot

app = FastAPI(
    title="EcoTrack - Building Energy AI Engine",
    version="1.0.0",
    description="Dedicated AI & Analytics microservice for building energy forecasting (XGBoost), anomaly detection (Isolation Forest), and conversational AI Copilot."
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Clean Domain AI Routers
app.include_router(energy.router)
app.include_router(forecast.router)
app.include_router(anomalies.router)
app.include_router(copilot.router)

@app.get("/")
def root():
    return {
        "system": "EcoTrack AI Engine",
        "status": "operational",
        "version": "1.0.0",
        "docs_url": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting EcoTrack AI Service at http://{host}:{port} ...")
    uvicorn.run("src.main:app", host=host, port=port, reload=True)
