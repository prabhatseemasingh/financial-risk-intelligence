"""Code-path checks use generated fixture data only; it is not market data or a project result."""

import unittest

import numpy as np
import pandas as pd

from risk_intelligence.data import prepare_market_data
from risk_intelligence.evaluation import run_research
from risk_intelligence.features import build_features
from risk_intelligence.portfolio import weights_from_probability
from risk_intelligence.regimes import descriptive_regimes


def synthetic_fixture(rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(2026)
    common = rng.normal(0.0002, 0.008, rows)
    returns = {
        "Equity_TR": common + rng.normal(0.0001, 0.006, rows),
        "Bond_TR": -0.12 * common + rng.normal(0.0001, 0.003, rows),
        "Gold_TR": -0.18 * common + rng.normal(0.0001, 0.005, rows),
    }
    prices = {name: 100 * np.cumprod(1 + values) for name, values in returns.items()}
    prices["India_VIX"] = 18 + np.abs(rng.normal(0, 4, rows))
    return pd.DataFrame(prices, index=pd.bdate_range("2015-01-01", periods=rows))


class PipelineTests(unittest.TestCase):
    def test_forward_volatility_starts_after_signal_date(self):
        returns = np.array([0.01, -0.02, 0.03, 0.015, -0.01, 0.005, 0.02, -0.015, 0.01])
        levels = 100 * np.cumprod(1 + returns)
        prices = pd.DataFrame({
            "Equity_TR": levels,
            "Bond_TR": np.linspace(100, 101, len(levels)),
            "Gold_TR": np.linspace(100, 102, len(levels)),
        }, index=pd.bdate_range("2020-01-01", periods=len(levels)))
        _, forward_vol = build_features(prices, horizon=3)
        observed_returns = pd.Series(levels).pct_change(fill_method=None).to_numpy()
        expected = np.std(observed_returns[1:4], ddof=1) * np.sqrt(252)
        self.assertAlmostEqual(float(forward_vol.iloc[0]), float(expected), places=10)

    def test_column_mapping_sorts_and_counts_incomplete_rows(self):
        dates = pd.bdate_range("2024-01-01", periods=110)
        frame = pd.DataFrame({
            "session": dates[::-1],
            "nifty_tri": np.arange(110, 220, dtype=float)[::-1],
            "gsec_total_return": np.arange(210, 320, dtype=float)[::-1],
            "gold_inr": np.arange(310, 420, dtype=float)[::-1],
        })
        frame.loc[0, "gold_inr"] = np.nan
        cleaned, report = prepare_market_data(
            frame,
            "session",
            ("nifty_tri", "gsec_total_return", "gold_inr"),
            source_note="Synthetic unit-test fixture only",
        )
        self.assertTrue(cleaned.index.is_monotonic_increasing)
        self.assertEqual(report.rows_dropped, 1)
        self.assertEqual(report.rows_used, 109)

    def test_allocation_bounds_and_full_pipeline(self):
        low = weights_from_probability(0.0)
        high = weights_from_probability(1.0)
        self.assertAlmostEqual(float(low.sum()), 1.0)
        self.assertAlmostEqual(float(high.sum()), 1.0)
        self.assertAlmostEqual(float(low["Equity_TR"]), 0.60)
        self.assertAlmostEqual(float(high["Equity_TR"]), 0.30)
        self.assertTrue((high >= 0).all())

        prices = synthetic_fixture()
        result = run_research(
            prices,
            holdout_sessions=120,
            validation_sessions=60,
            validation_folds=2,
            min_training_sessions=300,
            cost_bps=10,
        )
        self.assertEqual(len(result.holdout_predictions), 120)
        self.assertTrue(result.holdout_predictions["risk_probability"].between(0, 1).all())
        self.assertIn("Selected-model risk-responsive", result.portfolio_metrics.index)
        self.assertTrue(result.cost_sensitivity["Cost assumption (bps)"].isin([5, 10, 25]).all())
        self.assertGreater(len(result.regimes), 0)
        self.assertTrue(result.regimes[["cluster_id", "regime", "equity_vol_21"]].notna().all().all())
        self.assertTrue(result.regimes.index.is_monotonic_increasing)

    def test_regime_fit_uses_only_history_through_development_cutoff(self):
        prices = synthetic_fixture()
        features, _ = build_features(prices)
        features = features.dropna(subset=["Equity_TR_ret_21", "equity_vol_21", "equity_drawdown_252"])
        cutoff = features.index[650]
        baseline = descriptive_regimes(features, training_end=cutoff)

        changed_future = features.copy()
        changed_future.loc[changed_future.index > cutoff, "equity_vol_21"] *= 10
        changed_future.loc[changed_future.index > cutoff, "equity_drawdown_252"] = -0.95
        perturbed = descriptive_regimes(changed_future, training_end=cutoff)

        pd.testing.assert_frame_equal(
            baseline.loc[:cutoff, ["cluster_id", "regime"]],
            perturbed.loc[:cutoff, ["cluster_id", "regime"]],
        )


if __name__ == "__main__":
    unittest.main()

