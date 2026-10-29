import React, { useCallback, useEffect, useState } from "react";
import { api, inr, short, when } from "./api.js";
import TraceGraph from "./TraceGraph.jsx";

const useLoad = (fn, deps = []) => {
  const [data, setData] = useState(null), [err, setErr] = useState("");
  const reload = useCallback(() => { setErr(""); fn().then(setData).catch((e) => setErr(e.message)); }, deps); // eslint-disable-line
  useEffect(reload, [reload]);
  return [data, err, reload];
};
const Risk = ({ level }) => <span className={`pill ${level}`}>{level}</span>;
const Err = ({ msg }) => (msg ? <p className="err" role="alert">{msg}</p> : null);
const Loading = () => <p className="muted">Loading…</p>;
const Tok = ({ t, go }) => <button className="link mono" onClick={() => go("trace", t)} title={t}>{short(t)}</button>;

export function Overview({ go }) {
  const [s, err] = useLoad(api.stats);
  const [m] = useLoad(api.mlMetrics);
  if (err) return <Err msg={err} />;
  if (!s) return <Loading />;
  const max = Math.max(1, ...s.daily.map((d) => d.count));
  return (
    <>
      <h2>Overview</h2>
      <div className="tiles">
        <div className="tile"><span>Payments tracked</span><b>{s.transactions.toLocaleString("en-IN")}</b></div>
        <div className="tile"><span>Money followed</span><b>{inr(s.volume)}</b></div>
        <div className="tile"><span>Open alerts</span><b className={s.open_alerts ? "bad" : ""}>{s.open_alerts}</b></div>
        <div className="tile"><span>Frozen tokens</span><b>{s.frozen}</b></div>
        <div className={`tile ${s.ledger.valid ? "good" : "badbg"}`}><span>Ledger integrity</span>
          <b>{s.ledger.valid ? `Intact · ${s.ledger.checked} links` : "Tampering detected"}</b></div>
      </div>
      <div className="cols">
        <section className="card">
          <h3>Last 14 days</h3>
          {s.daily.length === 0 ? <p className="muted">No payments in this period.</p> : (
            <svg viewBox={`0 0 ${s.daily.length * 36} 150`} className="bars" role="img" aria-label="Payments per day, risky share highlighted">
              {s.daily.map((d, i) => {
                const h = (d.count / max) * 110, rh = (d.risky / max) * 110;
                return <g key={d.date} transform={`translate(${i * 36 + 6},0)`}>
                  <rect y={120 - h} width="24" height={h} fill="var(--line)" />
                  <rect y={120 - rh} width="24" height={rh} fill="var(--risk)" />
                  <text x="12" y="138" textAnchor="middle" className="axis">{d.date.slice(5)}</text></g>;
              })}
            </svg>)}
          <p className="muted small">Grey is all payments; red is the part scored medium or high risk.</p>
        </section>
        <section className="card">
          <h3>Accounts with the most risky payments</h3>
          {s.top_risky_accounts.length === 0 ? <p className="muted">Nothing flagged yet.</p> :
            <table><tbody>{s.top_risky_accounts.map((a) => (
              <tr key={a.account}><td>{a.account}</td><td>{a.flagged_txs} flagged</td><td>avg risk {a.avg_risk}</td></tr>))}</tbody></table>}
        </section>
      </div>
      {m && m.accuracy && (
        <section className="card">
          <h3>Fraud model (LSTM) — held-out test results</h3>
          <p className="muted small">Measured on {m.dataset}. Accuracy alone flatters rare-event models, so precision and recall are shown too.</p>
          <div className="tiles compact">
            {[["Accuracy", m.accuracy], ["Precision", m.precision], ["Recall", m.recall], ["F1", m.f1], ["ROC-AUC", m.roc_auc]].map(([k, v]) => (
              <div className="tile" key={k}><span>{k}</span><b>{(v * 100).toFixed(1)}%</b></div>))}
          </div>
        </section>)}
    </>
  );
}

export function Transactions({ role, go }) {
  const [risk, setRisk] = useState("");
  const [rows, err, reload] = useLoad(() => api.txs(`?limit=100${risk ? `&risk=${risk}` : ""}`), [risk]);
  const [accts, , reloadAccts] = useLoad(api.accounts);
  const [f, setF] = useState({ sender: "", receiver: "", amount: "", purpose: "", parent_token: "" });
  const [msg, setMsg] = useState(""), [e2, setE2] = useState("");
  const [na, setNa] = useState({ id: "", name: "", kind: "contractor" });
  const submit = async (ev) => {
    ev.preventDefault(); setMsg(""); setE2("");
    try {
      const t = await api.createTx({ ...f, amount: f.amount, parent_token: f.parent_token || null });
      setMsg(`Recorded. Token ${short(t.token)} — risk ${t.risk_level}${t.risk_reasons.length ? `: ${t.risk_reasons[0]}` : ""}`);
      reload();
    } catch (x) { setE2(x.message); }
  };
  const addAcct = async (ev) => { ev.preventDefault(); setE2(""); try { await api.createAccount(na); setNa({ id: "", name: "", kind: "contractor" }); reloadAccts(); } catch (x) { setE2(x.message); } };
  return (
    <>
      <h2>Transactions</h2>
      <div className="cols">
        <form className="card" onSubmit={submit}>
          <h3>Record a payment</h3>
          <label>From<select required value={f.sender} onChange={(e) => setF({ ...f, sender: e.target.value })}><option value="">Select account</option>{accts?.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.name}</option>)}</select></label>
          <label>To<select required value={f.receiver} onChange={(e) => setF({ ...f, receiver: e.target.value })}><option value="">Select account</option>{accts?.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.name}</option>)}</select></label>
          <label>Amount (₹)<input required inputMode="decimal" pattern="[0-9]+(\.[0-9]{1,2})?" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></label>
          <label>Purpose<input maxLength={256} value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} /></label>
          <label>Funded by token (leave empty for a new allocation)<input className="mono" minLength={64} maxLength={64} value={f.parent_token} onChange={(e) => setF({ ...f, parent_token: e.target.value.trim() })} /></label>
          <button className="btn primary">Record payment</button>
          {msg && <p className="ok" role="status">{msg}</p>}<Err msg={e2} />
        </form>
        <form className="card" onSubmit={addAcct}>
          <h3>Add an account</h3>
          <label>Account ID<input required pattern="[A-Za-z0-9_\-]+" value={na.id} onChange={(e) => setNa({ ...na, id: e.target.value })} /></label>
          <label>Name<input required value={na.name} onChange={(e) => setNa({ ...na, name: e.target.value })} /></label>
          <label>Type<select value={na.kind} onChange={(e) => setNa({ ...na, kind: e.target.value })}><option>department</option><option>contractor</option><option>beneficiary</option></select></label>
          <button className="btn">Add account</button>
        </form>
      </div>
      <section className="card">
        <div className="row"><h3>Latest payments</h3>
          <select aria-label="Filter by risk" value={risk} onChange={(e) => setRisk(e.target.value)}><option value="">All risk levels</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
          {role !== "officer" && <button className="btn" onClick={api.exportCsv}>Export CSV</button>}</div>
        <Err msg={err} />
        <div className="table-wrap"><table>
          <thead><tr><th>Token</th><th>From → To</th><th>Amount</th><th>Remaining</th><th>Risk</th><th>Status</th><th>When</th></tr></thead>
          <tbody>{rows?.map((t) => (
            <tr key={t.token}><td><Tok t={t.token} go={go} /></td><td>{t.sender} → {t.receiver}</td><td>{inr(t.amount)}</td><td>{inr(t.remaining)}</td>
              <td><Risk level={t.risk_level} /> <span className="muted small">{t.risk_score.toFixed(2)}</span></td><td>{t.status}</td><td>{when(t.ts)}</td></tr>))}</tbody>
        </table></div>
      </section>
    </>
  );
}

export function TracePage({ initial }) {
  const [q, setQ] = useState(initial || ""), [trace, setTrace] = useState(null), [sel, setSel] = useState(initial || ""), [err, setErr] = useState("");
  const [proof, setProof] = useState(null);
  const run = useCallback(async (t) => {
    setErr(""); setTrace(null); setProof(null);
    try { setTrace(await api.trace(t.trim())); setSel(t.trim()); } catch (x) { setErr(x.message); }
  }, []);
  useEffect(() => { if (initial) run(initial); }, [initial, run]);
  const node = trace?.nodes.find((n) => n.token === sel);
  return (
    <>
      <h2>Trace a token</h2>
      <form className="card row" onSubmit={(e) => { e.preventDefault(); run(q); }}>
        <input className="mono grow" placeholder="Paste a 64-character token" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Token" />
        <button className="btn primary">Trace money trail</button>
      </form>
      <Err msg={err} />
      {trace && (<>
        <div className="tiles compact">
          <div className="tile"><span>Original allocation</span><b>{inr(trace.summary.origin_amount)}</b></div>
          <div className="tile"><span>Hops</span><b>{trace.summary.hops}</b></div>
          <div className="tile"><span>Still unspent</span><b>{inr(trace.summary.still_unspent)}</b></div>
          <div className="tile"><span>Final recipients</span><b>{trace.summary.final_recipients.length}</b></div>
          <div className={`tile ${trace.summary.flagged_nodes ? "badbg" : "good"}`}><span>Risky links</span><b>{trace.summary.flagged_nodes}</b></div>
        </div>
        <section className="card"><h3>Money trail</h3>
          <p className="muted small">Line thickness shows how much money moved. Colour shows risk. Select a link for details.</p>
          <TraceGraph trace={trace} selected={sel} onSelect={(t) => { setSel(t); setProof(null); }} /></section>
        {node && (<section className="card">
          <h3>{node.sender} → {node.receiver} · {inr(node.amount)}</h3>
          <p className="mono small wrap">{node.token}</p>
          <p><Risk level={node.risk_level} /> score {node.risk_score.toFixed(2)} · status {node.status} · {when(node.ts)}</p>
          {node.purpose && <p>Purpose: {node.purpose}</p>}
          {node.risk_reasons.length > 0 && <ul>{node.risk_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
          <button className="btn" onClick={async () => setProof(await api.proof(node.token))}>Check inclusion proof</button>
          {proof && <p className={proof.valid ? "ok" : "muted"}>{!proof.anchored ? "Not anchored yet — it will be included in the next batch." : proof.valid ? `Verified: part of batch #${proof.batch_id} (root ${short(proof.merkle_root)})${proof.chain_tx ? " anchored on-chain" : ""}.` : "Proof failed."}</p>}
        </section>)}
      </>)}
    </>
  );
}

export function Alerts({ go }) {
  const [status, setStatus] = useState("open");
  const [rows, err, reload] = useLoad(() => api.alerts(status ? `?status=${status}` : ""), [status]);
  const [e2, setE2] = useState("");
  const act = async (a, body) => { setE2(""); try { await api.updateAlert(a.id, body); reload(); } catch (x) { setE2(x.message); } };
  return (
    <>
      <div className="row"><h2>Alerts</h2>
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="open">Open</option><option value="investigating">Investigating</option><option value="resolved">Resolved</option><option value="dismissed">Dismissed</option><option value="">All</option></select></div>
      <Err msg={err || e2} />
      {rows?.length === 0 && <p className="muted">No alerts in this view.</p>}
      {rows?.map((a) => (
        <article className="card alert" key={a.id}>
          <div className="row"><Risk level={a.level} /><strong>score {a.score.toFixed(2)}</strong><Tok t={a.token} go={go} /><span className="muted small">{when(Date.parse(a.created_at + "Z") / 1000)} · {a.status}</span></div>
          <ul>{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <div className="row">
            <button className="btn" onClick={() => act(a, { status: "investigating" })}>Start investigation</button>
            <button className="btn danger" onClick={() => act(a, { status: "investigating", freeze: true, note: "Frozen by auditor" })}>Freeze token</button>
            <button className="btn" onClick={() => act(a, { status: "resolved" })}>Resolve</button>
            <button className="btn ghost" onClick={() => act(a, { status: "dismissed", note: "False positive" })}>Dismiss as false positive</button>
          </div>
        </article>))}
    </>
  );
}

export function LedgerPage({ role }) {
  const [v, , reVerify] = useLoad(api.verifyLedger);
  const [b, , reB] = useLoad(api.batches);
  const [log] = useLoad(() => (role === "officer" ? Promise.resolve([]) : api.audit()), [role]);
  const [msg, setMsg] = useState("");
  const anchor = async () => { setMsg(""); try { const r = await api.anchor(); setMsg(`Anchored ${r.leaf_count} payments. Root ${short(r.merkle_root)}${r.chain_tx ? " · on-chain" : " · off-chain only (no RPC configured)"}`); reB(); } catch (x) { setMsg(x.message); } };
  return (
    <>
      <h2>Ledger & audit</h2>
      <section className="card"><div className="row"><h3>Integrity check</h3><button className="btn" onClick={reVerify}>Re-verify now</button></div>
        {v && <p className={v.valid ? "ok" : "err"}>{v.valid ? `Every one of ${v.checked} links verifies. Head ${short(v.head)}.` : `Chain broken at payment #${v.broken_at_id} (${short(v.broken_at_token)}). Records were changed after they were written.`}</p>}</section>
      <section className="card"><div className="row"><h3>Anchored batches</h3>{role === "admin" && <button className="btn primary" onClick={anchor}>Anchor pending payments</button>}</div>
        {msg && <p role="status">{msg}</p>}
        <table><thead><tr><th>#</th><th>Merkle root</th><th>Payments</th><th>On-chain tx</th><th>Created</th></tr></thead>
          <tbody>{b?.map((x) => <tr key={x.id}><td>{x.id}</td><td className="mono">{short(x.merkle_root)}</td><td>{x.leaf_count}</td><td className="mono">{x.chain_tx ? short(x.chain_tx) : "—"}</td><td>{x.created_at}</td></tr>)}</tbody></table></section>
      {role !== "officer" && <section className="card"><h3>Audit log</h3>
        <div className="table-wrap"><table><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th></tr></thead>
          <tbody>{log?.map((l) => <tr key={l.id}><td>{when(l.ts)}</td><td>{l.actor}</td><td>{l.action}</td><td className="mono">{short(l.target)}</td></tr>)}</tbody></table></div></section>}
    </>
  );
}

export function PublicVerify() {
  const [t, setT] = useState(""), [r, setR] = useState(null), [err, setErr] = useState("");
  const go = async (e) => { e.preventDefault(); setErr(""); setR(null); try { setR(await api.publicVerify(t.trim())); } catch (x) { setErr(x.message); } };
  return (
    <form onSubmit={go}>
      <label>Payment token<input className="mono" required value={t} onChange={(e) => setT(e.target.value)} placeholder="64-character token from your receipt" /></label>
      <button className="btn primary">Verify token</button>
      <Err msg={err} />
      {r && <div className="result">
        <p className={r.ledger_valid ? "ok" : "err"}>{r.ledger_valid ? "Genuine. The public ledger is intact." : "Warning: the ledger has been tampered with."}</p>
        <p>{inr(r.amount)} from <b>{r.sender}</b> to <b>{r.receiver}</b></p>
        <p className="muted small">{r.purpose || "No purpose recorded"} · {when(r.ts)}</p>
        <p>Downstream: {r.hops_downstream} hop(s), reaching {r.final_recipients.join(", ") || "no further recipients"}.</p>
        <p className="muted small">{r.anchored ? "Sealed in an anchored batch." : "Waiting to be sealed in the next batch."}</p></div>}
    </form>
  );
}
