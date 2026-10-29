import React from "react";
import { inr, short } from "./api.js";

const COL = 250, ROW = 74, W = 190, H = 52, PAD = 24;
const tone = { low: "var(--verify)", medium: "var(--warn)", high: "var(--risk)" };

/** Money-trail flow: each link's thickness is proportional to the amount that moved. */
export default function TraceGraph({ trace, selected, onSelect }) {
  const nodes = trace.nodes;
  const byDepth = {};
  nodes.forEach((n) => (byDepth[n.depth] = [...(byDepth[n.depth] || []), n]));
  const pos = {};
  Object.entries(byDepth).forEach(([d, list]) =>
    list.forEach((n, i) => (pos[n.token] = { x: PAD + d * COL, y: PAD + i * ROW })));
  const maxDepth = Math.max(...nodes.map((n) => n.depth));
  const maxRows = Math.max(...Object.values(byDepth).map((l) => l.length));
  const width = PAD * 2 + (maxDepth + 1) * COL - (COL - W);
  const height = PAD * 2 + maxRows * ROW - (ROW - H);
  const total = trace.origin.amount || 1;
  const byToken = Object.fromEntries(nodes.map((n) => [n.token, n]));

  return (
    <div className="graph-scroll">
      <svg width={width} height={height} role="img" aria-label="Money trail from original allocation to final recipients">
        {trace.edges.map((e) => {
          const a = pos[e.from], b = pos[e.to], child = byToken[e.to];
          if (!a || !b) return null;
          const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
          return <path key={e.to} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none"
            stroke={tone[child.risk_level]} strokeOpacity=".35" strokeWidth={Math.max(2, (child.amount / total) * 30)} />;
        })}
        {nodes.map((n) => {
          const p = pos[n.token], sel = selected === n.token;
          return (
            <g key={n.token} transform={`translate(${p.x},${p.y})`} className="gnode" tabIndex={0} role="button"
               aria-label={`${n.sender} to ${n.receiver}, ${inr(n.amount)}, ${n.risk_level} risk`}
               onClick={() => onSelect(n.token)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(n.token)}>
              <rect width={W} height={H} rx="6" fill="var(--card)" stroke={sel ? "var(--ink)" : "var(--line)"} strokeWidth={sel ? 2 : 1} />
              <rect width="6" height={H} rx="3" fill={tone[n.risk_level]} />
              <text x="16" y="21" className="gt-main">{n.sender} → {n.receiver}</text>
              <text x="16" y="40" className="gt-sub">{inr(n.amount)} · {short(n.token)}</text>
              {n.status === "frozen" && <text x={W - 8} y="16" textAnchor="end" className="gt-flag">frozen</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
