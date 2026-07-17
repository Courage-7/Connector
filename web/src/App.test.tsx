import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const jsonResponse = (payload: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );

describe("Connector dashboard", () => {
  beforeEach(() => {
    Object.defineProperty(document, "cookie", {
      configurable: true,
      value: "connector_dashboard_csrf=test-csrf",
      writable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the authenticated project and live catalog shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/v1/dashboard/session") {
          return jsonResponse({
            project: { id: "project-1", name: "AI Agent Workspace" },
            expires_at: "2026-07-17T08:00:00Z",
          });
        }
        if (path === "/v1/connections/supabase") {
          return jsonResponse([
            {
              id: "connection-1",
              connector: "supabase",
              status: "active",
              external_ref: "abcdefghijklmnopqrst",
              name: "4TH-IR - SquadZero",
              created_at: "2026-07-16T23:41:31Z",
            },
          ]);
        }
        if (path === "/v1/connections/outlook" || path === "/v1/connections/gmail") {
          return jsonResponse([]);
        }
        if (path.endsWith("/tables")) {
          return jsonResponse([
            { schema_name: "public", table_name: "Requests", kind: "table" },
            { schema_name: "public", table_name: "Metadata", kind: "table" },
          ]);
        }
        if (path.endsWith("/agent-policy")) {
          return jsonResponse({
            connection_id: "connection-1",
            approval_mode: "always",
            max_rows: 25,
            allowed_schemas: ["public"],
            masked_columns: {},
          });
        }
        if (path.endsWith("/query") && init?.method === "POST") {
          const headers = new Headers(init.headers);
          expect(headers.get("X-CSRF-Token")).toBe("test-csrf");
          return jsonResponse({
            data: [{ id: "row-1", status: "open" }],
            returned: 1,
            limit: 25,
          });
        }
        if (path.endsWith("/tables/public/Requests")) {
          return jsonResponse({
            schema_name: "public",
            table_name: "Requests",
            columns: [
              { name: "id", data_type: "uuid", nullable: false, ordinal_position: 1 },
              { name: "status", data_type: "text", nullable: false, ordinal_position: 2 },
            ],
          });
        }
        throw new Error(`Unexpected request: ${path}`);
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Requests" }, { timeout: 5_000 }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Current page: Data browser")).toBeVisible();
    expect(screen.getByText("4TH-IR - SquadZero")).toBeInTheDocument();
    expect((await screen.findAllByText("status")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Run approved query" })).toBeEnabled();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/v1/connections/supabase/connection-1/tables/public/Requests",
      expect.any(Object),
    ));
    fireEvent.click(screen.getByRole("button", { name: "Run approved query" }));
    expect(await screen.findAllByText("••••••")).toHaveLength(2);
  }, 10_000);

  it("does not render a tenant-key form when the session is absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse(
          { error: { code: "authentication_failed", message: "Valid authentication is required." } },
          401,
        ),
      ),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Dashboard session required" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument();
  });
});
