import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

const stored = (() => {
  try {
    return JSON.parse(localStorage.getItem("wfs.ui") ?? "{}") as {
      theme?: "dark" | "light";
      density?: "comfortable" | "compact";
    };
  } catch {
    return {};
  }
})();

document.documentElement.dataset.theme = stored.theme ?? "dark";
document.documentElement.dataset.density = stored.density ?? "comfortable";
document.documentElement.classList.toggle("dark", (stored.theme ?? "dark") === "dark");

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
