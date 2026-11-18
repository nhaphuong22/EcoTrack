# Google sign-in and registration

Google credentials are configured only in root `.env` (Docker interpolation) and `backend/.env` (local server). Both are Git-ignored. `.env.example` contains placeholders only; frontend assets contain no client secret.

## Google Cloud configuration

Configure this exact **Authorized redirect URI** for the Web application OAuth client:

```text
http://localhost:5000/api/v1/auth/google/callback
```

The screenshot-provided URI `http://localhost:5000/api/auth/google/callback` is missing `/v1` and causes `redirect_uri_mismatch`. Save the corrected URI, restart local development if environment variables changed, and begin a fresh sign-in attempt from the application. Google requires the redirect URI to match the registered value exactly: https://developers.google.com/identity/protocols/oauth2/web-server.

The local frontend is `http://localhost:3000`. It may remain in Authorized JavaScript origins; the server authorization-code flow does not expose the secret to JavaScript. Production endpoints must use HTTPS. Update GOOGLE_REDIRECT_URI and APP_FRONTEND_URL with the deployed URLs and configure the corresponding Google redirect URI. If the consent screen is in testing, the intended Google account may also need to be added as a test user.

## Implemented behavior

- A shared “Continue with Google” entry supports both signup and subsequent login.
- New Google accounts have no password, household membership or privileged role. Invitations remain required.
- Google identities are keyed by the stable Google subject, not merely by an email supplied by the browser.
- Existing password accounts require explicit linking: sign in with the password, then click Link Google. Linking verifies the original local session and matching verified Google email. The system never silently merges an unverified local email account.
- The backend uses google-auth-library to exchange the authorization code and verify ID-token signature, issuer, audience and expiry. It additionally checks verified email and nonce.
- OAuth flow state is one-use, browser-cookie-bound and expires after 10 minutes. PKCE S256 binds the authorization code to the server's verifier.
- Google access/refresh tokens are not persisted. Normal application sessions use the existing opaque HttpOnly cookie and the same household authorization checks.
- OAuth failures return generic fixed frontend error codes, without logging provider tokens, authorization codes or secrets. Return destinations come from server configuration, not caller input.

Migration `20261102100000_google_signin` adds a unique nullable Google subject, allows null passwords for Google-only users, and adds the expiring OAuthFlow table. Existing accounts and memberships are preserved.

## Verification and remaining external step

- Backend suite: 72 tests passed, including 10 Google flow tests covering signup/login, explicit linking, wrong-browser callbacks, replay, expiry and invalid claims. Provider responses are mocked in those tests.
- Existing household isolation: 77 PostgreSQL/HTTP/SSE checks still pass.
- Frontend tests and production build passed, including Google entry links and callback-error handling.
- Live PostgreSQL smoke check passed for OAuth start, persisted state, cancellation callback and one-use state cleanup. The authorization URL points to Google and contains no client secret.
- End-to-end consent and successful Google identity verification require an interactive browser sign-in after the correct redirect URI is saved in Google Cloud; this external step has not been claimed as verified.

Because the supplied client secret appeared in the conversation, replace it in Google Cloud and update the two ignored environment files after rotation. No secret value is reproduced here.
