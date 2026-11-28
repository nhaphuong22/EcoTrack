---
title: 'What-if simulator for HVAC setpoint and chiller schedule'
type: 'feature'
created: '2026-11-28'
status: 'done'
baseline_commit: '905b55af6379cd0e489d25d1e8fb2d9cc1c003ac'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Operators can see the 24 h forecast but cannot ask what a concrete action would save, such as raising the cooling setpoint or switching the chiller off earlier.

**Approach:** One pure calculation applies knowledge-base coefficients to the existing 24 h forecast and returns the change in kWh, VND and CO₂ as a low–high range. It is exposed through an ai-service route, the gateway, a dashboard tab with sliders, and a Copilot tool.

**Decisions (human):** HVAC share of total building electricity defaults to 50% (mid-point of the 40–60% range in the sources) and is editable in the UI; the coefficients apply to that HVAC share. Because the 6–8%/°C coefficient refers to chiller electricity, applying it to all HVAC overstates the saving somewhat, and the assumptions say so. CO₂ uses the grid factor 0.6766 tCO₂/MWh (Vietnam, 2022, Department of Climate Change, MONRE), labelled "2022" and overridable by env var. The Copilot tool ships in this story.

## Boundaries & Constraints

**Always:**
- Baseline = the same 24 h forecast the dashboard shows (`predict_next_24h_from_series` when the gateway sends ≥ 24 recent points, else `predict_next_24h`).
- Inputs: `setpoint_delta_c` 0–2 in 0.5 steps, `chiller_off_hours` integer 0–3, `hvac_share` 0.05–0.8 (default 0.5). Reject anything else with 422 at the ai-service and 400 at the gateway.
- Cooling hours are 07:00–18:00 Vietnam time (UTC+7; forecast timestamps are UTC). Chiller-off removes `hvac_share × predicted_kwh` for the hours in [18 − N, 18). The setpoint saving is `predicted_kwh × hvac_share × delta × rate`, with rate 6% (low) and 8% (high), on the remaining cooling hours only, so the two never double-count.
- Money = kWh × `get_tariff_rate_vnd()` (flat). CO₂ kg = kWh × factor. New `get_grid_emission_factor()` in `src/config.py`, env `GRID_EMISSION_FACTOR_TCO2_PER_MWH`, default 0.6766.
- The response echoes every assumption with its source (`qcvn_09_2017_hvac.md` for 6–8%/°C; the 2022 grid factor; the 50% HVAC default marked as an assumption, with the overstatement note), and the UI shows them.
- `ai-service/src/agent/orchestrator.py` and `prompts.py` have uncommitted user edits: add to them, never revert or reformat existing lines.

**Never:** No change to the forecast model, its route shape or the tariff logic. No new dependency. No time-of-use pricing. No `window.confirm` or modal dialog.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No action | delta 0, off 0 | All savings 0; scenario equals baseline | N/A |
| Setpoint only | delta 1, off 0, share 0.5 | Saving = Σ cooling-hour kWh × 0.5 × 1 × [0.06, 0.08] | N/A |
| Chiller off earlier | off 2 | Hours 16:00–18:00 VN lose `share × kWh`; setpoint not applied to them | N/A |
| Both | delta 2, off 1 | Sum without double counting; low ≤ high | N/A |
| Window has no cooling hours | Forecast covers only night hours | Savings 0 with a note | N/A |
| Out of range | delta 3, off 5, share 0.9, non-numeric | 422 (ai-service), 400 (gateway) | Error message names the field |
| Forecast unavailable | Model artifact missing | Same 503 `ERR_MODEL_NOT_FOUND` as the forecast | Gateway passes the status through |
| Copilot question | "Nếu nâng setpoint 1 độ thì tiết kiệm bao nhiêu?" | Tool runs with delta 1 and the answer quotes kWh, VND and CO₂ ranges | No numbers parsed: tool not called |

</frozen-after-approval>

## Code Map

- `ai-service/src/data_pipeline/serving_frame.py:456` `predict_next_24h`, `:510` `predict_next_24h_from_series` -- baseline; rows have UTC `timestamp`, `predicted_kwh`. Do not change.
- `ai-service/src/config.py:6` `get_tariff_rate_vnd` -- pattern for the new emission-factor getter.
- `ai-service/src/api/routers/forecast.py` -- prefix `/internal/forecast`, `_serialize_forecast` (:22); add `POST /whatif` here (no mount change). `/internal/*` needs `X-Internal-Token` (`main.py:61`).
- `ai-service/src/agent/tools/energy_tools.py:36` `query_forecast_summary` -- add the what-if tool beside it, reusing the pure function.
- `ai-service/src/agent/orchestrator.py` -- tools imported at :14-19; `_resolve_tool_calls` (:30) picks by Vietnamese keywords (:84-98) into `tool_data` (:40); context lines :150-166; heuristic fallback :378. "setpoint", "chiller", "tiết kiệm" already trigger RAG (:116-129): the what-if branch needs a conditional cue ("nếu", "giả sử", "what if") plus a parsed number.
- `backend/src/routes/forecast.js:8` -- proxy pattern (`getHourlyBuildingSeries('office_tower_01', 72)`, `callAIService`); add `POST /whatif` with Zod validation. Mounted under `/api/v1` with operator auth (`app.js:62,67`). Tests: `backend/tests/proxy.test.js` pattern.
- `frontend/src/App.jsx` -- tabs (:95-150), `headerMeta` (:55-83), content switch (:185-219); `services/api.js` pattern; style from `components/dashboard/ForecastChart.jsx` and self-fetching `components/reports/MonthlyReport.jsx`; tests like `__tests__/MonthlyReport.test.jsx`.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/src/data_pipeline/what_if.py` -- pure `simulate_what_if(forecast_rows, setpoint_delta_c, chiller_off_hours, hvac_share)` returning baseline, low/high savings (kWh, VND, kg CO₂), per-hour baseline and scenario, and assumptions with sources
- [x] `ai-service/src/config.py` -- `get_grid_emission_factor()`
- [x] `ai-service/src/api/routers/forecast.py` -- `POST /internal/forecast/whatif` with validated body (scenario + optional recent readings)
- [x] `ai-service/src/agent/tools/energy_tools.py`, `orchestrator.py` (and one line in `prompts.py` only if needed) -- what-if tool, keyword branch with number parsing, context line, fallback line
- [x] `backend/src/routes/forecast.js` -- `POST /api/v1/forecast/whatif` proxy with Zod validation
- [x] `frontend/src/services/api.js`, `components/dashboard/WhatIfPanel.jsx`, `App.jsx` -- "What-if" tab: labelled range inputs, HVAC-share number input, result cards (kWh, VND, CO₂ ranges), baseline vs scenario chart, assumptions list; ignore out-of-order responses
- [x] Tests -- pure function (matrix rows), ai-service route (token, 422), Copilot keyword routing, backend proxy (400, forwarding), frontend panel (render, slider change requests a new result, shows ranges)

**Acceptance Criteria:**
- Given the matrix above, when `pytest ai-service`, `npm run test --prefix backend` and the frontend Vitest suite run, then all pass and flake8 `--select=E9,F63,F7,F82` on `ai-service/src` reports 0

## Implementation Notes

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | Out-of-range numbers in a Copilot question are dropped silently; on the LLM path the model gets no what-if data | medium | patch | `validate_scenario` raises and the error is only logged |
| 2 | Copilot regexes fire on unrelated sentences ("nhiệt độ ngoài trời tăng 3 độ", "tắt đèn 2 giờ", "tắt lúc 17h", "3 hôm") | medium | patch | Patterns have no HVAC/chiller subject and a bare `h` |
| 3 | `/whatif` does not say whether the baseline is live or replayed; 1–23 readings fall back silently | low | patch | `/predict` already returns `source` |
| 4 | Panel keeps the previous scenario's numbers when the share is invalid or a request fails | low | patch | Result state is not cleared on those paths |
| 5 | Every slider step and keystroke sends a request that runs inference | low | patch | No debounce before `fetchWhatIf` |
| 6 | A 400 with an array `detail` shows the generic axios message | low | patch | Panel reads `detail` only as a string |
| 7 | Chart has no legend and the tooltip has no unit | low | patch | Default `<Tooltip />`, no `<Legend />` |
| 8 | Copilot assumption text hard-codes the 2022 factor | low | patch | Ignores `GRID_EMISSION_FACTOR_TCO2_PER_MWH` overrides |
| 9 | Missing tests: gateway forwarding of live readings, ai-service live-series route, streamed Copilot what-if, App tab | medium | patch | Grep found no test for each path |
| 10 | Copilot simulates on the replay forecast, not the live series the tab uses | medium | defer | The Copilot request carries no live readings; fixing it changes the chat contract |
| 11 | Forecast timestamps may not be UTC in the replay path | maybe-false | defer | Live path uses DB UTC timestamps; check the simulator's time alignment for replay |
| 12 | `test_route_simulates_on_forecast` needs real model files | false | reject | `conftest.py` trains fixture models into a temp models dir |
| 13 | Diff leaves out ChatMessage.jsx, CopilotStreaming.test.jsx, test_copilot_rag.py and model JSON files | false | reject | These are the user's uncommitted changes, deliberately excluded and not committed with this story |
| 14 | Negative or NaN `predicted_kwh` breaks low ≤ high or JSON | low | reject | The forecast clamps predictions at 0 |
| 15 | `building_id` is accepted but ignored | low | reject | Single-building dashboard; cosmetic |
| 16 | The what-if heuristic reply hides other topics in a combined question | low | reject | Fallback only without an LLM; rare |

## Design Notes

The 6–8%/°C coefficient in `qcvn_09_2017_hvac.md` describes setpoints below 24 °C; applying it to any starting setpoint is a simplification, stated in the assumptions. `hvac_chwst_reset.md` (2.5–3.5% per °C of chilled-water supply temperature) is a different control and is not used.

## Verification

**Commands:**
- `pytest ai-service -q` -- expected: all pass
- `python -m flake8 ai-service/src --select=E9,F63,F7,F82` -- expected: 0
- `npm run test --prefix backend` and `npm run test --prefix frontend -- --run` -- expected: all pass

**Manual checks:**
- Open the What-if tab, move the setpoint slider to +1 °C and check the kWh, VND and CO₂ ranges change and the assumptions are listed
