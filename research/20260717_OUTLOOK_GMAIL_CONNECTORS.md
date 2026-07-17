# Outlook Mail and Gmail connector requirements

Date: 2026-07-17

## Executive recommendation

Implement both providers, including real sending, but put them behind one shared email contract and a new provider-neutral action-approval system. The service already has reusable encrypted OAuth-attempt and connection storage, but its agent policies, approval requests, audit records, MCP tools, and dashboard endpoints are specialized around Supabase table queries. Sending mail must not be added by copying that query-specific path.

Recommended internal connector names are `outlook_mail` and `gmail`. Both should expose the same normalized actions:

- `list_folders`
- `search_messages`
- `get_message`
- `get_thread`
- `list_attachments`
- `get_attachment`
- `create_draft`
- `update_draft`
- `send_draft`
- `send_message`

Add `create_reply_draft` after the basic draft path is stable. Returned message bodies, headers, links, filenames, and attachment contents must always be labelled untrusted external data. A message must never be allowed to approve or trigger an outbound send.

## Existing codebase fit

The reusable pieces are:

- `core/contracts.py` and `core/registry.py`: the action protocol and explicit connector registry are already provider-neutral.
- `db/models.py:98-145`: `OAuthAttempt` and `ProviderConnection` already carry a connector name, encrypted provider secret, external reference, status, and token expiry.
- `core/security.py`: authenticated encryption is already used for provider credential documents.
- `api/actions.py`: action execution already verifies connector/action grants before dispatching to a registered connector.
- The Supabase OAuth implementation already demonstrates single-use state, PKCE, encrypted token persistence, refresh, disconnect, safe provider errors, bounded responses, and real-provider testing.

The parts that must be generalized are:

- `api/connections.py:56` is one Supabase-specific router and embeds Supabase token types, client calls, project selection, and refresh behavior.
- `api/schemas.py:17-45` restricts administrator credentials and grants to the literal connector `supabase`.
- `app.py:47-71` registers and stores only the Supabase implementations.
- `AgentAccessPolicy`, `AgentQueryRequest`, and `QueryAuditRecord` in `db/models.py:187-270` model schemas, tables, filters, row counts, and table-query approvals rather than generic provider actions.
- `mcp_server.py:70-287` hardcodes Supabase connection routes and six table-query tools.
- The dashboard connection, approval, and audit views assume a Supabase table-query shape.

Do not copy `QueryAuditRecord` for each provider, and do not store OAuth connection tokens a second time in `Credential`. Add a provider-neutral connection action service that decrypts one `ProviderConnection`, obtains a valid token through its OAuth provider, invokes the registered connector, and records a generic action audit.

## OAuth foundation

### Shared behavior

Extract the pure OAuth pieces first:

1. `OAuthMaterial` generation: high-entropy state, SHA-256 state digest, 43-128 character PKCE verifier, and unpadded base64url SHA-256 S256 challenge.
2. A token document that preserves access token, refresh token, expiry, granted scopes, token type, and provider-specific account metadata.
3. An OAuth provider protocol for authorization URL creation, code exchange, refresh, account discovery, and disconnect/revocation behavior.
4. A connection-token service that refreshes with skew, persists replacement tokens atomically, and converts revoked/invalid grants to a `reauthorization_required` connection status.

Reuse `OAuthAttempt`. Store the PKCE verifier and optional dashboard `return_to` in its encrypted context. Continue digesting state rather than storing it in plaintext, enforce the existing short expiry, and consume it exactly once. Validate the provider-returned state before any token exchange.

Refresh must be concurrency-safe. Use a transaction/compare-and-swap or a per-connection lock so parallel agent calls do not overwrite a newer token document. Microsoft normally returns a new refresh token; replace the stored token. Google often does not return a refresh token during refresh or later authorization responses; preserve the existing refresh token when the field is absent.

OAuth callbacks must first complete the provider exchange and account lookup, then create an active connection with a stable provider account ID as `external_ref`. The email/display name belongs in `name`. An email address alone should not be treated as a stable account identifier.

### Microsoft authorization

Register a confidential web application in Microsoft Entra ID. Use the v2 endpoints:

- Authorization: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize`
- Token and refresh: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
- Microsoft Graph: `https://graph.microsoft.com/v1.0`

Use `common` only if the app registration is configured to accept both Microsoft personal and work/school accounts; otherwise use the intended tenant or `organizations`. The redirect URI must exactly match the web-platform URI registered in Entra. Microsoft recommends authorization code flow and supports S256 PKCE for confidential clients as well as public clients. Request `offline_access` for a refresh token, and send `code_verifier` during code exchange. Microsoft documents replacing the stored refresh token with the new token returned by refresh. See [authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [delegated Graph access](https://learn.microsoft.com/en-us/graph/auth-v2-user), and [refresh-token lifecycle](https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens).

Minimum practical delegated scopes for all requested features:

```text
openid profile email offline_access User.Read Mail.ReadWrite Mail.Send
```

- `Mail.ReadWrite` is required to create and update drafts and also covers mailbox-content reads. It explicitly does not grant sending.
- `Mail.Send` is separately required to send a new message or an existing draft.
- `User.Read` supports a stable `/me` identity lookup.
- These delegated mail permissions are available to personal and organizational Microsoft accounts and are listed as not requiring admin consent by default, although a customer's tenant consent policy can still require administrator approval.

`Mail.ReadBasic` is insufficient because it excludes bodies and attachments. Do not request shared-mailbox scopes, application permissions, or send-as/on-behalf-of permissions in the first release. The official [Graph permission reference](https://learn.microsoft.com/en-us/graph/permissions-reference) distinguishes `Mail.Read`, `Mail.ReadWrite`, and `Mail.Send`.

Microsoft does not offer this confidential client a narrow, ordinary per-connection revocation endpoint equivalent to Google's token-revocation endpoint. Disconnect should securely delete the local token document and mark the connection disconnected. Offer the user the Microsoft My Apps permission-management link for consent revocation. Do not request `DelegatedPermissionGrant.ReadWrite.All` merely so the app can delete its own consent; that would be disproportionately powerful. Microsoft documents user permission removal in the [My Apps consent experience](https://learn.microsoft.com/en-us/entra/identity-platform/application-consent-experience). Refresh failure after provider revocation must move the connection to `reauthorization_required`.

### Google authorization

Create a Google Cloud web OAuth client, enable the Gmail API, configure the consent screen, and register the exact callback URI. Use:

- Authorization: `https://accounts.google.com/o/oauth2/v2/auth`
- Token and refresh: `https://oauth2.googleapis.com/token`
- Revocation: `https://oauth2.googleapis.com/revoke`
- Gmail REST: `https://gmail.googleapis.com/gmail/v1`

Use authorization code flow with random state, `access_type=offline`, `include_granted_scopes=true`, S256 PKCE, and `code_verifier` on exchange. Google's OIDC discovery advertises S256 support. `prompt=consent` should be used only when intentionally obtaining a replacement refresh token, not on every connection. See the [web-server OAuth guide](https://developers.google.com/identity/protocols/oauth2/web-server), [OIDC endpoint reference](https://developers.google.com/identity/openid-connect/reference), and [OAuth security practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices).

Use incremental authorization with these scopes:

```text
openid email
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.compose
```

- `gmail.readonly` is needed for search, bodies, threads, and attachments.
- `gmail.compose` covers Gmail-hosted draft management and sending.
- If drafts were excluded, the sensitive `gmail.send` scope could replace `gmail.compose`; it cannot satisfy the requested draft support.
- Avoid `gmail.modify` because Connector does not need to change labels or mailbox state, and never request `https://mail.google.com/` unless immediate permanent deletion is a real product requirement.

Both recommended Gmail scopes are restricted. Google's [scope reference](https://developers.google.com/workspace/gmail/api/auth/scopes) states that a public app using them needs restricted-scope verification, and server-side storage or transmission of restricted data requires a security assessment. This is a real production-readiness workstream, not a coding detail. External apps in Testing status also receive seven-day refresh tokens when Gmail scopes are present, so a testing OAuth project is appropriate for live acceptance but not durable production connections. Google documents token limits and invalidation in its [OAuth overview](https://developers.google.com/identity/protocols/oauth2).

On disconnect, POST the refresh token (or current access token if needed) to Google's revocation endpoint, then erase the encrypted local token even if the provider response is already-invalid. Revocation affects the combined authorization grant, so the UI should warn that all scopes granted to this Google Cloud project are removed.

## Provider REST mapping

### Outlook Mail through Microsoft Graph

| Capability | Graph v1.0 operation | Notes |
| --- | --- | --- |
| Account | `GET /me` | Store returned `id` as `external_ref`. |
| Folders | `GET /me/mailFolders` and recursively `/me/mailFolders/{id}/childFolders` | Root listing is not recursive; omit hidden folders by default. [Folder documentation](https://learn.microsoft.com/en-us/graph/api/user-list-mailfolders?view=graph-rest-1.0). |
| Search | `GET /me/messages?$search="..."&$select=...` | `$search` targets from, subject, and body by default, supports KQL properties, is sent-time sorted, and returns at most 1,000 results. [Search documentation](https://learn.microsoft.com/en-us/graph/search-query-parameter). |
| List folder messages | `GET /me/mailFolders/{id}/messages` | Follow `@odata.nextLink`; never accept an arbitrary caller-supplied next-link host. [List messages](https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messages?view=graph-rest-1.0). |
| Message | `GET /me/messages/{id}` | Use a narrow `$select` and default `Prefer: outlook.body-content-type="text"`; HTML is opt-in and sanitized. [Get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0). |
| Thread | list messages filtered by `conversationId` | Implementation inference to validate in the live gate: Outlook mailbox messages expose `conversationId` and list-messages supports OData filtering, while Graph's `conversationThread` resource is not a general mailbox-thread API. Normalize results in sent-time order. |
| Attachment metadata | `GET /me/messages/{id}/attachments?$select=id,name,contentType,size,isInline,lastModifiedDateTime` | Keep bytes out of metadata responses. [List attachments](https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0). |
| Attachment bytes | `GET /me/messages/{id}/attachments/{id}/$value` | Enforce connector byte/type limits before returning content. [Get attachment](https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0). |
| Create draft | `POST /me/messages` | Returns `201` and a draft; JSON is preferable to raw MIME initially. [Create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0). |
| Send draft | `POST /me/messages/{id}/send` | Returns `202 Accepted`, which is acceptance, not proof of final delivery. [Send draft](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0). |
| Direct send | `POST /me/sendMail` | Supports JSON or MIME and returns `202`. [sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0). |

Use well-known folder names such as `inbox`, `drafts`, and `sentitems` instead of localized display names. Message IDs can change after moves; where appropriate request immutable IDs, while recognizing that sending a draft is an exception. Preserve only provider IDs and selected metadata required for the feature.

Honor Graph `429` `Retry-After` for safe reads and use bounded exponential backoff when it is absent. Do not automatically retry a send after a timeout or ambiguous `5xx`; it can duplicate a real message. Microsoft's [throttling guide](https://learn.microsoft.com/en-us/graph/throttling) describes the required `Retry-After` behavior.

### Gmail

| Capability | Gmail v1 operation | Notes |
| --- | --- | --- |
| Account | `GET /users/me/profile` plus validated OIDC identity | Store OIDC `sub` as `external_ref`; profile supplies current email. |
| Folders | `GET /users/me/labels` | Normalize system/user labels as folders without pretending Gmail has Outlook's folder hierarchy. |
| Search | `GET /users/me/messages?q=...&maxResults=...&pageToken=...` | Uses Gmail search-box syntax; results initially contain only `id` and `threadId`. Follow bounded page tokens. [messages.list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list). |
| Message | `GET /users/me/messages/{id}?format=full` | Parse the MIME part tree and decode base64url bodies; `metadata` and `minimal` are useful for previews. [messages.get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get). |
| Thread | `GET /users/me/threads/{threadId}?format=full` | Native Gmail thread retrieval. [threads.get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get). |
| Attachment metadata | derive filename, MIME type, size, and `attachmentId` from message MIME parts | Do not fetch bytes during metadata listing. |
| Attachment bytes | `GET /users/me/messages/{messageId}/attachments/{attachmentId}` | Response data is base64url encoded. [attachments.get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments/get). |
| Create/update draft | `POST /users/me/drafts`, `PUT /users/me/drafts/{id}` | Body wraps an RFC 2822 MIME message, base64url encoded in `message.raw`. |
| Send draft | `POST /users/me/drafts/send` | Sends the existing draft. |
| Direct send | `POST /users/me/messages/send` | Sends base64url RFC 2822 MIME in `raw`. [Sending guide](https://developers.google.com/workspace/gmail/api/guides/sending). |

For replies, include the target `threadId`, matching `Subject`, and correct `References` and `In-Reply-To` headers. Before any send with a requested From address, enumerate `GET /users/me/settings/sendAs` and allow only the primary address or an alias whose `verificationStatus` is `accepted`. Do not implement alias creation with ordinary user OAuth; Google limits that operation to service accounts with domain-wide delegation. See [send-as listing](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs/list).

Gmail read retries should use bounded truncated exponential backoff for `429` and transient `5xx`. Sends are not safe for blind transport-level retries. Gmail documents API and mail-sending limits, including a maximum of 500 recipients per message, in its [usage limits](https://developers.google.com/workspace/gmail/api/reference/quota) and [error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors). Connector's own recipient limit should be much lower.

## Approval, audit, and security design

### Generic action request

Add a new model rather than stretching `AgentQueryRequest`:

- `id`, `project_id`, `connection_id`, `connector`, `action`
- encrypted immutable execution payload
- SHA-256 payload digest and a redacted human preview
- requester/actor, status, expiry, decision note, request/decision/execution timestamps
- one-time execution state and optional provider operation/reference ID

The approval screen must show the exact From, To, Cc, Bcc, subject, body, attachment names/sizes, and reply target that will be sent. Approval binds to the encrypted payload digest. Recompute it immediately before execution and reject changed, expired, replayed, or already-executing requests. If sending an existing provider draft, re-fetch it at execution and invalidate approval if its recipients, subject, body, or attachments differ from the approved digest.

Initial policy:

- Read/search/get: allowed when the connection's agent policy enables the named action; still bounded and audited.
- Create/update draft: explicit approval by default.
- Send direct or send draft: always explicit, one-time human approval. Do not add an `always_allow` mode in the first release.
- Shared mailbox, send-as, send-on-behalf, bulk mail, scheduled mail, and automated replies: denied until separately designed.

Mark an outbound operation `executing` in a committed transaction before calling the provider. A successful provider response moves it to `succeeded`. A transport timeout after request transmission is `unknown`, not `failed`; never retry it automatically. Reconcile against the draft/Sent folder using a connector operation identifier or unique message identifier before a human can retry.

### Generic action audit

Add `ActionAuditRecord` with connector, action, connection, actor, request ID, policy decision, payload digest, redacted target summary, status, provider reference, provider request ID, safe error code, and timestamps. Do not store OAuth tokens, raw bodies, recipient lists in plaintext, attachment bytes, or provider error bodies. Recipient count and optionally normalized recipient-domain summaries are sufficient for routine audit display. Keep the existing query audit during migration; later present both through one audit API.

### Content and transport safety

- Email bodies, subjects, senders, links, calendar snippets, MIME headers, filenames, and attachments are untrusted. Return an explicit trust label from API and MCP tools, as the Supabase MCP path already does.
- Default Outlook retrieval to text. Parse Gmail MIME with the standard-library email parser under strict decoded-size, part-count, nesting-depth, and header-length limits. Sanitize any rendered HTML, block active content and remote-image loading, and never fetch links automatically.
- Attachment download is a separate action with maximum byte size and allowed content-type policy. Sanitize filenames and never write a provider filename directly to a filesystem path. Malware scanning belongs before attachments are opened or forwarded.
- Reject CR/LF injection in all structured header values and use a real MIME builder for Gmail. Normalize and validate addresses, cap To/Cc/Bcc counts, and default Bcc to disallowed for agent sends.
- Do not permit the caller to set arbitrary Graph URLs, Gmail URLs, From addresses, internet headers, or MIME blobs. Accept strict structured fields and build provider requests server-side.
- Encrypt provider and action payload secrets at rest. Never send OAuth credentials to the browser, MCP client, model prompt, logs, or audit responses.
- Google permits user-facing generative-AI email productivity, but Gmail data cannot train or improve a generalized/foundation model, be permanently stored with such a model, or be transferred without user consent for the visible feature. Document Google Limited Use compliance and data deletion. See the [Google Workspace API user-data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy).

## Real-provider acceptance testing

Keep mocked deterministic tests for failure and security branches, but use real acceptance tests as the release gate. Use disposable Microsoft and Google accounts plus a controlled recipient mailbox. Never use production mailboxes or print message bodies/tokens.

For each provider, the live gate should perform this complete flow:

1. Start authorization through Connector, complete real provider consent with PKCE, and verify the persisted connection is active with the correct account identity and encrypted token bytes.
2. List real folders/labels, search a unique fixture message, retrieve it and its thread, and retrieve attachment metadata plus bytes for a small known fixture without logging the contents.
3. Force Connector's stored access-token expiry and prove a real refresh succeeds; confirm token persistence and continued API access. Google must preserve its refresh token when the refresh response omits one; Microsoft must persist the replacement refresh token.
4. Create a real draft addressed to the controlled sink, retrieve it, update it, and verify the provider's Drafts state.
5. Submit the exact draft/send through the agent action-request endpoint, approve it in the real dashboard, execute it once, and verify a second execution is rejected.
6. Confirm the unique message appears in Outlook Sent Items or Gmail's SENT label and reaches the controlled recipient. Verify Connector's action audit contains the successful provider reference but no plaintext body or token.
7. Run a second deliberately denied send and confirm the provider was never called. Run mutation, expiry, and replay cases against the approval digest.
8. Disconnect. For Gmail, verify remote revocation makes the refresh token unusable. For Microsoft, verify local access is gone and document/perform consent revocation through My Apps when testing the full account lifecycle.

Sending must use a unique non-secret subject marker and a benign body, target only the configured sink, cap the run to one actual message per provider, and clean up drafts/fixtures where doing so does not erase required audit evidence. An Outlook `202 Accepted` or Gmail API success alone is not the complete acceptance assertion; verify Sent state and receipt. Google's own error guide warns that API success is not by itself proof of final mail delivery.

Recommended test split:

- Unit: strict Pydantic inputs, address/header injection rejection, MIME serialization/parsing, normalization, digests, PKCE, token parsing, scope checks, response-size limits.
- Mocked HTTP integration: exact endpoints/queries, pagination, refresh races, missing Google refresh token, Microsoft rotation, revoked grants, 401/403/429/5xx mapping, safe read retries, and no send retry on ambiguity.
- API/database: OAuth replay, duplicate account constraints, CSRF/return navigation, approval/deny/expiry/mutation/replay, audit redaction, authorization boundaries.
- MCP: tool schema, connection scoping, untrusted-content envelope, send approval handoff, and inability for returned email content to execute an action.
- `pytest -m live`: the real flow above, explicitly enabled by provider-specific environment flags and configured sink addresses.

Do not put live access/refresh tokens in committed fixtures or command output. Prefer authorizing the disposable accounts through the normal dashboard into the encrypted test database. Separate Google OAuth projects for Testing and Production are advisable because Testing grants expire after seven days and production verification has different controls.

## Staged implementation plan

1. **Foundation and migration**
   - Extract shared PKCE/token/state utilities without changing Supabase behavior.
   - Add provider OAuth protocol, token refresh service, provider-neutral statuses, and concurrency-safe refresh persistence.
   - Add generic action-request/audit tables and strict email contracts.

2. **Outlook and Gmail read path**
   - Add configuration validation, OAuth clients, account discovery, connection routes, and disconnect semantics for both providers.
   - Register both connectors and implement folder/label listing, search, message/thread retrieval, and attachment metadata with bounded pagination.
   - Add attachment-byte retrieval as a separately governed action.

3. **Draft path**
   - Implement provider clients for create/get/update draft and normalized structured composition.
   - Add send-as validation, exact payload hashing, approval previews, and redacted action auditing.

4. **Sending path**
   - Implement send-draft first, because it gives the user and service a reviewable provider object before delivery.
   - Add direct send using the same create-review-approve execution service internally.
   - Add one-time execution, `unknown` reconciliation, no blind retry, recipient/body/attachment limits, and explicit approval.

5. **Agent and dashboard**
   - Generalize MCP connection discovery and add read tools plus `request_email_action`, action-status, and execute-approved-action tools.
   - Keep read output and executable action input as separate data paths.
   - Add both connections, draft previews, exact send approval, and unified audit entries to the existing workspace.

6. **Release gates**
   - Complete both real-provider acceptance flows, including one verified delivery per provider.
   - Complete Google restricted-scope verification/security-assessment preparation and Microsoft publisher/tenant-consent documentation before public production use.
   - Update deployment, secret rotation, consent revocation, data deletion, incident, and ambiguous-send runbooks.

This order includes sending in the committed scope while preventing the highest-risk feature from bypassing the connection, policy, approval, audit, and live-verification layers it depends on.
