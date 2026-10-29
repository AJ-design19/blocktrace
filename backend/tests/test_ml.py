import numpy as np

from ml.detector import Detector
from ml.features import N_FEATURES, SEQ_LEN, featurize


def _hist(amounts, gap=14400):
    return [{"ts": 1_750_000_000 + i * gap, "amount": a, "counterparty": "acc1"} for i, a in enumerate(amounts)]


def test_featurize_shape_and_padding():
    x = featurize(_hist([100, 200, 300]))
    assert x.shape == (SEQ_LEN, N_FEATURES)
    assert not x[: SEQ_LEN - 3].any()          # left padded with zeros
    assert np.isfinite(x).all()


def test_detector_scores_structuring_higher_than_normal():
    d = Detector()
    normal = d.score(_hist([4000, 5200, 4800, 5100, 4600, 5000, 4900, 5300, 4700, 5050]))
    fraud = d.score(_hist([4000, 5200, 4800, 5100, 4600, 5000, 49500, 49600, 49700, 49800], gap=300))
    assert fraud["score"] > normal["score"]
    assert fraud["is_anomaly"] and not normal["is_anomaly"]
