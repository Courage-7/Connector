import {
  CheckCircle2,
  Database,
  ExternalLink,
  LoaderCircle,
  Mail,
  Plus,
} from "lucide-react";
import { useEffect, useState } from "react";

import { connectorApi } from "../../api/client";
import type { ProviderConnection, SupabaseProject } from "../../api/types";

type ConnectionsPanelProps = {
  connections: ProviderConnection[];
  onConnect: (provider: "supabase" | "outlook" | "gmail") => void;
  onChanged: () => void;
};

export function ConnectionsPanel({
  connections,
  onConnect,
  onChanged,
}: ConnectionsPanelProps) {
  const pending = connections.find(
    (connection) => connection.connector === "supabase" && connection.status === "pending_project",
  );
  const [projects, setProjects] = useState<SupabaseProject[]>([]);
  const [selectedRef, setSelectedRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pending) return;
    let cancelled = false;
    connectorApi
      .projects(pending.id)
      .then((items) => {
        if (cancelled) return;
        setProjects(items);
        setSelectedRef(items[0]?.ref ?? "");
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Projects could not load.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [pending]);

  async function selectProject() {
    if (!pending || !selectedRef) return;
    setBusy(true);
    setError(null);
    try {
      await connectorApi.selectProject(pending.id, selectedRef);
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The project could not be selected.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="content-page" aria-labelledby="connections-title">
      <div className="page-heading-row">
        <div>
          <h1 id="connections-title">Connections</h1>
          <p>Authorize data sources without exposing provider credentials to your users or agent.</p>
        </div>
        <div className="connection-actions">
          <button className="secondary-action" type="button" onClick={() => onConnect("outlook")}>
            <Mail aria-hidden="true" size={16} />
            Outlook
          </button>
          <button className="secondary-action" type="button" onClick={() => onConnect("gmail")}>
            <Mail aria-hidden="true" size={16} />
            Gmail
          </button>
          <button className="primary-action" type="button" onClick={() => onConnect("supabase")}>
            <Plus aria-hidden="true" size={17} />
            Supabase
          </button>
        </div>
      </div>

      {error ? <div className="inline-error" role="alert">{error}</div> : null}

      {pending ? (
        <div className="pending-selection">
          <div className="section-icon" aria-hidden="true">
            <Database size={20} strokeWidth={1.7} />
          </div>
          <div className="pending-copy">
            <h2>Select a Supabase project</h2>
            <p>The account is authorized. Choose the project this workspace may browse.</p>
          </div>
          <label className="field-label">
            Project
            <select value={selectedRef} onChange={(event) => setSelectedRef(event.target.value)}>
              {projects.map((project) => (
                <option key={project.ref} value={project.ref}>
                  {project.name} · {project.region ?? "region unavailable"}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary-action"
            type="button"
            disabled={busy || !selectedRef}
            onClick={() => void selectProject()}
          >
            {busy ? <LoaderCircle className="spin" aria-hidden="true" size={17} /> : null}
            Use this project
          </button>
        </div>
      ) : null}

      <div className="connections-list">
        {connections.map((connection) => (
          <article className="connection-row" key={connection.id}>
            <div className="connection-provider-icon" aria-hidden="true">
              {connection.connector === "supabase" ? (
                <Database size={22} strokeWidth={1.7} />
              ) : (
                <Mail size={22} strokeWidth={1.7} />
              )}
            </div>
            <div className="connection-row-copy">
              <h2>{connection.name ?? `${providerLabel(connection.connector)} account`}</h2>
              <p>
                {providerLabel(connection.connector)} · {connection.external_ref ?? "Selection required"}
              </p>
            </div>
            <span className={`status-label ${connection.status}`}>
              {connection.status === "active" ? (
                <CheckCircle2 aria-hidden="true" size={15} />
              ) : null}
              {connection.status === "active"
                ? "Active"
                : connection.status === "reauthorization_required"
                  ? "Reconnect required"
                  : "Pending project"}
            </span>
            <ExternalLink aria-hidden="true" className="row-trailing-icon" size={17} />
          </article>
        ))}
        {connections.length === 0 ? (
          <div className="empty-state">
            <Database aria-hidden="true" size={26} strokeWidth={1.5} />
            <h2>No connections yet</h2>
            <p>Connect a database or mailbox to make it available through governed agent tools.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function providerLabel(provider: string): string {
  if (provider === "outlook") return "Outlook";
  if (provider === "gmail") return "Gmail";
  return "Supabase";
}
