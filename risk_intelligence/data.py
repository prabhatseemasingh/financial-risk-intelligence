from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_ASSETS = ("Equity_TR", "Bond_TR", "Gold_TR")
OPTIONAL_COLUMNS = ("India_VIX",)


@dataclass
class DataReport:
    rows_uploaded: int
    rows_used: int
    rows_dropped: int
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    missing_optional: int
    source_note: str


def _as_date_series(values: pd.Series) -> pd.Series:
    dates = pd.to_datetime(values, errors="coerce")
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    return dates.dt.normalize()


def prepare_market_data(
    raw: pd.DataFrame,
    date_column: str,
    asset_columns: Iterable[str],
    vix_column: str | None = None,
    source_note: str = "Source not provided",
) -> tuple[pd.DataFrame, DataReport]:
    """Map user-selected input columns to the app schema and validate levels.

    Required asset rows with missing/non-numeric values are excluded after
    validation and counted in the report. They are never interpolated.
    """
    asset_columns = tuple(asset_columns)
    if len(asset_columns) != 3 or len(set(asset_columns)) != 3:
        raise ValueError("Select three different columns for equity, bonds and gold.")
    if date_column not in raw.columns:
        raise ValueError("The selected date column is missing from the uploaded file.")
    if any(column not in raw.columns for column in asset_columns):
        raise ValueError("One or more selected asset columns are missing.")

    rename = dict(zip(asset_columns, REQUIRED_ASSETS, strict=True))
    if vix_column and vix_column in raw.columns and vix_column not in asset_columns:
        rename[vix_column] = "India_VIX"

    columns = [date_column, *asset_columns]
    if vix_column and vix_column in raw.columns and vix_column not in asset_columns:
        columns.append(vix_column)
    data = raw.loc[:, columns].copy().rename(columns=rename)
    data.insert(0, "Date", _as_date_series(data.pop(date_column)))
    uploaded_rows = len(data)

    if data["Date"].isna().any():
        bad = int(data["Date"].isna().sum())
        raise ValueError(f"{bad} row(s) have an unreadable date. Correct or remove them at the source.")
    if data["Date"].duplicated().any():
        dupes = int(data["Date"].duplicated(keep=False).sum())
        raise ValueError(f"Found {dupes} rows with duplicate dates. Resolve duplicates before modeling.")

    for column in (*REQUIRED_ASSETS, *(('India_VIX',) if "India_VIX" in data.columns else ())):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if (data.loc[:, list(REQUIRED_ASSETS)].dropna() <= 0).any().any():
        raise ValueError("Asset return-index/price levels must be positive.")

    data = data.sort_values("Date").set_index("Date")
    required_complete = data.loc[:, REQUIRED_ASSETS].notna().all(axis=1)
    dropped = int((~required_complete).sum())
    data = data.loc[required_complete].copy()
    if len(data) < 100:
        raise ValueError("Fewer than 100 complete daily observations remain after date alignment.")
    if data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted after alignment.")

    missing_optional = 0
    if "India_VIX" in data.columns:
        data["India_VIX"] = data["India_VIX"].where(data["India_VIX"] > 0)
        missing_optional = int(data["India_VIX"].isna().sum())

    report = DataReport(
        rows_uploaded=uploaded_rows,
        rows_used=len(data),
        rows_dropped=dropped,
        start_date=data.index[0],
        end_date=data.index[-1],
        missing_optional=missing_optional,
        source_note=(source_note or "Source not provided").strip(),
    )
    return data, report


def data_quality_table(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in data.columns:
        s = data[name]
        rows.append({
            "Series": name,
            "Observations": int(s.notna().sum()),
            "Missing": int(s.isna().sum()),
            "Minimum": float(s.min()) if s.notna().any() else np.nan,
            "Maximum": float(s.max()) if s.notna().any() else np.nan,
        })
    return pd.DataFrame(rows)

