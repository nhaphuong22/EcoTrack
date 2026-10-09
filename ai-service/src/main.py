import hmac
import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from src.config import get_internal_api_key
from src.data_pipeline.serving_frame import (
    InsufficientHistoryError,
    ModelArtifactError,
    ServingDataError,
)

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


@app.middleware("http")
async def enforce_internal_token(request: Request, call_next):
    if request.url.path == "/internal" or request.url.path.startswith("/internal/"):
        expected_key = get_internal_api_key()
        provided_key = request.headers.get("X-Internal-Token")
        if not expected_key or not provided_key or not hmac.compare_digest(
            provided_key.encode("utf-8"), expected_key.encode("utf-8")
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing internal service token", "code": "ERR_UNAUTHORIZED"},
            )
    return await call_next(request)

# Mount Clean Domain AI Routers
app.include_router(energy.router)
app.include_router(forecast.router)
app.include_router(anomalies.router)
app.include_router(copilot.router)


@app.exception_handler(ServingDataError)
async def serving_data_error_handler(request, exc: ServingDataError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "code": "ERR_DATA_NOT_FOUND"},
    )


@app.exception_handler(ModelArtifactError)
async def model_artifact_error_handler(request, exc: ModelArtifactError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "code": "ERR_MODEL_NOT_FOUND"},
    )


@app.exception_handler(InsufficientHistoryError)
async def insufficient_history_error_handler(request, exc: InsufficientHistoryError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "code": "ERR_INSUFFICIENT_HISTORY"},
    )

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
    if not get_internal_api_key():
        print("ERROR: INTERNAL_API_KEY environment variable is required but not set.", file=sys.stderr)
        sys.exit(1)
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting EcoTrack AI Service at http://{host}:{port} ...")
    uvicorn.run("src.main:app", host=host, port=port, reload=True)
