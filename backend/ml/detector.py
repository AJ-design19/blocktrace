"""Inference wrapper. Falls back to a transparent heuristic if TensorFlow or the
trained artifact is unavailable, so the API (and CI) never hard-depend on it."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

import numpy as np

from .features import FEATURE_NAMES, REPORTING_THRESHOLD, featurize

log = logging.getLogger("blocktrace.ml")
ART = Path(__file__).parent / "artifacts"


class Detector:
    def __init__(self) -> None:
        self.model = None
        self.threshold = 0.5
        self.mode = "heuristic"
        self._try_load()

    def _try_load(self) -> None:
        path = ART / "model.keras"
        if not path.exists():
            log.warning("No trained model at %s - using heuristic fallback", path)
            return
        try:
            import tensorflow as tf  # noqa: WPS433
            self.model = tf.keras.models.load_model(path)
            meta = ART / "metrics.json"
            if meta.exists():
                self.threshold = float(json.loads(meta.read_text()).get("threshold", 0.5))
            self.mode = "lstm"
        except Exception as exc:  # pragma: no cover
            log.error("Model load failed (%s) - using heuristic fallback", exc)

    def score(self, history: Sequence[dict]) -> dict:
        x = featurize(history)
        if self.model is not None:
            p = float(self.model.predict(x[None, ...], verbose=0)[0, 0])
        else:
            p = self._heuristic(x)
        return {"score": round(p, 4), "is_anomaly": p >= self.threshold, "engine": self.mode,
                "reasons": self._explain(x)}

    @staticmethod
    def _heuristic(x: np.ndarray) -> float:
        last = x[-1]
        s = 0.0
        s += 0.35 * last[7]                      # just under reporting threshold
        s += 0.25 * max(last[4], 0)              # spike vs own history
        s += 0.20 * last[8]                      # burst velocity
        s += 0.10 * last[5] * (1 if last[8] > 0.2 else 0)
        s += 0.10 * (1 if last[2] < -0.5 and last[3] > 0.5 else 0)  # night hours
        return float(min(s, 1.0))

    @staticmethod
    def _explain(x: np.ndarray) -> list[str]:
        """Human-readable reasons so an auditor never sees a bare number."""
        last, reasons = x[-1], []
        if last[7] > 0:
            reasons.append(f"Amount sits just below the {int(REPORTING_THRESHOLD):,} reporting threshold")
        if last[4] > 0.6:
            reasons.append("Amount is far above this account's usual size")
        if last[8] >= 0.3:
            reasons.append("Burst of transactions within the last hour")
        if last[5] == 1 and last[8] >= 0.2:
            reasons.append("Sending to a new counterparty during a burst")
        if last[6] == 1 and x[:, 6].sum() >= 3:
            reasons.append("Repeated round-number transfers")
        return reasons
