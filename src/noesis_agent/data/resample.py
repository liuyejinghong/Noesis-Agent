# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pandas as pd

from noesis_agent.data.ingestion import interval_to_milliseconds


@dataclass(slots=True)
class OhlcvValidationReport:
    row_count: int
    start_ts: str | None
    end_ts: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gap_count: int = 0
    max_gap_multiple: float = 1.0


def analyze_ohlcv(frame: pd.DataFrame, timeframe: str | None = None) -> OhlcvValidationReport:
    report = OhlcvValidationReport(
        row_count=len(frame),
        start_ts=None if frame.empty else str(frame.index.min()),
        end_ts=None if frame.empty else str(frame.index.max()),
    )
    errors: list[str] = []
    required_columns = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        errors.append(f"missing columns: {', '.join(missing)}")
        report.errors = errors
        return report
    if frame.empty:
        errors.append("dataframe is empty")
        report.errors = errors
        return report
    if not frame.index.is_monotonic_increasing:
        errors.append("timestamp index is not sorted ascending")
    if frame.index.has_duplicates:
        errors.append("timestamp index contains duplicates")
    if ((frame["high"] < frame["low"]) | (frame["high"] < frame["open"]) | (frame["high"] < frame["close"])).any():
        errors.append("high column violates OHLC bounds")
    if ((frame["low"] > frame["high"]) | (frame["low"] > frame["open"]) | (frame["low"] > frame["close"])).any():
        errors.append("low column violates OHLC bounds")
    report.errors = errors

    if timeframe is not None and not errors:
        expected_delta = pd.Timedelta(milliseconds=interval_to_milliseconds(timeframe))
        diffs = frame.index.to_series().diff().dropna()
        gap_diffs = diffs[diffs > expected_delta]
        if len(gap_diffs) > 0:
            report.gap_count = len(gap_diffs)
            report.max_gap_multiple = max((gap / expected_delta) for gap in gap_diffs)
            report.warnings.append(
                f"timestamp gaps detected: {report.gap_count} gap(s), max_gap_multiple={report.max_gap_multiple:.2f}"
            )
    return report


def validate_ohlcv(frame: pd.DataFrame, timeframe: str | None = None) -> list[str]:
    return analyze_ohlcv(frame, timeframe).errors


def resample_ohlcv(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    return cast(
        pd.DataFrame,
        frame.resample(timeframe)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(),
    )
