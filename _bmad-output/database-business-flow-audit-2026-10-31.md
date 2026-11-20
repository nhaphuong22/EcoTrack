# Database and business flow audit — 2026-10-31

Follow-up clarification: replay/synthetic realtime data is intentional for the equipment-free demo. F1 is therefore a description of separate demo pipelines, not a requirement to replace the simulator or connect physical devices. Remediation and subsequent live PostgreSQL verification are recorded in `implementation-artifacts/database-business-flow-fixes-2026-10-31.md`.

## Scope and validation

Inspected Prisma schema and both SQL migrations, Express routes/services, simulator, AI serving and Copilot tools, and frontend data hooks. No application code or database data was changed.

Backend verification: `npm.cmd test --prefix backend` passed 47 tests across 9 files. Database-dependent suites largely mock Prisma. The proxy suite attempted a real conversation write and reported that PostgreSQL at localhost:5432 was unreachable. A separate read-only Prisma probe also failed to initialize the connection. Live row counts, migration application, actual indexes, and stored-data integrity remain unverified. The database was not started or migrated during this audit.

## Current data model

- PostgreSQL accessed through Prisma in the gateway.
- Building has many Zone, MeterReading, AnomalyEvent, and Conversation records.
- MeterReading can refer to a building directly or an optional zone; timestamps use TIMESTAMPTZ.
- SQL migrations provide a composite unique index for zoned readings plus a partial unique index for zoneless readings. The latter is absent from the Prisma model, so migration-based provisioning is important; schema-only provisioning must be checked separately.
- Building/zone relations use cascading deletes. Status, severity, and role are strings rather than database enums/check constraints. Zone ownership is checked by the ingest service; its two independent foreign keys do not enforce building/zone agreement in the database.

## Current business flows

1. Building list/detail/history reads can seed default buildings and synthetic readings. History reads can also seed a newly created building when it has fewer than 24 readings.
2. Simulator generates per-zone batches → ingest validates key/payload/building/zone → Prisma createMany(skipDuplicates) → process-local EventEmitter → SSE → frontend zone state.
3. Dashboard metrics/timeseries → gateway TTL cache → AI serving frame → CSV and model artifacts. The AI replays a 720-hour historical window with shifted current timestamps. PostgreSQL ingest readings do not feed this path.
4. Forecast endpoint → recursive XGBoost forecast from that same replay frame. The dashboard currently passes historical timeseries to ForecastChart; fetchForecast is exported but has no production caller under frontend/src.
5. Anomaly list → AI replay detector + DB status lookup. A missing event is synced to DB on status update; listing itself does not persist detections.
6. Copilot → AI tools using the replay frame → best-effort conversation persistence. Request history is supplied by the client rather than restored from Conversation records.

## Findings, ordered by impact

### F1 — Critical: ingest and operational analytics use different sources

Evidence: backend/src/services/ingestService.js:56; ai-service/src/data_pipeline/serving_frame.py:145,191,263; ai-service/src/agent/tools/energy_tools.py:13.

A new ingested surge updates PostgreSQL and the zone view but cannot change KPI, forecast, AI anomaly detection, or Copilot metrics. This is acceptable as an explicit demo mode, but does not implement a shared live operational flow. Building identity is hardcoded to office_tower_01 in serving output.

Proposed direction: a building-scoped, hourly data provider sourced from persisted readings, with explicit demo/replay mode and source metadata. Define total-meter versus zone aggregation rules before connecting the two paths to avoid double counting.

### F2 — Critical: anomaly identity is unstable across serving windows

Evidence: ai-service/src/data_pipeline/serving_frame.py:241,292; backend/src/services/anomalyService.js:65,104.

The frame resets its index and IDs are ANOM-{idx}. As the replay window changes, an index can represent a different timestamp/observation. DB merge uses ID alone and upsert has an empty update. An old RESOLVED/IGNORED status can therefore attach to another event, while the DB snapshot retains an older timestamp/value.

Proposed identity change:

```diff
- "id": f"ANOM-{idx}",
+ "id": stable_event_id(building_id, observation_timestamp, detector_version),
```

Use a bounded deterministic hash or persist a generated ID behind a unique observation key. Define how replay runs differ from actual incident identity. Existing statuses need a migration/reconciliation policy.

### F3 — Critical for a shared deployment: mutation APIs lack user authorization

Evidence: backend/src/app.js:17-40; backend/src/routes/buildings.js:42; backend/src/routes/anomalies.js:23; backend/src/routes/ingest.js:28.

Building creation and anomaly status updates have no authentication/role middleware in this app. Ingest falls back to a public literal key when its environment variable is absent; docker-compose.yml does not pass INGEST_API_KEY to the backend. A client that reaches the gateway can create buildings/change incident statuses, and can ingest using the default key in that configuration.

Proposed direction: authenticate mutation routes, authorize by building/role, require INGEST_API_KEY and fail closed when missing. External gateway protections, if any, were not inspected.

### F4 — Warning: reads can add synthetic consumption to real buildings

Evidence: backend/src/services/buildingService.js:40,58-89,144.

GET history calls seedInitialReadingsIfNeeded for any existing building with fewer than 24 records. A newly created building or one with a few real readings can receive 72 invented records without source labels. Repeated/concurrent calls before the threshold is reached may add more samples because generated timestamps depend on the call time.

Proposed change:

```diff
- await seedInitialReadingsIfNeeded(buildingId);
+ // Seed only through an explicit demo initialization command.
```

Keep normal GET handlers read-only and label simulated data.

### F5 — Warning: history mixes building totals with zone readings

Evidence: backend/src/services/buildingService.js:146-162; backend/prisma/schema.prisma:41-54.

History filters only building_id, limits raw rows, and omits zone_id in its response. Ten zone readings at one instant become ten indistinguishable building points. Mixing those with zoneless total-meter data makes subsequent consumption sums unsafe; limit=168 means rows, not necessarily 168 hours.

Proposed direction: provide distinct total-meter and zone-history contracts. Aggregate by an agreed interval only after specifying whether zones cover the whole building and how totals take precedence.

### F6 — Warning: a partly duplicated batch broadcasts skipped records

Evidence: backend/src/services/ingestService.js:56-72; frontend/src/hooks/useLiveReadings.js:23.

createMany returns only an inserted count. If count is positive, the service broadcasts every input row, including rows skipped as duplicates. For example, an existing observation submitted with a changed value alongside one new row can update the live UI to a value never stored in DB. The frontend also does not reject older timestamps, so late arrivals can overwrite a newer displayed reading.

Proposed change:

```diff
- const result = await prisma.meterReading.createMany({data: records, skipDuplicates: true});
- if (result.count > 0) for (const r of records) broadcast(r);
+ const inserted = await prisma.meterReading.createManyAndReturn({data: records, skipDuplicates: true});
+ for (const r of inserted) broadcast(r);
```

Verify generated-client support before implementation. A durable outbox is a separate option if delivery across restarts/processes becomes required. Compare observation timestamps in the UI.

### F7 — Warning: incident history is incomplete and fallback invents estimates

Evidence: backend/src/services/anomalyService.js:19,58,84-131.

Listing does not save newly detected incidents. If AI returns any events, the response contains only that AI window, omitting DB incidents outside it even if still OPEN. When AI is unavailable, fallback manufactures predicted_kwh as 80% of actual, temperature as 28, and waste using fixed tariffs. These values are not the persisted model result and can materially change the operational/cost interpretation.

Proposed direction: persist detections independently of user updates; query incidents from DB with explicit building/time/status filters; store prediction, residual, tariff/model context when detected; represent unavailable values as unavailable. Separate status audit records from suggested_action text to support actor/time tracking and avoid lost concurrent notes.

### F8 — Warning: zone fallback can return another building's rooms

Evidence: backend/src/services/buildingService.js:246-261.

For a known building with no zones, including Hog_office_Betsy, fallback returns DEFAULT_ZONES_OFFICE_01 whose records still have building_id=office_tower_01. It also supplies random current readings. The response envelope and child ownership disagree even when DB is available but the requested building has no zones.

Proposed direction: return an empty list for a valid building without zones. If explicit demo fallback is enabled, use data belonging to the requested building and label its source/freshness.

### F9 — Warning: Copilot does not honor building context or isolate sessions

Evidence: ai-service/src/api/routers/copilot.py:14-25; backend/src/routes/copilot.js:32; backend/prisma/schema.prisma:85.

AI accepts building_id but does not pass it into process_chat; tools use the shared office_tower_01 frame. Gateway sessions combine building and date, grouping all users/tabs for that building/day. With a valid 50-character building ID the generated session ID is 66 characters, exceeding VARCHAR(50); the write fails and its exception is swallowed while chat succeeds.

Proposed direction: use a validated opaque session ID independent of building length, associate sessions with authenticated users/buildings, and pass building scope through tool calls. Decide whether history is durable or client-local and expose persistence failures appropriately.

## Recommended order

1. Stabilize anomaly identity and require authorization/explicit ingest credentials.
2. Define data source, interval, total-meter/zone semantics, building scope, and demo-mode behavior.
3. Remove request-time synthetic seeding; connect persisted observations to analytics.
4. Fix inserted-only SSE output, timestamp ordering, and zone fallback ownership.
5. Persist detection snapshots and status audit records; isolate Copilot sessions.
6. Add actual PostgreSQL integration coverage for migrations (including the zoneless partial index), duplicate/mixed batches, building/zone ownership, and incident identity across hour boundaries.

No migration drift or live data corruption is claimed: the running database could not be reached. The findings above describe behavior demonstrated by the checked-in code and the stated execution paths.
