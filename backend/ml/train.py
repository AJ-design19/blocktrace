"""Train + evaluate the LSTM fraud detector.  Run:  python -m ml.train"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

from .data import generate_dataset
from .model import build_model

ART = Path(__file__).parent / "artifacts"


def main(n: int = 40_000, epochs: int = 12, seed: int = 7):
    import tensorflow as tf
    tf.keras.utils.set_random_seed(seed)
    ART.mkdir(exist_ok=True)

    X, y = generate_dataset(n=n, seed=seed)
    X_tr, X_tmp, y_tr, y_tmp = train_test_split(X, y, test_size=0.30, stratify=y, random_state=seed)
    X_val, X_te, y_val, y_te = train_test_split(X_tmp, y_tmp, test_size=0.50, stratify=y_tmp, random_state=seed)

    pos = y_tr.mean()
    cw = {0: 1.0, 1: float((1 - pos) / pos) ** 0.5}   # soften imbalance, keep precision sane
    model = build_model()
    model.fit(
        X_tr, y_tr, validation_data=(X_val, y_val), epochs=epochs, batch_size=256, class_weight=cw, verbose=2,
        callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_auc", mode="max", patience=3, restore_best_weights=True)],
    )

    # pick the decision threshold on the validation set (best F1), report on untouched test set
    pv = model.predict(X_val, verbose=0).ravel()
    best_t, best_f1 = 0.5, 0.0
    for t in np.linspace(0.1, 0.9, 81):
        f = f1_score(y_val, pv >= t)
        if f > best_f1:
            best_t, best_f1 = float(t), float(f)

    pt = model.predict(X_te, verbose=0).ravel()
    pred = pt >= best_t
    tn, fp, fn, tp = confusion_matrix(y_te, pred).ravel()
    metrics = {
        "dataset": "synthetic (see ml/data.py)",
        "n_total": int(n), "fraud_rate": float(y.mean()), "test_size": int(len(y_te)),
        "threshold": best_t,
        "accuracy": float(accuracy_score(y_te, pred)),
        "precision": float(precision_score(y_te, pred)),
        "recall": float(recall_score(y_te, pred)),
        "f1": float(f1_score(y_te, pred)),
        "roc_auc": float(roc_auc_score(y_te, pt)),
        "false_positive_rate": float(fp / (fp + tn)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "baseline_accuracy_all_legit": float(1 - y_te.mean()),
    }
    model.save(ART / "model.keras")
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main(n=int(os.getenv("N_SAMPLES", 40_000)), epochs=int(os.getenv("EPOCHS", 12)))
