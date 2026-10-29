const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
let token = null;
try { token = sessionStorage.getItem("bt_token"); } catch { /* storage unavailable */ }

export const auth = {
  get token() { return token; },
  set(t) { token = t; try { t ? sessionStorage.setItem("bt_token", t) : sessionStorage.removeItem("bt_token"); } catch { /* ignore */ } },
};

async function req(path, { method = "GET", body, form, raw } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) { payload = new URLSearchParams(form); }
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(BASE + path, { method, headers, body: payload });
  if (res.status === 401 && token) { auth.set(null); window.location.reload(); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep */ }
    throw new Error(msg);
  }
  return raw ? res : res.json();
}

export const api = {
  login: (username, password) => req("/auth/login", { method: "POST", form: { username, password } }),
  me: () => req("/auth/me"),
  stats: () => req("/stats"),
  accounts: () => req("/accounts"),
  createAccount: (b) => req("/accounts", { method: "POST", body: b }),
  txs: (qs = "") => req(`/transactions${qs}`),
  createTx: (b) => req("/transactions", { method: "POST", body: b }),
  trace: (t) => req(`/transactions/${t}/trace`),
  alerts: (s = "") => req(`/alerts${s}`),
  updateAlert: (id, b) => req(`/alerts/${id}`, { method: "PATCH", body: b }),
  verifyLedger: () => req("/ledger/verify"),
  anchor: () => req("/ledger/anchor", { method: "POST" }),
  batches: () => req("/ledger/batches"),
  audit: () => req("/audit-log"),
  proof: (t) => req(`/transactions/${t}/proof`),
  publicVerify: (t) => req(`/public/verify/${t}`),
  publicSummary: () => req("/public/summary"),
  mlMetrics: () => req("/ml/metrics"),
  exportCsv: async () => {
    const r = await req("/transactions/export.csv", { raw: true });
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = "blocktrace_ledger.csv"; a.click();
    URL.revokeObjectURL(url);
  },
};

export const inr = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
export const short = (t) => (t ? `${t.slice(0, 8)}…${t.slice(-4)}` : "");
export const when = (ts) => new Date(ts * 1000).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
