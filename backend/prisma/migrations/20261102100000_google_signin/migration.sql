ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN google_sub VARCHAR(255);
CREATE UNIQUE INDEX users_google_sub_key ON users(google_sub);
CREATE TABLE oauth_flows (
  state_hash VARCHAR(64) PRIMARY KEY,
  browser_hash VARCHAR(64) NOT NULL,
  nonce VARCHAR(64) NOT NULL,
  code_verifier VARCHAR(128) NOT NULL,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX oauth_flows_expires_at_idx ON oauth_flows(expires_at);
