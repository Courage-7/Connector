# Environment setup

This guide explains where every Connector Service environment value comes from and how to
configure Supabase, Microsoft Outlook/Calendar/Teams, Google Gmail/Calendar, and the local MCP
adapter.

The examples use `http://localhost:8010` to avoid a collision with the other local development
service on port `8000`. If you choose another port, replace `8010` everywhere: the Uvicorn command,
all three provider callback URLs, `.env`, `.env.consumer`, and the provider dashboards.

## 1. Understand the environment files

| File | Purpose | Commit it? |
| --- | --- | --- |
| `.env.example` | Safe template for the Connector API | Yes |
| `.env` | Real API secrets and provider OAuth credentials | No |
| `.env.consumer.example` | Safe template for the dashboard/MCP client | Yes |
| `.env.consumer` | The one-time project API key used by the dashboard and MCP client | No |
| `.env.live.example` | Optional Supabase live-test template | Yes |
| `.env.live` | Temporary Supabase live-test credentials | No |
| `.env.email.live.example` | Optional Gmail/Outlook live-test template | Yes |
| `.env.email.live` | Temporary Gmail/Outlook refresh tokens | No |

The real files are excluded by `.gitignore`. Never paste a client secret, refresh token, project
API key, Supabase account token, or Fernet key into an `*.example` file.

Create the main file:

```powershell
Copy-Item .env.example .env
```

## 2. Generate the service-owned secrets

These values do not come from Supabase, Microsoft, or Google. Generate them locally and use a
different value for each setting.

Generate two random strings:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use the first output for `CONNECTOR_ADMIN_TOKEN` and the second for
`CONNECTOR_CURSOR_SIGNING_KEY`. Both must contain at least 32 characters.

Generate the credential-encryption key:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use that output for `CONNECTOR_CREDENTIAL_ENCRYPTION_KEY`. It must be a Fernet key, not an
ordinary password. Do not rotate it without a credential migration because existing encrypted
OAuth tokens would become unreadable.

The initial local section should look like this:

```dotenv
CONNECTOR_APP_NAME=Connector
CONNECTOR_ENVIRONMENT=development
CONNECTOR_DATABASE_URL=sqlite:///./connector_service.db
CONNECTOR_ADMIN_TOKEN=<first-random-string>
CONNECTOR_CREDENTIAL_ENCRYPTION_KEY=<fernet-key>
CONNECTOR_CURSOR_SIGNING_KEY=<second-random-string>
CONNECTOR_AUTO_CREATE_SCHEMA=false
CONNECTOR_LOG_LEVEL=INFO
CONNECTOR_ENABLED_PROVIDERS=supabase,outlook,gmail
```

Keep `CONNECTOR_AUTO_CREATE_SCHEMA=false` when using migrations. Create or update the local schema
with:

```powershell
alembic upgrade head
```

`CONNECTOR_ENABLED_PROVIDERS` accepts any comma-separated combination of `supabase`, `outlook`, and
`gmail`. Calendar is included in `outlook` and `gmail`; Microsoft Teams is included in `outlook`.
There are no separate `teams` or `calendar` provider names.

## 3. Create the Supabase OAuth application

These credentials authorize Connector to use the Supabase Management API on behalf of a user.
They are not a Supabase project URL, publishable key, anon key, secret key, or service-role key.

1. Open [Supabase Organization OAuth Apps](https://supabase.com/dashboard/org/_/apps).
2. Select the organization that will own the integration.
3. Select **Add application**.
4. Enter a name such as `Connector local development`.
5. Add this exact redirect URI:

   ```text
   http://localhost:8010/v1/connections/supabase/callback
   ```

6. Select only these Management API scopes:

   - **Projects → Read** (`projects:read`), used to list and select projects.
   - **Database → Read** (`database:read`), used for schema discovery and bounded read-only
     database queries.

7. Create the application.
8. Copy the generated client ID and client secret into `.env`:

   ```dotenv
   CONNECTOR_SUPABASE_OAUTH_CLIENT_ID=<oauth-app-client-id>
   CONNECTOR_SUPABASE_OAUTH_CLIENT_SECRET=<oauth-app-client-secret>
   CONNECTOR_SUPABASE_OAUTH_REDIRECT_URI=http://localhost:8010/v1/connections/supabase/callback
   CONNECTOR_SUPABASE_MANAGEMENT_API_URL=https://api.supabase.com
   ```

Supabase scopes are configured on the OAuth application. Connector intentionally does not send a
`scope` parameter in its authorization URL. If the configured scopes change, disconnect and
reauthorize existing Supabase connections.

Official references:

- [Build a Supabase integration](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration)
- [Supabase OAuth scopes](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration/oauth-scopes)
- [Supabase Management API](https://supabase.com/docs/reference/api/getting-started)

## 4. Create the Microsoft Entra application

One Microsoft Entra application supplies Outlook Mail, Outlook Calendar, and Microsoft Teams. Do
not create three separate clients.

### Register the application

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com/).
2. Go to **Entra ID → App registrations → New registration**.
3. Enter a name such as `Connector local development`.
4. Choose the supported account type:

   - Choose **Accounts in this organizational directory only** for a single Microsoft 365 tenant.
   - Choose **Accounts in any organizational directory** for a multi-tenant business application.

   Teams APIs require a work or school Microsoft 365 account. Personal Microsoft accounts do not
   support the Teams operations used here.

5. Complete the registration.
6. On **Overview**, copy **Application (client) ID**. Do not copy the Object ID or Directory ID into
   `CONNECTOR_OUTLOOK_OAUTH_CLIENT_ID`.

### Add the callback URL

1. Open **Authentication**.
2. Select **Add a platform → Web**.
3. Add this exact redirect URI:

   ```text
   http://localhost:8010/v1/connections/outlook/callback
   ```

4. Save the platform configuration.

### Add Microsoft Graph delegated permissions

Go to **API permissions → Add a permission → Microsoft Graph → Delegated permissions**, then add:

```text
openid
profile
email
offline_access
User.Read
Mail.ReadWrite
Mail.Send
Calendars.ReadWrite
Team.ReadBasic.All
Channel.ReadBasic.All
ChannelMessage.Read.All
ChannelMessage.Send
```

`ChannelMessage.Read.All` requires administrator consent. Select **Grant admin consent for
<tenant>** while signed in as an appropriate tenant administrator. A tenant's own consent policies
can also require administrator approval for additional permissions.

If you do not need Teams message reads, removing `ChannelMessage.Read.All` from the code and app
registration avoids that permission, but the current Teams message-list route will then fail.

### Create the client secret

1. Open **Certificates & secrets → Client secrets**.
2. Select **New client secret**.
3. Add a description and choose an expiry permitted by your organization.
4. Create the secret.
5. Copy the secret **Value immediately**. Microsoft displays it only once.

Use the secret **Value**, not the Secret ID:

```dotenv
CONNECTOR_OUTLOOK_OAUTH_CLIENT_ID=<application-client-id>
CONNECTOR_OUTLOOK_OAUTH_CLIENT_SECRET=<client-secret-value>
CONNECTOR_OUTLOOK_OAUTH_REDIRECT_URI=http://localhost:8010/v1/connections/outlook/callback
CONNECTOR_OUTLOOK_OAUTH_AUTHORITY=https://login.microsoftonline.com/common/oauth2/v2.0
CONNECTOR_OUTLOOK_GRAPH_API_URL=https://graph.microsoft.com/v1.0
```

For a strictly single-tenant deployment, replace `common` with the tenant's Directory ID:

```dotenv
CONNECTOR_OUTLOOK_OAUTH_AUTHORITY=https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0
```

The current service supports a client secret, not a certificate. Record the secret expiry and
rotate it before it expires. After adding Calendar or Teams permissions, disconnect and reconnect
existing Outlook connections so the user can grant the new scopes.

Official references:

- [Register a Microsoft Entra application](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app)
- [Configure a Web redirect URI](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri)
- [Create application credentials](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-credentials)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)

## 5. Create the Google OAuth client

One Google Cloud OAuth client supplies both Gmail and Google Calendar.

### Create or select a Google Cloud project

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project or select the project that will own the integration.
3. Open **APIs & Services → Library**.
4. Enable both APIs:

   - [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)

### Configure the Google Auth Platform

1. Open **Google Auth Platform → Branding**.
2. Configure the application name, support email, and developer contact email.
3. Open **Audience** and choose:

   - **Internal** only when every user belongs to the same Google Workspace organization.
   - **External** for personal Google accounts or multiple organizations.

4. If an External application remains in **Testing**, add every account that will connect under
   **Test users**.
5. Open **Data Access** and declare these scopes:

   ```text
   openid
   email
   https://www.googleapis.com/auth/gmail.readonly
   https://www.googleapis.com/auth/gmail.compose
   https://www.googleapis.com/auth/calendar.events
   ```

   Google may display `email` as `https://www.googleapis.com/auth/userinfo.email`.

### Create the Web client

1. Open **Google Auth Platform → Clients**.
2. Select **Create Client**.
3. Choose **Web application**.
4. Add this exact **Authorized redirect URI**:

   ```text
   http://localhost:8010/v1/connections/gmail/callback
   ```

5. Create the client.
6. Copy the client ID and client secret into `.env`:

   ```dotenv
   CONNECTOR_GMAIL_OAUTH_CLIENT_ID=<web-client-id>
   CONNECTOR_GMAIL_OAUTH_CLIENT_SECRET=<web-client-secret>
   CONNECTOR_GMAIL_OAUTH_REDIRECT_URI=http://localhost:8010/v1/connections/gmail/callback
   CONNECTOR_GMAIL_OAUTH_AUTHORITY=https://accounts.google.com/o/oauth2/v2
   CONNECTOR_GMAIL_TOKEN_URL=https://oauth2.googleapis.com
   CONNECTOR_GMAIL_USERINFO_URL=https://openidconnect.googleapis.com/v1
   CONNECTOR_GMAIL_API_URL=https://gmail.googleapis.com/gmail/v1
   CONNECTOR_GOOGLE_CALENDAR_API_URL=https://www.googleapis.com/calendar/v3
   ```

Keep downloaded OAuth client JSON files outside the repository.

The Gmail read and compose scopes are restricted scopes. An External public production
application generally needs Google's OAuth verification, and a backend that stores or transmits
restricted Gmail data may require a third-party security assessment unless an official exception
applies. An External app in Testing accepts only listed test users; refresh tokens for an app in
Testing can expire after seven days when non-basic scopes are requested.

After adding Calendar or Gmail scopes, disconnect and reconnect existing Gmail connections.

Official references:

- [Google OAuth for Web server applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Enable Google Workspace APIs](https://developers.google.com/workspace/guides/enable-apis)
- [Gmail scopes and classifications](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [OAuth production readiness](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
- [Restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

## 6. Redirect URI matching rules

The redirect URI in a provider console and the corresponding `.env` value must be identical.
Treat these as different URLs:

- `localhost` and `127.0.0.1`
- port `8000` and port `8010`
- paths with and without a trailing slash
- paths whose letter casing differs
- `http` and `https`

For this local setup, use exactly:

```text
Supabase: http://localhost:8010/v1/connections/supabase/callback
Microsoft: http://localhost:8010/v1/connections/outlook/callback
Google: http://localhost:8010/v1/connections/gmail/callback
```

Production callback URLs must use HTTPS. Update both `.env` and every provider console before
deploying.

## 7. Start and validate the API

Install dependencies, apply migrations, and start the service:

```powershell
python -m pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn connector_service.main:app --reload --port 8010
```

Open:

- Swagger UI: `http://127.0.0.1:8010/docs`
- ReDoc: `http://127.0.0.1:8010/redoc`
- Health check: `http://127.0.0.1:8010/health`

Confirm the environment loads without printing secrets:

```powershell
python -c "from connector_service.config import Settings; s=Settings(); print({'app': s.app_name, 'environment': s.environment, 'providers': s.enabled_provider_names, 'supabase_configured': bool(s.supabase_oauth_client_id), 'outlook_configured': bool(s.outlook_oauth_client_id), 'gmail_configured': bool(s.gmail_oauth_client_id)})"
```

If `/docs` shows `Workflow Development Environment`, you opened the other application still using
port `8000`. Use `http://127.0.0.1:8010/docs`.

## 8. Generate `.env.consumer` for MCP and the dashboard

The consumer API key does not come from a provider or MCP vendor. Connector creates it once when
an administrator creates a consuming project.

1. Ensure the API is running on port `8010`.
2. Open `http://127.0.0.1:8010/docs`.
3. Select **Authorize**.
4. Under `AdminToken`, enter the value of `CONNECTOR_ADMIN_TOKEN` from `.env`.
5. Call `POST /v1/admin/projects` with:

   ```json
   {
     "name": "my-agent-workspace"
   }
   ```

6. Copy `api_key` from the response immediately. Connector stores only a salted digest and cannot
   show the plaintext key again.
7. Create the consumer file:

   ```powershell
   Copy-Item .env.consumer.example .env.consumer
   ```

8. Populate it:

   ```dotenv
   CONNECTOR_CONSUMER_API_KEY=<one-time-api-key-from-the-response>
   CONNECTOR_MCP_BASE_URL=http://127.0.0.1:8010
   CONNECTOR_MCP_TIMEOUT_SECONDS=30
   CONNECTOR_MCP_ENABLED_PROVIDERS=supabase,outlook,gmail
   ```

`CONNECTOR_MCP_API_KEY` is accepted as an alias, but the repository examples consistently use
`CONNECTOR_CONSUMER_API_KEY`. The project ID returned by the endpoint is useful for administration,
but the current MCP and dashboard clients authenticate with the API key and do not read a project
ID environment variable.

Test the MCP/dashboard credentials without opening a browser:

```powershell
connector-dashboard --no-open
```

The command should print a one-time dashboard login URL.

## 9. Variables normally left at their defaults

| Variable | Default | Change it when |
| --- | --- | --- |
| `CONNECTOR_PROVIDER_TIMEOUT_SECONDS` | `15` | A provider needs a different request timeout |
| `CONNECTOR_PROVIDER_MAX_RETRIES` | `2` | Adjusting bounded Supabase data-call retries |
| `CONNECTOR_PROVIDER_RETRY_BASE_SECONDS` | `0.25` | Adjusting Supabase retry backoff |
| `CONNECTOR_MAX_PROVIDER_RESPONSE_BYTES` | `5242880` | Applying a stricter response-size ceiling |
| `CONNECTOR_MAX_PAGE_SIZE` | `100` | Applying a stricter global row limit |
| `CONNECTOR_SUPABASE_OAUTH_ATTEMPT_TTL_SECONDS` | `600` | Changing Supabase OAuth state lifetime |
| `CONNECTOR_SUPABASE_OAUTH_TOKEN_SKEW_SECONDS` | `60` | Refreshing Supabase tokens earlier |
| `CONNECTOR_EMAIL_OAUTH_ATTEMPT_TTL_SECONDS` | `600` | Changing Google/Microsoft OAuth state lifetime |
| `CONNECTOR_EMAIL_OAUTH_TOKEN_SKEW_SECONDS` | `60` | Refreshing Google/Microsoft tokens earlier |
| `CONNECTOR_EMAIL_SEND_APPROVAL_TTL_SECONDS` | `1800` | Changing email approval expiry |
| `CONNECTOR_DASHBOARD_LOGIN_TICKET_TTL_SECONDS` | `120` | Changing one-time dashboard ticket lifetime |
| `CONNECTOR_DASHBOARD_SESSION_TTL_SECONDS` | `28800` | Changing dashboard session lifetime |

Keep the provider authority and API URL defaults unless using a documented provider-compatible
endpoint or a tenant-specific Microsoft authority.

## 10. Optional live-test credentials

The deterministic test suite does not require real provider credentials. These files are needed
only when intentionally running tests marked `live`.

### Supabase live test

Copy `.env.live.example` to `.env.live`.

- Create `SUPABASE_MANAGEMENT_ACCESS_TOKEN` under the Supabase Dashboard's account access-token
  settings. This is an account token for a disposable acceptance test, not a project service-role
  key.
- Copy `SUPABASE_PROJECT_REF` from the project URL or project settings.
- Point `SUPABASE_LIVE_SCHEMA`, `SUPABASE_LIVE_TABLE`, and `SUPABASE_LIVE_COLUMNS` at a disposable,
  readable fixture table.

### Outlook and Gmail live tests

Copy `.env.email.live.example` to `.env.email.live`. These tests require refresh tokens belonging
to disposable accounts plus controlled recipient addresses. They can send real mail only when
`CONNECTOR_EMAIL_LIVE_SEND=true`.

Live refresh-token setup is intentionally separate from normal application setup. Obtain tokens
through each provider's authorization-code flow using the same client ID, client secret, redirect
URI, and scopes documented above. Never use a production mailbox for acceptance tests, and never
commit either populated live-test file.

## Troubleshooting

### Provider is listed as not configured

Set both the provider client ID and client secret. Connector rejects a partial pair. Restart
Uvicorn after editing `.env`.

### Microsoft reports an invalid client secret

Verify that `.env` contains the client secret **Value**, not the Secret ID, and that the secret has
not expired.

### Microsoft Teams returns access denied

Confirm the user has a work or school Microsoft 365 account, the tenant administrator granted
consent for `ChannelMessage.Read.All`, and the connection was reauthorized after permissions were
added.

### Google says access is blocked or the test user is unauthorized

For an External app in Testing, add the Google account under **Audience → Test users**. Confirm the
Gmail and Calendar APIs are enabled and the declared scopes match the scopes in this guide.

### OAuth callback reports a redirect mismatch

Compare the complete provider-console URL with `.env`, character for character. Check scheme,
hostname, port, path casing, and trailing slash.

### New scopes do not work on an existing connection

OAuth tokens do not automatically gain newly configured permissions. Disconnect and reconnect the
provider so the consent screen issues a token with the new scopes.
