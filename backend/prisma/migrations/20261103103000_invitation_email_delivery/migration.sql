-- Record whether the invitation email actually reached the invitee. Existing
-- rows predate outbound email, so email_sent_at stays NULL for them: the token
-- was shared by hand and nothing must be inferred about a delivery.
ALTER TABLE "invitations" ADD COLUMN "email_sent_at" TIMESTAMPTZ;
ALTER TABLE "invitations" ADD COLUMN "email_attempts" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "invitations" ADD COLUMN "email_last_error" VARCHAR(300);

-- A resend supersedes the outstanding invitation for the same invitee, so the
-- hot lookup is household + email rather than household alone.
DROP INDEX IF EXISTS "invitations_household_id_idx";
CREATE INDEX "invitations_household_id_email_idx" ON "invitations"("household_id", "email");
