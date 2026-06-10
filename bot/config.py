"""환경변수 기반 설정 로더."""

import os
from dataclasses import dataclass, field


def _env_list(key: str, default: str) -> list[str]:
    raw = os.environ.get(key, default)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class Config:
    # 감시할 심볼 (Binance USDT 무기한 선물)
    symbols: list[str] = field(
        default_factory=lambda: _env_list("SYMBOLS", "BTCUSDT,ETHUSDT")
    )
    # 캔들 주기: 1m, 5m, 15m, 1h, 4h, 1d ...
    interval: str = os.environ.get("INTERVAL", "15m")
    # 폴링 주기 (초)
    poll_seconds: int = int(os.environ.get("POLL_SECONDS", "60"))

    # 전략 파라미터
    ema_fast: int = int(os.environ.get("EMA_FAST", "9"))
    ema_slow: int = int(os.environ.get("EMA_SLOW", "21"))
    rsi_period: int = int(os.environ.get("RSI_PERIOD", "14"))
    rsi_long_max: float = float(os.environ.get("RSI_LONG_MAX", "70"))   # 과매수면 롱 제외
    rsi_short_min: float = float(os.environ.get("RSI_SHORT_MIN", "30"))  # 과매도면 숏 제외
    atr_period: int = int(os.environ.get("ATR_PERIOD", "14"))
    # 손절/익절 거리 (ATR 배수)
    atr_sl_mult: float = float(os.environ.get("ATR_SL_MULT", "1.5"))
    atr_tp_mult: float = float(os.environ.get("ATR_TP_MULT", "3.0"))

    # 같은 심볼 재알림 최소 간격 (초)
    cooldown_seconds: int = int(os.environ.get("COOLDOWN_SECONDS", "3600"))

    # Telegram (비워두면 콘솔 출력만)
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")

    def validate(self) -> None:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("EMA_FAST는 EMA_SLOW보다 작아야 합니다.")
        if not self.symbols:
            raise ValueError("SYMBOLS가 비어 있습니다.")
