---
title: 'Story 1.2 + 1.3: Per-zone ingest path and sensor simulator'
type: 'feature'
created: '2026-10-08'
status: 'done'
baseline_commit: '507b5c7c4fc5d95e5b26df984439980fe451eb23'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 1-2-simulate-building-sensors
  - 1-3-ingest-readings-per-zone
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** There is no way for live per-zone readings to enter the system. The database has no `Zone` model and no `zone_id`, the gateway has no ingest endpoint, and no simulator exists — so the live dashboard and floor plan (Epic 2) have nothing to show. Stories 1.2 (simulator) and 1.3 (ingest) are combined because the simulator is the producer for the ingest endpoint and neither is demonstrable alone.

**Approach:** Add a `Zone` model and an optional `zone_id` on `MeterReading` with a uniqueness rule that stores each reading once, seed 10 zones on one floor of `office_tower_01`, expose `POST /api/v1/ingest/readings` (guarded by `X-Ingest-Key`) and `GET /api/v1/buildings/:id/zones`, and add a simulator that replays BDG2 data through `stream_worker.py` and posts per-zone batches every 2–5 seconds.

## Boundaries & Constraints

**Always:**
- One reading per `(building_id, zone_id, timestamp)`; zoneless readings stay unique per `(building_id, timestamp)` (FR18). Duplicates are skipped, never error.
- The ingest endpoint validates with Zod and rejects a missing/wrong `X-Ingest-Key` with 401; unknown building or zone, or malformed payload, give 422 with the `{detail}` envelope and store nothing.
- `GET /api/v1/buildings/:id/zones` ships open now; Epic 5 Story 5.3 adds `requireAuth`.
- The simulator is a self-contained Node script in `backend/` (decided 2026-10-08): it reads the processed BDG2 CSV, posts all 10 zones every 2–5 s, retries on gateway failure without exiting, and raises one zone under `--anomaly-zone <id>`. It does not depend on the Python `stream_worker.py`.
- Timestamps cross the API as ISO 8601 UTC; energy values are floats in kWh.
- Backend tests use the mocked Prisma (`global.__mockPrisma`) like the existing suite; no real Postgres.

**Never:**
- Do not add user authentication or RBAC here (Epic 5). The only guard is `X-Ingest-Key`.
- Do not change the energy/forecast/anomaly/copilot routes or the AI service serving frame.
- Do not commit real BDG2 CSVs or secrets.
- Do not express the partial unique index as a Prisma `@@unique` (it cannot); use raw SQL in the migration.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ingest happy path | valid batch + correct `X-Ingest-Key` | 201 `{ stored: N }`; rows persisted | N/A |
| Ingest duplicate | batch repeats an existing `(building_id, zone_id, timestamp)` | 201; duplicate skipped, existing kept | `skipDuplicates` |
| Ingest bad key | missing/wrong `X-Ingest-Key` | 401 `{detail}` | nothing stored |
| Ingest unknown building/zone | `building_id`/`zone_id` not in DB | 422 `{detail}` | nothing stored |
| Ingest malformed | missing field / wrong type | 422 ZodError envelope | nothing stored |
| Zones list | `GET /buildings/office_tower_01/zones` | 200; 10 zones each with `latest_reading` or `null` | N/A |
| Zones unknown building | unknown id | 404 `{detail}` | N/A |
| Simulator tick | gateway up | posts 10 zone rows every 2–5 s from the replay | N/A |
| Simulator anomaly | `--anomaly-zone z3` | z3's kWh and temp clearly above others | N/A |
| Simulator gateway down | POST fails | logs and retries next tick; process stays up | per-tick try/except |

</frozen-after-approval>

## Code Map

- `backend/prisma/schema.prisma` -- add `Zone` (`id` VarChar PK, `building_id` FK cascade, `floor` Int, `name`, `created_at`), relation on `Building`; add `zone_id String?` + `Zone` relation on `MeterReading`; add `@@unique([building_id, zone_id, timestamp])`. Base pattern: existing `MeterReading` (lines 26-41) and `Building` (10-24).
- `backend/prisma/migrations/<new>/migration.sql` -- after Prisma's generated DDL, append raw SQL: dedupe existing `meter_readings` keeping lowest `id`, then `CREATE UNIQUE INDEX ... ON meter_readings (building_id, timestamp) WHERE zone_id IS NULL` (partial index Prisma cannot model).
- `backend/src/services/buildingService.js` -- extend `seedDefaultBuildingsIfNeeded` (line 24) to seed 10 zones for `office_tower_01`; add `listZonesWithLatest(buildingId)`.
- `backend/src/services/ingestService.js` -- NEW: validate building/zone existence, `prisma.meterReading.createMany({ skipDuplicates: true })`, return stored count.
- `backend/src/routes/ingest.js` -- NEW: `POST /readings`, Zod batch schema, `X-Ingest-Key` check. Zod/route pattern: `routes/buildings.js` (lines 7-14, 42-56).
- `backend/src/routes/buildings.js` -- add `GET /:id/zones` (mirror `/:id/history`, lines 59-72).
- `backend/src/app.js` -- mount `app.use('/api/v1/ingest', ingestRouter)` (line 36 area).
- `backend/.env.example` -- add `INGEST_API_KEY`.
- `backend/tests/ingest.test.js`, `backend/tests/zones.test.js` -- NEW, mocking `global.__mockPrisma` like `tests/buildings.test.js`.
- `backend/src/simulator/runSimulator.js` -- NEW Node script: read `ai-service/data/processed/office_building_clean.csv` (or the `sample_bdg2_energy.json` fallback), loop every 2–5 s posting a 10-zone batch to the ingest endpoint with `INGEST_API_KEY`, support `--anomaly-zone <id>`, retry on failure. Add a `simulate` npm script in `backend/package.json`.
- `ai-service/src/data_pipeline/stream_worker.py` -- reference only for the replay shape; not used (Node simulator is self-contained).

## Tasks & Acceptance

**Execution:**
- [x] `backend/prisma/schema.prisma` -- add `Zone`, `zone_id`, `@@unique([building_id, zone_id, timestamp])` -- FR33 (Zone), FR18.
- [x] `backend/prisma/migrations/<new>/migration.sql` -- generate with `prisma migrate dev --name add_zones_and_ingest`, then append the dedupe + partial-unique raw SQL -- FR18.
- [x] `backend/src/services/buildingService.js` -- seed 10 zones for `office_tower_01`; add `listZonesWithLatest` -- FR39.
- [x] `backend/src/services/ingestService.js` + `backend/src/routes/ingest.js` + mount in `app.js` -- ingest endpoint with Zod + `X-Ingest-Key` -- FR36.
- [x] `backend/src/routes/buildings.js` -- `GET /:id/zones` -- FR39.
- [x] `backend/.env.example` -- `INGEST_API_KEY` -- config.
- [x] `backend/src/simulator/runSimulator.js` + `simulate` script in `backend/package.json` -- replay 10 zones every 2–5 s, `--anomaly-zone`, retry-on-failure -- FR36.
- [x] `backend/tests/ingest.test.js`, `backend/tests/zones.test.js` -- cover every I/O matrix row for the two endpoints -- NFR8.

**Acceptance Criteria:**
- Given the mocked Prisma suite, when `npm run test --prefix backend` runs, then all tests pass including the new ingest and zones tests.
- Given the migration on a DB with duplicate readings, when applied, then duplicates are removed before the constraints are added and re-applying is idempotent.
- Given the simulator against a running gateway, when started, then `meter_readings` gains ~10 rows every 2–5 s and the rows carry distinct `zone_id`s.

### Review Findings

- [x] [Review][Patch] Limit maximum batch size in IngestBatchSchema (`backend/src/routes/ingest.js:19`)
- [x] [Review][Patch] Add test coverage for zoneless building-level readings (`backend/tests/ingest.test.js:125`)
- [x] [Review][Patch] Add test coverage for runSimulator with once flag (`backend/tests/simulator.test.js:84`)

## Implementation Notes

- Added `Zone` model and `zone_id` optional field to `MeterReading` in `schema.prisma`.
- Created and deployed migration `20261008235500_add_zones_and_ingest` with deduplication SQL before unique constraints, plus a partial index `WHERE zone_id IS NULL`.
- Implemented `listZonesWithLatest` in `buildingService.js` returning latest zone telemetry or null, and seeded 10 zones for `office_tower_01`.
- Mounted `POST /api/v1/ingest/readings` with Zod validation, `X-Ingest-Key` authentication, and duplicate skipping.
- Added `GET /api/v1/buildings/:id/zones` route.
- Implemented self-contained Node simulator `runSimulator.js` reading BDG2 data with 10-zone replay, `--anomaly-zone`, and error resilience. Added `npm run simulate`.
- Added test suites `ingest.test.js`, `zones.test.js`, and `simulator.test.js` passing all 35 backend tests. All 44 Python tests remain 100% green.

## Spec Change Log

## Review Triage Log

- `backend/src/routes/ingest.js:13`: [patch] Constrained `meter_reading_kwh` to non-negative floats via `.nonnegative()`.
- `backend/src/simulator/runSimulator.js:105`: [patch] Hardened gateway network error recovery to prevent simulator crash on connection drops.

## Design Notes

- **Partial unique index:** Postgres treats `NULL` as distinct, so `@@unique([building_id, zone_id, timestamp])` alone would not stop duplicate zoneless rows. The extra partial index `WHERE zone_id IS NULL` preserves the old `(building_id, timestamp)` guarantee for Story 1.1's building-level readings. Both are needed.
- **Zones:** `z1`..`z10` on `floor = 1`, names "Tầng 1 - Phòng 10x"; the simulator maps replay values to each zone with a small per-zone multiplier so the floor plan shows variation.
- **Combined story:** this spec closes sprint keys `1-2-simulate-building-sensors` and `1-3-ingest-readings-per-zone`; both are synced together.

## Verification

**Commands:**
- `cd backend && npm run test` -- expected: all pass, incl. new suites.
- `cd backend && npx prisma migrate reset --force && npx prisma migrate deploy` -- expected: migration applies cleanly on an empty DB.
- Manual: start gateway + simulator, then `GET /api/v1/buildings/office_tower_01/zones` shows 10 zones with recent `latest_reading`.
