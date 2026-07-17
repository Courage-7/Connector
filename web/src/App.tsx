import { useEffect, useState } from "react";

import { ApiError, connectorApi } from "./api/client";
import type { DashboardSession, ProviderConnection } from "./api/types";
import {
  AppShell,
  type DashboardPage,
  FullPageLoading,
  SessionExpired,
} from "./components/AppShell";
import { AgentAccess } from "./features/agent/AgentAccess";
import { AuditLog } from "./features/audit/AuditLog";
import { ConnectionsPanel } from "./features/connections/ConnectionsPanel";
import { DataBrowser } from "./features/data/DataBrowser";

export function App() {
  const [session, setSession] = useState<DashboardSession | null>(null);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [page, setPage] = useState<DashboardPage>("data");
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadWorkspace() {
      try {
        const [nextSession, nextConnections] = await Promise.all([
          connectorApi.session(),
          connectorApi.connections(),
        ]);
        if (cancelled) return;
        setSession(nextSession);
        setConnections(nextConnections);
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          setUnauthorized(true);
        } else {
          setError(caught instanceof Error ? caught.message : "The workspace could not load.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeConnection =
    connections.find(
      (connection) => connection.connector === "supabase" && connection.status === "active",
    ) ?? connections.find((connection) => connection.connector === "supabase") ?? null;

  async function refreshConnections() {
    const nextConnections = await connectorApi.connections();
    setConnections(nextConnections);
  }

  async function connectProvider(provider: "supabase" | "outlook" | "gmail") {
    setError(null);
    try {
      const authorization = await connectorApi.startAuthorization(provider);
      window.location.assign(authorization.authorization_url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authorization could not start.");
    }
  }

  async function signOut() {
    try {
      await connectorApi.signOut();
    } finally {
      setUnauthorized(true);
      setSession(null);
    }
  }

  if (loading) return <FullPageLoading />;
  if (unauthorized || !session) return <SessionExpired />;

  return (
    <AppShell
      page={page}
      session={session}
      connection={activeConnection}
      onPageChange={setPage}
      onConnect={() => void connectProvider("supabase")}
      onSignOut={() => void signOut()}
    >
      {error ? <div className="global-error" role="alert">{error}</div> : null}
      {page === "connections" ? (
        <ConnectionsPanel
          connections={connections}
          onConnect={(provider) => void connectProvider(provider)}
          onChanged={() => void refreshConnections()}
        />
      ) : null}
      {page === "data" ? (
        <DataBrowser key={activeConnection?.id ?? "no-connection"} connection={activeConnection} />
      ) : null}
      {page === "agent" ? <AgentAccess connection={activeConnection} /> : null}
      {page === "audit" ? <AuditLog /> : null}
    </AppShell>
  );
}
