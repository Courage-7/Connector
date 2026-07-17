# Delivery Plan

## Milestone 1 — User-authorized Supabase

- [x] Modular FastAPI foundation and encrypted secret storage.
- [x] Project/tenant API authentication.
- [x] Supabase OAuth authorization-code flow with PKCE and replay-safe state.
- [x] Encrypted access/refresh token persistence and refresh handling.
- [x] Supabase project selection after authorization.
- [x] Live discovery of readable user tables and columns.
- [x] Structured, parameterized, row-limited queries through `supabase_read_only_user`.
- [x] Remote OAuth revocation and local disconnect lifecycle.
- [x] Register the Supabase OAuth application with `projects:read` and `database:read`.
- [x] Run a real OAuth, project-discovery, table-discovery, and read-only-query acceptance flow.
- [x] Persist the three connector-service-owned runtime secrets for restart-safe connections.
- [x] Add the end-user connection and table-browser interface.
- [x] Add per-query audit records and approval preferences.

## Milestone 2 — Agent interface

- [x] MCP tools for connection listing, table discovery, table description, and structured queries.
- [x] Human approval for bounded agent queries before execution.
- [x] Prompt-injection-aware result handling and configurable column masking.

## Milestone 3 — Outlook Mail

- [x] Microsoft OAuth connection lifecycle with PKCE, encrypted tokens, and refresh handling.
- [x] Folder listing, message search, message/thread retrieval, and attachment metadata.
- [x] Draft creation and exact-content, one-time, human-approved sending.
- [ ] Complete the real Outlook OAuth and send-delivery acceptance gate with release credentials.

## Milestone 4 — Gmail and Google Calendar

- [x] Google OAuth connection lifecycle for Gmail with PKCE, encrypted tokens, refresh, and revoke.
- [x] Gmail label listing, search, message/thread retrieval, and attachment metadata.
- [x] Gmail draft creation and exact-content, one-time, human-approved sending.
- [ ] Complete the real Gmail OAuth and send-delivery acceptance gate with release credentials.
- [ ] Add Google Calendar event and free/busy tools.

## Milestone 5 — Reuse interfaces

- Typed Python client.
- Two consuming-project examples and connector contract tests.
- Deployment, secret rotation, revocation, and incident runbooks.
