# Database and business flow fixes — 2026-10-31

## Scope

Implemented directly at the user's explicit request to bypass the blocked BMAD workflow. Synthetic realtime telemetry and the CSV/model analytics replay remain intentional demo capabilities. This change does not claim to connect room telemetry to the separate analytics replay, add physical device support, or make multi-building model predictions.

## Behavior changes

| Business problem | Previous behavior | Implemented behavior |
| --- | --- | --- |
| Incident identity | ANOM-{row position} could refer to a different event after the serving window changed. | A bounded deterministic hash identifies the building, replay timestamp, actual reading and prediction. Moving the same observation to another row preserves its ID; another observation gets a different ID. |
| Incident durability | Detections were generally saved only when an operator updated their status; older incidents vanished from the current list. | Listing synchronizes detections and returns the union of current replay incidents and persisted incidents, including those outside the replay window. |
| Offline incident evidence | Missing predictions, temperature, and costs were invented using fixed ratios. | JSON snapshots preserve the original predictions and costs. Legacy unknown values are null and displayed as unavailable. |
| Status history | Operator notes were appended to suggested actions; concurrent writes could overwrite notes. | Separate JSON audit entries preserve previous/new status, note, timestamp, and shared operator identity. Compare-and-set updates reject stale writes with 409. Original advice remains unchanged. |
| Duplicate ingestion | A partly duplicated batch broadcast every supplied row, including skipped values never saved in DB. | PostgreSQL/Prisma RETURNING supplies exactly the inserted rows; only these are broadcast. |
| Out-of-order display | Late or duplicate SSE messages could replace a newer measurement. | The frontend rejects non-newer timestamps, malformed timestamps and foreign-building readings. Stale HTTP refreshes also preserve newer live measurements. Reconnects back off and old building callbacks are disposed. |
| History side effects | Reading a building's history could insert synthetic records, including for newly created custom buildings. | GET handlers no longer initialize demo data. Startup initialization remains limited to known demo buildings, and only when empty. Seed timestamps align to UTC hours. |
| Total/room history | Total-meter and room measurements were returned together without room identity. | Default history selects only zoneless building totals. `?zone_id=z1` selects that building's validated room. Records and response carry zone scope and source. No room totals are implicitly added to building totals. |
| Room ownership | Empty/offline fallback could give Hog_office_Betsy rooms belonging to office_tower_01. | Valid empty buildings return no rooms. Offline demo fallback is filtered by ownership and labelled `demo_fallback`. |
| Copilot sessions | Sessions combined all chats for a building/day, and long building IDs exceeded the database limit. | Server-generated UUIDs fit VARCHAR(50); the client reuses the returned session ID and resets it when clearing chat. A late answer cannot restore cleared history. API returns `conversation_saved` to report persistence outcome. |
| Copilot building scope | Another requested building silently used office_tower_01 measurements. | Unsupported building analytics return 422 before tool execution. Only office_tower_01 currently has the analytics replay. |
| Forecast display | The dashboard did not call the future forecast endpoint. | It fetches the actual 24-hour recursive forecast, appends future points without actual readings, and marks the present-time boundary. |
| Administrative API access | Building creation, incident status updates and cache clearing required no credentials. Ingest accepted a public default secret. | These administrative operations require `X-Operator-Key`; ingest requires `X-Ingest-Key`. Missing server configuration fails closed. This is shared-key protection for the demo, not per-user login/RBAC. |
| Validation | Malformed query limits and imprecise timestamp strings could slip into processing. | Integer limits are validated at the gateway, timestamps require ISO datetime with an offset, humidity stays within 0–100, and chat inputs/notes have size limits. |

## Database migration and existing records

Added and applied `20261031160000_incident_snapshots`, which adds nullable `snapshot` JSONB and non-null `status_history` JSONB defaulting to `[]` on anomaly_events. Prisma Client was regenerated, schema validation passed, and migration status reports up to date. Existing rows are retained.

Old positional incident IDs remain historical records. Their statuses are deliberately not copied to new hashed IDs because the old IDs cannot reliably identify the same underlying incident. Legacy records with no prediction snapshot show unavailable values instead of fabricated estimates.

The existing zoneless-reading partial unique index remains managed by SQL migrations. Use migration deployment rather than relying on `prisma db push` to provision a new database.

## Local demo credentials

Ran `node backend/scripts/configure-demo-keys.cjs` to provision missing/placeholder keys in root `.env` and `backend/.env`. Both files are Git-ignored. Existing custom values are preserved; if intentionally different custom values exist in both files, align them before switching between Docker and local execution. No key is embedded in frontend assets or printed in this report.

Restart the backend/simulator to reload environment variables. The simulator now loads `backend/.env`; callers can still supply `--api-key`. Docker Compose explicitly requires both keys for the gateway. Administrative API clients must send the operator header. The dashboard has no existing administrative write UI requiring a frontend key.

Commands for another checkout:

```powershell
npm.cmd run demo:keys --prefix backend
npm.cmd run prisma:generate --prefix backend
npm.cmd exec --prefix backend -- prisma migrate deploy --schema backend/prisma/schema.prisma
```

## Verification

- Backend: 57 tests passed, including 10 business regression tests.
- AI: 26 relevant tests passed across serving frame, anomaly mapping, forecasting and new business regressions. This was a targeted run, not the entire ML experimentation suite.
- Frontend: 24 tests passed, including existing UI tests plus new SSE ordering/reconnect and Copilot session lifecycle regressions.
- Frontend production build passed; Vite reports the existing large-bundle advisory.
- `node backend/scripts/verify-business-flows.cjs`: 11 checks passed against the configured PostgreSQL, exercising real unique indexes, partly duplicated batches, history separation, ownership validation, incident snapshots, status-history writes and offline reads. All fixture writes were rolled back.
- `prisma validate`, `prisma migrate status`, and `git diff --check` passed.

No physical devices or cloud LLM credentials are required for these checks. Independent changes to BMAD planning artifacts and MLflow/HPO files observed in the shared workspace were left untouched.
