# Connector Service

A reusable FastAPI service for connecting applications and AI agents to Supabase, Outlook, Gmail,
Google Calendar, Outlook Calendar, and Microsoft Teams without exposing provider credentials.
Provider access uses delegated OAuth, encrypted token storage, bounded operations, human approval
for governed agent writes, and redacted audit records.

The product flow is user-authorized: a person connects a provider in the browser, grants only the
required scopes, and remains in control of sensitive agent operations. Supabase access is bounded
to structured reads; Outlook and Gmail writes require exact-content approval before execution.

## Modular provider selection

Provider implementations are isolated under `src/connector_service/providers/<provider>/` and are
assembled through a typed provider catalog. A deployment can enable exactly the tools its consuming
project needs:

```dotenv
CONNECTOR_ENABLED_PROVIDERS=supabase
CONNECTOR_ENABLED_PROVIDERS=gmail
CONNECTOR_ENABLED_PROVIDERS=gmail,outlook
CONNECTOR_ENABLED_PROVIDERS=supabase,outlook,gmail
```

Disabled providers are not constructed, their provider-specific routes are not mounted, and their
action connectors are not registered. Authenticated projects can call `GET /v1/providers` to
discover enabled capabilities and configuration readiness. See
[`docs/architecture/provider-modules.md`](docs/architecture/provider-modules.md) for the extension
contract and package layout.

For a click-by-click guide to generating local secrets and obtaining every Supabase, Microsoft,
Google, dashboard, and MCP environment value, see
[`docs/configuration/environment-setup.md`](docs/configuration/environment-setup.md).

## Current capabilities

### Supabase

- OAuth authorization-code flow with PKCE and single-use, expiring state.
- Encrypted OAuth access and refresh tokens.
- Automatic access-token refresh and remote revocation on disconnect.
- Supabase project listing and explicit project selection.
- Live discovery of readable user tables and columns.
- Structured, parameterized, schema-qualified table queries.
- Secure dashboard sessions created from single-use login tickets.
- Approval-gated agent query requests, privacy masking, and redacted audit records.
- A stdio MCP adapter with structured tools and no arbitrary-SQL surface.
- Queries execute through Supabase's `supabase_read_only_user` Management API endpoint.
- Internal Supabase schemas are excluded from discovery.
- Query results are limited to 100 rows per request.
- Existing project API keys are stored as salted scrypt digests.
- Sanitized provider errors, response-size limits, request IDs, and structured logs.

The public query API does not accept arbitrary SQL. The service generates SQL only after validating
the selected schema, table, and columns against live metadata.

### Outlook Mail and Gmail

- OAuth authorization-code flow with PKCE, single-use state, encrypted tokens, and automatic
  refresh-token rotation.
- Stable mailbox identity, connection listing, local disconnect, and provider revocation where the
  provider supports it.
- Folder/label listing, message search, message detail, thread retrieval, and attachment metadata.
- Draft creation through Microsoft Graph or the Gmail API.
- Agent send requests store the exact proposed message encrypted and bind approval to a SHA-256
  digest of that content.
- A person reviews the exact recipients, subject, and body in the dashboard before approving or
  denying a send.
- An approved message can execute only once. Ambiguous provider outcomes are marked `unknown` and
  are never automatically retried.
- Email audit records contain action metadata and counts, never recipient addresses or body text.
- Mailbox content returned to an agent is explicitly labeled untrusted external data.

### Calendar and Microsoft Teams

- Existing Outlook and Gmail OAuth connections also provide Outlook Calendar and Google Calendar.
- Calendar routes list upcoming events and create, update, or delete events.
- Outlook connections can list joined Teams, channels, and channel messages, and send a channel
  message through Microsoft Graph.
- No duplicate OAuth connection or additional database schema is required.

## Connection flow

```text
Consumer application
    │  authenticated backend request
    ▼
Connector Service ── authorization URL ──► Provider consent screen
    ▲                                           │
    └───────── OAuth callback + code ───────────┘
    │
    ├── Supabase: select project, discover tables, run approved reads
    └── Outlook/Gmail: read mail, create drafts, approve and send once
```

The current `X-API-Key` identifies a consuming application or tenant. A customer-facing product
should authenticate its human users with its normal session/auth system and call this service from
its backend; do not place a connector-service API key in browser JavaScript.

## Register the Supabase OAuth application

1. Open the Supabase Dashboard and navigate to the organization's **OAuth Apps** settings.
2. Create an OAuth application.
3. Add this callback URL for local development:

   `http://localhost:8010/v1/connections/supabase/callback`

4. Grant only these OAuth scopes:

   - `projects:read`
   - `database:read`

5. Put the generated client ID and client secret in `.env`:

```dotenv
CONNECTOR_SUPABASE_OAUTH_CLIENT_ID=...
CONNECTOR_SUPABASE_OAUTH_CLIENT_SECRET=...
CONNECTOR_SUPABASE_OAUTH_REDIRECT_URI=http://localhost:8010/v1/connections/supabase/callback
```

Scopes are configured on the OAuth application, not sent as an authorization-URL parameter. Users
must re-authorize if the application's configured scopes change. See Supabase's
[OAuth integration guide](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration)
and [scope reference](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration/oauth-scopes).

## Register the email OAuth applications

### Microsoft Outlook

Create an app registration in Microsoft Entra ID, add this Web redirect URI, and create a client
secret:

`http://localhost:8010/v1/connections/outlook/callback`

Grant delegated permissions `openid`, `profile`, `email`, `offline_access`, `User.Read`,
`Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `Team.ReadBasic.All`,
`Channel.ReadBasic.All`, `ChannelMessage.Read.All`, and `ChannelMessage.Send`, then configure:

```dotenv
CONNECTOR_OUTLOOK_OAUTH_CLIENT_ID=...
CONNECTOR_OUTLOOK_OAUTH_CLIENT_SECRET=...
CONNECTOR_OUTLOOK_OAUTH_REDIRECT_URI=http://localhost:8010/v1/connections/outlook/callback
```

### Google Gmail

Create a Web application OAuth client in Google Cloud, enable the Gmail and Google Calendar APIs,
configure the OAuth consent screen, and add this authorized redirect URI:

`http://localhost:8010/v1/connections/gmail/callback`

The service requests `openid`, `email`, `gmail.readonly`, `gmail.compose`, and `calendar.events`,
then uses:

```dotenv
CONNECTOR_GMAIL_OAUTH_CLIENT_ID=...
CONNECTOR_GMAIL_OAUTH_CLIENT_SECRET=...
CONNECTOR_GMAIL_OAUTH_REDIRECT_URI=http://localhost:8010/v1/connections/gmail/callback
CONNECTOR_GOOGLE_CALENDAR_API_URL=https://www.googleapis.com/calendar/v3
```

Gmail's mail scopes are restricted. A public production application must complete Google's OAuth
verification requirements and may require a security assessment. Development accounts can be
listed as test users while the consent screen remains in testing.

## Local setup

```powershell
cd connector-service
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Generate the three service-owned secrets locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- Use independent random values for `CONNECTOR_ADMIN_TOKEN` and
  `CONNECTOR_CURSOR_SIGNING_KEY`.
- Use the Fernet value for `CONNECTOR_CREDENTIAL_ENCRYPTION_KEY`.
- These values come from your service, not from Supabase.

Create the schema and start the API:

```powershell
alembic upgrade head
python -m uvicorn connector_service.main:app --reload --port 8010
```

OpenAPI documentation is available at:

- Swagger UI: `http://127.0.0.1:8010/docs`
- ReDoc: `http://127.0.0.1:8010/redoc`
- OpenAPI JSON: `http://127.0.0.1:8010/openapi.json`
- Complete endpoint, schema, and use-case guide: [`docs/api-and-swagger-guide.md`](docs/api-and-swagger-guide.md)

In Swagger, select **Authorize** and enter either the consuming project's `X-API-Key` under
`ProjectApiKey` or the service administration token under `AdminToken`.

## Open the secure dashboard

Create `.env.consumer` from `.env.consumer.example` and set its one-time project API key. Keep this
file outside source control. With the API running, open the dashboard
through a short-lived, single-use login ticket:

```powershell
connector-dashboard
```

The command exchanges the consumer key server-to-server and opens `/app/`. Browser JavaScript
never receives the API key. The dashboard uses an `HttpOnly` session cookie, a separate CSRF token
for mutations, and an eight-hour default session. From there a user can:

1. Connect Supabase and approve the organization OAuth consent screen.
2. Select one authorized Supabase project.
3. Browse every readable table and its live column metadata.
4. Run bounded read-only previews with row-value masking enabled by default.
5. Approve or deny linked-agent query requests and review their audit history.
6. Connect Outlook or Gmail, review exact pending email sends, and approve or deny each one.

## Connect an AI agent with MCP

Install the project (`python -m pip install -e .`), keep the service running, and configure the AI
client to launch the local stdio adapter from this project directory. A typical MCP configuration is:

```json
{
  "mcpServers": {
    "connector-service": {
      "command": "connector-mcp",
      "cwd": "C:\\path\\to\\connector service"
    }
  }
}
```

The adapter reads `.env.consumer` inside its own process, so the model never needs the API key. Its
tools cover connection listing, Supabase schema discovery and approved structured queries, mailbox
folders, message search/detail/thread/attachment metadata, calendar event reads, Teams/channel
reads, and approval-gated email sending.
Provider data is labeled untrusted external data. Calling the request-send tool never sends mail;
the dashboard must approve the exact payload before the execute tool can send it once.

## API workflow

Create a consuming project through `POST /v1/admin/projects`. Save its one-time API key. Then:

1. `POST /v1/connections/supabase/authorize` with `X-API-Key`.
2. Open the returned `authorization_url` in the user's browser.
3. Supabase returns to the callback and creates a `pending_project` connection.
4. `GET /v1/connections/supabase/{connection_id}/projects`.
5. `POST /v1/connections/supabase/{connection_id}/select-project` with a project reference.
6. `GET /v1/connections/supabase/{connection_id}/tables`.
7. `GET /v1/connections/supabase/{connection_id}/tables/{schema}/{table}`.
8. `POST /v1/connections/supabase/{connection_id}/query`.
9. `DELETE /v1/connections/supabase/{connection_id}` to revoke and disconnect.

The Outlook and Gmail workflow uses the corresponding provider slug:

1. `POST /v1/connections/{provider}/authorize`, then open `authorization_url`.
2. The provider returns to `GET /v1/connections/{provider}/callback`.
3. Use the connection routes for folders, message search/detail/thread data, attachments, or drafts.
4. Use `/calendar/events` below the same connection for calendar operations.
5. For Outlook, use `/teams` below the connection to list teams, channels, and messages.
6. An agent creates a request with `POST /v1/agent/email/send-requests`.
7. A dashboard user reviews and approves it with
   `POST /v1/dashboard/email/send-requests/{request_id}/approve`.
8. The agent executes it once with `POST /v1/agent/email/send-requests/{request_id}/execute`.

Example structured query body:

```json
{
  "schema_name": "public",
  "table_name": "Requests",
  "columns": ["id", "status", "created_at"],
  "filters": [{"column": "status", "value": "open"}],
  "order": [{"column": "created_at", "direction": "desc"}],
  "limit": 25
}
```

## Verification

The full deterministic suite validates policy, encryption, OAuth replay protection, dashboard
sessions and CSRF, query approval, redacted auditing, MCP safety boundaries, query construction,
and provider error handling.

```powershell
python -m pytest
python -m compileall -q src tests
ruff check .
ruff format --check .
cd web
npm run lint
npm run test -- --run
npm run build
```

Real-provider acceptance is deliberately separate from the deterministic suite. Copy
`.env.live.example` to `.env.live`, then populate only the Supabase, Outlook, or Gmail section you
intend to test. Email live tests use disposable refresh tokens and sink mailbox addresses; sending
must be explicitly enabled only when those controlled inboxes are safe to use.

```powershell
python -m pytest -m live tests/live
```

The live gate performs real provider reads. The mail tests also create, approve, send, and verify one
uniquely identified benign message per configured provider, then prove replay is rejected and the
audit entry is redacted. It does not print tokens, message bodies, recipient addresses, or database
rows. These are release acceptance tests, not smoke tests.

## Security notes

- Never expose Supabase secret/service-role keys, Outlook/Gmail OAuth tokens, or connector API keys
  in a browser or AI prompt.
- Keep agent email sends approval-gated. Do not add automatic retries for ambiguous send outcomes.
- Keep manual approval enabled for agent tool calls involving production data.
- Prefer development projects or obfuscated data for AI workflows.
- Supabase table grants and Row Level Security are separate controls. Enable RLS on every exposed
  table and use ownership/authorization predicates appropriate to the application.
- The current live database-query endpoint is marked beta by Supabase. Keep its client isolated so
  endpoint or response changes can be adapted without changing the public connector contract.
