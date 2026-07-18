# Provider module architecture

Connector keeps provider-specific code isolated while reusing security, OAuth primitives,
persistence, policy enforcement, auditing, HTTP composition, and MCP transport.

```text
src/connector_service/
├── providers/
│   ├── catalog.py            # typed module registry and capabilities
│   ├── factory.py            # deployment composition root
│   ├── gmail/
│   │   ├── client.py         # Gmail API implementation
│   │   └── module.py         # Gmail registration
│   ├── outlook/
│   │   ├── client.py         # Microsoft Graph implementation
│   │   └── module.py         # Outlook registration
│   └── supabase/
│       ├── module.py         # Supabase registration
│       ├── management.py     # OAuth and Management API
│       ├── catalog.py        # safe schema discovery and querying
│       ├── connector.py      # policy-enforced action adapter
│       └── schemas.py        # Supabase-specific contracts
├── connectors/
│   ├── oauth.py              # shared PKCE/token primitives
│   └── email/                # shared mailbox protocols and schemas
├── core/                     # provider-neutral contracts, registry, security
├── db/                       # shared connection wallet and audit persistence
└── api/                      # routes composed from enabled capabilities
```

## Selecting modules

Set `CONNECTOR_ENABLED_PROVIDERS` to a comma-separated list. Disabled modules are not constructed,
their provider-specific routes are not mounted, and their action connectors are not registered.

```dotenv
# Database-only project
CONNECTOR_ENABLED_PROVIDERS=supabase

# Mail automation project
CONNECTOR_ENABLED_PROVIDERS=gmail,outlook

# Gmail-only project
CONNECTOR_ENABLED_PROVIDERS=gmail

# Complete Connector deployment
CONNECTOR_ENABLED_PROVIDERS=supabase,outlook,gmail
```

`GET /v1/providers` returns the enabled modules, configuration readiness, and declared
capabilities for the authenticated consuming project.

## Adding another provider

1. Create `providers/<name>/client.py` for provider API behavior.
2. Create `providers/<name>/module.py` returning a `ProviderModule` with explicit capabilities.
3. Add the builder and supported slug to the composition root and configuration allowlist.
4. Reuse shared contracts where the provider implements an existing capability; introduce a new
   provider-neutral contract when it adds a genuinely new capability.
5. Add isolation, combination, provider-client, and credential-backed live acceptance tests.

Importing a provider implementation never registers it automatically. Registration happens only
in `providers/factory.py`, which keeps deployments predictable and prevents accidental tool
exposure.
