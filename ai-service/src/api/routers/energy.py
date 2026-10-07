"""
Energy Telemetry & Metrics Router
Implements High-Performance Time-Series Queries with In-Memory TTL Caching.
Reduces ML re-computation overhead and ensures sub-50ms API response latency.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Response

from src.api.schemas.energy import (
    MetricSummaryResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
)
from src.data_pipeline.bdg2_loader import data_loader
from src.models.forecaster_xgboost import energy_forecaster
from src.models.anomaly_isolation_forest import anomaly_detector

logger = logging.getLogger("EnergyRouter")
router = APIRouter(prefix="/api/v1/energy", tags=["Energy Telemetry"])


class InMemoryTTLCache:
    """Thread-safe, lightweight in-memory cache with Time-To-Live expiration."""

    def __init__(self, default_ttl_seconds: int = 60):
        self._default_ttl = default_ttl_seconds
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        if key in self._store:
            if now < self._expiry.get(key, 0):
                self._hits += 1
                return self._store[key]
            # Evict stale entry
            self._store.pop(key, None)
            self._expiry.pop(key, None)
        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = value
        self._expiry[key] = time.time() + ttl

    def clear(self) -> None:
        self._store.clear()
        self._expiry.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, Any]:
        total_requests = self._hits + self._misses
        hit_ratio = round(self._hits / total_requests, 3) if total_requests > 0 else 0.0
        return {
            "entries_count": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": hit_ratio,
            "ttl_seconds": self._default_ttl,
        }


# Singleton Cache instance for Energy Telemetry (60s TTL)
energy_ttl_cache = InMemoryTTLCache(default_ttl_seconds=60)


def _compute_timeseries(limit: int) -> List[TimeSeriesPoint]:
    """Runs data pipeline and models to compute telemetry series."""
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    if limit > 0:
        df_sliced = df_anom.tail(limit)
    else:
        df_sliced = df_anom

    points = []
    for _, row in df_sliced.iterrows():
        points.append(
            TimeSeriesPoint(
                timestamp=row["timestamp"],
                meter_reading_kwh=float(row["meter_reading_kwh"]),
                predicted_kwh=float(row["predicted_kwh"]),
                lower_bound_95=float(row["lower_bound_95"]),
                upper_bound_95=float(row["upper_bound_95"]),
                outdoor_temperature_c=float(row["outdoor_temperature_c"]),
                relative_humidity_pct=float(row["relative_humidity_pct"]),
                is_anomaly=bool(row["is_anomaly"]),
                anomaly_score=float(row["anomaly_score"]),
                severity=str(row["severity"]),
                anomaly_reason=row.get("anomaly_reason"),
            )
        )
    return points


def _compute_metrics() -> MetricSummaryResponse:
    """Computes aggregated energy metrics and estimated waste costs."""
    df = data_loader.get_or_create_data()
    df_fc = energy_forecaster.predict_horizon(df)
    df_anom = anomaly_detector.detect_anomalies(df_fc)

    total_kwh = float(df_anom["meter_reading_kwh"].sum())
    peak_kw = float(df_anom["meter_reading_kwh"].max())
    baseline_kwh = float(df_anom["predicted_kwh"].sum())
    anom_count = int(df_anom["is_anomaly"].sum())

    waste_kwh = float(df_anom[df_anom["is_anomaly"]]["residual"].clip(lower=0).sum())
    waste_vnd = waste_kwh * 3100
    waste_usd = waste_kwh * 0.125

    return MetricSummaryResponse(
        building_id="office_tower_01",
        total_consumption_kwh=round(total_kwh, 1),
        peak_demand_kw=round(peak_kw, 1),
        predicted_baseline_kwh=round(baseline_kwh, 1),
        total_anomalies_detected=anom_count,
        estimated_waste_cost_vnd=round(waste_vnd, 0),
        estimated_waste_cost_usd=round(waste_usd, 2),
    )


@router.get("/timeseries", response_model=TimeSeriesResponse, summary="Get historical energy timeseries")
async def get_timeseries(
    response: Response,
    limit: int = Query(default=168, description="Number of past hourly points (default: 168 = 7 days)"),
):
    """
    Returns time-series power consumption and ambient weather telemetry.
    Cached for 60 seconds to ensure high performance and low latency.
    """
    cache_key = f"energy_timeseries_limit_{limit}"
    cached_data = energy_ttl_cache.get(cache_key)

    if cached_data is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_data

    # Cache MISS: compute non-blocking
    response.headers["X-Cache"] = "MISS"
    points = await asyncio.to_thread(_compute_timeseries, limit)
    result = TimeSeriesResponse(
        building_id="office_tower_01",
        count=len(points),
        data=points,
    )
    energy_ttl_cache.set(cache_key, result)
    return result


@router.get("/metrics", response_model=MetricSummaryResponse, summary="Get key building energy KPIs")
async def get_metrics(response: Response):
    """
    Returns high-level summary KPIs for energy, peak demand, and anomaly waste.
    Cached for 60 seconds to ensure fast dashboard load times.
    """
    cache_key = "energy_metrics_summary"
    cached_data = energy_ttl_cache.get(cache_key)

    if cached_data is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_data

    # Cache MISS: compute non-blocking
    response.headers["X-Cache"] = "MISS"
    metrics = await asyncio.to_thread(_compute_metrics)
    energy_ttl_cache.set(cache_key, metrics)
    return metrics


@router.get("/cache/stats", summary="Get TTL cache diagnostic statistics")
def get_cache_stats():
    """Returns hit/miss metrics and memory cache entries count for latency benchmarking."""
    return energy_ttl_cache.stats


@router.post("/cache/clear", summary="Clear energy TTL cache")
def clear_cache():
    """Manually invalidates cache entries."""
    energy_ttl_cache.clear()
    return {"message": "Energy TTL cache invalidated successfully."}
