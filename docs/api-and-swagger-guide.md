# Connector API and Swagger guide

This is the human-readable reference for Connector `0.1.0`. The live, executable reference is
Swagger at `http://127.0.0.1:8010/docs`; ReDoc is at `/redoc` and OpenAPI JSON at `/openapi.json`.

## Run only the API documentation

From Windows PowerShell in the repository root:

```powershell
python -m uvicorn connector_service.main:app --app-dir src --host 127.0.0.1 --port 8010 --reload
Start-Process "http://127.0.0.1:8010/docs"
```

The same FastAPI process serves static frontend files at `/` and `/app`, but they do not run as a
separate service and do not interfere with `/docs`. Provider routes depend on
`CONNECTOR_ENABLED_PROVIDERS` in `.env` (`supabase`, `outlook`, and/or `gmail`).

## Authentication

| Swagger scheme | HTTP header | Purpose | How to obtain it |
|---|---|---|---|
| `AdminToken` | `X-Admin-Token` | Create projects, credentials, and grants | Value of `CONNECTOR_ADMIN_TOKEN` in `.env` |
| `ProjectApiKey` | `X-API-Key` | Use project-scoped connections and actions | Returned once by `POST /v1/admin/projects` |

Paste only the value into Swagger's **Authorize** dialog. To issue a project key, authorize with
`AdminToken`, execute `POST /v1/admin/projects` with `{"name":"support-copilot"}`, save the
response's `api_key`, and authorize `ProjectApiKey` with it. A project key cannot be retrieved later.

## Complete endpoint catalog

`Admin` and `Project` in the Auth column mean the schemes above. `*` marks a required path or query
parameter. Request and response types are defined in the next section.

### Health, administration, and dashboard sessions

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `GET /health` | Public | — | — | `200` health object |
| `POST /v1/admin/projects` | Admin | — | `ProjectCreate` | `201 ProjectCreatedResponse` |
| `POST /v1/admin/credentials` | Admin | — | `CredentialCreate` | `201 CredentialResponse` |
| `POST /v1/admin/grants` | Admin | — | `GrantCreate` | `201 GrantResponse` |
| `POST /v1/dashboard/login-tickets` | Project | — | `LoginTicketOptions` | `200 LoginTicketResponse` |
| `GET /v1/dashboard/session/exchange` | Ticket | `ticket*`, `return_to` | — | `200` redirect and cookie |
| `GET /v1/dashboard/session` | Project/session | — | — | `200 DashboardSessionResponse` |
| `DELETE /v1/dashboard/session` | Project/session | — | — | `204` no body |

### Providers and Supabase

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `GET /v1/providers` | Project | — | — | `200 ProviderResponse[]` |
| `POST /v1/connections/supabase/authorize` | Project | — | `SupabaseOAuthStart` | `200 SupabaseOAuthStartResponse` |
| `GET /v1/connections/supabase/callback` | OAuth state | `code`, `state`, `error` | — | `200 SupabaseOAuthCallbackResponse` |
| `GET /v1/connections/supabase` | Project | — | — | `200 ProviderConnectionResponse[]` |
| `GET /v1/connections/supabase/{connection_id}/projects` | Project | `connection_id*` | — | `200 SupabaseProjectSummary[]` |
| `POST /v1/connections/supabase/{connection_id}/select-project` | Project | `connection_id*` | `SupabaseProjectSelection` | `200 ProviderConnectionResponse` |
| `GET /v1/connections/supabase/{connection_id}/tables` | Project | `connection_id*` | — | `200 TableSummary[]` |
| `GET /v1/connections/supabase/{connection_id}/tables/{schema_name}/{table_name}` | Project | all path values* | — | `200 TableDescription` |
| `POST /v1/connections/supabase/{connection_id}/query` | Project | `connection_id*` | `TableQuery` | `200 TableQueryResponse` |
| `DELETE /v1/connections/supabase/{connection_id}` | Project | `connection_id*` | — | `204` no body |

OAuth callbacks are invoked by providers. Execute an authorize endpoint, open the returned
`authorization_url`, finish consent, and then return to Swagger.

### Governed database queries

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `POST /v1/agent/connections/{connection_id}/query-requests` | Project | `connection_id*` | `TableQuery` | `200 AgentQueryRequestResponse` |
| `GET /v1/agent/query-requests/{query_request_id}` | Project | `query_request_id*` | — | `200 AgentQueryRequestResponse` |
| `POST /v1/agent/query-requests/{query_request_id}/execute` | Project | `query_request_id*` | — | `200 TableQueryResponse` |
| `GET /v1/dashboard/connections/{connection_id}/agent-policy` | Project | `connection_id*` | — | `200 AgentPolicyResponse` |
| `PUT /v1/dashboard/connections/{connection_id}/agent-policy` | Project | `connection_id*` | `AgentPolicyUpdate` | `200 AgentPolicyResponse` |
| `GET /v1/dashboard/query-requests` | Project | `status` | — | `200 AgentQueryRequestResponse[]` |
| `POST /v1/dashboard/query-requests/{query_request_id}/approve` | Project | `query_request_id*` | `QueryDecision` | `200 AgentQueryRequestResponse` |
| `POST /v1/dashboard/query-requests/{query_request_id}/deny` | Project | `query_request_id*` | `QueryDecision` | `200 AgentQueryRequestResponse` |
| `GET /v1/dashboard/audit` | Project | `limit` | — | `200 QueryAuditResponse[]` |

### Gmail and Outlook mail

Use `gmail` or `outlook` for `{provider}`.

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `POST /v1/connections/{provider}/authorize` | Project | `provider*` | `EmailOAuthStart` | `200 EmailOAuthStartResponse` |
| `GET /v1/connections/{provider}/callback` | OAuth state | provider*, `code`, `state`, `error` | — | `200 EmailOAuthCallbackResponse` |
| `GET /v1/connections/{provider}` | Project | `provider*` | — | `200 EmailConnectionResponse[]` |
| `GET /v1/connections/{provider}/{connection_id}/folders` | Project | provider*, connection* | — | `200 MailFolder[]` |
| `POST /v1/connections/{provider}/{connection_id}/messages/search` | Project | provider*, connection* | `MessageSearch` | `200 MessagePage` |
| `GET /v1/connections/{provider}/{connection_id}/messages/{message_id}` | Project | provider*, connection*, message* | — | `200 MessageDetail` |
| `GET /v1/connections/{provider}/{connection_id}/threads/{thread_id}` | Project | provider*, connection*, thread* | — | `200 MessageThread` |
| `GET /v1/connections/{provider}/{connection_id}/messages/{message_id}/attachments` | Project | provider*, connection*, message* | — | `200 AttachmentMetadata[]` |
| `POST /v1/connections/{provider}/{connection_id}/drafts` | Project | provider*, connection* | `EmailCompose` | `200 DraftResponse` |
| `DELETE /v1/connections/{provider}/{connection_id}` | Project | provider*, connection* | — | `204` no body |

### Governed email sending

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `POST /v1/agent/connections/{provider}/{connection_id}/email-send-requests` | Project | provider*, connection* | `EmailCompose` | `200 EmailSendStatusResponse` |
| `GET /v1/agent/email-send-requests/{send_request_id}` | Project | `send_request_id*` | — | `200 EmailSendStatusResponse` |
| `POST /v1/agent/email-send-requests/{send_request_id}/execute` | Project | `send_request_id*` | — | `200 EmailSendExecutionResponse` |
| `GET /v1/dashboard/email-send-requests` | Project | `status` | — | `200 EmailSendRequestResponse[]` |
| `POST /v1/dashboard/email-send-requests/{send_request_id}/approve` | Project | `send_request_id*` | `EmailDecision` | `200 EmailSendRequestResponse` |
| `POST /v1/dashboard/email-send-requests/{send_request_id}/deny` | Project | `send_request_id*` | `EmailDecision` | `200 EmailSendRequestResponse` |
| `GET /v1/dashboard/email-audit` | Project | `limit` | — | `200 EmailAuditResponse[]` |

Creating a draft does not send mail. Governed sending requires request, approval, and execution
before the request expires.

### Calendar

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `GET /v1/connections/{provider}/{connection_id}/calendar/events` | Project | provider*, connection*, `limit` | — | `200 CalendarEventPage` |
| `POST /v1/connections/{provider}/{connection_id}/calendar/events` | Project | provider*, connection* | `CalendarEventCreate` | `201 CalendarEvent` |
| `PATCH /v1/connections/{provider}/{connection_id}/calendar/events/{event_id}` | Project | provider*, connection*, event* | `CalendarEventUpdate` | `200 CalendarEvent` |
| `DELETE /v1/connections/{provider}/{connection_id}/calendar/events/{event_id}` | Project | provider*, connection*, event* | — | `204` no body |

### Microsoft Teams and generic actions

| Method and path | Auth | Parameters | JSON request | Success response |
|---|---|---|---|---|
| `GET /v1/connections/outlook/{connection_id}/teams` | Project | connection* | — | `200 TeamSummary[]` |
| `GET /v1/connections/outlook/{connection_id}/teams/{team_id}/channels` | Project | connection*, team* | — | `200 ChannelSummary[]` |
| `GET /v1/connections/outlook/{connection_id}/teams/{team_id}/channels/{channel_id}/messages` | Project | connection*, team*, channel*, `limit` | — | `200 ChannelMessage[]` |
| `POST /v1/connections/outlook/{connection_id}/teams/{team_id}/channels/{channel_id}/messages` | Project | connection*, team*, channel* | `ChannelMessageCreate` | `201 ChannelMessage` |
| `POST /v1/actions/{connector}/{action}` | Project | connector*, action* | `ActionExecutionRequest` | `200 ActionExecutionResponse` |

Supabase generic actions are `list_resources`, `describe_resource`, `list_rows`, `get_row`, and
`call_rpc`. Their `grant_id` must belong to the authenticated project and allow the exact action.

## Request and response models

Notation: `*` required, `?` optional, `T[]` array, and `null` explicitly nullable. Unknown JSON
fields are rejected. Date-times use ISO 8601.

### Administration and actions

```text
ProjectCreate { name*: string(1..120) }
ProjectCreatedResponse { id*, name*, api_key*: string, warning: string }
CredentialCreate { name*: string, connector*: "supabase", secret*: SupabaseCredentialInput }
SupabaseCredentialInput { project_url*: URI, api_key*: secret, authorization_token?: secret|null }
CredentialResponse { id*, name*, connector*: string }
GrantCreate { project_id*, credential_id*: string, connector*: "supabase",
  actions*: SupabaseAction[], policy*: SupabaseGrantPolicy, description?: string|null }
SupabaseAction = "list_resources" | "describe_resource" | "list_rows" | "get_row" | "call_rpc"
SupabaseGrantPolicy { resources?: ResourcePolicy[], rpcs?: RpcPolicy[] }
ResourcePolicy { resource*: string, columns*: string[], filter_columns?: string[],
  order_columns?: string[], id_column?: string|null, max_page_size?: integer(default 100) }
RpcPolicy { name*: string, allowed_arguments?: string[], max_rows?: integer(default 100) }
GrantResponse { id*, project_id*, credential_id*, connector*: string, actions*: string[] }
ActionExecutionRequest { grant_id*: string, input?: object }
ActionExecutionResponse { data*: any, meta*: ActionMeta }
ActionMeta { connector*, action*: string, returned?: integer|null, next_cursor?: string|null }
```

### Providers, Supabase, and governed queries

```text
ProviderResponse { name*, display_name*: string, configured*: boolean, capabilities*: string[] }
ProviderConnectionResponse { id*, connector*, status*: string, external_ref*: string|null,
  name*: string|null, created_at*: datetime }
SupabaseOAuthStart { organization_slug?: string|null, return_to?: "/app"|"/app/"|null }
SupabaseOAuthStartResponse { authorization_url*: string, expires_at*: datetime }
SupabaseOAuthCallbackResponse { connection*: ProviderConnectionResponse, next_step?: string }
SupabaseProjectSelection { project_ref*: 20-character lowercase reference }
SupabaseProjectSummary { ref*, name*: string, organization_slug?, region?, status?: string|null }
TableSummary { schema_name*, table_name*: string, kind*: "table"|"view" }
ColumnSummary { name*, data_type*: string, nullable*: boolean, ordinal_position*: integer }
TableDescription { schema_name*, table_name*: string, columns*: ColumnSummary[] }
EqualityFilter { column*: string, value*: any }
TableOrder { column*: string, direction?: "asc"|"desc" }
TableQuery { schema_name?: string(default "public"), table_name*: string, columns*: string[](1..50),
  filters?: EqualityFilter[](max 20), order?: TableOrder[](max 5), limit?: integer(1..100) }
TableQueryResponse { data*: object[], returned*: integer, limit*: integer }
AgentPolicyUpdate { approval_mode?: "always"|"never", max_rows?: integer(1..100),
  allowed_schemas?: string[], masked_columns?: object<string,string[]> }
AgentPolicyResponse { AgentPolicyUpdate fields plus connection_id*: string }
AgentQueryRequestResponse { id*, connection_id*, status*: string, query*: TableQuery,
  requested_at*: datetime, decided_at*: datetime|null, decision_note*: string|null }
QueryDecision { note?: string|null }
QueryAuditResponse { id*, connection_id*: string, query_request_id*: string|null, actor_type*,
  schema_name*, table_name*: string, columns*: string[], filters*: object[], order_by*: object[],
  row_limit*: integer, status*: string, returned_rows*: integer|null, error_code*: string|null,
  created_at*: datetime, completed_at*: datetime|null }
```

### Mail and governed sending

```text
EmailOAuthStart { return_to?: "/app"|"/app/"|null, login_hint?: string|null }
EmailOAuthStartResponse { authorization_url*: string, expires_at*: datetime }
EmailConnectionResponse { id*, connector*, status*: string, external_ref*: string|null,
  name*: string|null, created_at*: datetime }
EmailOAuthCallbackResponse { connection*: EmailConnectionResponse, next_step?: string }
MailFolder { id*, name*: string, unread_count?: integer|null, total_count?: integer|null }
EmailIdentity { address*: string, display_name?: string|null }
MessageSearch { query?: string|null, folder_id?: string|null, limit?: integer(1..50) }
MessageSummary { id*: string, thread_id?: string|null, subject*: string, sender*: EmailIdentity|null,
  recipients?: EmailIdentity[], received_at?: datetime|null, snippet?: string,
  has_attachments?: boolean, is_read?: boolean|null }
MessagePage { data*: MessageSummary[], returned*: integer }
MessageBody { content_type*: string, content*: string }
MessageDetail { MessageSummary fields plus cc_recipients?: EmailIdentity[],
  bcc_recipients?: EmailIdentity[], body?: MessageBody|null }
MessageThread { id*: string, messages*: MessageDetail[] }
AttachmentMetadata { id*, name*: string, content_type?: string|null, size?: integer|null,
  inline?: boolean }
EmailCompose { to*: string[](1..20), cc?: string[], bcc?: string[], subject*: string,
  text_body?: string|null, html_body?: string|null, reply_to_message_id?: string|null }
DraftResponse { id*: string, provider*: "gmail"|"outlook", subject*: string,
  recipient_count*: integer }
EmailDecision { note?: string|null }
EmailSendStatusResponse { id*, connection_id*: string, provider*: "gmail"|"outlook", status*: string,
  requested_at*: datetime, expires_at*: datetime, decided_at*: datetime|null,
  decision_note*: string|null }
EmailSendRequestResponse { EmailSendStatusResponse fields plus message*: EmailCompose }
EmailSendExecutionResponse { request_id*: string, provider*: "gmail"|"outlook", status*: string }
EmailAuditResponse { id*, connection_id*: string, send_request_id*: string|null, provider*, action*,
  actor_type*: string, recipient_count*, attachment_count*: integer, status*: string,
  returned_items*: integer|null, error_code*: string|null, created_at*: datetime,
  completed_at*: datetime|null }
```

### Calendar, Teams, and dashboard

```text
CalendarEventCreate { title*: string, start*: datetime, end*: datetime,
  timezone?: string(default "UTC"), description?: string|null, location?: string|null,
  attendees?: string[](max 50) }
CalendarEventUpdate { the same fields, all optional }
CalendarEvent { id*, title*: string, start?, end?: datetime|null, timezone?, description?,
  location?: string|null, attendees?: string[], web_url?: string|null }
CalendarEventPage { data*: CalendarEvent[], returned*: integer }
TeamSummary { id*, name*: string, description?: string|null }
ChannelSummary { id*, name*: string, description?: string|null }
ChannelMessageCreate { content*: string(1..20000) }
ChannelMessage { id*, content*: string, sender?: string|null, created_at?: datetime|null,
  web_url?: string|null }
LoginTicketOptions { return_to?: string(default "/app/") }
LoginTicketResponse { ticket*: string, login_url*: string, expires_at*: datetime }
DashboardSessionResponse { project*: {id*: string, name*: string}, expires_at*: datetime }
```

## Real use case: governed customer-support copilot

A support copilot needs to find a customer's subscription in Supabase, read their Gmail thread,
schedule a follow-up, and send a response only after a person approves it.

### 1. One-time setup

1. Create `support-copilot` through `POST /v1/admin/projects` and save its key.
2. Authorize `ProjectApiKey`; call `GET /v1/providers` and verify `configured: true`.
3. Start Supabase authorization with `{}`, open `authorization_url`, finish consent, then obtain the
   connection ID from `GET /v1/connections/supabase`.
4. List its projects and select one with `{"project_ref":"abcdefghijklmnopqrst"}`.
5. Start Gmail authorization with `{"login_hint":"support@example.com"}`, finish consent, and
   obtain the Gmail connection ID from `GET /v1/connections/gmail`.

### 2. Govern the customer lookup

Set the policy through `PUT /v1/dashboard/connections/{connection_id}/agent-policy`:

```json
{
  "approval_mode": "always",
  "max_rows": 10,
  "allowed_schemas": ["public"],
  "masked_columns": {"public.customers": ["password_hash", "payment_token"]}
}
```

Create a query request:

```json
{
  "schema_name": "public",
  "table_name": "customers",
  "columns": ["id", "email", "plan", "subscription_status"],
  "filters": [{"column": "email", "value": "customer@example.com"}],
  "limit": 1
}
```

Review it via `GET /v1/dashboard/query-requests?status=pending`, approve with
`{"note":"Approved for support ticket CS-1042"}`, then execute the query request. A successful
response has this shape:

```json
{
  "data": [{
    "id": "customer-id",
    "email": "customer@example.com",
    "plan": "business",
    "subscription_status": "past_due"
  }],
  "returned": 1,
  "limit": 1
}
```

### 3. Find the customer's thread

Execute `POST /v1/connections/gmail/{connection_id}/messages/search`:

```json
{
  "query": "from:customer@example.com subject:(billing)",
  "limit": 10
}
```

Use a returned message or thread ID to fetch the full normalized conversation.

### 4. Schedule the follow-up

```json
{
  "title": "Billing follow-up — CS-1042",
  "start": "2026-07-21T10:00:00Z",
  "end": "2026-07-21T10:30:00Z",
  "timezone": "UTC",
  "description": "Review the past-due Business subscription.",
  "attendees": ["customer@example.com"]
}
```

Send that body to `POST /v1/connections/gmail/{connection_id}/calendar/events`.

### 5. Send only after approval

Create an email send request with:

```json
{
  "to": ["customer@example.com"],
  "subject": "Update on support ticket CS-1042",
  "text_body": "We reviewed your Business subscription and scheduled a billing follow-up."
}
```

Review it via `GET /v1/dashboard/email-send-requests?status=pending`, approve it with
`{"note":"Customer identity and content verified"}`, and only then execute
`POST /v1/agent/email-send-requests/{send_request_id}/execute`. Confirm it in
`GET /v1/dashboard/email-audit`.

## Errors and safe testing

- `401`: missing or invalid credential; `403`: authenticated but not permitted.
- `404`: project-scoped resource not found; `409`: duplicate/conflicting resource.
- `422`: invalid path, query, or body; `500`: unexpected server error.

Service errors normally use:

```json
{
  "error": {
    "code": "machine_readable_code",
    "message": "Safe explanation",
    "details": {},
    "request_id": "correlation-id"
  }
}
```

Use IDs returned by preceding operations rather than placeholders. Calendar creation, mail
execution, Teams posting, and disconnect endpoints make real external changes, so test them with
non-production accounts first.
