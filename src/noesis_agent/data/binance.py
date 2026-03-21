# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import httpx
import pandas as pd

from noesis_agent.data.ingestion import OHLCV_COLUMNS, interval_to_milliseconds


class _BinanceKlinesAdapter:
    def __init__(
        self,
        *,
        source_id: str,
        base_url: str,
        market_label: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.source_id = source_id
        self._base_url = base_url
        self._market_label = market_label
        self._http_client = http_client or httpx.Client()

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame:
        params: dict[str, str | int] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        response = self._http_client.get(self._base_url, params=params, timeout=20.0)
        try:
            _ = response.raise_for_status()
            payload = cast(object, response.json())
        except httpx.HTTPStatusError as exc:
            payload = _response_json(exc.response)
            if isinstance(payload, dict):
                raise _binance_payload_error(
                    market_label=self._market_label,
                    symbol=symbol,
                    interval=interval,
                    payload=payload,
                ) from exc
            raise

        if isinstance(payload, dict):
            raise _binance_payload_error(
                market_label=self._market_label,
                symbol=symbol,
                interval=interval,
                payload=payload,
            )
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Binance payload for {symbol} {interval}: {payload!r}")

        return _payload_to_frame(payload)

    def fetch_klines_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame:
        interval_ms = interval_to_milliseconds(interval)
        cursor = start_time_ms
        total_span = max(end_time_ms - start_time_ms, 1)
        chunks: list[pd.DataFrame] = []

        while cursor <= end_time_ms:
            frame = self.fetch_klines(
                symbol=symbol,
                interval=interval,
                limit=1500,
                start_time_ms=cursor,
                end_time_ms=end_time_ms,
            )
            if frame.empty:
                break

            chunks.append(frame)
            last_open_ms = int(frame.index[-1].timestamp() * 1000)
            if progress_callback is not None:
                covered = min(max(last_open_ms - start_time_ms, 0), total_span)
                progress_callback(covered, total_span)

            next_cursor = last_open_ms + interval_ms
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(frame) < 1500:
                break

        if progress_callback is not None:
            progress_callback(total_span, total_span)

        if not chunks:
            return _empty_ohlcv_frame()

        combined = pd.concat(chunks).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        return combined.loc[:, OHLCV_COLUMNS]


class BinanceFuturesAdapter(_BinanceKlinesAdapter):
    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        super().__init__(
            source_id="binance_usdm",
            base_url="https://fapi.binance.com/fapi/v1/klines",
            market_label="Binance U本位合约",
            http_client=http_client,
        )


class BinanceSpotAdapter(_BinanceKlinesAdapter):
    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        super().__init__(
            source_id="binance_spot",
            base_url="https://api.binance.com/api/v3/klines",
            market_label="Binance 现货",
            http_client=http_client,
        )


def _payload_to_frame(payload: list[object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in payload:
        row = _as_row(item)
        rows.append(
            {
                "timestamp": pd.to_datetime(_to_int(row[0]), unit="ms", utc=True),
                "open": _to_float(row[1]),
                "high": _to_float(row[2]),
                "low": _to_float(row[3]),
                "close": _to_float(row[4]),
                "volume": _to_float(row[5]),
            }
        )
    if not rows:
        return _empty_ohlcv_frame()

    frame = pd.DataFrame(rows)
    frame = frame.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).set_index("timestamp")
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame.index.name = "timestamp"
    return frame.loc[:, OHLCV_COLUMNS]


def _empty_ohlcv_frame() -> pd.DataFrame:
    index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return pd.DataFrame(columns=OHLCV_COLUMNS, index=index)


def _as_row(item: object) -> list[object]:
    return cast(list[object], item)


def _to_int(value: object) -> int:
    return int(cast(int | str, value))


def _to_float(value: object) -> float:
    return float(cast(float | int | str, value))


def _response_json(response: httpx.Response) -> object:
    return cast(object, response.json())


def _binance_payload_error(
    *,
    market_label: str,
    symbol: str,
    interval: str,
    payload: dict[object, object],
) -> ValueError:
    error_message = str(payload.get("msg") or "unknown Binance error")
    return ValueError(f"{market_label} klines error for {symbol} {interval}: {error_message}")
