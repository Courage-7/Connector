# API and Swagger guide

Run the service on port 1080:

```powershell
python -m uvicorn connector_service.main:app --reload --port 1080
```

Open Swagger UI at <http://127.0.0.1:1080/docs>. The root URL redirects there. The service exposes
one authorization scheme named `BearerAuth`; `AdminToken` and `ProjectApiKey` no longer exist.

## Authenticate Swagger

1. Select **Authorize**.
2. Paste the value of `SERVICE_BEARER_TOKEN` from `.env`.
3. Do not add `Bearer `; Swagger adds it.
4. Select **Authorize**, then **Close**.
5. Execute `GET /v1/auth/me` to confirm the active subject.

Public endpoints are health, provider discovery, OpenAPI documentation, the OAuth callback, and MCP
discovery. Connections, tools, and MCP execution require Bearer authentication.

## Provider discovery

`GET /v1/providers` returns all product suites and their capabilities. A provider has:

- `status: available` when its OAuth/tools are implemented;
- `status: planned` when its future surface is visible but cannot yet execute;
- `configured: true` when the required OAuth client ID and secret are both present;
- a tool list with read/write type and implementation state.

Use `GET /v1/providers/{provider}` or `/tools` for one provider. Current slugs are `supabase`,
`google_workspace`, and `microsoft_365`.

## Connect Supabase

Execute `POST /v1/connections/supabase/authorize` with:

```json
{}
```

To preselect an organization:

```json
{
  "organization_slug": "your-organization-slug"
}
```

The response contains `authorization_url` and `expires_at`. Copy the URL and open it in a normal
browser tab. Swagger executes API calls through background JavaScript and cannot safely turn an
authenticated API response into top-level cross-origin navigation. A consuming web application
should navigate its browser to this returned URL.

After sign-in and consent, Supabase redirects to:

`GET /v1/oauth/supabase/callback?code=...&state=...`

The callback consumes the one-time state, exchanges the code, encrypts the tokens, stores a
connection, and returns:

```json
{
  "connection": {
    "id": "COPY_THIS_ID",
    "provider": "supabase",
    "status": "pending_resource",
    "external_reference": null,
    "display_name": null,
    "scopes": [],
    "created_at": "..."
  },
  "next_step": "List the authorized projects, then select one for this connection."
}
```

The callback does not require a Bearer header because the unpredictable, expiring, one-time state
binds it to the user who started the flow. Replaying the callback fails.

## Use the Supabase tools

All tool endpoints are `POST` so typed input is consistent between REST and MCP.

### List projects

`POST /v1/tools/supabase/list-projects`

```json
{
  "connection_id": "COPY_THIS_ID"
}
```

### Select one project

`POST /v1/tools/supabase/select-project`

```json
{
  "connection_id": "COPY_THIS_ID",
  "project_ref": "abcdefghijklmnopqrst"
}
```

The selected project must appear in the user's authorized project list. The connection becomes
`active`; a user cannot connect the same Supabase project twice.

### List readable tables/views

`POST /v1/tools/supabase/list-tables`

```json
{
  "connection_id": "COPY_THIS_ID"
}
```

The query runs as Supabase's read-only Management API user. Internal Supabase/PostgreSQL schemas and
relations without `SELECT` privileges are excluded.

### Describe a table

`POST /v1/tools/supabase/describe-table`

```json
{
  "connection_id": "COPY_THIS_ID",
  "schema_name": "public",
  "table_name": "customers"
}
```

### Query a table

`POST /v1/tools/supabase/query-table`

```json
{
  "connection_id": "COPY_THIS_ID",
  "query": {
    "schema_name": "public",
    "table_name": "customers",
    "columns": ["id", "email", "created_at"],
    "filters": [
      {"column": "status", "value": "active"}
    ],
    "order": [
      {"column": "created_at", "direction": "desc"}
    ],
    "limit": 25
  }
}
```

Only equality filters and `asc`/`desc` order are currently supported. The service validates every
identifier against live metadata, parameterizes values, schema-qualifies the relation, and enforces
a limit from 1 to 100. Arbitrary SQL is not accepted.

## Manage connections

- `GET /v1/connections` lists the authenticated user's active/pending connections.
- `GET /v1/connections?provider=supabase` filters that list.
- `GET /v1/connections/{connection_id}` returns one owner-scoped connection.
- `DELETE /v1/connections/{connection_id}` revokes Supabase authorization and hides the local
  connection.

Another Bearer subject receives 404 for a connection it does not own; connection IDs do not grant
access.

## MCP

`GET /v1/mcp` documents the MCP endpoint and current tools. Configure a Streamable HTTP MCP client:

```text
http://127.0.0.1:1080/mcp
Authorization: Bearer <token>
```

REST and MCP call the same application services, use the same connection IDs, and enforce the same
owner boundary. Current tool names are:

- `supabase_list_projects`
- `supabase_select_project`
- `supabase_list_tables`
- `supabase_describe_table`
- `supabase_query_table`

## Error envelope

Expected failures use one shape:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "The request is invalid.",
    "details": {},
    "request_id": "..."
  }
}
```

The response also includes `X-Request-ID`. Provider tokens, secrets, database passwords, raw
provider responses, and stack traces are not returned.

Common status codes:

- `401`: missing, invalid, expired, or unverifiable service Bearer token;
- `404`: provider/connection missing or owned by another subject;
- `409`: duplicate provider resource connection;
- `422`: invalid body, OAuth state, or tool precondition;
- `502`: provider rejected a request or returned an invalid response;
- `503`: provider unavailable, rate-limited, or timed out.
