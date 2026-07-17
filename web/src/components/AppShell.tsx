import {
  Bot,
  ChevronDown,
  CircleUserRound,
  Database,
  FileClock,
  Link2,
  LogOut,
  Plus,
} from "lucide-react";
import type { ReactNode } from "react";

import type { DashboardSession, ProviderConnection } from "../api/types";
import { BrandLockup } from "./BrandLockup";

export type DashboardPage = "connections" | "data" | "agent" | "audit";

type AppShellProps = {
  children: ReactNode;
  page: DashboardPage;
  session: DashboardSession;
  connection: ProviderConnection | null;
  onPageChange: (page: DashboardPage) => void;
  onConnect: () => void;
  onSignOut: () => void;
};

const navigation = [
  { id: "connections", label: "Connections", icon: Link2 },
  { id: "data", label: "Data browser", icon: Database },
  { id: "agent", label: "Agent access", icon: Bot },
  { id: "audit", label: "Audit", icon: FileClock },
] satisfies Array<{ id: DashboardPage; label: string; icon: typeof Link2 }>;

export function AppShell({
  children,
  page,
  session,
  connection,
  onPageChange,
  onConnect,
  onSignOut,
}: AppShellProps) {
  const initial = session.project.name.slice(0, 1).toUpperCase();
  const activeNavigation = navigation.find((item) => item.id === page) ?? navigation[1];
  const ActivePageIcon = activeNavigation.icon;

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="brand-button"
          type="button"
          onClick={() => onPageChange("data")}
        >
          <BrandLockup compact inverse />
        </button>
        <div className="topbar-page" aria-label={`Current page: ${activeNavigation.label}`}>
          <ActivePageIcon aria-hidden="true" size={16} strokeWidth={1.7} />
          <span>Workspace</span>
          <strong>{activeNavigation.label}</strong>
        </div>
        <div className="user-menu" aria-label="Current workspace">
          <span className="user-avatar" aria-hidden="true">
            {initial}
          </span>
          <span className="user-workspace">{session.project.name}</span>
          <ChevronDown aria-hidden="true" size={15} strokeWidth={1.8} />
          <button className="icon-button" type="button" onClick={onSignOut} title="Sign out">
            <LogOut aria-hidden="true" size={17} strokeWidth={1.8} />
            <span className="sr-only">Sign out</span>
          </button>
        </div>
      </header>

      <aside className="primary-rail">
        <nav className="primary-nav" aria-label="Dashboard">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item${page === id ? " is-active" : ""}`}
              key={id}
              type="button"
              onClick={() => onPageChange(id)}
            >
              <Icon aria-hidden="true" size={19} strokeWidth={1.7} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="rail-connect-block">
          <button className="secondary-action full-width" type="button" onClick={onConnect}>
            <Plus aria-hidden="true" size={17} />
            Connect Supabase
          </button>
          {connection ? (
            <div className="connection-summary">
              <Database aria-hidden="true" size={23} strokeWidth={1.7} />
              <div className="connection-copy">
                <strong>{connection.name ?? "Select a project"}</strong>
                <span>Supabase</span>
              </div>
              <span className={`status-dot ${connection.status}`}>
                {connection.status === "active" ? "Active" : "Pending"}
              </span>
            </div>
          ) : (
            <p className="rail-empty-copy">No Supabase connection yet.</p>
          )}
        </div>
      </aside>

      <main className="app-main">{children}</main>

      <nav className="mobile-nav" aria-label="Dashboard mobile navigation">
        {navigation.map(({ id, label, icon: Icon }) => (
          <button
            className={page === id ? "is-active" : ""}
            key={id}
            type="button"
            onClick={() => onPageChange(id)}
          >
            <Icon aria-hidden="true" size={18} strokeWidth={1.7} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}

export function SessionExpired() {
  return (
    <main className="session-screen">
      <div className="session-mark" aria-hidden="true">
        <CircleUserRound size={28} strokeWidth={1.6} />
      </div>
      <h1>Dashboard session required</h1>
      <p>
        Open a fresh one-time dashboard link from your trusted application backend. Tenant API
        keys are never entered into this page.
      </p>
    </main>
  );
}

export function FullPageLoading() {
  return (
    <main className="session-screen" aria-busy="true">
      <div className="loading-spinner" />
      <h1>Opening your workspace</h1>
      <p>Validating the secure browser session.</p>
    </main>
  );
}
