export type DashboardSession = {
  project: { id: string; name: string };
  expires_at: string;
};

export type ProviderConnection = {
  id: string;
  connector: string;
  status: "pending_project" | "active" | "reauthorization_required" | "disconnected";
  external_ref: string | null;
  name: string | null;
  created_at: string;
};

export type EmailProvider = "outlook" | "gmail";

export type EmailCompose = {
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  text_body: string | null;
  html_body: string | null;
  reply_to_message_id: string | null;
};

export type EmailSendRequest = {
  id: string;
  connection_id: string;
  provider: EmailProvider;
  status: string;
  message: EmailCompose;
  requested_at: string;
  expires_at: string;
  decided_at: string | null;
  decision_note: string | null;
};

export type EmailAudit = {
  id: string;
  connection_id: string;
  send_request_id: string | null;
  provider: EmailProvider;
  action: string;
  actor_type: string;
  recipient_count: number;
  attachment_count: number;
  status: string;
  returned_items: number | null;
  error_code: string | null;
  created_at: string;
  completed_at: string | null;
};

export type SupabaseProject = {
  ref: string;
  name: string;
  organization_slug: string | null;
  region: string | null;
  status: string | null;
};

export type TableSummary = {
  schema_name: string;
  table_name: string;
  kind: "table" | "view";
};

export type ColumnSummary = {
  name: string;
  data_type: string;
  nullable: boolean;
  ordinal_position: number;
};

export type TableDescription = {
  schema_name: string;
  table_name: string;
  columns: ColumnSummary[];
};

export type EqualityFilter = { column: string; value: unknown };
export type TableOrder = { column: string; direction: "asc" | "desc" };

export type TableQuery = {
  schema_name: string;
  table_name: string;
  columns: string[];
  filters?: EqualityFilter[];
  order?: TableOrder[];
  limit: number;
};

export type TableQueryResponse = {
  data: Record<string, unknown>[];
  returned: number;
  limit: number;
};

export type AgentPolicy = {
  connection_id: string;
  approval_mode: "always" | "never";
  max_rows: number;
  allowed_schemas: string[];
  masked_columns: Record<string, string[]>;
};

export type AgentQueryRequest = {
  id: string;
  connection_id: string;
  status: "pending" | "approved" | "denied" | "executed";
  query: TableQuery;
  requested_at: string;
  decided_at: string | null;
  decision_note: string | null;
};

export type QueryAudit = {
  id: string;
  connection_id: string;
  query_request_id: string | null;
  actor_type: string;
  schema_name: string;
  table_name: string;
  columns: string[];
  filters: Array<{ column: string; value_present: boolean }>;
  order_by: TableOrder[];
  row_limit: number;
  status: string;
  returned_rows: number | null;
  error_code: string | null;
  created_at: string;
  completed_at: string | null;
};
