from __future__ import annotations

from typing import cast

import httpx
import pandas as pd

from noesis_agent.data.storage import DataStore
from noesis_agent.logging.logger import get_logger

_logger = get_logger("data.collector")


class BinanceDataCollector:
    BASE_URL = "https://fapi.binance.com"

    def __init__(self, data_store: DataStore, symbols: list[str] | None = None) -> None:
        self._store = data_store
        self._symbols = symbols or ["BTCUSDT", "ETHUSDT"]

    def collect_funding_rates(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        response = httpx.get(
            f"{self.BASE_URL}/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": limit},
            timeout=15.0,
        )
        _ = response.raise_for_status()
        payload = cast(list[dict[str, object]], response.json())
        if not payload:
            return pd.DataFrame()

        frame = pd.DataFrame(payload)
        frame["timestamp"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
        frame["fundingRate"] = frame["fundingRate"].astype(float)
        frame["markPrice"] = frame["markPrice"].astype(float)
        frame = frame.set_index("timestamp")[["fundingRate", "markPrice"]]
        _ = self._store.save_snapshot("funding_rate", symbol, "history", frame)
        _logger.info("Collected %s funding rates for %s", len(frame), symbol)
        return frame

    def collect_open_interest(self, symbol: str, period: str = "1h", limit: int = 100) -> pd.DataFrame:
        response = httpx.get(
            f"{self.BASE_URL}/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
            timeout=15.0,
        )
        _ = response.raise_for_status()
        payload = cast(list[dict[str, object]], response.json())
        if not payload:
            return pd.DataFrame()

        frame = pd.DataFrame(payload)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        frame["sumOpenInterest"] = frame["sumOpenInterest"].astype(float)
        frame["sumOpenInterestValue"] = frame["sumOpenInterestValue"].astype(float)
        frame = frame.set_index("timestamp")[["sumOpenInterest", "sumOpenInterestValue"]]
        _ = self._store.save_snapshot("open_interest", symbol, period, frame)
        _logger.info("Collected %s OI records for %s", len(frame), symbol)
        return frame

    def collect_long_short_ratio(self, symbol: str, period: str = "1h", limit: int = 100) -> pd.DataFrame:
        response = httpx.get(
            f"{self.BASE_URL}/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
            timeout=15.0,
        )
        _ = response.raise_for_status()
        payload = cast(list[dict[str, object]], response.json())
        if not payload:
            return pd.DataFrame()

        frame = pd.DataFrame(payload)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        for column in ["longAccount", "shortAccount", "longShortRatio"]:
            frame[column] = frame[column].astype(float)
        frame = frame.set_index("timestamp")[["longAccount", "shortAccount", "longShortRatio"]]
        _ = self._store.save_snapshot("long_short_ratio", symbol, period, frame)
        _logger.info("Collected %s long/short records for %s", len(frame), symbol)
        return frame

    def collect_taker_buy_sell(self, symbol: str, period: str = "1h", limit: int = 100) -> pd.DataFrame:
        response = httpx.get(
            f"{self.BASE_URL}/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
            timeout=15.0,
        )
        _ = response.raise_for_status()
        payload = cast(list[dict[str, object]], response.json())
        if not payload:
            return pd.DataFrame()

        frame = pd.DataFrame(payload)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        for column in ["buySellRatio", "buyVol", "sellVol"]:
            frame[column] = frame[column].astype(float)
        frame = frame.set_index("timestamp")[["buySellRatio", "buyVol", "sellVol"]]
        _ = self._store.save_snapshot("taker_buy_sell", symbol, period, frame)
        _logger.info("Collected %s taker records for %s", len(frame), symbol)
        return frame

    def collect_all(self) -> dict[str, int]:
        results: dict[str, int] = {}
        for symbol in self._symbols:
            for name, method in [
                ("funding_rate", self.collect_funding_rates),
                ("open_interest", self.collect_open_interest),
                ("long_short_ratio", self.collect_long_short_ratio),
                ("taker_buy_sell", self.collect_taker_buy_sell),
            ]:
                try:
                    frame = method(symbol)
                    results[f"{symbol}_{name}"] = len(frame)
                except Exception as exc:
                    _logger.error("Failed to collect %s for %s: %s", name, symbol, exc)
                    results[f"{symbol}_{name}"] = 0
        return results
