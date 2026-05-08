import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const redirectedToCanonicalHost =
  typeof window !== "undefined" && window.location.hostname === "localhost";

if (redirectedToCanonicalHost) {
  const nextUrl = new URL(window.location.href);
  nextUrl.hostname = "127.0.0.1";
  window.location.replace(nextUrl.toString());
}

if (!redirectedToCanonicalHost) {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>,
  );
}
