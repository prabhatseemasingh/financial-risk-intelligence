from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import HORIZON, build_features, complete_feature_rows
from .metrics import classification_metrics
from .portfolio import evaluate_portfolios
from .regimes import descriptive_regimes


MODEL_NAMES = (
    "Rolling-volatility baseline",
    "Logistic regression",
    "Random forest",
    "Gradient boosting",
)


def _estimator(name: str, seed: int = 42):
    if name == "Rolling-volatility baseline":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=2_000, random_state=seed),
        )
    if name == "Logistic regression":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=2_000, random_state=seed),
        )
    if name == "Random forest":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=250,
                max_depth=5,
                min_samples_leaf=15,
                max_features="sqrt",
                random_state=seed,
                n_jobs=-1,
            ),
        )
    if name == "Gradient boosting":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            GradientBoostingClassifier(
                n_estimators=150,
                learning_rate=0.03,
                max_depth=2,
                min_samples_leaf=15,
                random_state=seed,
            ),
        )
    raise ValueError(f"Unknown model: {name}")


def _model_features(name: str, feature_frame: pd.DataFrame) -> list[str]:
    if name == "Rolling-volatility baseline":
        return ["equity_vol_21"]
    return list(feature_frame.columns)


def _probabilities(model, x: pd.DataFrame) -> np.ndarray:
    if not hasattr(model, "predict_proba"):
        raise ValueError("Model does not provide probability forecasts.")
    classes = list(model.classes_) if hasattr(model, "classes_") else list(model[-1].classes_)
    if 1 not in classes:
        return np.zeros(len(x), dtype=float)
    return model.predict_proba(x)[:, classes.index(1)]


def _fit_model(name: str, x: pd.DataFrame, y: pd.Series, seed: int):
    y = pd.Series(y, index=x.index).astype(int)
    if y.nunique() < 2:
        raise ValueError("A training window contains only one target class; more history is required.")
    model = _estimator(name, seed)
    model.fit(x.loc[:, _model_features(name, x)], y)
    return model


@dataclass
class ResearchResult:
    feature_frame: pd.DataFrame
    forward_volatility: pd.Series
    validation_metrics: pd.DataFrame
    validation_predictions: dict[str, pd.DataFrame]
    selected_model: str
    holdout_predictions: pd.DataFrame
    holdout_metrics: dict[str, float]
    portfolio_returns: pd.DataFrame
    portfolio_metrics: pd.DataFrame
    cost_sensitivity: pd.DataFrame
    portfolio_weights: dict[str, pd.DataFrame]
    current_probability: float
    current_features_date: pd.Timestamp
    current_volatility_threshold: float
    regimes: pd.DataFrame
    regime_error: str | None
    holdout_sessions: int
    validation_sessions: int
    validation_folds: int
    horizon: int
    high_risk_quantile: float
    cost_bps: float


def run_research(
    prices: pd.DataFrame,
    *,
    holdout_sessions: int = 756,
    validation_sessions: int = 252,
    validation_folds: int = 3,
    min_training_sessions: int = 756,
    horizon: int = HORIZON,
    high_risk_quantile: float = 0.80,
    cost_bps: float = 10.0,
    seed: int = 42,
) -> ResearchResult:
    """Run development CV, a locked prequential holdout, and portfolio tests.

    Model family selection uses development folds only. The selected family is
    fixed before the final holdout. During that holdout it is refit every
    validation block using only labels whose forward window has completed.
    """
    if holdout_sessions <= 0 or validation_sessions <= 0 or validation_folds < 2:
        raise ValueError("Use positive holdout/block lengths and at least two validation folds.")
    if not 0.5 < high_risk_quantile < 0.99:
        raise ValueError("High-risk quantile must be between 0.50 and 0.99.")
    if cost_bps < 0 or not np.isfinite(cost_bps):
        raise ValueError("Transaction cost must be a finite non-negative number of basis points.")

    features_raw, forward_vol_raw = build_features(prices, horizon=horizon)
    features = complete_feature_rows(features_raw)
    labeled_index = features.index.intersection(forward_vol_raw.dropna().index)
    x_all = features.loc[labeled_index].copy()
    fwd_all = forward_vol_raw.loc[labeled_index].astype(float)
    n = len(x_all)
    holdout_start = n - holdout_sessions
    minimum_development = min_training_sessions + validation_folds * validation_sessions + horizon
    if holdout_start < minimum_development:
        required = minimum_development + holdout_sessions
        raise ValueError(
            f"Not enough labeled history for this design. Found {n:,} labeled feature rows; "
            f"the selected settings need at least {required:,}. Default settings usually need about ten years "
            "of daily data after feature warm-up. Keep the final holdout and shorten validation blocks only "
            "if the supervisor approves the revised design."
        )

    # Development folds end before the final holdout. The gap removes rows
    # whose forward label would cross into the next evaluation block.
    development_end = holdout_start
    first_validation_start = development_end - validation_folds * validation_sessions
    validation_predictions: dict[str, list[pd.DataFrame]] = {name: [] for name in MODEL_NAMES}
    fold_score_rows: list[dict[str, float | int | str]] = []

    for fold_number in range(validation_folds):
        val_start = first_validation_start + fold_number * validation_sessions
        val_end = min(val_start + validation_sessions, development_end)
        train_end = val_start - horizon
        if train_end < min_training_sessions:
            raise ValueError("The first validation fold has too little training history.")

        train_vol = fwd_all.iloc[:train_end]
        threshold = float(train_vol.quantile(high_risk_quantile))
        y_train = (train_vol > threshold).astype(int)
        y_val = (fwd_all.iloc[val_start:val_end] > threshold).astype(int)
        val_x = x_all.iloc[val_start:val_end]

        for model_number, name in enumerate(MODEL_NAMES):
            cols = _model_features(name, x_all)
            model = _fit_model(name, x_all.iloc[:train_end].loc[:, cols], y_train, seed + model_number + fold_number * 100)
            probability = _probabilities(model, val_x.loc[:, cols])
            frame = pd.DataFrame({
                "actual_high_risk": y_val.to_numpy(),
                "risk_probability": probability,
                "forward_volatility": fwd_all.iloc[val_start:val_end].to_numpy(),
                "training_threshold": threshold,
                "fold": fold_number + 1,
            }, index=val_x.index)
            validation_predictions[name].append(frame)
            fold_metrics = classification_metrics(y_val, probability)
            fold_score_rows.append({"Model": name, "Fold": fold_number + 1, **fold_metrics})

    validation_frames = {
        name: pd.concat(frames).sort_index() for name, frames in validation_predictions.items()
    }
    fold_scores = pd.DataFrame(fold_score_rows)
    summary_rows = []
    for name, frame in validation_frames.items():
        combined = classification_metrics(frame["actual_high_risk"], frame["risk_probability"])
        mean_fold_brier = float(fold_scores.loc[fold_scores["Model"] == name, "Brier"].mean())
        summary_rows.append({"Model": name, "Mean fold Brier": mean_fold_brier, **combined})
    validation_metrics = pd.DataFrame(summary_rows).sort_values("Mean fold Brier").reset_index(drop=True)
    selected_model = str(validation_metrics.iloc[0]["Model"])

    # Prequential final holdout: selection and hyperparameters remain frozen;
    # the same model family is refit only at the declared block boundaries.
    holdout_frames = []
    block_number = 0
    for block_start in range(holdout_start, n, validation_sessions):
        block_end = min(block_start + validation_sessions, n)
        train_end = block_start - horizon
        if train_end < min_training_sessions:
            continue
        train_vol = fwd_all.iloc[:train_end]
        threshold = float(train_vol.quantile(high_risk_quantile))
        y_train = (train_vol > threshold).astype(int)
        x_train = x_all.iloc[:train_end]
        test_x = x_all.iloc[block_start:block_end]
        model_features = _model_features(selected_model, x_all)
        model = _fit_model(selected_model, x_train.loc[:, model_features], y_train, seed + 5_000 + block_number)
        probability = _probabilities(model, test_x.loc[:, model_features])
        y_test = (fwd_all.iloc[block_start:block_end] > threshold).astype(int)
        vol_cutoff = float(x_train["equity_vol_21"].quantile(high_risk_quantile))
        vol_baseline = (test_x["equity_vol_21"] > vol_cutoff).astype(float)
        holdout_frames.append(pd.DataFrame({
            "actual_high_risk": y_test.to_numpy(),
            "risk_probability": probability,
            "vol_baseline_probability": vol_baseline.to_numpy(),
            "forward_volatility": fwd_all.iloc[block_start:block_end].to_numpy(),
            "training_threshold": threshold,
            "volatility_threshold": vol_cutoff,
            "fold": block_number + 1,
        }, index=test_x.index))
        block_number += 1
    holdout_predictions = pd.concat(holdout_frames).sort_index()
    if holdout_predictions.empty:
        raise ValueError("The selected settings produced no final-holdout predictions.")
    holdout_metrics = classification_metrics(
        holdout_predictions["actual_high_risk"], holdout_predictions["risk_probability"]
    )

    # The current forecast uses all completed labels through the latest data
    # date. It is displayed separately from the locked historical holdout.
    latest_features_date = features.index[-1]
    all_train_vol = fwd_all
    current_threshold = float(all_train_vol.quantile(high_risk_quantile))
    current_y = (all_train_vol > current_threshold).astype(int)
    current_model_features = _model_features(selected_model, features)
    current_model = _fit_model(
        selected_model,
        x_all.loc[:, current_model_features],
        current_y,
        seed + 9_999,
    )
    current_x = features.loc[[latest_features_date], current_model_features]
    current_probability = float(_probabilities(current_model, current_x)[0])

    portfolio_returns, portfolio_metrics, portfolio_weights = evaluate_portfolios(
        prices, holdout_predictions, cost_bps=cost_bps
    )
    sensitivity_rows = []
    for scenario_bps in (5.0, 10.0, 25.0):
        _, scenario_metrics, _ = evaluate_portfolios(prices, holdout_predictions, cost_bps=scenario_bps)
        for strategy, metric_row in scenario_metrics.iterrows():
            sensitivity_rows.append({"Cost assumption (bps)": scenario_bps, "Strategy": strategy, **metric_row.to_dict()})
    cost_sensitivity = pd.DataFrame(sensitivity_rows)
    regime_error = None
    try:
        # The feature frame also has the final 21 unlabeled dates. Use the
        # actual development cutoff date rather than a row count so no
        # holdout observations enter the descriptive cluster fit.
        regimes = descriptive_regimes(features, training_end=x_all.index[development_end - 1])
    except ValueError as exc:
        regimes = pd.DataFrame(columns=["cluster_id", "regime", "equity_vol_21"])
        regime_error = str(exc)

    return ResearchResult(
        feature_frame=features,
        forward_volatility=forward_vol_raw,
        validation_metrics=validation_metrics,
        validation_predictions=validation_frames,
        selected_model=selected_model,
        holdout_predictions=holdout_predictions,
        holdout_metrics=holdout_metrics,
        portfolio_returns=portfolio_returns,
        portfolio_metrics=portfolio_metrics,
        cost_sensitivity=cost_sensitivity,
        portfolio_weights=portfolio_weights,
        current_probability=current_probability,
        current_features_date=latest_features_date,
        current_volatility_threshold=current_threshold,
        regimes=regimes,
        regime_error=regime_error,
        holdout_sessions=holdout_sessions,
        validation_sessions=validation_sessions,
        validation_folds=validation_folds,
        horizon=horizon,
        high_risk_quantile=high_risk_quantile,
        cost_bps=float(cost_bps),
    )

