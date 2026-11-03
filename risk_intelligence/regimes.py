from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


REGIME_FEATURES = ["Equity_TR_ret_21", "equity_vol_21", "equity_drawdown_252"]


def descriptive_regimes(
    features: pd.DataFrame,
    training_end: int | pd.Timestamp | None = None,
    clusters: int = 3,
) -> pd.DataFrame:
    """Fit descriptive clusters on earlier history, then assign later rows.

    Names describe trailing volatility rank only; they do not label bullish or
    bearish regimes and are not used as supervised prediction targets.
    """
    if clusters < 2:
        raise ValueError("Descriptive regime analysis needs at least two clusters.")
    missing = [name for name in REGIME_FEATURES if name not in features.columns]
    if missing:
        raise ValueError(f"Regime analysis requires features: {', '.join(missing)}.")
    valid = features.loc[:, REGIME_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    if training_end is not None:
        if isinstance(training_end, (pd.Timestamp, np.datetime64)):
            valid = valid.loc[valid.index <= pd.Timestamp(training_end)]
        else:
            valid = valid.iloc[:training_end]
    if len(valid) < clusters * 20:
        raise ValueError("Not enough complete history to fit descriptive regimes.")

    pipeline = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        KMeans(n_clusters=clusters, random_state=42, n_init=20),
    )
    pipeline.fit(valid)

    all_valid = features.loc[:, REGIME_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    raw = pipeline.predict(all_valid)
    fit_labels = pipeline.predict(valid)
    med_vol = pd.Series(features.loc[valid.index, "equity_vol_21"].to_numpy(), index=fit_labels).groupby(level=0).median()
    ordered = med_vol.sort_values().index.tolist()
    descriptors = ["lower trailing vol", "mid trailing vol", "higher trailing vol"]
    if clusters != 3:
        descriptors = [f"trailing-vol rank {rank + 1}" for rank in range(clusters)]
    name_map = {label: f"Cluster {rank + 1} ({descriptors[rank]})" for rank, label in enumerate(ordered)}
    result = pd.DataFrame({
        "cluster_id": raw,
        "regime": [name_map[label] for label in raw],
        "equity_vol_21": all_valid["equity_vol_21"],
    }, index=all_valid.index)
    return result

