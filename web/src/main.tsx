import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/manrope/wght.css";
import "@fontsource-variable/outfit/wght.css";

import { App } from "./App";
import { LandingPage } from "./landing/LandingPage";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Connector root element was not found.");

const isWorkspaceRoute = window.location.pathname.startsWith("/app");

createRoot(root).render(
  <StrictMode>
    {isWorkspaceRoute ? <App /> : <LandingPage />}
  </StrictMode>,
);
