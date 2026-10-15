# 0008: Web sessions survive a reload, with the refresh token in an HttpOnly cookie

- **Date:** 2026-10-14
- **Status:** accepted (reversible default, per AGENTS.md rule 4)

## Context

On phones the refresh token lives in the OS keychain (SecureStore) and biometrics unlock it. The web build has neither,
so tokens were kept in a JS `Map`: every reload, new tab or pasted link signed the learner out. The founder flagged this
as wrong, and rejected `localStorage` because any script on the page (an XSS bug) could read the token from it.

## Decision

- A web client sends `X-Lingard-Client: web` to `/v1/auth/*`. Sign-in, invite redemption and refresh then set the
  refresh token as a cookie, `lingard_refresh`: `HttpOnly`, `SameSite=Strict`, `Path=/v1/auth`, `Secure` outside
  local/test, and `Max-Age` of `refresh_token_days`. The JSON body carries `refresh_token: null`. Phones are unchanged.
- The access token (15 minutes) stays in memory only. On load the app calls `/v1/auth/refresh` with the cookie, and the
  server's existing checks apply: rotation, reuse detection and the 30-day PIN re-verify.
- `/refresh` accepts the cookie only alongside the custom header. A cross-site page can't add that header without a CORS
  preflight, which the origin allowlist refuses. `SameSite=Strict` also stops other sites from sending the cookie at all.
- Sign-out, and any failed web refresh, delete the cookie.
- Open tabs share one cookie, and replaying a rotated token revokes the session, so web refreshes are serialised across
  tabs with the Web Locks API (`navigator.locks`).

## Constraints

The web app and the API must be **same-site** (for example `app.example.com` and `api.example.com`, or localhost on two
ports) for a `SameSite=Strict` cookie to be sent. CORS now sends `allow_credentials`, so `cors_origins` must stay an
explicit list, never `*`.

## Verified

- API: `services/api/tests/test_auth_flow.py`. The cookie is HttpOnly, SameSite=Strict and path-scoped; a body-less
  refresh works and rotates the cookie; sign-out clears it; the cookie alone (without the header) is refused; a failed
  refresh deletes it; the CORS preflight allows credentials for listed origins only.
- App: `src/__tests__/client.test.ts` covers resume from the cookie, signed out when there is no cookie, early
  requests refreshing, and tabs taking turns.
- In Chrome on 2026-10-14, against a throwaway database schema: after sign-in, `document.cookie` had no
  `lingard_refresh`. Reloads of `/passport`, `/school` and `/city` stayed signed in, including two tabs loading at once,
  with no reuse revocation. After sign-out, a reload landed on sign-in.

## Reverting

Drop the `X-Lingard-Client` header from the web client. The API then falls back to tokens in the body.
