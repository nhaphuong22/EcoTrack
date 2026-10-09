"""
Anomaly Detection & Event Service for EcoTrack:
Evaluates real-time incoming energy telemetry using the trained Isolation Forest model
and the EnergyInferencePipeline. Automatically flags anomalies, calculates severity,
generates preliminary corrective actions, and persists records to the `anomaly_events` repository.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

import joblib
import pandas as pd

from src.config import get_models_dir
from src.data_pipeline.inference_pipeline import EnergyInferencePipeline
from src.data_pipeline.serving_frame import ModelArtifactError
from src.data_pipeline.stream_worker import meter_reading_repository

logger = logging.getLogger("AnomalyService")


class AnomalyEventRepository:
    """In-memory repository for storing detected anomaly events."""

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._events: List[Dict[str, Any]] = []

    def add_event(self, event: Dict[str, Any]) -> None:
        """Stores a newly generated anomaly event."""
        record = event.copy()
        if "created_at" not in record:
            record["created_at"] = datetime.now(timezone.utc).isoformat()

        self._events.append(record)
        if len(self._events) > self._max_size:
            self._events = self._events[-self._max_size:]

    def get_events(
        self, limit: Optional[int] = None, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns stored anomaly events, newest first."""
        events = list(reversed(self._events))
        if severity:
            events = [e for e in events if e.get("severity") == severity.upper()]
        if limit and limit > 0:
            events = events[:limit]
        return events

    def count(self) -> int:
        """Returns total count of logged anomaly events."""
        return len(self._events)

    def clear(self) -> None:
        """Empties anomaly event repository."""
        self._events.clear()


# Global singleton repository for anomaly events
anomaly_event_repository = AnomalyEventRepository()


class AnomalyDetectionService:
    """
    Evaluates streaming meter readings against the Isolation Forest model,
    assigns severity levels, and logs actionable incident events.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        pipeline: Optional[EnergyInferencePipeline] = None,
        event_repository: Optional[AnomalyEventRepository] = None,
        score_threshold: float = -0.035,
    ):
        models_dir = get_models_dir()
        self.model_path = Path(model_path) if model_path else (models_dir / "isolation_forest.joblib")
        self.pipeline = pipeline or EnergyInferencePipeline(models_dir=models_dir)
        self.event_repository = event_repository or anomaly_event_repository
        self.score_threshold = score_threshold

        self.iso_model: Any = None
        self._history_buffer: List[Dict[str, Any]] = []

        self._load_model()
        self._initialize_baseline_history()

    def _load_model(self) -> None:
        """Loads trained Isolation Forest estimator from disk, raising ModelArtifactError if missing."""
        if not self.model_path.exists():
            raise ModelArtifactError(
                f"Model artifact not found: {self.model_path.name}",
                file_path=str(self.model_path),
            )

        try:
            logger.info("Loading Isolation Forest model from %s...", self.model_path)
            self.iso_model = joblib.load(self.model_path)
        except Exception as e:
            raise ModelArtifactError(
                f"Failed to load model artifact {self.model_path.name}: {e}",
                file_path=str(self.model_path),
            )


    def _initialize_baseline_history(self) -> None:
        """
        Pre-seeds initial 24 historical points from office_building_clean.csv
        so that incoming readings immediately have valid 24h lag context.
        """
        backend_dir = Path(__file__).resolve().parents[2]
        csv_path = backend_dir / "data" / "processed" / "office_building_clean.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, nrows=48)
                records = df[["timestamp", "meter_reading", "air_temperature"]].to_dict(orient="records")
                self._history_buffer = records[-24:]
                logger.info("Pre-seeded anomaly service buffer with %d baseline readings.", len(self._history_buffer))
            except Exception as e:
                logger.warning("Could not pre-seed anomaly baseline history: %s", e)

    def determine_severity(
        self,
        anomaly_score: float,
        actual_reading: float,
        lag_24h: Optional[float] = None,
    ) -> str:
        """
        Determines anomaly severity based on score deviation and contextual surge ratio.
        - HIGH: Anomaly score >= 0.00 OR consumption surge >= 200% above diurnal baseline
        - MEDIUM: Anomaly score >= -0.03 OR consumption surge >= 100% above diurnal baseline
        - LOW: Mild anomaly
        """
        surge_ratio = (actual_reading / lag_24h) if (lag_24h and lag_24h > 0) else 1.0

        if anomaly_score >= 0.00 or surge_ratio >= 3.0:
            return "HIGH"
        elif anomaly_score >= -0.03 or surge_ratio >= 1.8:
            return "MEDIUM"
        else:
            return "LOW"

    def generate_suggested_action(
        self, severity: str, actual_reading: float, timestamp: str
    ) -> str:
        """Generates domain-specific preliminary corrective action advice."""
        if severity == "HIGH":
            return (
                f"Khẩn cấp ({actual_reading:.1f} kWh): Phụ tải tăng vọt bất thường. "
                f"Kiểm tra ngay cụm chiller/HVAC trung tâm, van bypass hoặc sự cố kẹt rơ-le công suất."
            )
        elif severity == "MEDIUM":
            return (
                f"Cảnh báo ({actual_reading:.1f} kWh): Tải tiêu thụ lệch chuẩn ngoài giờ. "
                f"Kiểm tra hệ thống chiếu sáng khu vực, quạt thông gió FCU hoặc thiết bị chưa tắt sau ca làm việc."
            )
        else:
            return (
                f"Lưu ý ({actual_reading:.1f} kWh): Dao động phụ tải nhẹ bất thường so với nền nhiệt độ. "
                f"Tiếp tục theo dõi các chu kỳ kế tiếp để xác nhận xu hướng."
            )

    def process_reading(
        self,
        reading: Dict[str, Any],
        historical_context_df: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates a newly received smart meter reading.
        Extracts features with 24h historical lag, evaluates Isolation Forest,
        and logs an event if anomalous.
        """
        if self.iso_model is None:
            self._load_model()

        # 1. Prepare historical context (need at least 24 prior readings)
        if historical_context_df is not None and len(historical_context_df) >= 24:
            context_df = historical_context_df
        elif meter_reading_repository.count() >= 24:
            context_df = meter_reading_repository.get_recent_readings(limit=48)
        elif len(self._history_buffer) >= 24:
            context_df = pd.DataFrame(self._history_buffer[-24:])
        else:
            # Buffer still accumulating
            self._history_buffer.append(reading)
            return None

        # 2. Extract lag_24h for contextual surge calculation
        try:
            lag_24h = float(context_df["meter_reading"].iloc[-24])
        except Exception:
            lag_24h = float(context_df["meter_reading"].iloc[-1])

        # 3. Format target point DataFrame
        target_df = pd.DataFrame([{
            "timestamp": reading["timestamp"],
            "meter_reading": float(reading["meter_reading"]),
            "air_temperature": float(reading.get("air_temperature", 25.0)),
        }])

        # 4. Prepare feature matrix for Isolation Forest
        X_anomaly = self.pipeline.prepare_anomaly_features(
            data_df=target_df,
            historical_context_df=context_df,
            drop_initial_lags=False,
        )

        # 5. Predict using Isolation Forest
        raw_pred = int(self.iso_model.predict(X_anomaly)[0])  # -1: anomaly, 1: inlier
        raw_decision = float(self.iso_model.decision_function(X_anomaly)[0])
        anomaly_score = -raw_decision

        actual_reading = float(reading["meter_reading"])
        surge_ratio = actual_reading / lag_24h if lag_24h > 0 else 1.0

        # Anomaly trigger: Isolation Forest pred == -1 OR score above threshold OR surge >= 2.5x
        is_anomaly = (raw_pred == -1) or (anomaly_score >= self.score_threshold) or (surge_ratio >= 2.5)

        # Update rolling buffer
        self._history_buffer.append(reading)
        if len(self._history_buffer) > 100:
            self._history_buffer = self._history_buffer[-50:]

        if not is_anomaly:
            return None

        # 6. Construct Anomaly Event
        severity = self.determine_severity(
            anomaly_score=anomaly_score,
            actual_reading=actual_reading,
            lag_24h=lag_24h,
        )
        suggested_action = self.generate_suggested_action(
            severity=severity,
            actual_reading=actual_reading,
            timestamp=str(reading["timestamp"]),
        )

        event = {
            "id": f"ANOM-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": str(reading["timestamp"]),
            "building_id": reading.get("building_id", "Hog_office_Betsy"),
            "actual_reading": round(actual_reading, 2),
            "anomaly_score": round(anomaly_score, 4),
            "severity": severity,
            "suggested_action": suggested_action,
            "status": "OPEN",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        # 7. Persist to repository
        self.event_repository.add_event(event)
        logger.warning(
            "Anomaly detected at %s! Reading: %.2f kWh, Score: %.4f, Severity: %s",
            event["timestamp"],
            event["actual_reading"],
            event["anomaly_score"],
            event["severity"],
        )
        return event

    def get_anomaly_events(
        self, limit: Optional[int] = None, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves stored anomaly events."""
        return self.event_repository.get_events(limit=limit, severity=severity)

    def clear_events(self) -> None:
        """Clears all stored events."""
        self.event_repository.clear()
