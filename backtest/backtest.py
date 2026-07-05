#!/usr/bin/env python3
"""
퀀트 진입 타점 전략 백테스터
crypto-quant-entry-signals.pine 의 신호 로직을 그대로 재현하여
과거 OHLCV 데이터로 성과를 검증한다.

신호 로직 (파인 스크립트와 동일):
  롱  : (최근 RSI 과매도 or 상승 다이버전스) + BB 하단 터치 + MACD 상방 전환
  숏  : (최근 RSI 과매수 or 하락 다이버전스) + BB 상단 터치 + MACD 하방 전환
  쿨다운: 직전 신호 후 N봉 이내 재신호 금지, 봉 마감 확정 기준

트레이드 관리 (README 권장 운용 원칙과 동일):
  손절  : max(한도 스탑, 스윙 스탑)  — 원금 손실이 한도(-10%)를 넘지 않음
  1차 익절: +1R 도달 시 50% 청산 후 손절가를 본절(진입가)로 이동
  2차 익절: +2R 도달 시 잔량 전량 청산
  동일 봉에서 손절/익절 동시 도달 시 손절 우선(보수적 가정)
  포지션 보유 중 신규 신호는 무시 (1포지션 원칙)

수수료: 시장가(테이커) 왕복 반영 (기본 0.055%/사이드, 바이비트 선물 기준)
"""

import math
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ═══════════════ 설정 ═══════════════
@dataclass
class Config:
    # 지표
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    bb_len: int = 20
    bb_mult: float = 2.0
    bb_lookback: int = 5
    rsi_len: int = 14
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    os_lookback: int = 5
    lbL: int = 5
    lbR: int = 3
    range_lower: int = 5
    range_upper: int = 60
    div_lookback: int = 5
    macd_fast: int = 12
    macd_slow: int = 26
    macd_sig: int = 9
    # 신호
    require_div: bool = False
    use_trend_filter: bool = False
    cooldown: int = 10
    # 리스크
    capital: float = 1000.0
    leverage: float = 5.0
    max_loss_pct: float = 10.0     # 원금 대비 최대 손실 한도 %
    use_swing_sl: bool = True
    swing_len: int = 10
    tp1_r: float = 1.0
    tp2_r: float = 2.0
    tp1_exit_frac: float = 0.5     # 1차 익절 비중
    taker_fee: float = 0.00055    # 사이드당 수수료
    warmup: int = 250


# ═══════════════ 지표 (파인 스크립트와 동일 계산) ═══════════════
def rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1.0 / n, adjust=False).mean()

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(close: pd.Series, n: int) -> pd.Series:
    diff = close.diff()
    up = rma(diff.clip(lower=0), n)
    dn = rma((-diff).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn)

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return rma(tr, n)

def barssince(cond: np.ndarray) -> np.ndarray:
    """각 시점에서 cond가 마지막으로 참이었던 이후 경과 봉 수 (참인 봉=0)."""
    out = np.full(len(cond), 10 ** 9, dtype=np.int64)
    last = -1
    for i in range(len(cond)):
        if cond[i]:
            last = i
        if last >= 0:
            out[i] = i - last
    return out

def pivots(vals: np.ndarray, lbL: int, lbR: int, is_low: bool) -> np.ndarray:
    """피벗 확정 시점(피벗 발생 lbR봉 후)에 True. ta.pivotlow/high 재현."""
    n = len(vals)
    found = np.zeros(n, dtype=bool)
    for i in range(lbL, n - lbR):
        v = vals[i]
        if np.isnan(v):
            continue
        win_l = vals[i - lbL:i]
        win_r = vals[i + 1:i + lbR + 1]
        if is_low:
            ok = np.all(v < win_l) and np.all(v <= win_r)
        else:
            ok = np.all(v > win_l) and np.all(v >= win_r)
        if ok:
            found[i + lbR] = True  # 확정 시점
    return found


def compute_signals(df: pd.DataFrame, c: Config) -> pd.DataFrame:
    o = df.copy()
    o["ema_fast"] = ema(o["close"], c.ema_fast)
    o["ema_mid"] = ema(o["close"], c.ema_mid)
    o["ema_slow"] = ema(o["close"], c.ema_slow)
    basis = o["close"].rolling(c.bb_len).mean()
    dev = c.bb_mult * o["close"].rolling(c.bb_len).std(ddof=0)  # 파인 ta.stdev = 모집단 표준편차
    o["bb_upper"], o["bb_lower"] = basis + dev, basis - dev
    o["rsi"] = rsi(o["close"], c.rsi_len)
    macd_line = ema(o["close"], c.macd_fast) - ema(o["close"], c.macd_slow)
    sig_line = ema(macd_line, c.macd_sig)
    o["hist"] = macd_line - sig_line
    o["macd"], o["signal"] = macd_line, sig_line
    o["atr"] = atr(o, 14)
    o["swing_low"] = o["low"].rolling(c.swing_len).min()
    o["swing_high"] = o["high"].rolling(c.swing_len).max()

    r = o["rsi"].to_numpy()
    lo, hi = o["low"].to_numpy(), o["high"].to_numpy()
    n = len(o)

    # ── 다이버전스 (파인 스크립트의 valuewhen/_inRange 로직 재현) ──
    pl_found = pivots(r, c.lbL, c.lbR, is_low=True)
    ph_found = pivots(r, c.lbL, c.lbR, is_low=False)
    bull_div = np.zeros(n, dtype=bool)
    bear_div = np.zeros(n, dtype=bool)
    since_pl = barssince(pl_found)
    since_ph = barssince(ph_found)
    prev_pl_idx = -1
    for i in range(n):
        if pl_found[i]:
            if prev_pl_idx >= 0:
                gap = since_pl[i - 1] if i > 0 else 10 ** 9  # _inRange(plFound[1])
                if c.range_lower <= gap <= c.range_upper:
                    cur, prv = i - c.lbR, prev_pl_idx - c.lbR
                    if r[cur] > r[prv] and lo[cur] < lo[prv]:
                        bull_div[i] = True
            prev_pl_idx = i
    prev_ph_idx = -1
    for i in range(n):
        if ph_found[i]:
            if prev_ph_idx >= 0:
                gap = since_ph[i - 1] if i > 0 else 10 ** 9
                if c.range_lower <= gap <= c.range_upper:
                    cur, prv = i - c.lbR, prev_ph_idx - c.lbR
                    if r[cur] < r[prv] and hi[cur] > hi[prv]:
                        bear_div[i] = True
            prev_ph_idx = i

    # ── 조건 부품 ──
    oversold_recent = barssince(r < c.rsi_os) <= c.os_lookback
    overbought_recent = barssince(r > c.rsi_ob) <= c.os_lookback
    bb_lower_touch = barssince(lo <= o["bb_lower"].to_numpy()) <= c.bb_lookback
    bb_upper_touch = barssince(hi >= o["bb_upper"].to_numpy()) <= c.bb_lookback
    h = o["hist"].to_numpy()
    h1, h2 = np.roll(h, 1), np.roll(h, 2)
    m, s = o["macd"].to_numpy(), o["signal"].to_numpy()
    m1, s1 = np.roll(m, 1), np.roll(s, 1)
    macd_up = (h > h1) & (h1 <= h2) | ((m > s) & (m1 <= s1))
    macd_dn = (h < h1) & (h1 >= h2) | ((m < s) & (m1 >= s1))
    macd_up[:2] = macd_dn[:2] = False
    bull_recent = barssince(bull_div) <= c.div_lookback
    bear_recent = barssince(bear_div) <= c.div_lookback
    trend_l = ~np.zeros(n, dtype=bool) if not c.use_trend_filter else (o["close"] > o["ema_slow"]).to_numpy()
    trend_s = ~np.zeros(n, dtype=bool) if not c.use_trend_filter else (o["close"] < o["ema_slow"]).to_numpy()

    long_base = oversold_recent | bull_recent
    short_base = overbought_recent | bear_recent
    if c.require_div:
        long_base = long_base & bull_recent
        short_base = short_base & bear_recent
    o["long_trig"] = long_base & bb_lower_touch & macd_up & trend_l
    o["short_trig"] = short_base & bb_upper_touch & macd_dn & trend_s
    return o


# ═══════════════ 트레이드 시뮬레이션 ═══════════════
@dataclass
class Trade:
    side: str
    entry_time: object
    entry: float
    sl: float
    tp1: float
    tp2: float
    exit_time: object = None
    outcome: str = ""      # SL / TP1+BE / TP1+TP2 / EOD
    pnl_pct_capital: float = 0.0  # 원금 대비 순손익 %

def run_backtest(df: pd.DataFrame, c: Config):
    o = compute_signals(df, c)
    n = len(o)
    stop_frac = c.max_loss_pct / c.leverage / 100.0

    equity = c.capital
    eq_curve = [equity]
    trades: list[Trade] = []
    last_sig = -10 ** 9
    pos = None  # dict: side, entry, sl, tp1, tp2, qty, half_done, trade

    cl, hi, lo = o["close"].to_numpy(), o["high"].to_numpy(), o["low"].to_numpy()
    times = o.index

    for i in range(c.warmup, n):
        # ── 1) 보유 포지션 관리 (봉 고가/저가 기준, 손절 우선 보수적 체결) ──
        if pos is not None:
            side, t = pos["side"], pos["trade"]
            filled_exit = False
            if side == "L":
                hit_sl = lo[i] <= pos["sl"]
                hit_tp1 = hi[i] >= pos["tp1"]
                hit_tp2 = hi[i] >= pos["tp2"]
            else:
                hit_sl = hi[i] >= pos["sl"]
                hit_tp1 = lo[i] <= pos["tp1"]
                hit_tp2 = lo[i] <= pos["tp2"]
            def close_qty(qty, price):
                nonlocal equity
                d = (price - pos["entry"]) if side == "L" else (pos["entry"] - price)
                equity_delta = qty * d - qty * price * c.taker_fee
                equity += equity_delta
            if hit_sl:  # 손절(또는 본절) 우선
                close_qty(pos["qty"], pos["sl"])
                t.outcome = "TP1+BE" if pos["half_done"] else "SL"
                filled_exit = True
            else:
                if (not pos["half_done"]) and hit_tp1:
                    q = pos["qty"] * c.tp1_exit_frac
                    close_qty(q, pos["tp1"])
                    pos["qty"] -= q
                    pos["half_done"] = True
                    pos["sl"] = pos["entry"]  # 본절 이동
                if pos["half_done"] and hit_tp2:
                    close_qty(pos["qty"], pos["tp2"])
                    t.outcome = "TP1+TP2"
                    filled_exit = True
            if filled_exit:
                t.exit_time = times[i]
                t.pnl_pct_capital = (equity - pos["eq0"]) / pos["eq0"] * 100
                trades.append(t)
                eq_curve.append(equity)
                pos = None
            if equity <= 0:
                break

        # ── 2) 신규 진입 (봉 마감 확정, 쿨다운, 1포지션 원칙) ──
        if pos is None and i - last_sig > c.cooldown:
            is_long = bool(o["long_trig"].iloc[i])
            is_short = bool(o["short_trig"].iloc[i]) and not is_long
            if is_long or is_short:
                last_sig = i
                entry = cl[i]
                if is_long:
                    sl_cap = entry * (1 - stop_frac)
                    sl_sw = o["swing_low"].iloc[i] - 0.5 * o["atr"].iloc[i]
                    sl = max(sl_cap, sl_sw) if c.use_swing_sl else sl_cap
                    if sl >= entry:
                        sl = sl_cap
                    rr = entry - sl
                    tp1, tp2 = entry + rr * c.tp1_r, entry + rr * c.tp2_r
                else:
                    sl_cap = entry * (1 + stop_frac)
                    sl_sw = o["swing_high"].iloc[i] + 0.5 * o["atr"].iloc[i]
                    sl = min(sl_cap, sl_sw) if c.use_swing_sl else sl_cap
                    if sl <= entry:
                        sl = sl_cap
                    rr = sl - entry
                    tp1, tp2 = entry - rr * c.tp1_r, entry - rr * c.tp2_r
                notional = equity * c.leverage
                qty = notional / entry
                equity -= notional * c.taker_fee  # 진입 수수료
                pos = dict(side="L" if is_long else "S", entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                           qty=qty, half_done=False, eq0=equity + notional * c.taker_fee,
                           trade=Trade("LONG" if is_long else "SHORT", times[i], entry, sl, tp1, tp2))

    # 미청산 포지션은 마지막 봉 종가 청산
    if pos is not None:
        side = pos["side"]
        d = (cl[-1] - pos["entry"]) if side == "L" else (pos["entry"] - cl[-1])
        equity += pos["qty"] * d - pos["qty"] * cl[-1] * c.taker_fee
        t = pos["trade"]
        t.exit_time, t.outcome = times[-1], "EOD"
        t.pnl_pct_capital = (equity - pos["eq0"]) / pos["eq0"] * 100
        trades.append(t)
        eq_curve.append(equity)

    return trades, equity, np.array(eq_curve)


def summarize(name: str, trades: list, final_eq: float, eq_curve: np.ndarray, c: Config, years: float) -> dict:
    n = len(trades)
    if n == 0:
        return {"설정": name, "트레이드": 0}
    wins = [t for t in trades if t.pnl_pct_capital > 0]
    losses = [t for t in trades if t.pnl_pct_capital <= 0]
    gross_p = sum(t.pnl_pct_capital for t in wins)
    gross_l = -sum(t.pnl_pct_capital for t in losses)
    peak = np.maximum.accumulate(eq_curve)
    mdd = ((eq_curve - peak) / peak).min() * 100
    total_ret = (final_eq / c.capital - 1) * 100
    cagr = ((final_eq / c.capital) ** (1 / years) - 1) * 100 if final_eq > 0 else -100
    outcomes = pd.Series([t.outcome for t in trades]).value_counts().to_dict()
    return {
        "설정": name,
        "트레이드": n,
        "승률%": round(len(wins) / n * 100, 1),
        "TP2도달": outcomes.get("TP1+TP2", 0),
        "TP1+본절": outcomes.get("TP1+BE", 0),
        "손절": outcomes.get("SL", 0),
        "PF": round(gross_p / gross_l, 2) if gross_l > 0 else float("inf"),
        "평균손익%": round(np.mean([t.pnl_pct_capital for t in trades]), 2),
        "누적수익%": round(total_ret, 1),
        "연환산%": round(cagr, 1),
        "MDD%": round(mdd, 1),
        "롱/숏": f"{sum(1 for t in trades if t.side=='LONG')}/{sum(1 for t in trades if t.side=='SHORT')}",
    }


def load_cdd_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=1)
    for fmt in ("%Y-%m-%d %I-%p", "%Y-%m-%d"):
        try:
            df["date"] = pd.to_datetime(df["date"], format=fmt)
            break
        except (ValueError, TypeError):
            continue
    df = df.sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "Coinbase_BTCUSD_1h.csv"
    df = load_cdd_csv(path)
    years = (df.index[-1] - df.index[0]).days / 365.25
    print(f"데이터: {path}  {df.index[0]} ~ {df.index[-1]}  ({len(df)}봉, {years:.2f}년)\n")

    variants = [
        ("① 기본 (과매도/과매수 or 다이버전스)", Config()),
        ("② 다이버전스 필수", Config(require_div=True)),
        ("③ EMA200 추세 필터", Config(use_trend_filter=True)),
        ("④ 다이버전스 필수 + 추세 필터", Config(require_div=True, use_trend_filter=True)),
    ]
    rows = []
    all_trades = {}
    for name, cfg in variants:
        trades, eq, curve = run_backtest(df, cfg)
        rows.append(summarize(name, trades, eq, curve, cfg, years))
        all_trades[name] = trades
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))

    # 연도별 분해 (기본 설정)
    print("\n[기본 설정 연도별]")
    t0 = all_trades[variants[0][0]]
    tdf = pd.DataFrame([(t.entry_time.year, t.side, t.pnl_pct_capital, t.outcome) for t in t0],
                       columns=["year", "side", "pnl", "outcome"])
    g = tdf.groupby("year").agg(트레이드=("pnl", "size"), 승률=("pnl", lambda x: round((x > 0).mean() * 100, 1)),
                                합계손익=("pnl", lambda x: round(x.sum(), 1)))
    print(g.to_string())
