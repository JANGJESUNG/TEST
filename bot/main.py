"""크립토 선물 롱/숏 시그널 알람 봇 메인 루프.

실행: python -m bot.main
"""

import logging
import time

import requests

from .config import Config
from .exchange import BinanceFutures
from .notifier import Notifier
from .strategy import evaluate

log = logging.getLogger("bot")


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config()
    cfg.validate()
    exchange = BinanceFutures()
    notifier = Notifier(cfg)

    # 중복 알림 방지: 심볼별 마지막 알림 캔들/시각
    last_alert_candle: dict[str, int] = {}
    last_alert_time: dict[str, float] = {}

    log.info(
        "봇 시작 — 심볼=%s 주기=%s 폴링=%ds EMA=%d/%d RSI=%d",
        ",".join(cfg.symbols), cfg.interval, cfg.poll_seconds,
        cfg.ema_fast, cfg.ema_slow, cfg.rsi_period,
    )

    while True:
        for symbol in cfg.symbols:
            try:
                candles = exchange.klines(symbol, cfg.interval, limit=200)
                sig = evaluate(symbol, candles, cfg)
                if sig is None:
                    continue
                # 같은 캔들에 대해 한 번만, 그리고 쿨다운 적용
                if last_alert_candle.get(symbol) == sig.candle_close_time:
                    continue
                now = time.monotonic()
                if now - last_alert_time.get(symbol, float("-inf")) < cfg.cooldown_seconds:
                    log.info("%s %s 시그널은 쿨다운으로 생략", symbol, sig.side)
                    continue
                notifier.send(sig)
                last_alert_candle[symbol] = sig.candle_close_time
                last_alert_time[symbol] = now
            except requests.RequestException:
                log.exception("%s 시세 조회 실패 — 다음 폴링에 재시도", symbol)
            except Exception:
                log.exception("%s 처리 중 오류", symbol)
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    run()
