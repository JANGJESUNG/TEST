"""시그널 알림 발송: Telegram(설정 시) + 콘솔."""

import logging
from datetime import datetime, timezone

import requests

from .config import Config
from .strategy import Signal

log = logging.getLogger(__name__)


def format_signal(sig: Signal, interval: str) -> str:
    emoji = "🟢" if sig.side == "LONG" else "🔴"
    ts = datetime.fromtimestamp(sig.candle_close_time / 1000, tz=timezone.utc)
    return (
        f"{emoji} *{sig.side}* 시그널 — `{sig.symbol}` ({interval})\n"
        f"진입가: `{sig.price:,.4f}`\n"
        f"손절가: `{sig.stop_loss:,.4f}`\n"
        f"익절가: `{sig.take_profit:,.4f}`\n"
        f"RSI: `{sig.rsi:.1f}`  EMA: `{sig.ema_fast:,.4f} / {sig.ema_slow:,.4f}`\n"
        f"캔들 마감: {ts:%Y-%m-%d %H:%M} UTC\n"
        f"_참고용 시그널입니다. 투자 판단과 책임은 본인에게 있습니다._"
    )


class Notifier:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()

    def send(self, sig: Signal) -> None:
        text = format_signal(sig, self.cfg.interval)
        log.info("시그널 발생:\n%s", text)
        if self.cfg.telegram_bot_token and self.cfg.telegram_chat_id:
            self._send_telegram(text)

    def _send_telegram(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
        try:
            resp = self.session.post(
                url,
                json={
                    "chat_id": self.cfg.telegram_chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException:
            log.exception("Telegram 전송 실패")
