import type {
  AgentPolicy,
  AgentQueryRequest,
  DashboardSession,
  EmailAudit,
  EmailProvider,
  EmailSendRequest,
  ProviderConnection,
  QueryAudit,
  SupabaseProject,
  TableDescription,
  TableQuery,
  TableQueryResponse,
  TableSummary,
} from "./types";

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const item of document.cookie.split(";")) {
    const normalized = item.trim();
    if (normalized.startsWith(prefix)) {
      return decodeURIComponent(normalized.slice(prefix.length));
    }
  }
  return null;
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = readCookie("connector_dashboard_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let payload: ErrorEnvelope = {};
    try {
      payload = (await response.json()) as ErrorEnvelope;
    } catch {
      // The safe fallback below intentionally ignores non-JSON provider details.
    }
    throw new ApiError(
      response.status,
      payload.error?.code ?? "request_failed",
      payload.error?.message ?? "The request could not be completed.",
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const connectorApi = {
  session: () => apiRequest<DashboardSession>("/v1/dashboard/session"),
  connections: async () => {
    const groups = await Promise.all(
      (["supabase", "outlook", "gmail"] as const).map((provider) =>
        apiRequest<ProviderConnection[]>(`/v1/connections/${provider}`),
      ),
    );
    return groups.flat();
  },
  startAuthorization: (provider: "supabase" | EmailProvider) =>
    apiRequest<{ authorization_url: string; expires_at: string }>(
      `/v1/connections/${provider}/authorize`,
      {
        method: "POST",
        body: JSON.stringify({ return_to: "/app/" }),
      },
    ),
  projects: (connectionId: string) =>
    apiRequest<SupabaseProject[]>(
      `/v1/connections/supabase/${encodeURIComponent(connectionId)}/projects`,
    ),
  selectProject: (connectionId: string, projectRef: string) =>
    apiRequest<ProviderConnection>(
      `/v1/connections/supabase/${encodeURIComponent(connectionId)}/select-project`,
      { method: "POST", body: JSON.stringify({ project_ref: projectRef }) },
    ),
  tables: (connectionId: string) =>
    apiRequest<TableSummary[]>(
      `/v1/connections/supabase/${encodeURIComponent(connectionId)}/tables`,
    ),
  describeTable: (connectionId: string, schemaName: string, tableName: string) =>
    apiRequest<TableDescription>(
      `/v1/connections/supabase/${encodeURIComponent(connectionId)}/tables/${encodeURIComponent(schemaName)}/${encodeURIComponent(tableName)}`,
    ),
  query: (connectionId: string, query: TableQuery) =>
    apiRequest<TableQueryResponse>(
      `/v1/connections/supabase/${encodeURIComponent(connectionId)}/query`,
      { method: "POST", body: JSON.stringify(query) },
    ),
  policy: (connectionId: string) =>
    apiRequest<AgentPolicy>(
      `/v1/dashboard/connections/${encodeURIComponent(connectionId)}/agent-policy`,
    ),
  updatePolicy: (connectionId: string, policy: Omit<AgentPolicy, "connection_id">) =>
    apiRequest<AgentPolicy>(
      `/v1/dashboard/connections/${encodeURIComponent(connectionId)}/agent-policy`,
      { method: "PUT", body: JSON.stringify(policy) },
    ),
  queryRequests: (status = "pending") =>
    apiRequest<AgentQueryRequest[]>(
      `/v1/dashboard/query-requests?status=${encodeURIComponent(status)}`,
    ),
  approveQuery: (requestId: string) =>
    apiRequest<AgentQueryRequest>(
      `/v1/dashboard/query-requests/${encodeURIComponent(requestId)}/approve`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  denyQuery: (requestId: string) =>
    apiRequest<AgentQueryRequest>(
      `/v1/dashboard/query-requests/${encodeURIComponent(requestId)}/deny`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  emailSendRequests: (status = "pending") =>
    apiRequest<EmailSendRequest[]>(
      `/v1/dashboard/email-send-requests?status=${encodeURIComponent(status)}`,
    ),
  approveEmailSend: (requestId: string) =>
    apiRequest<EmailSendRequest>(
      `/v1/dashboard/email-send-requests/${encodeURIComponent(requestId)}/approve`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  denyEmailSend: (requestId: string) =>
    apiRequest<EmailSendRequest>(
      `/v1/dashboard/email-send-requests/${encodeURIComponent(requestId)}/deny`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  audit: () => apiRequest<QueryAudit[]>("/v1/dashboard/audit?limit=100"),
  emailAudit: () => apiRequest<EmailAudit[]>("/v1/dashboard/email-audit?limit=100"),
  signOut: () =>
    apiRequest<void>("/v1/dashboard/session", { method: "DELETE" }),
};
