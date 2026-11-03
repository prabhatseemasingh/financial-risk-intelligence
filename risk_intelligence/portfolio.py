from __future__ import annotations

import numpy as np
import pandas as pd

from .data import REQUIRED_ASSETS
from .metrics import portfolio_metrics


def weights_from_probability(probability: float) -> pd.Series:
    """Illustrative long-only rule: equity 60% to 30% as risk probability rises."""
    p = float(np.clip(probability, 0.0, 1.0))
    equity = 0.60 - 0.30 * p
    defensive = (1.0 - equity) / 2.0
    return pd.Series({"Equity_TR": equity, "Bond_TR": defensive, "Gold_TR": defensive})


def _portfolio_path(
    asset_returns: pd.DataFrame,
    holdout: pd.DataFrame,
    probability: pd.Series,
    cost_bps: float,
    strategy_name: str,
    dynamic: bool,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    dates = asset_returns.index
    test_dates = holdout.index
    first_pos = dates.get_indexer([test_dates[0]])[0]
    last_pos = dates.get_indexer([test_dates[-1]])[0]
    if first_pos < 0 or last_pos < 0:
        raise ValueError("Holdout dates do not align with price returns.")
    index = dates[first_pos:last_pos + 1]
    r = asset_returns.loc[index, list(REQUIRED_ASSETS)].copy()

    # Positions are recorded at the close when an order is executed. A signal
    # formed after close t is scheduled at the next session's close, and earns
    # close-to-close returns only after that execution point.
    positions = pd.DataFrame(np.nan, index=index, columns=REQUIRED_ASSETS, dtype=float)
    positions.iloc[0] = [0.60, 0.20, 0.20]
    execution_targets: dict[pd.Timestamp, pd.Series] = {}
    if dynamic:
        signal_dates = holdout.groupby(holdout.index.to_period("M"), sort=True).tail(1).index
        for signal_date in signal_dates:
            signal_pos = dates.get_indexer([signal_date])[0]
            if signal_pos < 0 or signal_pos + 1 >= len(dates):
                continue
            execution_date = dates[signal_pos + 1]
            if execution_date not in positions.index:
                continue
            p = float(probability.loc[signal_date])
            execution_targets[execution_date] = weights_from_probability(p)

    for execution_date, weights in execution_targets.items():
        positions.loc[execution_date] = weights.reindex(list(REQUIRED_ASSETS)).to_numpy()
    positions = positions.ffill().fillna(pd.Series([0.60, 0.20, 0.20], index=REQUIRED_ASSETS))

    turnover = (positions - positions.shift(1)).abs().sum(axis=1) / 2.0
    turnover.iloc[0] = 1.0  # Initial portfolio entry, charged consistently to each comparator.
    gross = (r * positions.shift(1).fillna(positions)).sum(axis=1)
    # The initial allocation is established at the first holdout close, so it
    # cannot earn the close-to-close return ending at that same close.
    gross.iloc[0] = 0.0
    cost_fraction = turnover * (float(cost_bps) / 10_000.0)
    net = (1.0 + gross) * (1.0 - cost_fraction) - 1.0
    net.name = strategy_name
    turnover.name = strategy_name
    return net, turnover, positions


def evaluate_portfolios(
    prices: pd.DataFrame,
    holdout: pd.DataFrame,
    cost_bps: float = 10.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    """Compare the selected forecast policy with simple portfolio baselines."""
    if holdout.empty:
        raise ValueError("No final holdout forecasts are available for portfolio evaluation.")
    asset_returns = prices.loc[:, list(REQUIRED_ASSETS)].pct_change(fill_method=None).dropna(how="any")
    predictions = holdout.copy()
    if "risk_probability" not in predictions or "vol_baseline_probability" not in predictions:
        raise ValueError("Holdout data is missing model or volatility-baseline probabilities.")

    series: dict[str, pd.Series] = {}
    turnovers: dict[str, pd.Series] = {}
    positions: dict[str, pd.DataFrame] = {}

    def add(name: str, p: pd.Series | None, dynamic: bool, static_weights: list[float] | None = None) -> None:
        if dynamic:
            daily, turnover, weights = _portfolio_path(asset_returns, predictions, p, cost_bps, name, True)
        else:
            fixed_p = pd.Series(0.0, index=predictions.index)
            daily, turnover, weights = _portfolio_path(asset_returns, predictions, fixed_p, cost_bps, name, False)
            if static_weights is not None:
                # Hold the comparator's target weights for every day in the
                # holdout; changing only row zero would silently revert it to
                # the helper's default 60/20/20 allocation on day two.
                weights = pd.DataFrame(
                    np.tile(np.asarray(static_weights, dtype=float), (len(weights.index), 1)),
                    index=weights.index,
                    columns=REQUIRED_ASSETS,
                )
                aligned = asset_returns.reindex(weights.index).fillna(0.0).loc[:, list(REQUIRED_ASSETS)]
                turnover = (weights - weights.shift(1)).abs().sum(axis=1) / 2.0
                turnover.iloc[0] = 1.0
                gross = (aligned * weights.shift(1).fillna(weights)).sum(axis=1)
                # Static portfolios also enter at the first holdout close.
                gross.iloc[0] = 0.0
                daily = (1.0 + gross) * (1.0 - turnover * cost_bps / 10_000.0) - 1.0
                daily.name = name
        series[name] = daily
        turnovers[name] = turnover
        positions[name] = weights

    add("Selected-model risk-responsive", predictions["risk_probability"], True)
    add("Rolling-volatility rule", predictions["vol_baseline_probability"], True)
    add("Static 60 / 20 / 20", None, False, [0.60, 0.20, 0.20])
    add("Equal weight", None, False, [1 / 3, 1 / 3, 1 / 3])
    add("Equity buy-and-hold", None, False, [1.0, 0.0, 0.0])

    return_series = pd.DataFrame(series)
    metric_rows = []
    for name in return_series.columns:
        row = {"Strategy": name, **portfolio_metrics(return_series[name], turnovers[name], cost_bps)}
        metric_rows.append(row)
    metric_table = pd.DataFrame(metric_rows).set_index("Strategy")
    return return_series, metric_table, positions

