"""What-if savings for HVAC setpoint raise and earlier chiller-off, applied to the 24 h forecast."""
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from src.config import get_grid_emission_factor, get_tariff_rate_vnd

VN_UTC_OFFSET_HOURS = 7
COOLING_START_HOUR = 7  # Vietnam local time, inclusive
COOLING_END_HOUR = 18   # Vietnam local time, exclusive
SETPOINT_RATE_LOW = 0.06
SETPOINT_RATE_HIGH = 0.08


def _vn_hour(timestamp: Any) -> int:
    ts = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc)
    # Forecast timestamps are UTC; naive values are treated as UTC.
    return (ts.hour + VN_UTC_OFFSET_HOURS) % 24


def validate_scenario(setpoint_delta_c: float, chiller_off_hours: int, hvac_share: float) -> None:
    if not 0 <= setpoint_delta_c <= 2 or (setpoint_delta_c * 2) % 1 != 0:
        raise ValueError("setpoint_delta_c must be between 0 and 2 in 0.5 steps")
    if isinstance(chiller_off_hours, bool) or int(chiller_off_hours) != chiller_off_hours or not 0 <= chiller_off_hours <= 3:
        raise ValueError("chiller_off_hours must be an integer between 0 and 3")
    if not 0.05 <= hvac_share <= 0.8:
        raise ValueError("hvac_share must be between 0.05 and 0.8")


def _triple(kwh: float, tariff: float, factor: float) -> Dict[str, float]:
    return {"kwh": round(kwh, 2), "vnd": round(kwh * tariff, 0), "co2_kg": round(kwh * factor, 2)}


def simulate_what_if(
    forecast_rows: Iterable[Dict[str, Any]],
    setpoint_delta_c: float = 0.0,
    chiller_off_hours: int = 0,
    hvac_share: float = 0.5,
) -> Dict[str, Any]:
    validate_scenario(setpoint_delta_c, chiller_off_hours, hvac_share)
    chiller_off_hours = int(chiller_off_hours)
    tariff = get_tariff_rate_vnd()
    factor = get_grid_emission_factor()  # tCO2/MWh == kg CO2/kWh
    off_start = COOLING_END_HOUR - chiller_off_hours

    hours: List[Dict[str, Any]] = []
    baseline = low = high = 0.0
    cooling_hours = 0
    for row in forecast_rows:
        kwh = float(row["predicted_kwh"])
        vn_hour = _vn_hour(row["timestamp"])
        hvac_kwh = kwh * hvac_share
        if off_start <= vn_hour < COOLING_END_HOUR:
            save_low = save_high = hvac_kwh
        elif COOLING_START_HOUR <= vn_hour < COOLING_END_HOUR:
            save_low = hvac_kwh * setpoint_delta_c * SETPOINT_RATE_LOW
            save_high = hvac_kwh * setpoint_delta_c * SETPOINT_RATE_HIGH
        else:
            save_low = save_high = 0.0
        cooling_hours += COOLING_START_HOUR <= vn_hour < COOLING_END_HOUR
        baseline += kwh
        low += save_low
        high += save_high
        hours.append({
            "timestamp": str(row["timestamp"]),
            "vn_hour": vn_hour,
            "baseline_kwh": round(kwh, 2),
            "scenario_low_kwh": round(kwh - save_high, 2),
            "scenario_high_kwh": round(kwh - save_low, 2),
        })

    notes = []
    if cooling_hours == 0:
        notes.append("Cửa sổ dự báo không có giờ làm mát (07:00–18:00 giờ Việt Nam) nên tiết kiệm bằng 0.")

    return {
        "scenario": {
            "setpoint_delta_c": setpoint_delta_c,
            "chiller_off_hours": chiller_off_hours,
            "hvac_share": hvac_share,
        },
        "baseline": _triple(baseline, tariff, factor),
        "savings": {"low": _triple(low, tariff, factor), "high": _triple(high, tariff, factor)},
        "hours": hours,
        "notes": notes,
        "assumptions": [
            {
                "key": "setpoint_rate",
                "label": "Mỗi °C nâng setpoint giảm 6–8% điện năng chiller, áp dụng cho phần HVAC trong giờ làm mát còn chạy. "
                         "Hệ số gốc mô tả setpoint dưới 24 °C; áp dụng cho mọi setpoint là giản lược.",
                "value": [SETPOINT_RATE_LOW, SETPOINT_RATE_HIGH],
                "source": "qcvn_09_2017_hvac.md",
            },
            {
                "key": "hvac_share",
                "label": "Tỷ trọng HVAC trong tổng điện tòa nhà (giả định, mặc định 50% = điểm giữa 40–60%). "
                         "Hệ số 6–8%/°C là của chiller; áp dụng cho toàn bộ HVAC làm tiết kiệm bị ước tính cao hơn phần nào.",
                "value": hvac_share,
                "source": "Giả định",
            },
            {
                "key": "cooling_hours",
                "label": "Giờ làm mát 07:00–18:00 giờ Việt Nam (UTC+7); tắt chiller sớm N giờ bỏ phần HVAC trong [18−N, 18).",
                "value": [COOLING_START_HOUR, COOLING_END_HOUR],
                "source": "Giả định",
            },
            {
                "key": "grid_emission_factor",
                "label": "Hệ số phát thải lưới điện Việt Nam năm 2022 (tCO₂/MWh).",
                "value": factor,
                "source": "Cục Biến đổi khí hậu, Bộ TN&MT (2022)",
            },
            {
                "key": "tariff_vnd",
                "label": "Giá điện phẳng (VND/kWh), không tính theo khung giờ.",
                "value": tariff,
                "source": "TARIFF_RATE_VND",
            },
        ],
    }
