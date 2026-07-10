#!/usr/bin/env python3
"""추세 순응 + 눌림목(pullback) 진입 전략 — 역추세 계열의 대안 검증.

구조:
  롱  : EMA50 > EMA200 & 종가 > EMA200 (상승 추세 확인)
        + 최근 N봉 내 저가가 EMA20 터치/이탈 (눌림 발생)
        + 눌림 중 RSI가 50 아래로 (되돌림 깊이 확인)
        + 종가가 EMA20 위로 복귀 (추세 재개 트리거, 봉 마감 확정)
  숏  : 완전 대칭
  관리: 기존과 동일 (스윙+한도 스탑, TP1 1R 부분청산+본절 이동, TP2 3R)
"""
import numpy as np
import pandas as pd

from backtest import Config, ema, rsi, atr, adx, barssince


def compute_signals_trend(df: pd.DataFrame, c: Config) -> pd.DataFrame:
    o = df.copy()
    o["ema_fast"] = ema(o["close"], c.ema_fast)    # 20
    o["ema_mid"] = ema(o["close"], c.ema_mid)      # 50
    o["ema_slow"] = ema(o["close"], c.ema_slow)    # 200
    o["rsi"] = rsi(o["close"], c.rsi_len)
    o["atr"] = atr(o, 14)
    o["swing_low"] = o["low"].rolling(c.swing_len).min()
    o["swing_high"] = o["high"].rolling(c.swing_len).max()

    cl = o["close"].to_numpy()
    lo, hi = o["low"].to_numpy(), o["high"].to_numpy()
    e20, e50, e200 = o["ema_fast"].to_numpy(), o["ema_mid"].to_numpy(), o["ema_slow"].to_numpy()
    r = o["rsi"].to_numpy()
    n = len(o)

    up_trend = (e50 > e200) & (cl > e200)
    dn_trend = (e50 < e200) & (cl < e200)

    # 눌림: 최근 N봉 내 EMA20 터치 + RSI 되돌림
    pull_lo = barssince(lo <= e20) <= c.bb_lookback          # 상승 추세 속 눌림
    pull_hi = barssince(hi >= e20) <= c.bb_lookback          # 하락 추세 속 반등
    rsi_dip = barssince(r < 50) <= c.bb_lookback
    rsi_pop = barssince(r > 50) <= c.bb_lookback

    # 트리거: 종가의 EMA20 재돌파 (추세 재개)
    above = cl > e20
    below = cl < e20
    cross_up = above & ~np.roll(above, 1)
    cross_dn = below & ~np.roll(below, 1)
    cross_up[0] = cross_dn[0] = False

    # 선택: ADX 하한 (추세 전략은 추세 강도가 있어야 유리)
    regime_ok = np.ones(n, dtype=bool)
    if c.adx_max > 0:  # 재사용: 추세 전략에서는 '하한'으로 해석 (adx > adx_max)
        regime_ok = (adx(o, 14) > c.adx_max).to_numpy()

    o["long_trig"] = up_trend & pull_lo & rsi_dip & cross_up & regime_ok
    o["short_trig"] = dn_trend & pull_hi & rsi_pop & cross_dn & regime_ok
    return o


if __name__ == "__main__":
    from experiments import build_datasets, BASE
    from backtest import run_backtest, summarize

    pd.set_option("display.width", 260)
    ds = build_datasets()

    def run_all_trend(cfg_over, label, fee_bump=0.0):
        rows, pooled = [], []
        for name, (df, fee) in ds.items():
            c = Config(**{**BASE, **cfg_over, "taker_fee": fee + (fee_bump if fee >= 0.0005 else 0)})
            c.warmup = min(250, max(210, len(df) // 10))
            if len(df) <= c.warmup + 60:
                continue
            years = max((df.index[-1] - df.index[0]).days / 365.25, 0.1)
            tr, eq, curve = run_backtest(df, c, signal_fn=compute_signals_trend)
            rows.append(summarize(f"{label}|{name}", tr, eq, curve, c, years))
            pooled += [t.pnl_pct_capital for t in tr]
        p = np.array(pooled)
        w, l = p[p > 0], p[p <= 0]
        agg = dict(트레이드=len(p), 승률=round((p > 0).mean() * 100, 1) if len(p) else 0,
                   PF=round(w.sum() / -l.sum(), 2) if len(l) and l.sum() < 0 else float("inf"),
                   평균손익=round(p.mean(), 2) if len(p) else 0)
        return rows, agg

    variants = [
        ("눌림목 기본 (ADX 무관)", {"adx_max": 0.0, "tp1_exit_frac": 0.3}),
        ("눌림목 + ADX>20", {"adx_max": 20.0, "tp1_exit_frac": 0.3}),
        ("눌림목 + ADX>25", {"adx_max": 25.0, "tp1_exit_frac": 0.3}),
        ("눌림목 + 눌림 인정 3봉", {"adx_max": 0.0, "tp1_exit_frac": 0.3, "bb_lookback": 3}),
        ("눌림목 + TP2=2R", {"adx_max": 0.0, "tp1_exit_frac": 0.3, "tp2_r": 2.0}),
        ("눌림목 + TP2=4R", {"adx_max": 0.0, "tp1_exit_frac": 0.3, "tp2_r": 4.0}),
    ]
    for label, over in variants:
        rows, agg = run_all_trend(over, label)
        _, agg_s = run_all_trend(over, label, fee_bump=0.00025)
        print(f"══ {label} | 풀링: {agg} | 수수료 스트레스 PF: {agg_s['PF']}")
        print(pd.DataFrame(rows).to_string(index=False))
        print()
