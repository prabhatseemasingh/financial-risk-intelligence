from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from risk_intelligence.data import data_quality_table, prepare_market_data
from risk_intelligence.evaluation import run_research
from risk_intelligence.metrics import calibration_table
from risk_intelligence.portfolio import weights_from_probability

st.set_page_config(
    page_title="Financial Risk Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT_DIR = Path(__file__).resolve().parent
PUBLIC_SAMPLE_DATA_PATH = PROJECT_DIR / "data" / "default_project_sample.csv"
PREPARED_DATA_PATH = PUBLIC_SAMPLE_DATA_PATH
MAX_UPLOAD_MB = 10
MAX_UPLOAD_ROWS = 10_000
MAX_UPLOAD_COLUMNS = 50
PREPARED_SOURCE_NOTE = (
    "NIFTY 50 Gross TRI, Nifty 10 Yr Benchmark G-Sec, and split-adjusted Gold BeES Growth NAV; "
    "exact common trading dates; Gold BeES pre-2019-12-23 NAV divided by 100 per NSE circular CML42873; "
    "sources and limitations documented in data/DEFAULT_SAMPLE_SOURCE.md."
)
SAVED_RUN_DIR = PROJECT_DIR / "results" / "run_2026-11-03_default"
SAVED_REGIMES_PATH = SAVED_RUN_DIR / "descriptive_regimes.csv"
SAVED_SUMMARY_PATH = SAVED_RUN_DIR / "run_summary.json"


@st.cache_data(show_spinner=False)
def load_saved_regimes(path: str, modified_ns: int) -> pd.DataFrame:
    """Load the saved project's regime assignments for a local demo fallback."""
    del modified_ns  # Cache key changes when the artifact is replaced.
    frame = pd.read_csv(path, parse_dates=["Date"]).set_index("Date").sort_index()
    required = {"cluster_id", "regime", "equity_vol_21"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Saved regime file is missing columns: {', '.join(sorted(missing))}.")
    frame["equity_vol_21"] = pd.to_numeric(frame["equity_vol_21"], errors="coerce")
    frame = frame.dropna(subset=["regime", "equity_vol_21"])
    if frame.empty:
        raise ValueError("The saved regime file contains no complete cluster assignments.")
    return frame


@st.cache_data(show_spinner=False)
def load_saved_analysis(summary_path: str, modified_ns: int, expected_data_hash: str):
    """Rebuild the dashboard view from persisted outputs after a page refresh."""
    del modified_ns  # Cache key changes when the run is regenerated.
    summary_file = Path(summary_path)
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    if summary.get("data", {}).get("sha256") != expected_data_hash:
        raise ValueError("The saved analysis was produced from a different input file.")
    run_dir = summary_file.parent

    def read_indexed(filename: str) -> pd.DataFrame:
        frame = pd.read_csv(run_dir / filename, parse_dates=["Date"])
        return frame.set_index("Date").sort_index()

    regimes = load_saved_regimes(
        str(run_dir / "descriptive_regimes.csv"),
        (run_dir / "descriptive_regimes.csv").stat().st_mtime_ns,
    )
    weight_files = {
        "Selected-model risk-responsive": "selected_model_risk_responsive.csv",
        "Rolling-volatility rule": "rolling_volatility_rule.csv",
        "Static 60 / 20 / 20": "static_60_20_20.csv",
        "Equal weight": "equal_weight.csv",
        "Equity buy-and-hold": "equity_buy_and_hold.csv",
    }
    portfolio_weights = {
        name: read_indexed(str(Path("portfolio_weights") / filename))
        for name, filename in weight_files.items()
    }
    return SimpleNamespace(
        selected_model=summary["model_family_selected_on_development_only"],
        current_probability=float(summary["current_high_risk_probability"]),
        current_features_date=pd.Timestamp(summary["current_forecast_as_of"]),
        current_volatility_threshold=float(summary["training_only_high_risk_volatility_threshold"]),
        validation_metrics=pd.read_csv(run_dir / "validation_metrics.csv"),
        holdout_predictions=read_indexed("holdout_predictions.csv"),
        holdout_metrics=summary["holdout_forecast_metrics"],
        portfolio_returns=read_indexed("portfolio_returns.csv"),
        portfolio_metrics=pd.read_csv(run_dir / "portfolio_metrics.csv", index_col=0),
        cost_sensitivity=pd.read_csv(run_dir / "cost_sensitivity.csv"),
        portfolio_weights=portfolio_weights,
        regimes=regimes,
        regime_error=summary.get("descriptive_regime_analysis", {}).get("fit_error"),
        cost_bps=float(summary["cost_bps"]),
        design=summary.get("design", {}),
    )


PREPARED_DATA_HASH = (
    hashlib.sha256(PREPARED_DATA_PATH.read_bytes()).hexdigest()
    if PREPARED_DATA_PATH.is_file()
    else None
)
PIPELINE_FILES = (
    "data.py",
    "evaluation.py",
    "features.py",
    "metrics.py",
    "portfolio.py",
    "regimes.py",
)
PIPELINE_CODE_HASH = hashlib.sha256(
    b"".join((PROJECT_DIR / "risk_intelligence" / name).read_bytes() for name in PIPELINE_FILES)
).hexdigest()
SAVED_REGIMES_ERROR = None
try:
    SAVED_REGIMES = (
        load_saved_regimes(str(SAVED_REGIMES_PATH), SAVED_REGIMES_PATH.stat().st_mtime_ns)
        if SAVED_REGIMES_PATH.is_file()
        else pd.DataFrame()
    )
except (OSError, ValueError, pd.errors.ParserError) as exc:
    SAVED_REGIMES = pd.DataFrame()
    SAVED_REGIMES_ERROR = str(exc)
SAVED_ANALYSIS = None
SAVED_ANALYSIS_ERROR = None
try:
    if SAVED_SUMMARY_PATH.is_file() and PREPARED_DATA_HASH:
        SAVED_ANALYSIS = load_saved_analysis(
            str(SAVED_SUMMARY_PATH),
            SAVED_SUMMARY_PATH.stat().st_mtime_ns,
            PREPARED_DATA_HASH,
        )
except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
    SAVED_ANALYSIS_ERROR = str(exc)


def chart_sample(frame: pd.DataFrame, max_rows: int = 400) -> pd.DataFrame:
    """Thin chart-only data while preserving the full research series elsewhere."""
    if len(frame) <= max_rows:
        return frame
    stride = max(1, (len(frame) + max_rows - 1) // max_rows)
    positions = set(range(0, len(frame), stride))
    positions.add(len(frame) - 1)
    return frame.iloc[sorted(positions)]


st.title("Financial Risk Intelligence")
st.caption("Research prototype for high-volatility forecasting and risk-responsive portfolio evaluation")
st.warning(
    "Educational research tool only. It does not provide investment advice, execute trades, "
    "or guarantee future performance. The aligned project sample is loaded by default; new uploads "
    "refresh the analysis for your session only."
)

with st.sidebar:
    st.header("1. Add verified data")
    use_prepared_data = st.checkbox(
        "Use the prepared project sample (2015–2026)",
        value=PREPARED_DATA_PATH.is_file(),
        disabled=not PREPARED_DATA_PATH.is_file(),
        help="Loads the aligned common-date project CSV. Uncheck this option to upload a newer CSV.",
    )
    uploaded = st.file_uploader(
        "Upload a CSV of daily index or adjusted-price levels",
        type=["csv"],
        disabled=use_prepared_data,
        max_upload_size=MAX_UPLOAD_MB,
        help=f"One combined CSV, up to {MAX_UPLOAD_MB} MB and {MAX_UPLOAD_ROWS:,} data rows. Use daily observations; do not upload generated or interpolated market data.",
    )
    st.caption("Only the sample or CSV you select is sent to Streamlit for analysis. This code does not scan your device or save uploads to disk or GitHub. Do not upload personal or sensitive files.")
    st.markdown(
        "Required series: equity total-return level, government-bond total-return level, "
        "and an adjusted domestic-gold proxy level. India VIX is optional."
    )
    template_path = Path(__file__).parent / "data" / "market_data_template.csv"
    try:
        with template_path.open("rb") as template_file:
            st.download_button(
                "Download empty CSV template",
                template_file.read(),
                file_name="market_data_template.csv",
                mime="text/csv",
            )
    except OSError:
        pass

    raw = None
    prices = None
    report = None
    upload_hash = None
    input_name = None
    source_note = ""
    if use_prepared_data:
        try:
            raw_bytes = PREPARED_DATA_PATH.read_bytes()
            upload_hash = hashlib.sha256(raw_bytes).hexdigest()
            input_name = PREPARED_DATA_PATH.name
            raw = pd.read_csv(BytesIO(raw_bytes))
            source_note = PREPARED_SOURCE_NOTE
            st.caption("Using the prepared sample; see Data and method for its date range and source notes.")
        except Exception as exc:
            st.error(f"Could not load the prepared project data: {exc}")
    elif uploaded is not None:
        raw_bytes = uploaded.getvalue()
        input_name = uploaded.name.replace("\\", "/").rsplit("/", 1)[-1]
        if len(raw_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"The CSV is larger than the {MAX_UPLOAD_MB} MB limit.")
        else:
            upload_hash = hashlib.sha256(raw_bytes).hexdigest()
            try:
                raw = pd.read_csv(BytesIO(raw_bytes), nrows=MAX_UPLOAD_ROWS + 1)
                if len(raw) > MAX_UPLOAD_ROWS:
                    raw = None
                    st.error(f"The CSV exceeds the {MAX_UPLOAD_ROWS:,}-row limit. Prepare a smaller daily history and upload it again.")
                elif len(raw.columns) > MAX_UPLOAD_COLUMNS:
                    raw = None
                    st.error(f"The CSV has more than {MAX_UPLOAD_COLUMNS} columns. Upload only the required market series and optional India VIX.")
            except Exception as exc:  # Show a useful file-specific error in the interface.
                st.error(f"Could not read this CSV: {exc}")

    if raw is not None and not raw.empty:
        columns = list(raw.columns)

        def suggested(options: list[str], hints: tuple[str, ...]) -> str:
            lowered = {str(c).lower(): c for c in options}
            for hint in hints:
                for key, original in lowered.items():
                    if hint in key:
                        return original
            return options[0]

        date_col = st.selectbox("Date column", columns, index=columns.index(suggested(columns, ("date", "time"))))
        remaining = [c for c in columns if c != date_col]
        if len(remaining) < 3:
            st.error("The CSV needs a date column and three asset level columns.")
        else:
            eq_guess = suggested(remaining, ("equity_tr", "nifty", "equity", "stock"))
            equity_col = st.selectbox("Equity total-return level", remaining, index=remaining.index(eq_guess))
            after_equity = [c for c in remaining if c != equity_col]
            bond_guess = suggested(after_equity, ("bond_tr", "bond", "gsec", "government"))
            bond_col = st.selectbox("Government-bond total-return level", after_equity, index=after_equity.index(bond_guess))
            after_bond = [c for c in after_equity if c != bond_col]
            gold_guess = suggested(after_bond, ("gold_tr", "gold"))
            gold_col = st.selectbox("Adjusted domestic-gold proxy level", after_bond, index=after_bond.index(gold_guess))
            vix_options = ["No India VIX"] + [c for c in remaining if c not in {equity_col, bond_col, gold_col}]
            vix_guess = suggested(vix_options[1:], ("india_vix", "vix")) if len(vix_options) > 1 else "No India VIX"
            vix_col = st.selectbox("Optional volatility index", vix_options, index=vix_options.index(vix_guess) if vix_guess in vix_options else 0)
            source_note = st.text_input(
                "Source and return-definition note",
                value=source_note,
                placeholder="Example: provider, series names, retrieval date, TRI/adjusted-level convention",
                disabled=use_prepared_data,
            )
            if use_prepared_data:
                rights_confirmed = True
            else:
                rights_confirmed = st.checkbox(
                    "I have checked the source terms and confirmed these are comparable daily return levels."
                )
            mapping_signature = hashlib.sha256(
                repr((upload_hash, date_col, equity_col, bond_col, gold_col, vix_col)).encode("utf-8")
            ).hexdigest()
            if st.session_state.get("mapping_signature") != mapping_signature:
                st.session_state["mapping_signature"] = mapping_signature
                st.session_state.pop("research_result", None)
                st.session_state.pop("research_result_signature", None)
                st.session_state.pop("attempted_run_signature", None)
                st.session_state.pop("data_report", None)
                st.session_state.pop("prepared_data", None)
            if rights_confirmed:
                try:
                    prices, report = prepare_market_data(
                        raw,
                        date_col,
                        (equity_col, bond_col, gold_col),
                        None if vix_col == "No India VIX" else vix_col,
                        source_note=source_note,
                    )
                except Exception as exc:
                    st.error(str(exc))
            else:
                st.session_state.pop("research_result", None)
                st.session_state.pop("research_result_signature", None)
                st.session_state.pop("data_report", None)
                st.session_state.pop("prepared_data", None)
                st.info("Confirm source rights and return definitions to enable analysis.")
            if rights_confirmed and not source_note.strip():
                st.info("Enter a short source note before running the research pipeline.")

    st.header("2. Evaluation settings")
    holdout_choice = st.selectbox("Final holdout", ["3 years (756 sessions)", "2 years (504 sessions)"], index=0)
    holdout_sessions = 756 if holdout_choice.startswith("3") else 504
    validation_choice = st.selectbox("Development validation block", ["1 year (252 sessions)", "6 months (126 sessions)"], index=0)
    validation_sessions = 252 if validation_choice.startswith("1") else 126
    validation_folds = st.selectbox("Development folds", [3, 2], index=0)
    cost_bps = st.selectbox("Base transaction-cost assumption", [10, 5, 25], index=0)
    st.caption("These are research assumptions. Agree on them before interpreting results.")
    st.caption("After data and source confirmation, analysis refreshes automatically when the file, column mapping, or settings change. Uploaded files are processed for this session and do not replace the shared sample.")
    run_clicked = st.button(
        "Run / refresh walk-forward analysis",
        type="primary",
        disabled=prices is None or not source_note.strip(),
    )

if upload_hash is not None and st.session_state.get("upload_hash") != upload_hash:
    st.session_state["upload_hash"] = upload_hash
    st.session_state.pop("research_result", None)
    st.session_state.pop("research_result_signature", None)
    st.session_state.pop("attempted_run_signature", None)
    st.session_state.pop("data_report", None)
    st.session_state.pop("prepared_data", None)
if upload_hash is None:
    st.session_state.pop("upload_hash", None)
    st.session_state.pop("mapping_signature", None)
    st.session_state.pop("research_result", None)
    st.session_state.pop("research_result_signature", None)
    st.session_state.pop("attempted_run_signature", None)
    st.session_state.pop("data_report", None)
    st.session_state.pop("prepared_data", None)

run_signature = (
    hashlib.sha256(
        repr((
            upload_hash,
            st.session_state.get("mapping_signature"),
            holdout_sessions,
            validation_sessions,
            validation_folds,
            float(cost_bps),
            PIPELINE_CODE_HASH,
        )).encode("utf-8")
    ).hexdigest()
    if upload_hash is not None
    else None
)
if (
    st.session_state.get("research_result") is not None
    and st.session_state.get("research_result_signature") != run_signature
):
    st.session_state.pop("research_result", None)
    st.session_state.pop("research_result_signature", None)

if prices is not None and report is not None:
    st.session_state["prepared_data"] = prices
    st.session_state["data_report"] = report
auto_run = (
    prices is not None
    and report is not None
    and bool(source_note.strip())
    and run_signature is not None
    and st.session_state.get("research_result_signature") != run_signature
    and st.session_state.get("attempted_run_signature") != run_signature
)
if (run_clicked or auto_run) and prices is not None:
    st.session_state["attempted_run_signature"] = run_signature
    try:
        with st.spinner("Building features, selecting a model on development folds, and scoring the final holdout…"):
            result = run_research(
                prices,
                holdout_sessions=holdout_sessions,
                validation_sessions=validation_sessions,
                validation_folds=validation_folds,
                cost_bps=float(cost_bps),
            )
        st.session_state["research_result"] = result
        st.session_state["research_result_signature"] = run_signature
        st.session_state["data_report"] = report
        st.session_state["prepared_data"] = prices
        st.success("Analysis completed from the selected market observations.")
    except Exception as exc:
        st.session_state.pop("research_result", None)
        st.session_state.pop("research_result_signature", None)
        st.error(f"Analysis could not run: {exc}")

result = st.session_state.get("research_result")
showing_saved_analysis = False
if result is None and upload_hash == PREPARED_DATA_HASH and SAVED_ANALYSIS is not None:
    saved_design = SAVED_ANALYSIS.design
    saved_settings_match = (
        saved_design.get("holdout_sessions") == holdout_sessions
        and saved_design.get("validation_sessions") == validation_sessions
        and saved_design.get("validation_folds") == validation_folds
        and float(SAVED_ANALYSIS.cost_bps) == float(cost_bps)
    )
    if saved_settings_match:
        result = SAVED_ANALYSIS
        showing_saved_analysis = True
prices = st.session_state.get("prepared_data", prices)
report = st.session_state.get("data_report", report)

if prices is None or report is None:
    st.info(
        "Start by uploading an authorized daily CSV and mapping the date, equity, bond and gold columns. "
        "The project folder includes the expected column format and source guidance."
    )
    st.subheader("Study workflow")
    st.markdown(
        "1. Verify the data source, rights, currency and total-return convention.\n"
        "2. Upload daily levels and map the columns in the left panel.\n"
        "3. Run the development comparison and prequential final holdout.\n"
        "4. Review forecast quality, portfolio results after costs, and the saved assumptions."
    )
    st.stop()

report_cols = st.columns(4)
report_cols[0].metric("Aligned daily rows", f"{report.rows_used:,}")
report_cols[1].metric("First date", report.start_date.strftime("%Y-%m-%d"))
report_cols[2].metric("Last date", report.end_date.strftime("%Y-%m-%d"))
report_cols[3].metric("Rows excluded", f"{report.rows_dropped:,}")
if showing_saved_analysis:
    st.info("Showing the saved default walk-forward run for the selected sample and settings. Click **Run walk-forward analysis** to recompute it.")
elif upload_hash == PREPARED_DATA_HASH and SAVED_ANALYSIS_ERROR:
    st.warning(f"Saved analysis outputs could not be loaded: {SAVED_ANALYSIS_ERROR}")
if report.rows_dropped:
    st.warning(f"Excluded {report.rows_dropped:,} rows with missing or non-numeric required asset levels. No values were interpolated.")
if report.missing_optional:
    st.caption(f"India VIX has {report.missing_optional:,} missing values. The model imputes these inside each training fold only.")

tabs = st.tabs(["Overview", "Regimes", "Risk forecast", "Portfolio", "Data and method"])

with tabs[0]:
    st.subheader("Market observations")
    levels = prices[["Equity_TR", "Bond_TR", "Gold_TR"]].copy()
    normalized = levels.div(levels.iloc[0]).mul(100)
    st.line_chart(chart_sample(normalized), height=320)
    st.caption("Series are rebased to 100 at the first common date. The display is thinned for responsiveness; calculations use every aligned daily row. Confirm each series is a total-return or adjusted-return level before comparing them.")
    if result is None:
        if upload_hash == PREPARED_DATA_HASH and not SAVED_REGIMES.empty:
            st.info("Saved descriptive clusters are available in the Regimes tab. The forecast, holdout evaluation and portfolio comparison will appear after the analysis finishes.")
        else:
            st.info("The analysis is starting for this data and these settings. It will rerun automatically when they change.")
    else:
        latest_cols = st.columns(3)
        latest_cols[0].metric("Current high-risk probability", f"{result.current_probability:.1%}")
        latest_cols[1].metric("Forecast as of", result.current_features_date.strftime("%Y-%m-%d"))
        latest_cols[2].metric("Model family selected on development folds", result.selected_model)
        st.caption(
            f"The forecast uses features through {result.current_features_date:%Y-%m-%d}; training uses only forward labels "
            "whose full 21-session windows were observed by the latest input date. It is separate from final-holdout scores."
        )

with tabs[1]:
    st.subheader("Descriptive volatility regimes")
    live_regime_error = getattr(result, "regime_error", None) if result is not None else None
    if live_regime_error:
        st.warning(f"The latest clustering attempt could not complete: {live_regime_error}")
    regime_frame = None
    showing_saved_regimes = False
    if result is not None and not result.regimes.empty:
        regime_frame = result.regimes
        showing_saved_regimes = showing_saved_analysis
    elif upload_hash == PREPARED_DATA_HASH and not SAVED_REGIMES.empty:
        regime_frame = SAVED_REGIMES
        showing_saved_regimes = True
    if regime_frame is None or regime_frame.empty:
        if SAVED_REGIMES_ERROR and upload_hash == PREPARED_DATA_HASH:
            st.warning(f"Saved regime results could not be loaded: {SAVED_REGIMES_ERROR}")
        st.info("Run the analysis to fit descriptive clusters on the development history.")
    else:
        regime_positions = set(range(0, len(regime_frame), max(1, (len(regime_frame) + 399) // 400)))
        regime_positions.add(len(regime_frame) - 1)
        regime_positions.update(
            regime_frame.index.get_indexer_for(
                regime_frame.index[regime_frame["regime"].ne(regime_frame["regime"].shift())]
            ).tolist()
        )
        regime_positions.update(
            regime_frame.index.get_indexer_for(
                regime_frame.index[regime_frame["regime"].str.contains("higher trailing vol", regex=False)]
            ).tolist()
        )
        regime_plot = regime_frame.iloc[sorted(regime_positions)].reset_index(names="Date")
        st.scatter_chart(regime_plot, x="Date", y="equity_vol_21", color="regime", height=340)
        st.caption("K-means clusters are descriptive and are ordered only by median trailing 21-session volatility in the fit sample. The plot is thinned for responsiveness while preserving regime changes and higher-volatility points; the download contains all assigned dates. These are not future labels or buy/sell signals.")
        if showing_saved_regimes:
            st.caption(
                "Showing the saved 2026-11-03 project run. Clusters were fitted through the development cutoff "
                "and then assigned across the available history. Run the analysis to refit for new settings or data."
            )
        latest_regime = regime_frame.iloc[-1]
        st.write(f"Latest descriptive cluster: **{latest_regime['regime']}**")
        st.download_button(
            "Download full daily regime assignments as CSV",
            regime_frame.to_csv(index_label="Date").encode("utf-8"),
            file_name="descriptive_regimes.csv",
            mime="text/csv",
        )

with tabs[2]:
    st.subheader("Risk forecast evidence")
    if result is None:
        st.info("Run the analysis to compare candidate models on development folds and evaluate the selected family on the final holdout.")
    else:
        st.markdown(f"**Model family selected using development folds:** {result.selected_model}")
        st.caption("Selection uses development Brier scores only. The final holdout remains chronologically later and is not used for model selection.")
        st.dataframe(result.validation_metrics.style.format(precision=4), use_container_width=True)
        holdout_metrics = pd.DataFrame([result.holdout_metrics], index=["Selected model, final holdout"])
        st.markdown("**Final holdout forecast scores**")
        st.dataframe(holdout_metrics.style.format(precision=4), use_container_width=True)
        forecast_plot = result.holdout_predictions[["risk_probability", "actual_high_risk"]].rename(
            columns={"risk_probability": "Forecast probability", "actual_high_risk": "Observed high-risk event"}
        )
        st.line_chart(chart_sample(forecast_plot), height=300)
        calibration = calibration_table(
            result.holdout_predictions["actual_high_risk"],
            result.holdout_predictions["risk_probability"],
        )
        st.markdown("**Final holdout calibration bins**")
        st.dataframe(calibration, use_container_width=True, hide_index=True)
        st.download_button(
            "Download holdout forecasts as CSV",
            result.holdout_predictions.to_csv(index_label="Date").encode("utf-8"),
            file_name="holdout_forecasts.csv",
            mime="text/csv",
        )

with tabs[3]:
    st.subheader("Portfolio comparison")
    if result is None:
        st.info("Run the analysis to calculate monthly allocations and compare them with static baselines after transaction costs.")
    else:
        st.caption(
            f"Risk probability source: {result.selected_model}. Dynamic rule: equity weight = 60% − 30% × probability; remaining weight split equally between bonds and gold. "
            f"Signals are formed after close and applied at the next session close. Base cost assumption: {result.cost_bps:.0f} bps per one-way turnover."
        )
        st.dataframe(result.portfolio_metrics.style.format(precision=4), use_container_width=True)
        wealth = (1 + result.portfolio_returns).cumprod()
        st.line_chart(chart_sample(wealth), height=340)
        st.markdown("**Transaction-cost sensitivity**")
        st.dataframe(result.cost_sensitivity.style.format(precision=4), use_container_width=True, hide_index=True)
        latest_weights = result.portfolio_weights["Selected-model risk-responsive"].iloc[-1]
        weight_view = pd.DataFrame({"Latest held weight": latest_weights}).style.format("{:.1%}")
        st.markdown("**Latest held allocation for the selected-model risk-responsive strategy**")
        st.dataframe(weight_view, use_container_width=True)
        portfolio_export = result.portfolio_returns.join(result.portfolio_weights["Selected-model risk-responsive"].add_prefix("Weight "))
        st.download_button(
            "Download portfolio path and weights as CSV",
            portfolio_export.to_csv(index_label="Date").encode("utf-8"),
            file_name="portfolio_path.csv",
            mime="text/csv",
        )
        st.caption("Sharpe uses a zero risk-free proxy. VaR and CVaR are historical one-day loss estimates. Results depend on the uploaded sample and the stated cost assumption.")

with tabs[4]:
    st.subheader("Data provenance and method")
    st.write(f"**Source note:** {report.source_note or 'No source note supplied.'}")
    if upload_hash:
        st.write(f"**Input file:** {input_name or 'Uploaded CSV'}")
        st.code(f"SHA-256: {upload_hash}")
    st.write(f"**Sample:** {report.start_date:%Y-%m-%d} to {report.end_date:%Y-%m-%d}")
    st.dataframe(data_quality_table(prices).style.format(precision=4), use_container_width=True, hide_index=True)
    st.markdown(
        "**Target:** forward annualized 21-session equity volatility exceeds the training-fold 80th percentile.  "
        "**Features:** lagged 1/5/21-session returns, trailing 21/63-session volatility, drawdown and cross-asset correlations; India VIX is optional.  "
        "**Evaluation:** chronological development folds, a 21-session label purge, a later holdout with annual refits, and next-session-close execution."
    )
    st.markdown("**Primary source references**")
    st.markdown(
        "- [NSE historical index, India VIX, TRI and ETF archives](https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives)\n"
        "- [Nifty Indices historical data and fixed-income return convention](https://www.niftyindices.com/reports/historical-data)\n"
        "- [NSE index FAQ: NIFTY 50 Total Returns Index](https://www.nseindia.com/static/products-services/indices-faqs)\n"
        "- [RBI Database on Indian Economy](https://dbie.rbi.org.in/)\n"
        "- [scikit-learn time-series cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split)\n"
        "- [Streamlit Community Cloud dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)"
    )
    st.markdown(
        "[Default sample preparation record, source fingerprints and Gold BeES adjustment]("
        "https://github.com/prabhatseemasingh/financial-risk-intelligence/blob/main/data/DEFAULT_SAMPLE_SOURCE.md)."
    )
    st.error("No live prices are fetched. The app reports only calculations from the selected input file and labels the date of the latest data.")

st.divider()
st.caption("Research prototype. Verify data rights and assumptions. Historical results do not predict future performance.")
