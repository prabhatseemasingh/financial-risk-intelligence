from __future__ import annotations

import numpy as np
import pandas as pd

from .data import REQUIRED_ASSETS


HORIZON = 21
FEATURE_WINDOWS = (21, 63)


def build_features(prices: pd.DataFrame, horizon: int = HORIZON) -> tuple[pd.DataFrame, pd.Series]:
    """Create point-in-time features and forward realized volatility labels.

    A row dated t uses prices and returns through close t. The forward target
    uses equity returns t+1 through t+horizon, so the current day's return is
    excluded from the target.
    """
    if any(asset not in prices.columns for asset in REQUIRED_ASSETS):
        raise ValueError(f"Input must contain {', '.join(REQUIRED_ASSETS)}.")
    levels = prices.loc[:, list(REQUIRED_ASSETS)].astype(float)
    returns = levels.pct_change(fill_method=None)

    feature_map: dict[str, pd.Series] = {}
    for asset in REQUIRED_ASSETS:
        for lag in (1, 5, 21):
            feature_map[f"{asset}_ret_{lag}"] = levels[asset].pct_change(lag, fill_method=None)

    equity_returns = returns["Equity_TR"]
    for window in FEATURE_WINDOWS:
        feature_map[f"equity_vol_{window}"] = equity_returns.rolling(window, min_periods=window).std(ddof=1) * np.sqrt(252)

    feature_map["equity_drawdown_252"] = levels["Equity_TR"] / levels["Equity_TR"].rolling(252, min_periods=63).max() - 1
    for lhs, rhs, label in (
        ("Equity_TR", "Bond_TR", "equity_bond"),
        ("Equity_TR", "Gold_TR", "equity_gold"),
        ("Bond_TR", "Gold_TR", "bond_gold"),
    ):
        feature_map[f"corr_{label}_63"] = returns[lhs].rolling(63, min_periods=63).corr(returns[rhs])

    if "India_VIX" in prices.columns:
        feature_map["india_vix"] = pd.to_numeric(prices["India_VIX"], errors="coerce")

    features = pd.DataFrame(feature_map, index=prices.index).replace([np.inf, -np.inf], np.nan)
    forward_returns = equity_returns.shift(-1)
    forward_vol = (
        forward_returns.iloc[::-1]
        .rolling(horizon, min_periods=horizon)
        .std(ddof=1)
        .iloc[::-1]
        * np.sqrt(252)
    )
    forward_vol.name = "forward_equity_vol"
    return features, forward_vol


def complete_feature_rows(features: pd.DataFrame) -> pd.DataFrame:
    required = [column for column in features.columns if column != "india_vix"]
    return features.replace([np.inf, -np.inf], np.nan).dropna(subset=required)

