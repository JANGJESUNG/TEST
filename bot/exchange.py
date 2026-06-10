"""Binance USDT-M 선물 공개 시세 API 클라이언트 (API 키 불필요)."""

import os
from dataclasses import dataclass

import requests

# 지역/IP 차단 시 미러나 테스트넷(https://testnet.binancefuture.com)으로 교체 가능
BASE_URL = os.environ.get("BINANCE_FAPI_BASE", "https://fapi.binance.com")


@dataclass
class Candle:
    open_time: int   # ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int  # ms


class BinanceFutures:
    def __init__(self, timeout: float = 10.0):
        self.session = requests.Session()
        self.timeout = timeout

    def klines(self, symbol: str, interval: str, limit: int = 200) -> list[Candle]:
        """완결된 캔들만 반환한다 (마지막 진행 중 캔들은 제외)."""
        resp = self.session.get(
            f"{BASE_URL}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        rows = resp.json()
        candles = [
            Candle(
                open_time=int(r[0]),
                open=float(r[1]),
                high=float(r[2]),
                low=float(r[3]),
                close=float(r[4]),
                volume=float(r[5]),
                close_time=int(r[6]),
            )
            for r in rows
        ]
        return candles[:-1] if candles else []
