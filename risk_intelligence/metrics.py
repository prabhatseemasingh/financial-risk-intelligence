from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, balanced_accuracy_score, brier_score_loss, precision_score, recall_score, roc_auc_score


def classification_metrics(y_true: pd.Series | np.ndarray, probability: pd.Series | np.ndarray) -> dict[str, float]:
    y = np.asarray(y_true, dtype=int)
    p = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
    if len(y) == 0:
        return {"Brier": np.nan, "PR-AUC": np.nan, "ROC-AUC": np.nan, "Recall@0.5": np.nan, "Precision@0.5": np.nan, "Balanced accuracy@0.5": np.nan}
    labels = (p >= 0.5).astype(int)
    try:
        roc_auc = float(roc_auc_score(y, p)) if np.unique(y).size == 2 else np.nan
    except ValueError:
        roc_auc = np.nan
    try:
        pr_auc = float(average_precision_score(y, p)) if np.unique(y).size == 2 else np.nan
    except ValueError:
        pr_auc = np.nan
    try:
        bal_acc = float(balanced_accuracy_score(y, labels)) if np.unique(y).size == 2 else np.nan
    except ValueError:
        bal_acc = np.nan
    return {
        "Brier": float(brier_score_loss(y, p)),
        "PR-AUC": pr_auc,
        "ROC-AUC": roc_auc,
        "Recall@0.5": float(recall_score(y, labels, zero_division=0)),
        "Precision@0.5": float(precision_score(y, labels, zero_division=0)),
        "Balanced accuracy@0.5": bal_acc,
    }


def calibration_table(y_true: pd.Series | np.ndarray, probability: pd.Series | np.ndarray, bins: int = 10) -> pd.DataFrame:
    data = pd.DataFrame({"actual": np.asarray(y_true, dtype=float), "probability": np.asarray(probability, dtype=float)})
    if data.empty:
        return pd.DataFrame(columns=["Probability bin", "Mean predicted probability", "Observed high-risk share", "Count"])
    edges = np.linspace(0, 1, bins + 1)
    data["bin"] = pd.cut(data["probability"], edges, include_lowest=True, duplicates="drop")
    result = data.groupby("bin", observed=True).agg(
        mean_probability=("probability", "mean"),
        observed_rate=("actual", "mean"),
        count=("actual", "size"),
    ).reset_index()
    result["Probability bin"] = result["bin"].astype(str)
    return result.rename(columns={
        "mean_probability": "Mean predicted probability",
        "observed_rate": "Observed high-risk share",
        "count": "Count",
    })[["Probability bin", "Mean predicted probability", "Observed high-risk share", "Count"]]


def portfolio_metrics(returns: pd.Series, turnover: pd.Series, cost_bps: float) -> dict[str, float]:
    r = pd.Series(returns, dtype=float).dropna()
    tr = pd.Series(turnover, dtype=float).reindex(r.index).fillna(0.0)
    if r.empty:
        return {}
    wealth = (1 + r).cumprod()
    years = len(r) / 252
    cagr = float(wealth.iloc[-1] ** (1 / years) - 1) if years > 0 and wealth.iloc[-1] > 0 else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else np.nan
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 and r.std(ddof=1) > 0 else np.nan
    downside = r.where(r < 0, 0.0)
    downside_dev = float(np.sqrt(np.mean(downside**2)) * np.sqrt(252))
    sortino = float(r.mean() * 252 / downside_dev) if downside_dev > 0 else np.nan
    drawdown = wealth / wealth.cummax() - 1
    q05 = float(r.quantile(0.05))
    tail = r[r <= q05]
    return {
        "CAGR": cagr,
        "Annualized volatility": vol,
        "Sharpe (Rf=0)": sharpe,
        "Sortino (MAR=0)": sortino,
        "Maximum drawdown": float(drawdown.min()),
        "1-day historical VaR 95% (loss)": -q05,
        "1-day historical CVaR 95% (loss)": -float(tail.mean()) if len(tail) else np.nan,
        "Total one-way turnover": float(tr.sum()),
        "Estimated transaction cost": float(tr.sum() * cost_bps / 10_000),
        "Observations": int(len(r)),
    }

