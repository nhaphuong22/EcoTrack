import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.mlops.retrain import RetrainAlreadyRunningError, start_retrain
from src.mlops.status import get_mlops_status

router = APIRouter(prefix="/internal/mlops", tags=["MLOps"])


@router.get("/status")
async def mlops_status():
    """
    Return consolidated model, drift, anomaly-quality, retrain-history, and
    benchmark status (FR26). Runs blocking disk and MLflow reads off the event loop.
    """
    return await asyncio.to_thread(get_mlops_status)


@router.post("/retrain", status_code=202)
async def trigger_retrain():
    """
    Trigger on-demand model retraining in a background thread with guarded
    promotion (FR25). Returns 202 with run metadata, or 409 if already running.
    """
    try:
        return start_retrain(trigger="manual")
    except RetrainAlreadyRunningError as exc:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc), "code": "ERR_RETRAIN_IN_PROGRESS"},
        )
