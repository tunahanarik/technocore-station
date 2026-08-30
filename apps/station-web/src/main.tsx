import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";
import { applyTheme, detectSystemTheme } from "./theme";

// Follow the operating system before the first paint of app content.
applyTheme(detectSystemTheme());

const container = document.getElementById("root");
if (container === null) {
  throw new Error("root container missing from index.html");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
