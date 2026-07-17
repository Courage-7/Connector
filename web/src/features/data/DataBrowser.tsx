import {
  Check,
  Database,
  EyeOff,
  Filter,
  LoaderCircle,
  LockKeyhole,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Table2,
} from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { connectorApi } from "../../api/client";
import type {
  AgentPolicy,
  ProviderConnection,
  TableDescription,
  TableQueryResponse,
  TableSummary,
} from "../../api/types";

type DataBrowserProps = { connection: ProviderConnection | null };

const defaultPolicy = (connectionId: string): AgentPolicy => ({
  connection_id: connectionId,
  approval_mode: "always",
  max_rows: 25,
  allowed_schemas: ["public"],
  masked_columns: {},
});

export function DataBrowser({ connection }: DataBrowserProps) {
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [selected, setSelected] = useState<TableSummary | null>(null);
  const [description, setDescription] = useState<TableDescription | null>(null);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [policy, setPolicy] = useState<AgentPolicy | null>(null);
  const [preview, setPreview] = useState<TableQueryResponse | null>(null);
  const [search, setSearch] = useState("");
  const [privacyMode, setPrivacyMode] = useState(true);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingDescription, setLoadingDescription] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  useEffect(() => {
    if (!connection || connection.status !== "active") return;
    let cancelled = false;
    Promise.all([connectorApi.tables(connection.id), connectorApi.policy(connection.id)])
      .then(([nextTables, nextPolicy]) => {
        if (cancelled) return;
        setTables(nextTables);
        setPolicy(nextPolicy);
        const preferred =
          nextTables.find(
            (table) => table.schema_name === "public" && table.table_name === "Requests",
          ) ??
          nextTables.find((table) => table.schema_name === "public") ??
          nextTables[0] ??
          null;
        setSelected(preferred);
        setLoadingDescription(preferred !== null);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "The table catalog could not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalog(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connection]);

  useEffect(() => {
    if (!connection || !selected) return;
    let cancelled = false;
    connectorApi
      .describeTable(connection.id, selected.schema_name, selected.table_name)
      .then((nextDescription) => {
        if (cancelled) return;
        setDescription(nextDescription);
        setSelectedColumns(nextDescription.columns.slice(0, 50).map((column) => column.name));
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Column metadata could not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingDescription(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connection, selected]);

  const filteredTables = useMemo(() => {
    if (!deferredSearch) return tables;
    return tables.filter((table) =>
      `${table.schema_name}.${table.table_name}`.toLowerCase().includes(deferredSearch),
    );
  }, [deferredSearch, tables]);

  function toggleColumn(column: string) {
    setPreview(null);
    setSelectedColumns((current) =>
      current.includes(column)
        ? current.filter((item) => item !== column)
        : [...current, column],
    );
  }

  function chooseTable(table: TableSummary) {
    setSelected(table);
    setDescription(null);
    setSelectedColumns([]);
    setPreview(null);
    setLoadingDescription(true);
    setError(null);
  }

  async function runPreview() {
    if (!connection || !selected || !policy || selectedColumns.length === 0) return;
    setRunning(true);
    setError(null);
    try {
      const nextPolicy = {
        approval_mode: policy.approval_mode,
        max_rows: policy.max_rows,
        allowed_schemas: policy.allowed_schemas,
        masked_columns: policy.masked_columns,
      };
      const [, result] = await Promise.all([
        connectorApi.updatePolicy(connection.id, nextPolicy),
        connectorApi.query(connection.id, {
          schema_name: selected.schema_name,
          table_name: selected.table_name,
          columns: selectedColumns,
          filters: [],
          order: [],
          limit: policy.max_rows,
        }),
      ]);
      setPreview(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The approved query could not run.");
    } finally {
      setRunning(false);
    }
  }

  if (!connection || connection.status !== "active") {
    return (
      <section className="empty-workspace">
        <Database aria-hidden="true" size={30} strokeWidth={1.5} />
        <h1>Connect a Supabase project</h1>
        <p>Authorize an account and select a project before browsing its read-only catalog.</p>
      </section>
    );
  }

  return (
    <div className="data-browser">
      <aside className="table-rail" aria-label="Available tables">
        <div className="table-search-row">
          <label className="search-field">
            <Search aria-hidden="true" size={16} strokeWidth={1.8} />
            <span className="sr-only">Search tables</span>
            <input
              type="search"
              value={search}
              placeholder="Search tables"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <button className="icon-button bordered" type="button" title="Filter tables">
            <Filter aria-hidden="true" size={16} strokeWidth={1.8} />
            <span className="sr-only">Filter tables</span>
          </button>
        </div>
        <div className="table-list" aria-busy={loadingCatalog}>
          {filteredTables.map((table) => {
            const isSelected =
              selected?.schema_name === table.schema_name &&
              selected?.table_name === table.table_name;
            return (
              <button
                className={`table-list-item${isSelected ? " is-active" : ""}`}
                key={`${table.schema_name}.${table.table_name}`}
                type="button"
                onClick={() => chooseTable(table)}
              >
                <Table2 aria-hidden="true" size={16} strokeWidth={1.7} />
                <span>
                  <strong>{table.table_name}</strong>
                  <small>{table.schema_name}</small>
                </span>
              </button>
            );
          })}
          {loadingCatalog ? (
            <div className="rail-loading"><LoaderCircle className="spin" size={18} /> Loading catalog</div>
          ) : null}
          {!loadingCatalog && filteredTables.length === 0 ? (
            <p className="rail-empty-copy">No readable tables match this search.</p>
          ) : null}
        </div>
      </aside>

      <section className="table-workspace" aria-labelledby="selected-table-title">
        <header className="table-workspace-header">
          <div>
            <h1 id="selected-table-title">{selected?.table_name ?? "Select a table"}</h1>
            {selected ? <p>Schema: <strong>{selected.schema_name}</strong></p> : null}
          </div>
          <button
            className="text-action"
            type="button"
            disabled={!selected || loadingDescription}
            onClick={() => selected && chooseTable({ ...selected })}
          >
            <RefreshCw aria-hidden="true" size={15} />
            Refresh
          </button>
        </header>

        {error ? <div className="inline-error" role="alert">{error}</div> : null}

        <section className="metadata-section" aria-labelledby="columns-title">
          <div className="section-heading-line">
            <h2 id="columns-title">Columns ({description?.columns.length ?? 0})</h2>
            {loadingDescription ? <LoaderCircle className="spin" aria-hidden="true" size={17} /> : null}
          </div>
          <div className="metadata-table-wrap">
            <table className="metadata-table">
              <thead>
                <tr>
                  <th>Column name</th>
                  <th>Data type</th>
                  <th>Nullable</th>
                  <th>Position</th>
                </tr>
              </thead>
              <tbody>
                {description?.columns.map((column) => (
                  <tr key={column.name}>
                    <td><strong>{column.name}</strong></td>
                    <td>{column.data_type}</td>
                    <td>{column.nullable ? "Yes" : "No"}</td>
                    <td>{column.ordinal_position}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="preview-section" aria-labelledby="preview-title">
          <div className="section-heading-line">
            <h2 id="preview-title">Preview rows ({preview?.returned ?? 0})</h2>
            <span>{preview ? `Showing ${preview.returned} of at most ${preview.limit}` : "Run an approved query to preview rows"}</span>
          </div>
          <div className="preview-table-wrap">
            {preview && preview.data.length > 0 ? (
              <table className="preview-table">
                <thead>
                  <tr>{selectedColumns.map((column) => <th key={column}>{column}</th>)}</tr>
                </thead>
                <tbody>
                  {preview.data.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {selectedColumns.map((column) => (
                        <td key={column} title={privacyMode ? "Value masked" : String(row[column] ?? "")}>
                          {formatCell(row[column], privacyMode)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="preview-empty">
                <EyeOff aria-hidden="true" size={23} strokeWidth={1.5} />
                <p>No row values loaded. Privacy masking is on by default.</p>
              </div>
            )}
          </div>
        </section>
      </section>

      <aside className="agent-inspector" aria-label="Agent access controls">
        <h2>Agent access</h2>
        <div className="inspector-rule">
          <LockKeyhole aria-hidden="true" size={18} strokeWidth={1.7} />
          <div><strong>Read only</strong><span>The agent can only run SELECT queries.</span></div>
        </div>
        <label className="inspector-rule selectable">
          <ShieldCheck aria-hidden="true" size={18} strokeWidth={1.7} />
          <div><strong>Approval required</strong><span>Queries wait for a dashboard decision.</span></div>
          <input
            type="checkbox"
            checked={(policy?.approval_mode ?? "always") === "always"}
            onChange={(event) =>
              setPolicy((current) => ({
                ...(current ?? defaultPolicy(connection.id)),
                approval_mode: event.target.checked ? "always" : "never",
              }))
            }
          />
        </label>

        <label className="field-label inspector-field">
          Row limit
          <span>Maximum rows returned per query.</span>
          <input
            type="number"
            min={1}
            max={100}
            value={policy?.max_rows ?? 25}
            onChange={(event) => {
              const nextValue = Math.max(1, Math.min(100, Number(event.target.value) || 1));
              setPolicy((current) => ({
                ...(current ?? defaultPolicy(connection.id)),
                max_rows: nextValue,
              }));
            }}
          />
        </label>

        <div className="selected-columns">
          <div className="inspector-section-heading">
            <strong>Selected columns</strong>
            <span>{selectedColumns.length} selected</span>
          </div>
          {description?.columns.map((column) => (
            <label className="column-checkbox" key={column.name}>
              <input
                type="checkbox"
                checked={selectedColumns.includes(column.name)}
                onChange={() => toggleColumn(column.name)}
              />
              <span className="custom-checkbox"><Check aria-hidden="true" size={12} /></span>
              <span>{column.name}</span>
            </label>
          ))}
        </div>

        <label className="privacy-toggle">
          <input
            type="checkbox"
            checked={privacyMode}
            onChange={(event) => setPrivacyMode(event.target.checked)}
          />
          Mask row values
        </label>

        <button
          className="primary-action full-width run-query"
          type="button"
          disabled={running || selectedColumns.length === 0 || !selected}
          onClick={() => void runPreview()}
        >
          {running ? (
            <LoaderCircle className="spin" aria-hidden="true" size={17} />
          ) : (
            <Play aria-hidden="true" size={16} fill="currentColor" />
          )}
          Run approved query
        </button>
      </aside>
    </div>
  );
}

function formatCell(value: unknown, privacyMode: boolean): string {
  if (value === null || value === undefined) return "n/a";
  if (privacyMode) return "••••••";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
