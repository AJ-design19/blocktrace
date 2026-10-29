"""Shared feature engineering for training and live inference.

Keeping this in ONE place is what prevents train/serve skew: the API scores a
transaction with exactly the same function the model was trained with.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

SEQ_LEN = 10
N_FEATURES = 9
REPORTING_THRESHOLD = 50_000.0  # amounts just under this are classic "structuring"
FEATURE_NAMES = [
    "log_amount", "log_gap", "hour_sin", "hour_cos", "amount_vs_history",
    "new_counterparty", "round_amount", "near_threshold", "burst_velocity",
]


def featurize(txs: Sequence[dict]) -> np.ndarray:
    """txs: chronological list of {ts:int seconds, amount:float, counterparty:str}
    for ONE sender. Returns (SEQ_LEN, N_FEATURES) left-padded with zeros."""
    txs = list(txs)[-SEQ_LEN:]
    out = np.zeros((SEQ_LEN, N_FEATURES), dtype=np.float32)
    offset = SEQ_LEN - len(txs)
    seen: set[str] = set()
    amounts: list[float] = []
    for i, t in enumerate(txs):
        amt = max(float(t["amount"]), 0.01)
        ts = int(t["ts"])
        gap = (ts - int(txs[i - 1]["ts"])) if i > 0 else 86_400
        gap = max(gap, 0)
        hour = (ts % 86_400) / 3600.0
        mean_prev = float(np.mean(amounts)) if amounts else amt
        velocity = sum(1 for j in range(max(0, i - 9), i) if ts - int(txs[j]["ts"]) <= 3600)
        out[offset + i] = [
            math.log1p(amt) / 14.0,
            math.log1p(gap) / 12.0,
            math.sin(2 * math.pi * hour / 24.0),
            math.cos(2 * math.pi * hour / 24.0),
            float(np.clip(math.log(amt / max(mean_prev, 0.01)), -3, 3)) / 3.0,
            0.0 if t["counterparty"] in seen else 1.0,
            1.0 if amt % 1000 == 0 else 0.0,
            1.0 if 0.90 * REPORTING_THRESHOLD <= amt < REPORTING_THRESHOLD else 0.0,
            min(velocity, 10) / 10.0,
        ]
        seen.add(t["counterparty"])
        amounts.append(amt)
    return out
