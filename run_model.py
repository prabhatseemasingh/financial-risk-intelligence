from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from risk_intelligence.data import prepare_market_data
from risk_intelligence.evaluation import run_research


PROJECT = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT / "data" / "default_project_sample.csv"
DEFAULT_OUTPUT = PROJECT / "results" / "run_2026-11-03_default"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def project_path(path: Path, label: str) -> Path:
    """Resolve a CLI path and keep reads/writes inside the project directory."""
    resolved = path.resolve()
    if not resolved.is_relative_to(PROJECT.resolve()):
        raise ValueError(f"{label} must be inside the project folder: {path}")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the financial risk research model.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--holdout-sessions", type=int, default=756)
    parser.add_argument("--validation-sessions", type=int, default=252)
    parser.add_argument("--validation-folds", type=int, default=3)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()

    input_path = project_path(args.input, "Input data path")
    output_dir = project_path(args.output_dir, "Output directory")
    if not input_path.is_file():
        raise FileNotFoundError(f"Prepared input file not found: {input_path}")

    raw = pd.read_csv(input_path)
    prices, data_report = prepare_market_data(
        raw,
        date_column="Date",
        asset_columns=("Equity_TR", "Bond_TR", "Gold_TR"),
        source_note="User-authorized academic research input; see data/processed/README.md and data_manifest.json.",
    )
    result = run_research(
        prices,
        holdout_sessions=args.holdout_sessions,
        validation_sessions=args.validation_sessions,
        validation_folds=args.validation_folds,
        cost_bps=args.cost_bps,
    )

    holdout_start = result.holdout_predictions.index.min()
    fitted_regime_rows = result.regimes.loc[result.regimes.index < holdout_start]
    regime_fit_through = fitted_regime_rows.index.max() if not fitted_regime_rows.empty else None
    regime_counts = result.regimes["regime"].value_counts().sort_index().to_dict() if not result.regimes.empty else {}

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "portfolio_weights").mkdir(exist_ok=True)

    def save_frame(frame: pd.DataFrame, filename: str) -> None:
        data = frame.copy()
        data.index.name = data.index.name or "Date"
        data.to_csv(output_dir / filename, date_format="%Y-%m-%d", float_format="%.10g")

    result.validation_metrics.to_csv(output_dir / "validation_metrics.csv", index=False, float_format="%.10g")
    result.portfolio_metrics.to_csv(output_dir / "portfolio_metrics.csv", float_format="%.10g")
    result.cost_sensitivity.to_csv(output_dir / "cost_sensitivity.csv", index=False, float_format="%.10g")
    save_frame(result.holdout_predictions, "holdout_predictions.csv")
    save_frame(result.portfolio_returns, "portfolio_returns.csv")
    save_frame(result.feature_frame, "feature_history.csv")
    save_frame(result.regimes, "descriptive_regimes.csv")
    for strategy, weights in result.portfolio_weights.items():
        save_frame(weights, f"portfolio_weights/{safe_name(strategy)}.csv")

    summary = {
        "model_family_selected_on_development_only": result.selected_model,
        "current_high_risk_probability": result.current_probability,
        "current_forecast_as_of": result.current_features_date.strftime("%Y-%m-%d"),
        "training_only_high_risk_volatility_threshold": result.current_volatility_threshold,
        "high_risk_quantile": result.high_risk_quantile,
        "target_horizon_sessions": result.horizon,
        "holdout_start": result.holdout_predictions.index.min().strftime("%Y-%m-%d"),
        "holdout_end": result.holdout_predictions.index.max().strftime("%Y-%m-%d"),
        "holdout_prediction_rows": int(len(result.holdout_predictions)),
        "holdout_forecast_metrics": result.holdout_metrics,
        "validation_metrics": result.validation_metrics.to_dict(orient="records"),
        "portfolio_metrics": result.portfolio_metrics.reset_index().to_dict(orient="records"),
        "descriptive_regime_analysis": {
            "fit_through_date": regime_fit_through.strftime("%Y-%m-%d") if regime_fit_through is not None else None,
            "assigned_observations": int(len(result.regimes)),
            "assigned_counts": {str(name): int(count) for name, count in regime_counts.items()},
            "fit_error": result.regime_error,
        },
        "cost_bps": result.cost_bps,
        "data": {
            "file": input_path.relative_to(PROJECT.resolve()).as_posix(),
            "sha256": sha256(input_path),
            "rows_used": data_report.rows_used,
            "start_date": data_report.start_date.strftime("%Y-%m-%d"),
            "end_date": data_report.end_date.strftime("%Y-%m-%d"),
            "rows_dropped": data_report.rows_dropped,
        },
        "design": {
            "holdout_sessions": args.holdout_sessions,
            "validation_sessions": args.validation_sessions,
            "validation_folds": args.validation_folds,
            "seed": 42,
            "selection_metric": "Mean development-fold Brier score",
            "holdout_protocol": "Chronological prequential holdout; model family selected before holdout; training labels purged by the forward horizon.",
            "sharpe_convention": "Risk-free rate set to zero by current project implementation.",
            "dynamic_portfolio_rebalance": "Monthly signal at the final available holdout session; weights execute at the next session close and earn subsequent close-to-close returns.",
            "static_comparator_weights": {
                "Static 60 / 20 / 20": {"Equity_TR": 0.60, "Bond_TR": 0.20, "Gold_TR": 0.20},
                "Equal weight": {"Equity_TR": 1 / 3, "Bond_TR": 1 / 3, "Gold_TR": 1 / 3},
                "Equity buy-and-hold": {"Equity_TR": 1.0, "Bond_TR": 0.0, "Gold_TR": 0.0},
            },
            "transaction_cost_convention": "One-way turnover times the stated basis-point rate; initial holdout entry is charged consistently to every strategy.",
        },
        "permission_note": "User confirmed permission to train the model for this project on 2026-11-03. Public redistribution or deployment rights for raw data were not established by this run.",
        "interpretation_note": "Historical research results only; not investment advice or a claim of future performance. Gold input is split-adjusted Growth Plan NAV, not ETF exchange closing price or spot gold.",
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(json_safe(summary), indent=2, allow_nan=False), encoding="utf-8"
    )

    # A concise report is generated from the actual model outputs above.
    metric_rows = result.portfolio_metrics.reset_index().to_dict(orient="records")
    report_lines = [
        "# Model run results",
        "",
        f"- Data window: {data_report.start_date:%Y-%m-%d} to {data_report.end_date:%Y-%m-%d} ({data_report.rows_used:,} aligned rows)",
        f"- Locked holdout: {result.holdout_predictions.index.min():%Y-%m-%d} to {result.holdout_predictions.index.max():%Y-%m-%d} ({len(result.holdout_predictions):,} predictions)",
        f"- Model family selected on development folds: **{result.selected_model}**",
        f"- Current high-risk probability as of {result.current_features_date:%Y-%m-%d}: **{result.current_probability:.1%}**",
        f"- Forecast Brier score on holdout: **{result.holdout_metrics.get('Brier', float('nan')):.4f}**",
        f"- Descriptive clusters: **{len(result.regimes):,}** dates assigned using centroids fit through **{regime_fit_through:%Y-%m-%d}**" if regime_fit_through is not None else f"- Descriptive clusters: unavailable ({result.regime_error or 'no usable development history'})",
        "",
        "## Portfolio metrics on the holdout",
        "",
        "| Strategy | CAGR | Annualized volatility | Sharpe (Rf=0) | Max drawdown | Total turnover |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        strategy = row.get("Strategy", row.get("index", ""))
        report_lines.append(
            f"| {strategy} | {row.get('CAGR', float('nan')):.2%} | "
            f"{row.get('Annualized volatility', float('nan')):.2%} | "
            f"{row.get('Sharpe (Rf=0)', float('nan')):.3f} | "
            f"{row.get('Maximum drawdown', float('nan')):.2%} | "
            f"{row.get('Total one-way turnover', float('nan')):.2f} |"
        )
    report_lines.extend([
        "",
        "Forecast metrics, descriptive cluster counts, and complete assumptions are in `run_summary.json`; detailed predictions, returns, weights, regimes, and cost sensitivity are saved as CSV files in this folder.",
        "",
        "The final period was held out chronologically. Model selection used development-fold Brier score only. Results depend on the specified date window, NAV proxy, costs, rebalance rule, and zero-risk-free Sharpe convention; they are not a guarantee of future performance.",
        "Static comparator weights are held constant throughout the holdout. Dynamic weights use month-end holdout probabilities, execute at the next session close, and are charged for one-way turnover including initial entry.",
        "",
        "The user confirmed permission to train this project model. Separate permission to redistribute raw market data or include it in a public deployment was not established.",
    ])
    (output_dir / "README.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "output_dir": output_dir.relative_to(PROJECT.resolve()).as_posix(),
        "selected_model": result.selected_model,
        "holdout_start": result.holdout_predictions.index.min().strftime("%Y-%m-%d"),
        "holdout_end": result.holdout_predictions.index.max().strftime("%Y-%m-%d"),
        "holdout_rows": len(result.holdout_predictions),
        "holdout_brier": result.holdout_metrics.get("Brier"),
        "current_probability": result.current_probability,
    }, indent=2))


if __name__ == "__main__":
    main()
