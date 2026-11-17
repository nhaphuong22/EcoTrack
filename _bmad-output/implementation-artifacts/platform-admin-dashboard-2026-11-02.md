# Platform administrator and original dashboard

Created a separate `admin@ecotrack.local` account with `is_platform_admin=true`, without changing the existing building manager or Google resident accounts. A random password is stored only in Git-ignored `backend/.demo-admin.key` and a salted hash is stored in PostgreSQL.

Sign in through the normal account portal, then click **Dashboard hệ thống**. This opens the original KPI/forecast/anomaly/Copilot dashboard using a lazy-loaded component. **Về cổng cư dân** returns to the scoped portal; logout is available from the dashboard navigation. Residents and building managers do not receive the dashboard button, and the backend independently restricts legacy APIs to platform administrators.

The legacy realtime hook now sends session cookies through credentialed EventSource. The scoped portal closes its own stream while the system dashboard is open.

Local provisioning can be repeated with `npm run setup:admin --prefix backend`. An explicitly selected existing account can be promoted with `-- --email user@example.com`; the script preserves its password. This is a trusted local administrative command, not a public API.

Verification: live PostgreSQL/HTTP checks passed for administrator login, administrator profile, access to legacy building APIs, and denial of anonymous access. Frontend regression tests cover role-based button visibility and switching to/from the original dashboard. The frontend production build was also checked.
