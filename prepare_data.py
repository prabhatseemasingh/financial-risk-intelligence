from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_series(path: Path, date_column: str, value_column: str, canonical: str) -> tuple[pd.Series, dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Source file does not exist: {path}")
    raw = pd.read_csv(path)
    missing = [name for name in (date_column, value_column) if name not in raw.columns]
    if missing:
        raise ValueError(f"{path.name}: missing selected column(s): {', '.join(missing)}")

    dates = pd.to_datetime(raw[date_column], errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    values = pd.to_numeric(raw[value_column], errors="coerce")
    series = pd.DataFrame({"Date": dates.dt.normalize(), canonical: values})
    invalid = series["Date"].isna() | series[canonical].isna()
    dropped_invalid = int(invalid.sum())
    series = series.loc[~invalid].copy()
    if series["Date"].duplicated().any():
        raise ValueError(f"{path.name}: duplicate dates exist. Resolve them at the source before combining.")
    if (series[canonical] <= 0).any():
        raise ValueError(f"{path.name}: return-index/price levels must be positive.")
    series = series.sort_values("Date").set_index("Date")[canonical]
    source_info = {
        "file_name": path.name,
        "sha256": sha256_file(path),
        "source_rows": len(raw),
        "usable_rows": len(series),
        "rows_dropped_for_missing_or_invalid_values": dropped_invalid,
        "date_column": date_column,
        "value_column": value_column,
    }
    return series, source_info


def merge_sources(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    files = [
        (Path(args.equity_file), args.equity_date, args.equity_value, "Equity_TR"),
        (Path(args.bond_file), args.bond_date, args.bond_value, "Bond_TR"),
        (Path(args.gold_file), args.gold_date, args.gold_value, "Gold_TR"),
    ]
    sources: dict[str, dict] = {}
    series_map: dict[str, pd.Series] = {}
    for path, date_column, value_column, canonical in files:
        series_map[canonical], sources[canonical] = read_series(path, date_column, value_column, canonical)

    before_counts = {name: len(series) for name, series in series_map.items()}
    combined = pd.concat(series_map.values(), axis=1, join="inner").dropna().sort_index()
    vix_info = None
    if args.vix_file:
        vix_series, vix_info = read_series(Path(args.vix_file), args.vix_date, args.vix_value, "India_VIX")
        combined = combined.join(vix_series, how="left")
        sources["India_VIX"] = vix_info

    if len(combined) < 100:
        raise ValueError(f"Only {len(combined)} aligned rows remain. At least 100 are required to prepare the file.")
    output = combined.reset_index(names="Date")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_note": args.source_note,
        "alignment": "Inner join on exact dates for equity, bond and gold. No price interpolation or synthetic rows.",
        "required_source_row_counts": before_counts,
        "aligned_rows": int(len(output)),
        "start_date": str(output["Date"].iloc[0].date()),
        "end_date": str(output["Date"].iloc[-1].date()),
        "optional_vix_file": vix_info,
        "sources": sources,
    }
    return output, manifest


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine separately downloaded authorized market CSVs by exact date; no data is fetched or filled."
    )
    parser.add_argument("--equity-file", required=True)
    parser.add_argument("--equity-date", required=True)
    parser.add_argument("--equity-value", required=True)
    parser.add_argument("--bond-file", required=True)
    parser.add_argument("--bond-date", required=True)
    parser.add_argument("--bond-value", required=True)
    parser.add_argument("--gold-file", required=True)
    parser.add_argument("--gold-date", required=True)
    parser.add_argument("--gold-value", required=True)
    parser.add_argument("--vix-file")
    parser.add_argument("--vix-date")
    parser.add_argument("--vix-value")
    parser.add_argument("--source-note", required=True)
    parser.add_argument("--output", default="data/processed/market_levels.csv")
    return parser


def main() -> None:
    parser = make_parser()
    args = parser.parse_args()
    if args.vix_file and not (args.vix_date and args.vix_value):
        parser.error("--vix-date and --vix-value are required when --vix-file is supplied.")
    destination = Path(args.output).resolve()
    if not destination.is_relative_to(PROJECT.resolve()):
        parser.error("--output must point to a file inside the project folder.")
    output, manifest = merge_sources(args)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = destination.with_suffix(".manifest.json")
    output.to_csv(destination, index=False, date_format="%Y-%m-%d")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {len(output):,} aligned rows: {manifest['start_date']} to {manifest['end_date']}")
    for name, before in manifest["required_source_row_counts"].items():
        print(f"{name}: {before:,} source rows")
    print("No interpolation was used. Review the manifest and confirm the source terms before modeling.")
    print(f"CSV: {destination}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
