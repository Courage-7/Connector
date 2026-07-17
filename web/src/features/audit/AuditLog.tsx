import { CheckCircle2, FileClock, Mail, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { connectorApi } from "../../api/client";
import type { EmailAudit, QueryAudit } from "../../api/types";

export function AuditLog() {
  const [records, setRecords] = useState<QueryAudit[]>([]);
  const [emailRecords, setEmailRecords] = useState<EmailAudit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([connectorApi.audit(), connectorApi.emailAudit()])
      .then(([queryItems, emailItems]) => {
        if (!cancelled) {
          setRecords(queryItems);
          setEmailRecords(emailItems);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Audit history could not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="content-page" aria-labelledby="audit-title">
      <div className="page-heading-row">
        <div>
          <h1 id="audit-title">Audit</h1>
          <p>Review database and mailbox activity without storing query values or message bodies.</p>
        </div>
      </div>
      {error ? <div className="inline-error" role="alert">{error}</div> : null}

      <div className="audit-table-wrap" aria-busy={loading}>
        <table className="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Actor</th>
              <th>Relation</th>
              <th>Columns</th>
              <th>Limit</th>
              <th>Returned</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{new Date(record.created_at).toLocaleString()}</td>
                <td>{record.actor_type}</td>
                <td><strong>{record.schema_name}.{record.table_name}</strong></td>
                <td>{record.columns.join(", ")}</td>
                <td>{record.row_limit}</td>
                <td>{record.returned_rows ?? "n/a"}</td>
                <td>
                  <span className={`audit-status ${record.status}`}>
                    {record.status === "succeeded" ? (
                      <CheckCircle2 aria-hidden="true" size={14} />
                    ) : (
                      <XCircle aria-hidden="true" size={14} />
                    )}
                    {record.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && records.length === 0 && emailRecords.length === 0 ? (
          <div className="empty-state">
            <FileClock aria-hidden="true" size={27} strokeWidth={1.5} />
            <h2>No audited activity yet</h2>
            <p>Database queries and governed mailbox actions will appear here.</p>
          </div>
        ) : null}
      </div>
      {emailRecords.length > 0 ? (
        <div className="audit-table-wrap email-audit-wrap">
          <div className="section-heading-line">
            <h2><Mail aria-hidden="true" size={16} /> Mailbox activity</h2>
          </div>
          <table className="audit-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Provider</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Recipients</th>
                <th>Returned</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {emailRecords.map((record) => (
                <tr key={record.id}>
                  <td>{new Date(record.created_at).toLocaleString()}</td>
                  <td><strong>{record.provider === "outlook" ? "Outlook" : "Gmail"}</strong></td>
                  <td>{record.actor_type}</td>
                  <td>{record.action.replaceAll("_", " ")}</td>
                  <td>{record.recipient_count}</td>
                  <td>{record.returned_items ?? "n/a"}</td>
                  <td>
                    <span className={`audit-status ${record.status}`}>
                      {record.status === "succeeded" ? (
                        <CheckCircle2 aria-hidden="true" size={14} />
                      ) : (
                        <XCircle aria-hidden="true" size={14} />
                      )}
                      {record.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
