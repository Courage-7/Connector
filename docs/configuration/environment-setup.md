# Environment setup

Connector Service deliberately uses one configuration contract:

- `.env.example` is the committed template;
- `.env` is the ignored local file;
- production injects the same variable names from its secret manager.

There is no `.env.consumer`, `.env.live`, connector-prefixed duplicate, project API key, or admin
token. Never commit a populated `.env`.

## 1. Create the local file

From the repository root:

```powershell
Copy-Item .env.example .env
```

The application validates configuration on startup. Misspelled legacy variables are ignored, so use
the names in `.env.example` exactly.

## 2. Create the connector metadata database

This database stores only connector-owned metadata:

- user/provider connection records;
- one-time OAuth state;
- encrypted provider access and refresh tokens.

It does not copy customer email, calendar events, Teams messages, or Supabase table rows. Use a
dedicated Supabase project so this control-plane data is isolated from projects users connect later.

1. Sign in to the [Supabase Dashboard](https://supabase.com/dashboard).
2. Create or open the dedicated connector-service project.
3. Select **Connect** at the top of the project page.
4. Choose a PostgreSQL connection method reachable from the FastAPI host. For local networks without
   IPv6, use the session pooler shown by Supabase. For deployment, use the connection option suitable
   for that platform.
5. Copy the URI, replace the password placeholder with the project's database password, and set:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

If the copied scheme is `postgresql://`, it is also accepted. If the password contains `@`, `:`, `/`,
`?`, `#`, or `%`, URL-encode the password before inserting it. Do not use a Supabase publishable,
secret, anon, or service-role API key here; `DATABASE_URL` is a PostgreSQL connection string.

For local development:

```dotenv
AUTO_CREATE_SCHEMA=true
```

For production:

```dotenv
AUTO_CREATE_SCHEMA=false
```

Then run schema migrations during deployment:

```powershell
python -m alembic upgrade head
```

## 3. Create development Bearer authentication

Generate a random value:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output into:

```dotenv
ENVIRONMENT=development
AUTH_MODE=static
SERVICE_BEARER_TOKEN=PASTE_THE_GENERATED_VALUE
DEVELOPMENT_SUBJECT=local-development-user
```

`SERVICE_BEARER_TOKEN` protects user connection and tool endpoints while keeping development simple.
It is not generated through an API and does not change on restart. In Swagger, select **Authorize**,
paste only the value, and close the dialog. Swagger supplies `Authorization: Bearer` itself.

Static Bearer authentication is intentionally rejected when `ENVIRONMENT=production`.

## 4. Create the provider-token encryption key

Generate a Fernet key:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set:

```dotenv
TOKEN_ENCRYPTION_KEY=PASTE_THE_GENERATED_VALUE
```

Keep this value stable. Changing or losing it makes existing encrypted provider connections
unreadable. In production, store it in the deployment platform's secret manager and include it in
the backup/recovery plan. Do not reuse `SERVICE_BEARER_TOKEN` as the encryption key.

## 5. Register the Supabase provider OAuth application

This OAuth app lets a customer authorize access to Supabase organizations/projects they control. It
is separate from the dedicated database in step 2.

1. In the Supabase Dashboard, open the organization that owns the integration.
2. Open **Organization Settings** > **OAuth Apps**.
3. Create or edit the OAuth application.
4. Set its local callback URL exactly to:

   `http://localhost:1080/v1/oauth/supabase/callback`

   `127.0.0.1`, port `8000`, port `1081`, `/v1/connections/...`, and a trailing slash are different
   redirect URIs and will fail validation.
5. Configure the OAuth app scopes:

   - `projects:read`
   - `database:read`

6. Copy the application ID into `SUPABASE_OAUTH_CLIENT_ID`.
7. Generate a client secret and copy the complete value immediately into
   `SUPABASE_OAUTH_CLIENT_SECRET`. The masked value shown later cannot be reconstructed.

```dotenv
SUPABASE_OAUTH_CLIENT_ID=YOUR_APPLICATION_ID
SUPABASE_OAUTH_CLIENT_SECRET=YOUR_COMPLETE_CLIENT_SECRET
SUPABASE_OAUTH_REDIRECT_URI=http://localhost:1080/v1/oauth/supabase/callback
SUPABASE_MANAGEMENT_API_URL=https://api.supabase.com
```

Supabase scopes are configured on the OAuth app; this service does not send a deprecated `scope`
query parameter. It uses authorization-code OAuth with PKCE, stores state once, expires state after
10 minutes by default, refreshes access tokens, and revokes the refresh token on disconnect. See the
official [Supabase OAuth integration guide](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration)
and [Management API reference](https://supabase.com/docs/reference/api/introduction).

## 6. Start and verify the current phase

Install and run:

```powershell
python -m pip install -e ".[dev]"
python -m uvicorn connector_service.main:app --reload --port 1080
```

Open <http://127.0.0.1:1080/docs>. Confirm:

1. `GET /health` returns `status: ok`.
2. `GET /v1/providers` lists Supabase, Google Workspace, and Microsoft 365.
3. Only Supabase has `status: available`; the other providers are deliberately marked `planned`.
4. After Swagger authorization, `GET /v1/auth/me` returns `local-development-user`.
5. `POST /v1/connections/supabase/authorize` returns an `authorization_url` on
   `https://api.supabase.com`.
6. Open that URL in the browser, sign in, approve access, and let Supabase return to port 1080.

The authorize operation returns a URL instead of forcing a cross-origin redirect from Swagger's
background `fetch` request. A real consuming web application should call the endpoint from its
backend, return the URL to its frontend, then assign that URL to `window.location`.

## 7. Configure production Supabase Auth

In production, the client application should sign in its users and pass the user's access token to this
service. Connector Service validates the token and uses its `sub` claim as the owner boundary.

1. Open the Supabase project that provides customer authentication.
2. Copy its **Project URL** from project settings. Do not copy an anon/publishable key.
3. Under Auth signing keys, use an asymmetric RSA or elliptic-curve signing key. The service verifies
   `RS256` and `ES256` through Supabase's public JWKS endpoint. A project still using only the legacy
   symmetric JWT secret will not expose a usable public key.
4. Configure:

```dotenv
ENVIRONMENT=production
AUTH_MODE=supabase_jwt
SUPABASE_AUTH_URL=https://YOUR_AUTH_PROJECT_REF.supabase.co
SUPABASE_AUTH_AUDIENCE=authenticated
JWKS_CACHE_SECONDS=300
AUTO_CREATE_SCHEMA=false
```

The service obtains public signing keys from
`SUPABASE_AUTH_URL/auth/v1/.well-known/jwks.json`; no Supabase JWT secret belongs in this service.
Refer to Supabase's [JWT signing-key guide](https://supabase.com/docs/guides/auth/signing-keys).

## 8. Prepare Google Workspace for the next phase

These values may be added now, but Google endpoints remain marked planned until that slice is built.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select/create a project.
2. Enable **Gmail API** and **Google Calendar API** under **APIs & Services**.
3. Configure the OAuth consent screen/Google Auth Platform branding, audience, contact details, and
   test users. Choose External when independent customer Google accounts must connect.
4. Create an OAuth client with application type **Web application**.
5. Add this exact authorized redirect URI:

   `http://localhost:1080/v1/oauth/google_workspace/callback`

6. Copy the client ID and client secret into:

```dotenv
GMAIL_OAUTH_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GMAIL_OAUTH_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET
GMAIL_OAUTH_REDIRECT_URI=http://localhost:1080/v1/oauth/google_workspace/callback
```

The planned service requests `openid`, `email`, Gmail read-only, Gmail compose, and Calendar events
access. Gmail scopes are sensitive/restricted; an external production app may need Google
verification and, depending on data handling, an independent security assessment. Keep the app in
testing and list test users during development. Google's redirect URI must match exactly, including
scheme, host, port, path, case, and trailing slash. See Google's
[web-server OAuth guide](https://developers.google.com/identity/protocols/oauth2/web-server) and
[Gmail server-side authorization guide](https://developers.google.com/workspace/gmail/api/auth/web-server).

## 9. Prepare Microsoft 365 for the next phase

These values may be added now, but Microsoft endpoints remain marked planned until that slice is
built.

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com/).
2. Go to **Entra ID** > **App registrations** > **New registration**.
3. For a multi-customer SaaS, choose accounts in any organizational directory. If personal
   Outlook.com accounts are also required, choose the option that also includes personal Microsoft
   accounts; Teams capabilities will still require a work/school tenant.
4. Under **Authentication**, add platform **Web** and this redirect URI:

   `http://localhost:1080/v1/oauth/microsoft_365/callback`

5. Copy **Application (client) ID** into `OUTLOOK_OAUTH_CLIENT_ID`.
6. Under **Certificates & secrets**, create a client secret for development and copy its **Value**
   immediately—not the secret ID. Microsoft shows the value only once.
7. Under **API permissions**, add Microsoft Graph delegated permissions appropriate to the selected
   tool set:

   - `openid`, `profile`, `email`, `offline_access`, `User.Read`
   - `Mail.ReadWrite`, `Mail.Send`
   - `Calendars.ReadWrite`
   - `Team.ReadBasic.All`, `Channel.ReadBasic.All`
   - `ChannelMessage.Read.All`, `ChannelMessage.Send`

   Some Teams permissions require tenant administrator consent. A tenant may also restrict user
   consent, so plan an admin-consent onboarding step for B2B customers.

```dotenv
OUTLOOK_OAUTH_CLIENT_ID=YOUR_APPLICATION_CLIENT_ID
OUTLOOK_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET_VALUE
OUTLOOK_OAUTH_REDIRECT_URI=http://localhost:1080/v1/oauth/microsoft_365/callback
OUTLOOK_OAUTH_AUTHORITY=https://login.microsoftonline.com/common/oauth2/v2.0
OUTLOOK_GRAPH_API_URL=https://graph.microsoft.com/v1.0
```

For production, Microsoft recommends certificates or federated credentials over long-lived client
secrets; the current next-phase implementation plan starts with the confidential web-client secret
flow for simplicity. See Microsoft's [app registration guide](https://learn.microsoft.com/en-us/graph/auth-register-app-v2),
[redirect URI guide](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri),
and [Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

## 10. Common startup errors

`development and production require a PostgreSQL DATABASE_URL`

- The old `sqlite://`/in-memory configuration is still present. Replace it with the dedicated
  Supabase PostgreSQL connection string.

`SERVICE_BEARER_TOKEN is required when AUTH_MODE=static`

- Generate the token in step 3 and place it in `.env` without quotes or a `Bearer ` prefix.

`TOKEN_ENCRYPTION_KEY` validation error

- Generate a Fernet key in step 4. A random phrase is not a valid Fernet key.

Supabase shows `redirect_uri` or callback mismatch

- Align both the dashboard OAuth app and `.env` to
  `http://localhost:1080/v1/oauth/supabase/callback` exactly, then restart Uvicorn.

Swagger returns 401

- Select **Authorize**, paste `SERVICE_BEARER_TOKEN`, and retry. Do not use the Supabase OAuth client
  secret, database password, access token, anon key, or a generated project API key.

Production JWTs all return 401

- Confirm `SUPABASE_AUTH_URL`, issuer, audience, token expiry, and that the Auth project has an
  asymmetric signing key visible at its JWKS endpoint.
