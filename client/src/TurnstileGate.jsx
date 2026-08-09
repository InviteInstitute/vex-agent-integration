// Full-screen Cloudflare Turnstile challenge, shown when the server's
// TurnstileGateMiddleware 403s a /v1/* call (see App.jsx's postJson/getJson,
// which dispatch the 'turnstile:required' event this listens for). Ported from
// lm-dashboard/frontend/src/TurnstileGate.jsx, using fetch instead of axios
// since this client has no axios dependency.
import { useEffect, useRef, useState } from "react";

const TURNSTILE_SITE_KEY = "0x4AAAAAAD9y1rcwgwx5PODV";

const apiBase = import.meta.env.VITE_API_BASE_URL?.trim() || "http://127.0.0.1:8000/v1";

export default function TurnstileGate() {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(false);
  const elRef = useRef(null);
  const widgetId = useRef(null);

  useEffect(() => {
    const onRequired = () => setOpen(true);
    window.addEventListener("turnstile:required", onRequired);
    return () => window.removeEventListener("turnstile:required", onRequired);
  }, []);

  useEffect(() => {
    if (!open || widgetId.current) return;

    const doRender = () => {
      if (widgetId.current || !window.turnstile || !elRef.current) return;
      widgetId.current = window.turnstile.render(elRef.current, {
        sitekey: TURNSTILE_SITE_KEY,
        action: "turnstile-agent-v1",
        callback: async (token) => {
          try {
            const response = await fetch(`${apiBase}/turnstile/verify/`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({ token }),
            });
            if (!response.ok) throw new Error("verify failed");
            window.location.reload();
          } catch {
            setError(true);
            window.turnstile.reset(widgetId.current);
          }
        },
        "error-callback": () => setError(true),
      });
    };

    // The Cloudflare api.js is loaded async+defer, so window.turnstile often
    // isn't ready yet when the gate first opens on a fresh page load. Poll
    // until it is, then render; give up after ~15s and show the error rather
    // than hanging on "Verifying...".
    if (window.turnstile) {
      doRender();
      return;
    }
    let waited = 0;
    const iv = setInterval(() => {
      if (window.turnstile) {
        clearInterval(iv);
        doRender();
      } else if ((waited += 150) >= 15000) {
        clearInterval(iv);
        setError(true);
      }
    }, 150);
    return () => clearInterval(iv);
  }, [open]);

  if (!open) return null;
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgb(134, 190, 241)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        fontFamily:
          '"Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
        color: "#213246",
      }}
    >
      <p>Verifying you're not a bot&hellip;</p>
      <div ref={elRef} />
      {error && <p style={{ color: "#ef4444" }}>Verification failed. Please try again.</p>}
    </div>
  );
}
