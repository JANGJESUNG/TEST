import unittest

from bot.config import Config
from bot.exchange import Candle
from bot.indicators import atr, ema, rsi
from bot.strategy import evaluate


def make_candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            open_time=i * 60_000,
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=1.0,
            close_time=i * 60_000 + 59_999,
        )
        for i, c in enumerate(closes)
    ]


class IndicatorTests(unittest.TestCase):
    def test_ema_constant_series(self):
        values = [100.0] * 50
        result = ema(values, 9)
        self.assertTrue(all(abs(v - 100.0) < 1e-9 for v in result))

    def test_ema_too_short(self):
        self.assertEqual(ema([1.0, 2.0], 5), [])

    def test_rsi_all_gains_is_100(self):
        closes = [float(i) for i in range(1, 40)]
        result = rsi(closes, 14)
        self.assertTrue(all(v == 100.0 for v in result))

    def test_rsi_bounds(self):
        closes = [100 + ((-1) ** i) * (i % 7) for i in range(60)]
        for v in rsi([float(c) for c in closes], 14):
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 100.0)

    def test_atr_positive(self):
        closes = [100.0 + i * 0.5 for i in range(40)]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = atr(highs, lows, closes, 14)
        self.assertTrue(result)
        self.assertTrue(all(v > 0 for v in result))


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def test_long_signal_on_golden_cross(self):
        # 완만한 하락 후 반등 → 마지막 캔들에서 골든크로스 (RSI < 70 유지)
        closes = [100.0 - i * 0.2 for i in range(60)] + [89.0 + j * 0.8 for j in range(1, 6)]
        sig = evaluate("BTCUSDT", make_candles(closes), self.cfg)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.side, "LONG")
        self.assertLess(sig.stop_loss, sig.price)
        self.assertGreater(sig.take_profit, sig.price)

    def test_short_signal_on_dead_cross(self):
        # 완만한 상승 후 하락 → 마지막 캔들에서 데드크로스 (RSI > 30 유지)
        closes = [100.0 + i * 0.2 for i in range(60)] + [111.0 - j * 0.8 for j in range(1, 6)]
        sig = evaluate("BTCUSDT", make_candles(closes), self.cfg)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.side, "SHORT")
        self.assertGreater(sig.stop_loss, sig.price)
        self.assertLess(sig.take_profit, sig.price)

    def test_no_signal_on_steady_trend(self):
        closes = [100.0 + i * 0.5 for i in range(80)]
        sig = evaluate("BTCUSDT", make_candles(closes), self.cfg)
        self.assertIsNone(sig)

    def test_no_signal_with_insufficient_data(self):
        closes = [100.0 + i for i in range(10)]
        sig = evaluate("BTCUSDT", make_candles(closes), self.cfg)
        self.assertIsNone(sig)


if __name__ == "__main__":
    unittest.main()
