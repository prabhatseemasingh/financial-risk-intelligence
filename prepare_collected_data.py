from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parent
DOWNLOADS = Path.home() / "Downloads"
DEFAULT_GOLD = DOWNLOADS / "Nippon India ETF Gold BeES.csv"
DEFAULT_EQUITY = DOWNLOADS / "NIFTY 50 Total Returns Index (Gross).csv"
DEFAULT_BOND = DOWNLOADS / "Nifty 10 Yr Benchmark G-Sec.csv"
DEFAULT_OUTPUT = PROJECT / "data" / "processed" / "market_data_aligned.csv"
SPLIT_EFFECTIVE_DATE = pd.Timestamp("2019-12-19")
FIRST_POST_SPLIT_NAV_DATE = pd.Timestamp("2019-12-23")
GOLD_SPLIT_FACTOR = 100.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_series(
    path: Path,
    *,
    date_column: str,
    value_column: str,
    date_format: str,
    output_name: str,
    id_column: str | None = None,
    expected_id: str | None = None,
    expected_plan_column: str | None = None,
    expected_plan: str | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    raw = pd.read_csv(path)
    required = [date_column, value_column]
    if id_column:
        required.append(id_column)
    if expected_plan_column:
        required.append(expected_plan_column)
    missing_columns = [column for column in required if column not in raw.columns]
    if missing_columns:
        raise ValueError(f"{path.name} is missing expected columns: {missing_columns}")

    if id_column and expected_id:
        identifiers = raw[id_column].astype(str).str.strip().dropna().unique().tolist()
        if identifiers != [expected_id]:
            raise ValueError(f"Unexpected series name(s) in {path.name}: {identifiers}")
    if expected_plan_column and expected_plan:
        plans = raw[expected_plan_column].astype(str).str.strip().dropna().unique().tolist()
        if plans != [expected_plan]:
            raise ValueError(f"Unexpected plan(s) in {path.name}: {plans}")

    dates = pd.to_datetime(raw[date_column], format=date_format, errors="coerce")
    values = pd.to_numeric(raw[value_column], errors="coerce")
    bad_dates = int(dates.isna().sum())
    bad_values = int(values.isna().sum())
    if bad_dates or bad_values:
        raise ValueError(
            f"{path.name} has {bad_dates} unparseable date(s) and {bad_values} missing/non-numeric value(s)."
        )
    if dates.duplicated().any():
        examples = dates[dates.duplicated(keep=False)].dt.strftime("%Y-%m-%d").unique()[:5].tolist()
        raise ValueError(f"{path.name} has duplicate dates, including {examples}.")
    if (values <= 0).any():
        raise ValueError(f"{path.name} contains non-positive index/NAV levels.")

    series = pd.DataFrame({"Date": dates, output_name: values}).sort_values("Date")
    detail: dict[str, object] = {
        "file": path.name,
        "sha256": sha256(path),
        "source_rows": int(len(raw)),
        "valid_rows": int(len(series)),
        "duplicate_dates": 0,
        "missing_or_invalid_dates": bad_dates,
        "missing_or_non_numeric_values": bad_values,
        "non_positive_levels": 0,
        "first_date": series["Date"].min().strftime("%Y-%m-%d"),
        "last_date": series["Date"].max().strftime("%Y-%m-%d"),
        "source_value_column": value_column,
        "prepared_column": output_name,
    }
    return series, detail


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and exact-date-align the three collected project CSVs."
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--equity", type=Path, default=DEFAULT_EQUITY)
    parser.add_argument("--bond", type=Path, default=DEFAULT_BOND)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    gold, gold_info = read_series(
        args.gold,
        date_column="NAV DATE",
        value_column="NAV",
        date_format="%d-%m-%Y",
        output_name="Gold_TR",
        id_column="Scheme Name",
        expected_id="Nippon India ETF Gold BeES",
        expected_plan_column="Scheme Plan",
        expected_plan="Growth Plan",
    )
    equity, equity_info = read_series(
        args.equity,
        date_column="Date",
        value_column="Total Returns Index",
        date_format="%d-%b-%y",
        output_name="Equity_TR",
        id_column="IndexName",
        expected_id="NIFTY 50",
    )
    bond, bond_info = read_series(
        args.bond,
        date_column="Date",
        value_column="Close",
        date_format="%d-%b-%y",
        output_name="Bond_TR",
        id_column="Index Name",
        expected_id="NIFTY 10 YR BENCHMARK G-SEC",
    )

    # Gold BeES changed face value from Rs 100 to Rs 1 effective 2019-12-19.
    # The supplied NAV file remains on the old per-unit scale through 2019-12-20;
    # its first observation on the new scale is 2019-12-23. Convert all earlier
    # NAV observations to the post-split unit basis so the series stays continuous.
    pre_split_mask = gold["Date"] < FIRST_POST_SPLIT_NAV_DATE
    adjusted_rows = int(pre_split_mask.sum())
    gold.loc[pre_split_mask, "Gold_TR"] = gold.loc[pre_split_mask, "Gold_TR"] / GOLD_SPLIT_FACTOR

    aligned = equity.merge(bond, on="Date", how="inner", validate="one_to_one")
    aligned = aligned.merge(gold, on="Date", how="inner", validate="one_to_one")
    aligned = aligned.sort_values("Date").reset_index(drop=True)
    if aligned.empty:
        raise ValueError("The three files have no exact common dates.")
    if aligned[["Equity_TR", "Bond_TR", "Gold_TR"]].isna().any().any():
        raise ValueError("Missing levels remain after alignment; no values were filled.")
    if (aligned[["Equity_TR", "Bond_TR", "Gold_TR"]] <= 0).any().any():
        raise ValueError("Non-positive levels remain after alignment.")

    largest_moves: dict[str, dict[str, object]] = {}
    for column in ("Equity_TR", "Bond_TR", "Gold_TR"):
        returns = aligned.set_index("Date")[column].pct_change(fill_method=None).dropna()
        largest_date = returns.abs().idxmax()
        largest_moves[column] = {
            "date": largest_date.strftime("%Y-%m-%d"),
            "simple_return": float(returns.loc[largest_date]),
            "review_note": "Retained as observed; review against source, not automatically removed or winsorized.",
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    aligned["Date"] = aligned["Date"].dt.strftime("%Y-%m-%d")
    aligned.to_csv(args.output, index=False, float_format="%.10g")

    inputs = {"gold": gold_info, "equity": equity_info, "bond": bond_info}
    details = {
        "created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "output_file": str(args.output.resolve()),
        "output_sha256": sha256(args.output),
        "rows_used": int(len(aligned)),
        "start_date": str(aligned["Date"].iloc[0]),
        "end_date": str(aligned["Date"].iloc[-1]),
        "alignment": "Exact inner join on daily dates; no interpolation, forward fill, or backfill.",
        "rows_excluded_by_exact_join": {
            "gold": int(gold_info["valid_rows"]) - len(aligned),
            "equity": int(equity_info["valid_rows"]) - len(aligned),
            "bond": int(bond_info["valid_rows"]) - len(aligned),
        },
        "largest_absolute_daily_moves": largest_moves,
        "gold_split_adjustment": {
            "source_action": "NSE circular CML42873: Gold BeES face value changed from Rs 100 to Rs 1 effective 2019-12-19.",
            "factor": GOLD_SPLIT_FACTOR,
            "adjusted_rows": adjusted_rows,
            "adjustment_rule": f"Divide NAV observations dated before {FIRST_POST_SPLIT_NAV_DATE:%Y-%m-%d} by {GOLD_SPLIT_FACTOR:g}; the supplied file remains on the old unit basis through 2019-12-20 and first shows the new unit basis on 2019-12-23.",
            "classification": "Corporate-action unit adjustment; not an imputed observation.",
        },
        "source_rights_status": "User reports permission to train the project model, confirmed in conversation on 2026-11-03. Permission for public redistribution or deployment of raw data is not established by that confirmation.",
        "inputs": inputs,
    }
    manifest_path = args.output.with_name("data_manifest.json")
    manifest_path.write_text(json.dumps(details, indent=2), encoding="utf-8")

    print(json.dumps({
        "output": str(args.output.resolve()),
        "manifest": str(manifest_path.resolve()),
        "rows_used": len(aligned),
        "first_date": aligned["Date"].iloc[0],
        "last_date": aligned["Date"].iloc[-1],
        "gold_rows_split_adjusted": adjusted_rows,
        "excluded": details["rows_excluded_by_exact_join"],
    }, indent=2))


if __name__ == "__main__":
    main()

