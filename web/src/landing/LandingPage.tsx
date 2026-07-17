import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  Cloud,
  Code2,
  Database,
  FileCheck2,
  Mail,
  MessageSquareMore,
  RotateCcw,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  siDropbox,
  siGithub,
  siGmail,
  siGooglecalendar,
  siGoogledrive,
  siHubspot,
  siJira,
  siLinear,
  siNotion,
  siPostgresql,
  siSnowflake,
  siSupabase,
  type SimpleIcon,
} from "simple-icons";
import type { LucideIcon } from "lucide-react";

import { BrandLockup } from "../components/BrandLockup";
import { ProviderLogo } from "./ProviderLogo";
import { TypewriterHeadline } from "./TypewriterHeadline";
import "./landing.css";

type Availability = "live" | "next" | "planned";

type Provider = {
  name: string;
  icon?: SimpleIcon;
  fallback?: LucideIcon;
  color: string;
  availability: Availability;
};

const providers = {
  supabase: { name: "Supabase", icon: siSupabase, color: "#3ECF8E", availability: "live" },
  postgres: { name: "PostgreSQL", icon: siPostgresql, color: "#79A7D3", availability: "planned" },
  snowflake: { name: "Snowflake", icon: siSnowflake, color: "#6CCCF1", availability: "planned" },
  gmail: { name: "Gmail", icon: siGmail, color: "#EA4335", availability: "next" },
  outlook: { name: "Outlook", fallback: Mail, color: "#4A9BFF", availability: "next" },
  slack: { name: "Slack", fallback: MessageSquareMore, color: "#E6A9DD", availability: "planned" },
  teams: { name: "Microsoft Teams", fallback: UsersRound, color: "#8C91E8", availability: "planned" },
  calendar: { name: "Google Calendar", icon: siGooglecalendar, color: "#74A8FF", availability: "next" },
  notion: { name: "Notion", icon: siNotion, color: "#F4F6FA", availability: "planned" },
  drive: { name: "Google Drive", icon: siGoogledrive, color: "#F6C85F", availability: "planned" },
  onedrive: { name: "OneDrive", fallback: Cloud, color: "#58A9F8", availability: "planned" },
  dropbox: { name: "Dropbox", icon: siDropbox, color: "#6F9CFF", availability: "planned" },
  github: { name: "GitHub", icon: siGithub, color: "#F4F6FA", availability: "next" },
  linear: { name: "Linear", icon: siLinear, color: "#B4B9FF", availability: "planned" },
  jira: { name: "Jira", icon: siJira, color: "#6C9EFF", availability: "planned" },
  hubspot: { name: "HubSpot", icon: siHubspot, color: "#FF8B63", availability: "planned" },
  salesforce: { name: "Salesforce", fallback: Cloud, color: "#66C7EE", availability: "planned" },
} satisfies Record<string, Provider>;

const providerLanes = [
  { name: "Data", icon: Database, providers: [providers.supabase, providers.postgres, providers.snowflake] },
  {
    name: "Communication",
    icon: Mail,
    providers: [providers.gmail, providers.outlook, providers.slack, providers.teams, providers.calendar],
  },
  {
    name: "Knowledge and files",
    icon: FileCheck2,
    providers: [providers.notion, providers.drive, providers.onedrive, providers.dropbox],
  },
  {
    name: "Work and developer",
    icon: Code2,
    providers: [providers.github, providers.linear, providers.jira, providers.hubspot, providers.salesforce],
  },
] as const;

const workflow = [
  { title: "Connect", body: "Authorize a provider without exposing its credentials to the agent." },
  { title: "Scope", body: "Choose the project, tables, fields, and row limits that are allowed." },
  { title: "Request", body: "The agent submits a structured action against that bounded scope." },
  { title: "Approve", body: "A person reviews the action before anything reaches the provider." },
  { title: "Audit", body: "The outcome is recorded with actor, scope, status, and returned rows." },
] as const;

const availabilityCopy: Record<Availability, string> = {
  live: "Live now",
  next: "Next",
  planned: "Planned",
};

const navigationItems = [
  { id: "integrations", label: "Integrations" },
  { id: "security", label: "Security" },
  { id: "how-it-works", label: "How it works" },
] as const;

function useActiveSection() {
  const [activeSection, setActiveSection] = useState("");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return undefined;

    const sections = navigationItems
      .map(({ id }) => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio);
        if (visible[0]) setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-24% 0px -56%", threshold: [0.1, 0.3, 0.55] },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  return activeSection;
}

function ProviderChip({ provider }: { provider: Provider }) {
  return (
    <div
      className={`provider-chip provider-${provider.availability}`}
      tabIndex={0}
      aria-label={`${provider.name}, ${availabilityCopy[provider.availability]}`}
    >
      <span className="provider-chip-icon">
        <ProviderLogo icon={provider.icon} fallback={provider.fallback} color={provider.color} size={21} />
      </span>
      <span className="provider-chip-copy">
        <strong>{provider.name}</strong>
        <span>{availabilityCopy[provider.availability]}</span>
      </span>
    </div>
  );
}

function ProviderLane({ lane }: { lane: (typeof providerLanes)[number] }) {
  const LaneIcon = lane.icon;
  return (
    <div className="provider-lane">
      <div className="provider-lane-label">
        <LaneIcon aria-hidden="true" size={18} strokeWidth={1.7} />
        <span>{lane.name}</span>
      </div>
      <div className="provider-lane-track">
        <div className="provider-lane-line" aria-hidden="true" />
        {lane.providers.map((provider) => <ProviderChip key={provider.name} provider={provider} />)}
      </div>
    </div>
  );
}

function OrbitNode({ provider, className }: { provider: Provider; className: string }) {
  return (
    <span className={`orbit-node-position ${className}`}>
      <span className="orbit-node" title={provider.name}>
        <ProviderLogo icon={provider.icon} fallback={provider.fallback} color={provider.color} size={23} />
      </span>
    </span>
  );
}

function ConnectorConstellation() {
  return (
    <div className="connector-constellation" aria-hidden="true">
      <div className="constellation-haze" />
      <div className="orbit orbit-outer">
        <OrbitNode provider={providers.gmail} className="orbit-at-top" />
        <OrbitNode provider={providers.outlook} className="orbit-at-right" />
        <OrbitNode provider={providers.calendar} className="orbit-at-bottom" />
        <OrbitNode provider={providers.slack} className="orbit-at-left" />
      </div>
      <div className="orbit orbit-inner">
        <OrbitNode provider={providers.supabase} className="orbit-at-top" />
        <OrbitNode provider={providers.notion} className="orbit-at-right" />
        <OrbitNode provider={providers.github} className="orbit-at-bottom" />
        <OrbitNode provider={providers.drive} className="orbit-at-left" />
      </div>
      <div className="constellation-core">
        <BrandLockup compact inverse />
        <span>Governed access</span>
      </div>
      <span className="route-pulse pulse-one" />
      <span className="route-pulse pulse-two" />
      <span className="route-pulse pulse-three" />
    </div>
  );
}

function GovernanceDemo() {
  const [decision, setDecision] = useState<"pending" | "approved" | "denied">("pending");

  return (
    <div className={`governance-demo is-${decision}`}>
      <div className="governance-demo-header">
        <div>
          <span>Example request</span>
          <strong>Read public.Requests</strong>
        </div>
        <span className="demo-state">{decision}</span>
      </div>
      <dl className="request-summary">
        <div><dt>Columns</dt><dd>id, status</dd></div>
        <div><dt>Row limit</dt><dd>5</dd></div>
        <div><dt>Access</dt><dd>Read only</dd></div>
      </dl>
      {decision === "pending" ? (
        <div className="governance-actions">
          <button type="button" className="demo-action secondary" onClick={() => setDecision("denied")}>Deny</button>
          <button type="button" className="demo-action primary" onClick={() => setDecision("approved")}>
            <Check aria-hidden="true" size={16} /> Approve
          </button>
        </div>
      ) : (
        <div className="governance-result" aria-live="polite">
          <div>
            <ShieldCheck aria-hidden="true" size={19} />
            <span>{decision === "approved" ? "Approved and added to the audit trail" : "Denied and added to the audit trail"}</span>
          </div>
          <button type="button" onClick={() => setDecision("pending")}>
            <RotateCcw aria-hidden="true" size={15} /> Reset demo
          </button>
        </div>
      )}
    </div>
  );
}

export function LandingPage() {
  const activeSection = useActiveSection();

  return (
    <div className="landing-page" id="top">
      <header className="site-header">
        <div className="site-header-shell">
          <a className="site-brand" href="#top" aria-label="Connector home">
            <BrandLockup inverse />
          </a>
          <nav className="site-navigation" aria-label="Primary navigation">
            {navigationItems.map((item) => (
              <a
                className={activeSection === item.id ? "is-active" : undefined}
                href={`#${item.id}`}
                aria-current={activeSection === item.id ? "location" : undefined}
                key={item.id}
              >
                {item.label}
              </a>
            ))}
          </nav>
          <a className="header-workspace-action" href="/app/">
            <span>Open workspace</span>
            <ArrowUpRight aria-hidden="true" size={17} strokeWidth={1.8} />
          </a>
        </div>
      </header>

      <main>
        <section className="landing-hero" aria-labelledby="hero-heading">
          <div className="hero-copy" id="hero-heading">
            <TypewriterHeadline />
            <p>A secure control plane for data, email, calendars, and the agents that use them.</p>
            <div className="hero-actions">
              <a className="landing-action primary" href="/app/">
                Open workspace <ArrowRight aria-hidden="true" size={18} />
              </a>
              <a className="landing-action secondary" href="#integrations">Explore connectors</a>
            </div>
          </div>
          <ConnectorConstellation />
        </section>

        <section className="integrations-section landing-section" id="integrations" aria-labelledby="integrations-title">
          <div className="section-copy-stack">
            <h2 id="integrations-title">Your tools, one governed path.</h2>
            <p>Bring data, communication, files, and work systems into the same controlled agent workflow.</p>
          </div>
          <div className="availability-legend" aria-label="Connector availability">
            <span className="legend-live">Live now</span>
            <span className="legend-next">Next</span>
            <span className="legend-planned">Planned</span>
          </div>
          <div className="provider-switchboard">
            {providerLanes.map((lane) => <ProviderLane key={lane.name} lane={lane} />)}
          </div>
          <p className="section-closing-line">One policy layer. More of your stack.</p>
        </section>

        <section className="workflow-section landing-section" id="how-it-works" aria-labelledby="workflow-title">
          <div className="section-copy-stack">
            <h2 id="workflow-title">From permission to proof.</h2>
            <p>Every connector follows one governed path, so access stays understandable as your toolset grows.</p>
          </div>
          <div className="workflow-path">
            {workflow.map((item) => (
              <article className="workflow-stage" key={item.title}>
                <span className="workflow-node" aria-hidden="true" />
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="security-section landing-section" id="security" aria-labelledby="security-title">
          <div className="security-copy">
            <h2 id="security-title">Control survives the connection.</h2>
            <p>Permissions, approvals, row limits, and audit records stay between every tool and every agent.</p>
            <div className="security-principles">
              <span><Database aria-hidden="true" size={18} /> Read only by default</span>
              <span><ShieldCheck aria-hidden="true" size={18} /> Approval before execution</span>
              <span><FileCheck2 aria-hidden="true" size={18} /> Audit every outcome</span>
            </div>
          </div>
          <GovernanceDemo />
        </section>

        <section className="landing-cta" aria-labelledby="cta-title">
          <Bot aria-hidden="true" size={34} strokeWidth={1.5} />
          <h2 id="cta-title">Bring your tools into one governed workspace.</h2>
          <p>Connect Supabase now. Add more connectors as they become available.</p>
          <a className="landing-action primary" href="/app/">Open workspace <ArrowRight aria-hidden="true" size={18} /></a>
        </section>
      </main>

      <footer className="landing-footer">
        <BrandLockup compact inverse />
        <p>Secure connectors for the tools your agent needs.</p>
        <div>
          <a href="#integrations">Integrations</a>
          <a href="#security">Security</a>
          <a href="#how-it-works">How it works</a>
        </div>
      </footer>
    </div>
  );
}
