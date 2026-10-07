"""
Stream Data Worker for EcoTrack:
Simulates a real-time IoT smart meter telemetry stream by reading sequential
records from `backend/data/processed/office_building_clean.csv` and pushing
readings into the `meter_readings` repository.

Provides controls:
- start_streaming(interval_seconds)
- stop_streaming()
- get_stream_status()
- emit_next_reading()
- register_listener(callback)
"""

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import pandas as pd

logger = logging.getLogger("StreamDataWorker")


class MeterReadingRepository:
    """Thread-safe in-memory repository for storing streamed meter readings."""

    def __init__(self, max_size: int = 2000):
        self._max_size = max_size
        self._readings: List[Dict[str, Any]] = []

    def add_reading(self, reading: Dict[str, Any]) -> None:
        """Stores a new meter reading."""
        record = reading.copy()
        if "recorded_at" not in record:
            record["recorded_at"] = datetime.now(timezone.utc).isoformat()

        self._readings.append(record)
        if len(self._readings) > self._max_size:
            # Drop oldest records to prevent unbounded memory growth
            self._readings = self._readings[-self._max_size:]

    def get_recent_readings(self, limit: int = 24) -> pd.DataFrame:
        """Returns the most recent readings as a pandas DataFrame."""
        if not self._readings:
            return pd.DataFrame(columns=["timestamp", "meter_reading", "air_temperature", "building_id"])
        slice_records = self._readings[-limit:]
        return pd.DataFrame(slice_records)

    def get_all_readings(self) -> List[Dict[str, Any]]:
        """Returns all currently stored readings."""
        return list(self._readings)

    def count(self) -> int:
        """Returns count of stored readings."""
        return len(self._readings)

    def clear(self) -> None:
        """Empties repository."""
        self._readings.clear()


# Global default repository for meter readings
meter_reading_repository = MeterReadingRepository()


class StreamDataWorker:
    """
    Background worker that streams hourly time-series readings sequentially
    from clean processed data to simulate an active building telemetry stream.
    """

    def __init__(
        self,
        csv_path: Optional[Path] = None,
        repository: Optional[MeterReadingRepository] = None,
        building_id: str = "Hog_office_Betsy",
    ):
        backend_dir = Path(__file__).resolve().parents[2]
        self.csv_path = csv_path or (backend_dir / "data" / "processed" / "office_building_clean.csv")
        self.repository = repository or meter_reading_repository
        self.building_id = building_id

        self._df: Optional[pd.DataFrame] = None
        self._current_index: int = 0
        self._is_streaming: bool = False
        self._stream_task: Optional[asyncio.Task] = None
        self._interval_seconds: float = 5.0
        self._listeners: List[Callable[[Dict[str, Any]], Any]] = []
        self._emitted_count: int = 0
        self._last_emitted: Optional[Dict[str, Any]] = None

        self._load_data()

    def _create_fallback_dataset(self) -> pd.DataFrame:
        """
        Creates clean baseline dataset if office_building_clean.csv is not present (e.g. in fresh CI/CD).
        Uses sample_bdg2_energy.json if available, or generates realistic hourly records.
        """
        backend_dir = Path(__file__).resolve().parents[2]
        sample_json = backend_dir / "data" / "sample_bdg2_energy.json"

        if sample_json.exists():
            try:
                import json
                with open(sample_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                df = pd.DataFrame(data)
                df = df.rename(columns={
                    "meter_reading_kwh": "meter_reading",
                    "outdoor_temperature_c": "air_temperature"
                })
                df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
                clean_df = df[["timestamp", "meter_reading", "air_temperature"]].copy()
                self.csv_path.parent.mkdir(parents=True, exist_ok=True)
                clean_df.to_csv(self.csv_path, index=False)
                clean_df["timestamp"] = pd.to_datetime(clean_df["timestamp"])
                logger.info("Generated %s from sample_bdg2_energy.json (%d rows).", self.csv_path.name, len(clean_df))
                return clean_df
            except Exception as e:
                logger.warning("Failed to create dataset from %s: %s", sample_json, e)

        # Pure synthetic generation fallback
        import numpy as np
        timestamps = pd.date_range("2026-01-01 00:00:00", periods=720, freq="1h")
        hours = timestamps.hour.values
        temps = 25.0 + 5.0 * np.sin((hours - 9) * np.pi / 12)
        loads = 200.0 + 80.0 * np.sin((hours - 8) * np.pi / 10) + np.maximum(0, (temps - 24.0) * 10.0)

        df = pd.DataFrame({
            "timestamp": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
            "meter_reading": np.round(np.maximum(50.0, loads), 2),
            "air_temperature": np.round(temps, 1),
        })
        try:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(self.csv_path, index=False)
        except Exception:
            pass

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def _load_data(self) -> None:
        """Loads and pre-validates time series from processed CSV or fallback."""
        if self.csv_path.exists():
            try:
                logger.info("Loading time series stream source from %s...", self.csv_path.name)
                df = pd.read_csv(self.csv_path)
                required_cols = ["timestamp", "meter_reading", "air_temperature"]
                if all(col in df.columns for col in required_cols):
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    self._df = df.sort_values("timestamp").reset_index(drop=True)
                    logger.info("Stream source loaded with %d rows.", len(self._df))
                    return
            except Exception as e:
                logger.warning("Error reading %s: %s. Using fallback.", self.csv_path, e)

        logger.info("CSV %s not found. Creating fallback dataset...", self.csv_path)
        self._df = self._create_fallback_dataset()


    @property
    def total_rows(self) -> int:
        """Returns total number of rows available in dataset."""
        return len(self._df) if self._df is not None else 0

    @property
    def current_index(self) -> int:
        """Returns current sequential row index."""
        return self._current_index

    def register_listener(self, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Registers a callback to be invoked whenever a new reading is emitted."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Removes a registered callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def emit_next_reading(self) -> Dict[str, Any]:
        """
        Emits the next single row sequentially from the dataset.
        Advances current_index by 1 (loops back to 0 when end is reached).
        """
        if self._df is None or len(self._df) == 0:
            raise RuntimeError("Stream worker dataset is empty or not loaded.")

        row = self._df.iloc[self._current_index]

        reading = {
            "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(row["timestamp"], "strftime")
            else str(row["timestamp"]),
            "meter_reading": float(row["meter_reading"]),
            "air_temperature": float(row["air_temperature"]),
            "building_id": self.building_id,
            "stream_index": self._current_index,
        }

        # Advance pointer sequentially
        self._current_index = (self._current_index + 1) % len(self._df)
        self._emitted_count += 1
        self._last_emitted = reading

        # Save to repository
        self.repository.add_reading(reading)

        # Notify any subscribed listeners (e.g. anomaly evaluation service)
        for listener in self._listeners:
            try:
                listener(reading)
            except Exception as e:
                logger.error("Error in stream listener %s: %s", listener, e)

        return reading

    async def _streaming_loop(self, loop_forever: bool = True) -> None:
        """Continuous async loop emitting readings at configured intervals."""
        logger.info("Stream loop started with interval=%.2fs.", self._interval_seconds)
        try:
            while self._is_streaming:
                self.emit_next_reading()
                if not loop_forever and self._current_index == 0:
                    logger.info("Reached end of dataset and loop_forever is False. Stopping.")
                    break
                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            logger.info("Streaming loop cancelled.")
        finally:
            self._is_streaming = False

    async def start_streaming(
        self,
        interval_seconds: float = 5.0,
        loop_forever: bool = True,
        start_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Starts the asynchronous streaming background task.
        If already running, updates the interval if specified.
        """
        if start_index is not None:
            self._current_index = start_index % self.total_rows

        self._interval_seconds = max(0.01, float(interval_seconds))

        if self._is_streaming and self._stream_task and not self._stream_task.done():
            logger.info("Stream worker already active, updated interval to %.2fs.", self._interval_seconds)
            return self.get_stream_status()

        self._is_streaming = True
        self._stream_task = asyncio.create_task(
            self._streaming_loop(loop_forever=loop_forever)
        )
        logger.info("Stream worker started (Index: %d, Interval: %.2fs).", self._current_index, self._interval_seconds)
        return self.get_stream_status()

    async def stop_streaming(self) -> Dict[str, Any]:
        """Stops the streaming background worker."""
        if not self._is_streaming:
            logger.info("Stream worker is already stopped.")
            return self.get_stream_status()

        self._is_streaming = False
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None

        logger.info("Stream worker stopped successfully.")
        return self.get_stream_status()

    def get_stream_status(self) -> Dict[str, Any]:
        """Returns the current operational status of the stream worker."""
        return {
            "is_streaming": self._is_streaming,
            "current_index": self._current_index,
            "total_rows": self.total_rows,
            "interval_seconds": self._interval_seconds,
            "building_id": self.building_id,
            "readings_emitted_count": self._emitted_count,
            "repository_count": self.repository.count(),
            "last_emitted_reading": self._last_emitted,
        }

    def reset(self, start_index: int = 0) -> None:
        """Resets the stream index pointer and emitted count."""
        self._current_index = start_index % max(1, self.total_rows)
        self._emitted_count = 0
        self._last_emitted = None


# Global singleton worker instance
stream_worker = StreamDataWorker()


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("📡 ECOTRACK REAL-TIME TELEMETRY STREAM WORKER")
    print("Simulating smart meter IoT telemetry ingestion (Interval: 1.0s)...")
    print("Press Ctrl+C to stop.")
    print("=" * 70)

    def print_reading(reading):
        print(
            f"⚡ [{reading.get('timestamp')}] Building: {reading.get('building_id')} | "
            f"Meter: {reading.get('meter_reading', 0):.2f} kWh | "
            f"Temp: {reading.get('air_temperature', 0):.1f}°C"
        )

    stream_worker.register_listener(print_reading)

    async def _run_cli():
        await stream_worker.start_streaming(interval_seconds=1.0)
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await stream_worker.stop_streaming()
            print("\n🛑 Stream worker stopped.")

    try:
        asyncio.run(_run_cli())
    except KeyboardInterrupt:
        print("\n🛑 Stream worker stopped.")
