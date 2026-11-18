import asyncio
from contextlib import asynccontextmanager
import hmac
import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from src.config import get_internal_api_key, get_models_dir
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

from src.api.routers import energy, forecast, anomalies, copilot, mlops
from src.mlops.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        await asyncio.to_thread(stop_scheduler)


app = FastAPI(
    title="EcoTrack - Building Energy AI Engine",
    version="1.0.0",
    description="Dedicated AI & Analytics microservice for building energy forecasting (XGBoost), anomaly detection (Isolation Forest), and conversational AI Copilot.",
    lifespan=lifespan,
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
app.include_router(mlops.router)


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
def health(details: bool = False):
    if not details:
        return {"status": "healthy"}

    models_dir = get_models_dir()
    xgb_exists = (models_dir / "xgboost_forecaster.joblib").is_file()
    iso_exists = (models_dir / "isolation_forest.joblib").is_file()

    # Report the real champion status (Story 4.5), feeding Story 2.3 / 4.10. This loads the
    # champion artifact (no caching) so health agrees with what serving actually does, rather
    # than reporting a champion the service would 503 on. Best-effort: never raises.
    champion_status = "unavailable"
    champion_version = None
    try:
        from src.mlops.tracking import champion_health

        _health = champion_health()
        champion_status = _health["status"]
        champion_version = _health["version"]
    except Exception:
        champion_status = "unavailable"
        champion_version = None

    # Forecast availability mirrors serving: a resolved champion serves; a broken champion
    # makes serving 503 (no fallback), so it is NOT "loaded"; otherwise serving falls back to
    # the on-disk forecaster.
    if champion_status == "resolved":
        forecast_status = "loaded"
    elif champion_status == "broken":
        forecast_status = "unavailable"
    else:
        forecast_status = "loaded" if xgb_exists else "unavailable"

    copilot_engine = "rule_based_fallback"
    if os.getenv("GEMINI_API_KEY", "").strip():
        copilot_engine = "google_genai"
    elif os.getenv("OPENAI_API_KEY", "").strip():
        copilot_engine = "openai"

    return {
        "status": "healthy",
        "models": {
            "forecast": forecast_status,
            "anomaly": "loaded" if iso_exists else "unavailable",
            "champion_version": champion_version,
            "champion": champion_status,
        },
        "copilot_engine": copilot_engine,
    }

if __name__ == "__main__":
    import uvicorn
    if not get_internal_api_key():
        print("ERROR: INTERNAL_API_KEY environment variable is required but not set.", file=sys.stderr)
        sys.exit(1)
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting EcoTrack AI Service at http://{host}:{port} ...")
    uvicorn.run("src.main:app", host=host, port=port, reload=True)
