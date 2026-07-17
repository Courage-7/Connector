import { Bot, Check, Clock3, Mail, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";

import { connectorApi } from "../../api/client";
import type {
  AgentQueryRequest,
  EmailSendRequest,
  ProviderConnection,
} from "../../api/types";

type AgentAccessProps = { connection: ProviderConnection | null };

export function AgentAccess({ connection }: AgentAccessProps) {
  const [requests, setRequests] = useState<AgentQueryRequest[]>([]);
  const [emailRequests, setEmailRequests] = useState<EmailSendRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      connectorApi.queryRequests("pending"),
      connectorApi.emailSendRequests("pending"),
    ])
      .then(([queryItems, emailItems]) => {
        if (!cancelled) {
          setRequests(queryItems);
          setEmailRequests(emailItems);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Approval requests could not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function decide(requestId: string, decision: "approve" | "deny") {
    setError(null);
    try {
      if (decision === "approve") await connectorApi.approveQuery(requestId);
      else await connectorApi.denyQuery(requestId);
      setRequests((current) => current.filter((item) => item.id !== requestId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The decision could not be saved.");
    }
  }

  async function decideEmail(requestId: string, decision: "approve" | "deny") {
    setError(null);
    try {
      if (decision === "approve") await connectorApi.approveEmailSend(requestId);
      else await connectorApi.denyEmailSend(requestId);
      setEmailRequests((current) => current.filter((item) => item.id !== requestId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The email decision could not be saved.");
    }
  }

  return (
    <section className="content-page" aria-labelledby="agent-title">
      <div className="page-heading-row">
        <div>
          <h1 id="agent-title">Agent access</h1>
          <p>Review database queries and exact outbound email content before agent execution.</p>
        </div>
        <div className="security-summary">
          <ShieldCheck aria-hidden="true" size={18} />
          Approval required
        </div>
      </div>

      {connection ? (
        <div className="context-strip">
          <Bot aria-hidden="true" size={18} />
          <span>Agent queries are scoped to</span>
          <strong>{connection.name}</strong>
        </div>
      ) : null}
      {error ? <div className="inline-error" role="alert">{error}</div> : null}

      <div className="approval-list" aria-busy={loading}>
        {requests.map((item) => (
          <article className="approval-row" key={item.id}>
            <div className="approval-icon" aria-hidden="true">
              <Clock3 size={19} strokeWidth={1.7} />
            </div>
            <div className="approval-copy">
              <h2>{item.query.schema_name}.{item.query.table_name}</h2>
              <p>
                {item.query.columns.length} columns · up to {item.query.limit} rows · requested {" "}
                {new Date(item.requested_at).toLocaleString()}
              </p>
              <div className="column-inline-list">
                {item.query.columns.map((column) => (
                  <code key={column}>{column}</code>
                ))}
              </div>
            </div>
            <div className="approval-actions">
              <button
                className="secondary-action"
                type="button"
                onClick={() => void decide(item.id, "deny")}
              >
                <X aria-hidden="true" size={16} />
                Deny
              </button>
              <button
                className="primary-action"
                type="button"
                onClick={() => void decide(item.id, "approve")}
              >
                <Check aria-hidden="true" size={16} />
                Approve
              </button>
            </div>
          </article>
        ))}
        {emailRequests.map((item) => (
          <article className="approval-row email-approval-row" key={item.id}>
            <div className="approval-icon" aria-hidden="true">
              <Mail size={19} strokeWidth={1.7} />
            </div>
            <div className="approval-copy">
              <h2>{item.provider === "outlook" ? "Outlook" : "Gmail"} send</h2>
              <p>
                To: {item.message.to.join(", ")} · requested {" "}
                {new Date(item.requested_at).toLocaleString()}
              </p>
              {item.message.cc.length > 0 ? <p>Cc: {item.message.cc.join(", ")}</p> : null}
              <strong className="email-approval-subject">{item.message.subject}</strong>
              <pre className="email-approval-body">
                {item.message.text_body ?? item.message.html_body ?? ""}
              </pre>
            </div>
            <div className="approval-actions">
              <button
                className="secondary-action"
                type="button"
                onClick={() => void decideEmail(item.id, "deny")}
              >
                <X aria-hidden="true" size={16} />
                Deny
              </button>
              <button
                className="primary-action"
                type="button"
                onClick={() => void decideEmail(item.id, "approve")}
              >
                <Check aria-hidden="true" size={16} />
                Approve send
              </button>
            </div>
          </article>
        ))}
        {!loading && requests.length === 0 && emailRequests.length === 0 ? (
          <div className="empty-state">
            <ShieldCheck aria-hidden="true" size={27} strokeWidth={1.5} />
            <h2>No pending requests</h2>
            <p>Your linked agent has no database query or email send waiting for approval.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
