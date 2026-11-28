import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.agent.orchestrator import CopilotOrchestrator, parse_what_if_args
from src.config import get_tariff_rate_vnd
from src.data_pipeline.serving_frame import ModelArtifactError
from src.data_pipeline.what_if import simulate_what_if
from src.main import app


def _rows(start_utc_hour=0, hours=24, kwh=100.0):
    # 00:00 UTC == 07:00 Vietnam time, so the default window starts at the cooling start.
    base = datetime(2026, 11, 28, start_utc_hour, tzinfo=timezone.utc)
    return [
        {"timestamp": (base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"), "predicted_kwh": kwh}
        for h in range(hours)
    ]


def _kwh(result):
    return result["savings"]["low"]["kwh"], result["savings"]["high"]["kwh"]


def test_no_action_equals_baseline():
    r = simulate_what_if(_rows(), 0, 0, 0.5)
    assert _kwh(r) == (0, 0)
    assert r["baseline"]["kwh"] == 2400
    assert all(h["scenario_low_kwh"] == h["baseline_kwh"] == h["scenario_high_kwh"] for h in r["hours"])


def test_setpoint_only_applies_to_cooling_hours():
    r = simulate_what_if(_rows(), 1, 0, 0.5)
    # 11 cooling hours (07-18 VN) x 100 kWh x 0.5 share x 1 °C x [6%, 8%]
    assert _kwh(r) == pytest.approx((33.0, 44.0))
    assert r["savings"]["low"]["vnd"] == round(33.0 * get_tariff_rate_vnd())
    assert r["savings"]["low"]["co2_kg"] == pytest.approx(33.0 * 0.6766, abs=0.01)


def test_chiller_off_removes_hvac_share_for_last_hours():
    r = simulate_what_if(_rows(), 0, 2, 0.5)
    assert _kwh(r) == (100.0, 100.0)
    off = [h for h in r["hours"] if h["scenario_high_kwh"] < h["baseline_kwh"]]
    assert [h["vn_hour"] for h in off] == [16, 17]


def test_both_actions_do_not_double_count():
    r = simulate_what_if(_rows(), 2, 1, 0.5)
    # off hour 17: 50; setpoint on 10 remaining cooling hours: 10 x 50 x 2 x [6%, 8%]
    low, high = _kwh(r)
    assert (low, high) == pytest.approx((110.0, 130.0))
    assert low <= high


def test_night_window_has_zero_savings_and_note():
    r = simulate_what_if(_rows(start_utc_hour=12, hours=12), 2, 3, 0.5)
    assert _kwh(r) == (0, 0)
    assert r["notes"]


def test_assumptions_cite_sources():
    sources = {a["key"]: a["source"] for a in simulate_what_if(_rows(), 1, 0, 0.5)["assumptions"]}
    assert sources["setpoint_rate"] == "qcvn_09_2017_hvac.md"
    assert "2022" in sources["grid_emission_factor"]
    assert sources["hvac_share"] == "Giả định"


def test_emission_factor_env_override(monkeypatch):
    monkeypatch.setenv("GRID_EMISSION_FACTOR_TCO2_PER_MWH", "1.0")
    assert simulate_what_if(_rows(), 1, 0, 0.5)["savings"]["low"]["co2_kg"] == 33.0


@pytest.mark.parametrize("args", [(3, 0, 0.5), (0.3, 0, 0.5), (0, 5, 0.5), (0, 0, 0.9)])
def test_pure_function_rejects_out_of_range(args):
    with pytest.raises(ValueError):
        simulate_what_if(_rows(), *args)


def _client(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "whatif-token")
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    return TestClient(app)


def test_route_requires_token(monkeypatch):
    with _client(monkeypatch) as client:
        assert client.post("/internal/forecast/whatif", json={}).status_code == 401


@pytest.mark.parametrize("body,field", [
    ({"setpoint_delta_c": 3}, "setpoint_delta_c"),
    ({"setpoint_delta_c": 0.7}, "setpoint_delta_c"),
    ({"chiller_off_hours": 5}, "chiller_off_hours"),
    ({"hvac_share": 0.9}, "hvac_share"),
    ({"setpoint_delta_c": "abc"}, "setpoint_delta_c"),
])
def test_route_rejects_invalid_with_422(monkeypatch, body, field):
    with _client(monkeypatch) as client:
        resp = client.post("/internal/forecast/whatif", json=body, headers={"X-Internal-Token": "whatif-token"})
    assert resp.status_code == 422
    assert field in str(resp.json()["detail"])


def test_route_simulates_on_forecast(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.post(
            "/internal/forecast/whatif",
            json={"setpoint_delta_c": 1, "chiller_off_hours": 1},
            headers={"X-Internal-Token": "whatif-token"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hours"]) == 24
    assert body["savings"]["low"]["kwh"] <= body["savings"]["high"]["kwh"]
    assert body["assumptions"]
    assert body["source"] == "replay"


def test_route_uses_live_series_when_24_readings(monkeypatch):
    readings = [
        {"timestamp": r["timestamp"], "meter_reading_kwh": 100.0} for r in _rows(hours=24)
    ]
    live_df = pd.DataFrame([
        {**r, "lower_bound_95": 90.0, "upper_bound_95": 110.0, "outdoor_temperature_c": 26.0} for r in _rows()
    ])
    with patch("src.api.routers.forecast.predict_next_24h_from_series", return_value=live_df) as live, \
         patch("src.api.routers.forecast.predict_next_24h") as replay:
        with _client(monkeypatch) as client:
            resp = client.post(
                "/internal/forecast/whatif",
                json={"setpoint_delta_c": 1, "recent_readings": readings},
                headers={"X-Internal-Token": "whatif-token"},
            )
    assert resp.status_code == 200
    assert live.called and not replay.called
    assert resp.json()["source"] == "live_db"
    assert resp.json()["savings"]["low"]["kwh"] == 33.0


def test_route_returns_503_when_model_missing(monkeypatch):
    with patch("src.api.routers.forecast.predict_next_24h", side_effect=ModelArtifactError("missing")):
        with _client(monkeypatch) as client:
            resp = client.post("/internal/forecast/whatif", json={}, headers={"X-Internal-Token": "whatif-token"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "ERR_MODEL_NOT_FOUND"


def test_parse_what_if_args():
    assert parse_what_if_args("nếu nâng setpoint 1 độ thì tiết kiệm bao nhiêu?") == {"setpoint_delta_c": 1.0}
    assert parse_what_if_args("giả sử tắt chiller sớm 2 tiếng") == {"chiller_off_hours": 2}
    assert parse_what_if_args("nâng setpoint 1 độ có tốt không") is None  # no conditional cue
    assert parse_what_if_args("nếu tiết kiệm điện thì sao") is None  # no number
    assert parse_what_if_args("nếu tắt chiller sớm hơn 1 giờ") == {"chiller_off_hours": 1}
    assert parse_what_if_args("giả sử tăng nhiệt độ đặt điều hòa 0,5 độ") == {"setpoint_delta_c": 0.5}


@pytest.mark.parametrize("msg", [
    "nếu nhiệt độ ngoài trời tăng 3 độ",
    "nếu tắt đèn 2 giờ",
    "nếu tắt lúc 17h",
    "nếu tắt chiller sớm 2 hôm",
])
def test_parse_what_if_ignores_unrelated_sentences(msg):
    assert parse_what_if_args(msg) is None


@pytest.mark.parametrize("msg", [
    "Nếu nâng setpoint 3 độ thì sao?",
    "Nếu nâng setpoint 1.3 độ thì sao?",
    "Nếu tắt chiller sớm 5 tiếng thì sao?",
])
def test_copilot_out_of_range_reports_allowed_ranges(msg):
    orch = CopilotOrchestrator()
    orch.gemini_key = orch.openai_key = ""
    with patch("src.rag.retriever.query_knowledge", return_value=[]):
        _tools, tool_data, _s, context = orch._resolve_tool_calls(msg)
        reply, _t, _src, _e = orch.process_chat(msg)
    assert "0–2 °C" in tool_data["what_if"]["error"] and "0–3 giờ" in tool_data["what_if"]["error"]
    assert "Không mô phỏng được" in context and "0–2 °C" in context
    assert "Không mô phỏng được" in reply and "0–3 giờ" in reply


def test_copilot_reply_uses_overridden_emission_factor(monkeypatch):
    monkeypatch.setenv("GRID_EMISSION_FACTOR_TCO2_PER_MWH", "0.5")
    orch = CopilotOrchestrator()
    orch.gemini_key = orch.openai_key = ""
    with patch("src.rag.retriever.query_knowledge", return_value=[]):
        reply, _t, _s, _e = orch.process_chat("Nếu nâng setpoint 1 độ thì tiết kiệm bao nhiêu?")
    assert "0.5 tCO₂/MWh" in reply


def test_stream_chat_what_if_streams_ranges():
    orch = CopilotOrchestrator()
    orch.gemini_key = orch.openai_key = ""

    async def collect():
        return [e async for e in orch.stream_chat("Nếu nâng setpoint 1 độ thì tiết kiệm bao nhiêu?")]

    with patch("src.rag.retriever.query_knowledge", return_value=[]):
        events = asyncio.run(collect())
    text = "".join(e["token"] for e in events if e["type"] == "token")
    assert "simulate_what_if" in next(e for e in events if e["type"] == "sources")["tools_used"]
    assert "kWh**" in text and "VNĐ**" in text and "kg**" in text and " – " in text


def test_copilot_calls_what_if_tool_and_quotes_ranges():
    orch = CopilotOrchestrator()
    orch.gemini_key = orch.openai_key = ""
    with patch("src.rag.retriever.query_knowledge", return_value=[]):
        reply, tools, _sources, engine = orch.process_chat("Nếu nâng setpoint 1 độ thì tiết kiệm bao nhiêu?")
    assert "simulate_what_if" in tools
    assert engine == "heuristic"
    assert "kWh" in reply and "VNĐ" in reply and "CO₂" in reply and "–" in reply


def test_copilot_skips_tool_without_number():
    orch = CopilotOrchestrator()
    with patch("src.rag.retriever.query_knowledge", return_value=[]):
        tools, tool_data, _s, _c = orch._resolve_tool_calls("Nếu tiết kiệm điện thì làm gì?")
    assert "simulate_what_if" not in tools
    assert tool_data["what_if"] is None
