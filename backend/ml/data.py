"""Synthetic transaction generator with realistic fraud typologies.

Real government / bank ledgers are confidential, so the model is benchmarked on
synthetic data. Hard negatives (night-time payments, big one-off invoices, round
amounts) and noisy labels are included on purpose so the score is not trivially
perfect. Swap `generate_dataset` for a real labelled export in production.
"""
from __future__ import annotations

import numpy as np

from .features import REPORTING_THRESHOLD, SEQ_LEN, featurize

FRAUD_TYPES = ["structuring", "pass_through", "spike", "round_trip"]


def _normal_tx(rng, base, pool, ts):
    amt = float(np.exp(rng.normal(np.log(base), 0.6)))
    if rng.random() < 0.05:
        amt = round(amt / 1000) * 1000 or 1000.0           # honest round payments
    if rng.random() < 0.04:
        amt *= rng.uniform(3, 6)                          # honest large invoice
    if base < REPORTING_THRESHOLD * 0.3 and rng.random() < 0.8:
        amt = min(amt, REPORTING_THRESHOLD * 0.85)       # small accounts rarely hit the limit
    hour = rng.integers(8, 20) if rng.random() < 0.88 else rng.integers(0, 24)
    cp = f"acc{rng.integers(0, 10_000)}" if rng.random() < 0.08 else pool[rng.integers(0, len(pool))]
    return {"ts": ts, "amount": amt, "counterparty": cp, "_hour": int(hour)}


def _fraud_tx(rng, kind, base, pool, ts, i):
    if kind == "structuring":
        amt = rng.uniform(0.91, 0.995) * REPORTING_THRESHOLD
        cp = f"acc{rng.integers(0, 10_000)}" if rng.random() < 0.5 else pool[0]
        return {"ts": ts, "amount": float(amt), "counterparty": cp, "_gap": rng.uniform(60, 1200)}
    if kind == "pass_through":
        amt = base * rng.uniform(3, 9)
        return {"ts": ts, "amount": float(amt), "counterparty": f"acc{rng.integers(0, 10_000)}", "_gap": rng.uniform(20, 700)}
    if kind == "spike":
        amt = base * rng.uniform(8, 30)
        return {"ts": ts, "amount": float(amt), "counterparty": f"acc{rng.integers(0, 10_000)}", "_hour": int(rng.integers(0, 5)), "_gap": rng.uniform(600, 5000)}
    # round_trip: same two parties, round amounts, quick succession
    amt = float(rng.choice([5000, 10000, 20000, 25000, 40000]))
    return {"ts": ts, "amount": amt, "counterparty": f"loop{i % 2}", "_gap": rng.uniform(120, 1500)}


def make_sequence(rng, fraud_kind: str | None):
    base = float(np.exp(rng.uniform(7.5, 15.5) + rng.normal(0, 0.4)))   # Rs 2k .. Rs 6 crore typical sizes
    pool = [f"acc{rng.integers(0, 10_000)}" for _ in range(rng.integers(2, 8))]
    k = int(rng.integers(3, 6)) if fraud_kind else 0
    if fraud_kind and rng.random() < 0.12:
        k = 2                                              # weak / partial pattern -> harder
    ts = int(rng.integers(1_700_000_000, 1_760_000_000))
    txs = []
    for i in range(SEQ_LEN):
        ts += int(rng.exponential(14_400)) + 60
        if fraud_kind and i >= SEQ_LEN - k:
            tx = _fraud_tx(rng, fraud_kind, base, pool, ts, i)
            if "_gap" in tx:
                ts = txs[-1]["ts"] + int(tx["_gap"]) if txs else ts
                tx["ts"] = ts
        else:
            tx = _normal_tx(rng, base, pool, ts)
        if "_hour" in tx:                                  # pin hour of day
            tx["ts"] = (tx["ts"] // 86_400) * 86_400 + tx["_hour"] * 3600 + int(rng.integers(0, 3600))
            ts = max(ts, tx["ts"])
        txs.append({k: v for k, v in tx.items() if not k.startswith("_")})
    txs.sort(key=lambda t: t["ts"])
    if rng.random() < 0.30:                                  # short history (left-padded at inference)
        keep = int(rng.integers(4, SEQ_LEN)) if fraud_kind else int(rng.integers(1, SEQ_LEN))
        txs = txs[-keep:]
    return txs


def generate_dataset(n: int = 40_000, fraud_rate: float = 0.10, seed: int = 7, label_noise: float = 0.01):
    rng = np.random.default_rng(seed)
    X = np.zeros((n, SEQ_LEN, 9), dtype=np.float32)
    y = np.zeros(n, dtype=np.float32)
    for i in range(n):
        is_fraud = rng.random() < fraud_rate
        kind = FRAUD_TYPES[rng.integers(0, len(FRAUD_TYPES))] if is_fraud else None
        X[i] = featurize(make_sequence(rng, kind))
        y[i] = 1.0 if is_fraud else 0.0
        if rng.random() < label_noise:
            y[i] = 1.0 - y[i]
    return X, y
