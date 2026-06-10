# Crypto Futures Long/Short Signal Alert Bot

Binance USDT 무기한 선물 시세를 주기적으로 조회해서 **롱/숏 진입 시그널**이 발생하면
Telegram(또는 콘솔)으로 자동 알림을 보내는 봇입니다.

## 시그널 로직

가장 최근 **완결된 캔들** 기준으로 평가합니다 (진행 중 캔들은 사용하지 않아 리페인팅 없음).

| 시그널 | 조건 |
|---|---|
| 🟢 LONG | EMA(9)가 EMA(21)을 상향 돌파 (골든크로스) + RSI(14) < 70 |
| 🔴 SHORT | EMA(9)가 EMA(21)을 하향 돌파 (데드크로스) + RSI(14) > 30 |

알림에는 진입가와 함께 **ATR 기반 손절가(1.5×ATR) / 익절가(3.0×ATR)** 가 포함됩니다.
모든 파라미터는 환경변수로 조정할 수 있습니다.

- 같은 캔들에 대해서는 한 번만 알림
- 심볼별 쿨다운(기본 1시간)으로 알림 스팸 방지
- 시세 조회는 Binance 공개 API를 사용하므로 **거래소 API 키가 필요 없습니다**

## 설치 및 실행

```bash
pip install -r requirements.txt

# 설정 (선택 — 기본값으로도 동작)
cp .env.example .env
# .env 수정 후 환경변수로 로드
export $(grep -v '^#' .env | xargs)

python -m bot.main
```

Telegram 설정 없이 실행하면 콘솔 로그로만 시그널을 출력합니다.

## Telegram 알림 설정

1. Telegram에서 [@BotFather](https://t.me/BotFather)에게 `/newbot` → 봇 토큰 발급
2. 만든 봇에게 아무 메시지나 보낸 뒤 아래로 chat id 확인:
   ```bash
   curl "https://api.telegram.org/bot<토큰>/getUpdates"
   ```
3. 환경변수 설정:
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC..."
   export TELEGRAM_CHAT_ID="987654321"
   ```

## 주요 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SYMBOLS` | `BTCUSDT,ETHUSDT` | 감시 심볼 (쉼표 구분) |
| `INTERVAL` | `15m` | 캔들 주기 (1m/5m/15m/1h/4h/1d) |
| `POLL_SECONDS` | `60` | 폴링 주기 (초) |
| `EMA_FAST` / `EMA_SLOW` | `9` / `21` | EMA 기간 |
| `RSI_PERIOD` | `14` | RSI 기간 |
| `RSI_LONG_MAX` / `RSI_SHORT_MIN` | `70` / `30` | RSI 필터 |
| `ATR_SL_MULT` / `ATR_TP_MULT` | `1.5` / `3.0` | 손절/익절 ATR 배수 |
| `COOLDOWN_SECONDS` | `3600` | 심볼별 재알림 최소 간격 |

## 알림 예시

```
🟢 LONG 시그널 — BTCUSDT (15m)
진입가: 67,250.0000
손절가: 66,800.5000
익절가: 68,149.0000
RSI: 58.3  EMA: 67,180.2 / 67,120.8
캔들 마감: 2026-06-10 14:30 UTC
```

## 테스트

```bash
python -m unittest discover tests
```

## 면책

이 봇이 제공하는 시그널은 참고용이며 투자 권유가 아닙니다.
선물 거래는 원금 이상의 손실이 발생할 수 있으며, 모든 투자 판단과 책임은 사용자 본인에게 있습니다.
