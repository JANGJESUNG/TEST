"""EMA 크로스 + RSI 필터 기반 롱/숏 시그널 전략.

- LONG : 빠른 EMA가 느린 EMA를 상향 돌파 (골든크로스) + RSI가 과매수 아님
- SHORT: 빠른 EMA가 느린 EMA를 하향 돌파 (데드크로스) + RSI가 과매도 아님
- 손절/익절가는 ATR 배수로 제안
"""

from dataclasses import dataclass

from .config import Config
from .exchange import Candle
from .indicators import atr, ema, rsi


@dataclass
class Signal:
    symbol: str
    side: str          # "LONG" | "SHORT"
    price: float       # 진입 기준가 (시그널 캔들 종가)
    rsi: float
    ema_fast: float
    ema_slow: float
    stop_loss: float
    take_profit: float
    candle_close_time: int  # ms


def evaluate(symbol: str, candles: list[Candle], cfg: Config) -> Signal | None:
    """가장 최근 완결 캔들에서 크로스가 발생했는지 평가한다."""
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]

    fast = ema(closes, cfg.ema_fast)
    slow = ema(closes, cfg.ema_slow)
    rsi_vals = rsi(closes, cfg.rsi_period)
    atr_vals = atr(highs, lows, closes, cfg.atr_period)

    if len(fast) < 2 or len(slow) < 2 or not rsi_vals or not atr_vals:
        return None

    # 길이가 다른 시계열을 끝에서부터 맞춘다
    fast_prev, fast_now = fast[-2], fast[-1]
    slow_prev, slow_now = slow[-2], slow[-1]
    rsi_now = rsi_vals[-1]
    atr_now = atr_vals[-1]
    price = closes[-1]

    side = None
    if fast_prev <= slow_prev and fast_now > slow_now and rsi_now < cfg.rsi_long_max:
        side = "LONG"
    elif fast_prev >= slow_prev and fast_now < slow_now and rsi_now > cfg.rsi_short_min:
        side = "SHORT"

    if side is None:
        return None

    if side == "LONG":
        stop_loss = price - atr_now * cfg.atr_sl_mult
        take_profit = price + atr_now * cfg.atr_tp_mult
    else:
        stop_loss = price + atr_now * cfg.atr_sl_mult
        take_profit = price - atr_now * cfg.atr_tp_mult

    return Signal(
        symbol=symbol,
        side=side,
        price=price,
        rsi=rsi_now,
        ema_fast=fast_now,
        ema_slow=slow_now,
        stop_loss=stop_loss,
        take_profit=take_profit,
        candle_close_time=candles[-1].close_time,
    )
