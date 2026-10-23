---
title: 'Story 2.2: See the building live on a floor plan'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 2-2-see-the-building-live-on-a-floor-plan
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Facility operators lack spatial awareness of energy waste and temperature hotspots across the building floors. Numerical tables and global load charts do not convey which physical room is consuming excessive energy or experiencing HVAC anomalies. FR42 and NFR10 require an interactive live 2D floor plan that updates in real time and links directly to AI Copilot diagnostics.

**Approach (Ponytail - clean, rich aesthetics, zero boilerplate):**
- Create a dedicated React component `FloorPlan.jsx` rendering an interactive SVG floor plan of the building's zones.
- Fetch initial zones and latest readings via `GET /api/v1/buildings/:id/zones`.
- Implement a custom streaming hook `useLiveReadings.js` that opens an SSE connection (`GET /api/v1/stream/readings?building_id=...`), updates the active zone states, and reconnects with exponential backoff on connection drop, displaying a "Mất kết nối" badge when disconnected.
- Provide a toggle between "Nhiệt độ" (°C) and "Lãng phí" (kWh / Waste level) with a green-to-red color scale, legend, and accessibility-compliant text descriptions.
- Allow clicking or keyboard interaction (Enter/Space) on any room to open a Zone Detail Drawer/Panel with recent metrics and a one-click "Hỏi Copilot" action that activates `CopilotDrawer` with that zone's exact context.

## Boundaries & Constraints

**Always:**
- SVG layout renders all zones cleanly with responsive scaling, room names, and live values.
- Dual-indicator accessibility: Every zone displays both color-coded indicators and descriptive text status (e.g. "Tối ưu", "Cảnh báo", "Nhiệt cao"), satisfying a11y requirements.
- Keyboard accessible: Zones have `tabIndex={0}`, `role="button"`, and respond to `Enter` or `Space` to open the detail panel.
- Reconnection resilience: On stream disconnect, show "Mất kết nối / Đang kết nối lại...", and retry with backoff.
- "Hỏi Copilot" triggers `sendMessage` with a structured diagnostic prompt for the selected zone and opens `CopilotDrawer`.
- Isolation: Live reading updates are scoped to zone state and do not trigger costly re-renders of the global Recharts timeseries component.

**Never:**
- Do not add heavy 3D or GIS libraries (Three.js, Mapbox, Leaflet) — standard SVG with Tailwind styling is fast, crisp, and responsive.
- Do not alter or break existing `/api/v1/buildings/:id/zones` or `/api/v1/copilot/chat` contracts.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Initial Load | Navigated to Floor Plan tab | Loads zones from `/api/v1/buildings/:id/zones`, displays 10 rooms with initial readings | Error alert if API fails |
| Realtime SSE Reading | SSE emits `reading` for `z1` | `z1` SVG cell transitions color and updates temperature/load smoothly | Ignores invalid payloads |
| Metric Toggle | User clicks "Lãng phí" | Color scale recalculates based on kWh consumption; legend switches | Instant UI update |
| Click / Enter Zone | User selects `Phòng 102` | Opens Zone Detail Panel showing temperature, kWh, humidity, and "Hỏi Copilot" button | Focus trapped / accessible |
| Ask Copilot | User clicks "Hỏi Copilot" | `CopilotDrawer` opens, pre-fills & sends contextual prompt for that room | Reuses existing `useCopilot` |
| Stream Loss | Backend SSE drops | Shows "Mất kết nối" badge, triggers automatic reconnect with exponential backoff | Retries until restored |

</frozen-after-approval>

## Code Map

- `frontend/src/services/api.js`: Add `fetchZones(buildingId)` calling `GET /api/v1/buildings/:id/zones`.
- `frontend/src/lib/copilotPrompt.js`: Add `buildZonePrompt(zone)` formatting room metrics into an analytical prompt for the Copilot.
- `frontend/src/hooks/useLiveReadings.js` (NEW): Custom hook establishing SSE connection to `/api/v1/stream/readings?building_id=...`, handling heartbeat, disconnect detection, and backoff reconnection.
- `frontend/src/components/dashboard/FloorPlan.jsx` (NEW): Rich SVG floor plan with room grid, gradient fills, metric toggles, legend, and accessibility keyboard navigation.
- `frontend/src/components/dashboard/ZoneDetailModal.jsx` (NEW): Slide-over inspector panel for selected zone with metrics breakdown and "Hỏi Copilot" button.
- `frontend/src/App.jsx`: Integrate tab navigation ("Dashboard Tổng quan" vs "Sơ đồ Mặt bằng 2D") or embedded floor plan view, linking `onAskCopilotZone` to `sendMessage`.
- `frontend/src/__tests__/FloorPlan.test.jsx` (NEW): Vitest + React Testing Library tests covering zone rendering, metric toggling, keyboard accessibility, and "Hỏi Copilot" triggering.

## Tasks & Acceptance

**Execution:**
- [ ] `frontend/src/services/api.js` — Add `fetchZones`.
- [ ] `frontend/src/lib/copilotPrompt.js` — Add `buildZonePrompt`.
- [ ] `frontend/src/hooks/useLiveReadings.js` — Real-time SSE stream hook with reconnection backoff.
- [ ] `frontend/src/components/dashboard/FloorPlan.jsx` — 2D SVG floor plan with dual color/text indicators and toggle.
- [ ] `frontend/src/components/dashboard/ZoneDetailModal.jsx` — Zone detail panel with "Hỏi Copilot".
- [ ] `frontend/src/App.jsx` — Add navigation tab and connect Floor Plan to Copilot drawer.
- [ ] `frontend/src/__tests__/FloorPlan.test.jsx` — Unit and component tests.
- [ ] Update `_bmad-output/implementation-artifacts/sprint-status.yaml` — Mark `2-2-see-the-building-live-on-a-floor-plan: done`.

**Acceptance Criteria:**
- Given the Floor Plan page, when it loads, then an SVG plan of one floor shows the zones returned by `GET /api/v1/buildings/:id/zones`, each labelled with its name and latest temperature.
- Given the readings stream is connected through fetch/SSE, when a reading for a zone arrives, then that zone's colour and values update without reloading, and other components do not re-render.
- Given a toggle between "Nhiệt độ" and "Lãng phí", when switched, zones are coloured on a green-to-red scale for the selected measure, with a legend, and state conveyed by text.
- Given I click or press Enter on a zone, when detail panel opens, it shows latest readings and an "Hỏi Copilot" action.
- Given the stream drops, a "Mất kết nối" indicator appears and client reconnects with backoff.
