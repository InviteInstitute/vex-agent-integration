import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import TurnstileGate from "./TurnstileGate";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <TurnstileGate />
    <App />
  </React.StrictMode>,
);
