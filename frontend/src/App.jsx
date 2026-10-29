import React, { useEffect, useState } from "react";
import { api, auth } from "./api.js";
import { Overview, Transactions, TracePage, Alerts, LedgerPage, PublicVerify } from "./pages.jsx";

const TABS = [
  ["overview", "Overview", "officer"], ["transactions", "Transactions", "officer"], ["trace", "Trace a token", "officer"],
  ["alerts", "Alerts", "auditor"], ["ledger", "Ledger & audit", "officer"],
];
const RANK = { officer: 1, auditor: 2, admin: 3 };

function Login({ onDone }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("staff");
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { const r = await api.login(u, p); auth.set(r.access_token); onDone(r.role); }
    catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <main className="login">
      <section className="login-intro">
        <h1>Follow every rupee from release to recipient.</h1>
        <p>Each payment carries its own cryptographic token. Anyone can check that a token is genuine and where it went. Nobody can quietly edit the record.</p>
        <div className="seg" role="tablist">
          <button role="tab" aria-selected={mode === "staff"} onClick={() => setMode("staff")}>Staff sign in</button>
          <button role="tab" aria-selected={mode === "public"} onClick={() => setMode("public")}>Check a token (public)</button>
        </div>
      </section>
      <section className="login-card">
        {mode === "staff" ? (
          <form onSubmit={submit}>
            <label>Username<input value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" required /></label>
            <label>Password<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
            {err && <p className="err" role="alert">{err}</p>}
            <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        ) : <PublicVerify />}
      </section>
    </main>
  );
}

export default function App() {
  const [role, setRole] = useState(null), [tab, setTab] = useState("overview"), [focus, setFocus] = useState("");
  const [ready, setReady] = useState(!auth.token);
  useEffect(() => { if (auth.token) api.me().then((m) => setRole(m.role)).catch(() => auth.set(null)).finally(() => setReady(true)); }, []);
  if (!ready) return null;
  if (!role) return <Login onDone={setRole} />;
  const go = (t, token = "") => { setFocus(token); setTab(t); };
  return (
    <div className="shell">
      <header className="top">
        <strong className="brand">BlockTrace</strong>
        <nav aria-label="Main">
          {TABS.filter(([, , min]) => RANK[role] >= RANK[min]).map(([id, label]) => (
            <button key={id} aria-current={tab === id ? "page" : undefined} onClick={() => go(id)}>{label}</button>
          ))}
        </nav>
        <span className="who">{role}</span>
        <button className="btn ghost" onClick={() => { auth.set(null); setRole(null); }}>Sign out</button>
      </header>
      <main className="page">
        {tab === "overview" && <Overview go={go} />}
        {tab === "transactions" && <Transactions role={role} go={go} />}
        {tab === "trace" && <TracePage initial={focus} />}
        {tab === "alerts" && <Alerts go={go} />}
        {tab === "ledger" && <LedgerPage role={role} />}
      </main>
    </div>
  );
}
