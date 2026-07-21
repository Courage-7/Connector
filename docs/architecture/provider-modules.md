# Provider architecture

The service is organized by feature and provider, with a small composition root:

```text
src/connector_service/
  bootstrap/                 settings, dependencies, application composition
  identity/                  static Bearer and Supabase JWT authentication
  catalog/                   provider/tool discovery contracts
  connections/               OAuth lifecycle and owner-scoped repository
  infrastructure/
    database/                async SQLAlchemy control-plane persistence
    crypto.py                provider-token encryption
  providers/
    supabase/                current OAuth/API adapter and typed tools
  mcp/                       authenticated adapter over the same application tools
  main.py                    ASGI entry point
```

FastAPI routes do not contain provider business logic. They validate inputs, obtain the authenticated
principal and repository, then call an application service. MCP tools call those same services rather
than proxying REST internally.

## Runtime flow

```text
HTTP/MCP request
  -> Bearer authenticator
  -> Principal(subject, tenant_id)
  -> owner-scoped repository
  -> provider tool service
  -> provider API client
```

The subject is included in every connection lookup. Provider credentials are decrypted only inside
the connection/tool service immediately before a provider call. They are never part of response
models.

## Persistence boundary

The control-plane schema intentionally has two tables:

- `oauth_transactions`: short-lived, one-time OAuth state and encrypted PKCE context;
- `provider_connections`: owner, provider resource selection, status, metadata, expiry, and encrypted
  credentials.

No projects, API-key issuance, grants, dashboard sessions, approval requests, audits, provider data
cache, or frontend state are stored in this phase. Schema changes use Alembic; `create_all` exists only
as a local development convenience.

## Provider catalog

The catalog is product-facing rather than a runtime plugin registry. It advertises the stable provider
suite, capabilities, tool names, read/write classification, implementation state, and configuration
state. This lets an application or agent understand the intended surface while provider slices are
implemented incrementally.

The catalog never claims a planned tool is callable. Executable routes and MCP tools are added only
when a provider's complete vertical slice—OAuth, encrypted persistence, REST, MCP, and tests—is ready.

## Adding the next provider slice

For Google Workspace or Microsoft 365:

1. Create a provider package only when that vertical slice starts; do not keep speculative clients.
2. Define a provider-specific configuration dataclass; do not pass global settings deep into clients.
3. Build authorization, code exchange, refresh, identity, and revocation methods.
4. Reuse `OAuthTransaction`, `ProviderConnection`, `SecretCipher`, and `ConnectionRepository`.
5. Add provider-neutral connection responses under `connections/`.
6. Add typed tool input/output models under the provider package.
7. Implement an application tool service with owner-scoped lookups.
8. Expose the same service through REST and MCP.
9. Change the catalog entries from planned to available only after deterministic tests pass.

Google Workspace is one OAuth connection for Gmail and Google Calendar. Microsoft 365 is one OAuth
connection for Outlook Mail, Outlook Calendar, and Teams. The product should not require separate
connections for capabilities backed by the same provider token.

## MCP choice

Provider-hosted/community MCP servers can be useful for internal automation, but they are not a
replacement for this B2C service. This service must own customer authentication, provider consent,
encrypted token persistence, tenant boundaries, stable contracts, and provider-independent behavior.

Our MCP endpoint is therefore a thin transport over our own typed application services. If a provider
MCP is evaluated later, it belongs behind that application boundary as an adapter and must not become
the source of truth for identity or stored credentials.
