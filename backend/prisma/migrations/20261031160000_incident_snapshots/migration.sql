-- Keep the original demo/model evidence, including tariffs and predictions.
ALTER TABLE "anomaly_events" ADD COLUMN "snapshot" JSONB;
ALTER TABLE "anomaly_events" ADD COLUMN "status_history" JSONB NOT NULL DEFAULT '[]';
