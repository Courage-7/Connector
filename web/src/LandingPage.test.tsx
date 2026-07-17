import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LandingPage } from "./landing/LandingPage";

describe("Connector landing page", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("communicates the real connector availability without overstating support", () => {
    render(<LandingPage />);

    expect(screen.getByRole("heading", { name: "Connect your tools. Keep control." })).toBeVisible();
    expect(screen.getByLabelText("Supabase, Live now")).toBeVisible();
    expect(screen.getByLabelText("Gmail, Next")).toBeVisible();
    expect(screen.getByLabelText("Salesforce, Planned")).toBeVisible();
    expect(screen.getAllByRole("link", { name: /open workspace/i })).toHaveLength(3);
    expect(document.querySelector(".switchboard-core")).not.toBeInTheDocument();
  });

  it("marks the section currently crossing the navigation focus zone", () => {
    let callback: IntersectionObserverCallback = () => undefined;
    class TestIntersectionObserver {
      readonly root = null;
      readonly rootMargin = "";
      readonly thresholds = [];

      constructor(nextCallback: IntersectionObserverCallback) {
        callback = nextCallback;
      }

      disconnect() {}
      observe() {}
      takeRecords() { return []; }
      unobserve() {}
    }
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);
    render(<LandingPage />);

    const security = document.getElementById("security");
    expect(security).not.toBeNull();
    act(() => {
      callback(
        [
          {
            isIntersecting: true,
            intersectionRatio: 0.8,
            target: security!,
          } as unknown as IntersectionObserverEntry,
        ],
        {} as IntersectionObserver,
      );
    });

    const primaryNavigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(primaryNavigation).getByRole("link", { name: "Security" })).toHaveAttribute(
      "aria-current",
      "location",
    );
  });

  it("records an approval decision and can reset the interactive governance example", () => {
    render(<LandingPage />);

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByText("Approved and added to the audit trail")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Deny" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset demo" }));
    expect(screen.getByRole("button", { name: "Deny" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  });
});
