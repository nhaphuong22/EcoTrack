import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from src.database import init_db
from src.api.routers import energy, forecast, anomalies, copilot, buildings

# Initialize Database Schema
init_db()

app = FastAPI(
    title="EcoTrack - Building Energy Management & Copilot API",
    version="1.0.0",
    description="Backend API for building energy forecasting (XGBoost), anomaly detection (Isolation Forest), and conversational AI Copilot."
)

# CORS configuration for Frontend SPA
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(buildings.router)
app.include_router(energy.router)
app.include_router(forecast.router)
app.include_router(anomalies.router)
app.include_router(copilot.router)

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
