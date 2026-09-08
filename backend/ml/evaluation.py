import numpy as np
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    log_loss,
    brier_score_loss,
)


def metrics(frame, probabilities):
    p = np.asarray(probabilities)
    y = frame.podium.to_numpy()
    if len(p) != len(y) or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid prediction probabilities")
    ranked = frame[["race_id", "driver_id", "podium"]].copy()
    ranked["probability"] = p
    chosen = (
        ranked.sort_values(["race_id", "probability", "driver_id"], ascending=[True, False, True])
        .groupby("race_id")
        .head(3)
    )
    hits = chosen.groupby("race_id").podium.sum()
    bins = []
    ece = 0.0
    for lower in np.arange(0, 1, 0.1):
        upper = lower + 0.1
        mask = (p >= lower) & ((p < upper) if upper < 0.999 else (p <= 1))
        count = int(mask.sum())
        if count:
            predicted, observed = float(p[mask].mean()), float(y[mask].mean())
            ece += count / len(y) * abs(predicted - observed)
            bins.append(
                {
                    "lower": float(lower),
                    "upper": float(upper),
                    "count": count,
                    "mean_probability": predicted,
                    "observed_rate": observed,
                }
            )
    return {
        "rows": len(y),
        "races": int(frame.race_id.nunique()),
        "positive_rate": float(y.mean()),
        "precision": float(precision_score(y, p >= 0.5, zero_division=0)),
        "recall": float(recall_score(y, p >= 0.5, zero_division=0)),
        "f1": float(f1_score(y, p >= 0.5, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier_score": float(brier_score_loss(y, p)),
        "top3_hit_rate": float(hits.sum() / len(chosen)),
        "exact_podium_set_rate": float((hits == 3).mean()),
        "ece_10_bins": ece,
        "calibration_bins": bins,
    }
