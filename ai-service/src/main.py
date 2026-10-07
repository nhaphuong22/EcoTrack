import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from src.api.routers import energy, forecast, anomalies, copilot, internal

app = FastAPI(
    title="EcoTrack - Building Energy Management & Copilot AI Engine",
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

# Mount AI Routers
app.include_router(energy.router)
app.include_router(forecast.router)
app.include_router(anomalies.router)
app.include_router(copilot.router)
app.include_router(internal.router)

@app.get("/")
def root():
    return {
        "system": "EcoTrack BEMS Engine",
        "status": "operational",
        "version": "1.0.0",
        "docs_url": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
