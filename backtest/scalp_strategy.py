#!/usr/bin/env python3
"""15분봉용 고승률 스캘핑 후보 검증 — 단기 평균회귀 계열.

구조 요구사항 (저TF에서 성립하기 위한 조건):
  · 짧은 보유 (시간 청산 포함)
  · 높은 승률: 목표(TP)가 손절(SL)보다 가깝다 (TP 0.5R 등)
  · 수수료 민감 → 지정가(메이커) 진입 시나리오 포함 검증

후보:
  A. RSI(2) 급락/급등 평균회귀 (Connors 계열)
     롱: 종가 > EMA200 + RSI(2) < 10  /  숏: 종가 < EMA200 + RSI(2) > 90
  B. 볼린저 밴드 페이드
     롱: 종가 < BB(20,2) 하단 + RSI(7) < 25  /  숏: 대칭

청산: SL = 2×ATR (한도 캡), TP = tp2_r×R (0.5~1.0), 시간 청산 N봉.
TP1/본절 이동 없음 (be_mode=none, tp1_exit_frac=0).
"""
import glob
import json

import numpy as np
import pandas as pd

from backtest import Config, run_backtest, summarize, ema, rsi, atr
from experiments import BASE, resample

DATA = "data"

def load_30m(sym):
    df = pd.read_csv(f"{DATA}/30m/{sym}.csv")
    df.columns = [c.split(".")[-1].lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float)

def load_ft5m(path):
    raw = json.load(open(path))
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("ts").astype(float)

def base_cols(df, c):
    o = df.copy()
    o["ema_slow"] = ema(o["close"], 200)
    o["atr"] = atr(o, 14)
    o["swing_low"] = o["low"].rolling(c.swing_len).min()
    o["swing_high"] = o["high"].rolling(c.swing_len).max()
    return o

def make_connors(rsi_n=2, buy_th=10.0, trend_gate=True):
    def fn(df, c):
        o = base_cols(df, c)
        r = rsi(o["close"], rsi_n).to_numpy()
        cl = o["close"].to_numpy()
        e200 = o["ema_slow"].to_numpy()
        gate_l = (cl > e200) if trend_gate else np.ones(len(o), dtype=bool)
        gate_s = (cl < e200) if trend_gate else np.ones(len(o), dtype=bool)
        o["long_trig"] = gate_l & (r < buy_th)
        o["short_trig"] = gate_s & (r > 100 - buy_th)
        return o
    return fn

def make_bbfade(rsi_th=25.0, trend_gate=False):
    def fn(df, c):
        o = base_cols(df, c)
        basis = o["close"].rolling(20).mean()
        dev = 2.0 * o["close"].rolling(20).std(ddof=0)
        r7 = rsi(o["close"], 7).to_numpy()
        cl = o["close"].to_numpy()
        e200 = o["ema_slow"].to_numpy()
        gate_l = (cl > e200) if trend_gate else np.ones(len(o), dtype=bool)
        gate_s = (cl < e200) if trend_gate else np.ones(len(o), dtype=bool)
        o["long_trig"] = gate_l & (cl < (basis - dev).to_numpy()) & (r7 < rsi_th)
        o["short_trig"] = gate_s & (cl > (basis + dev).to_numpy()) & (r7 > 100 - rsi_th)
        return o
    return fn

SCALP = dict(tp1_exit_frac=0.0, be_mode="none", tp1_r=99.0,  # TP1/본절 비활성
             atr_stop_mult=2.0, use_swing_sl=False, cooldown=5)

def run_pool(datasets, fn, over, fee):
    rows, pooled = [], []
    for name, df in datasets.items():
        c = Config(**{**BASE, **SCALP, **over, "taker_fee": fee})
        c.warmup = 250
        if len(df) <= c.warmup + 60:
            continue
        yrs = max((df.index[-1] - df.index[0]).days / 365.25, 0.05)
        tr, eq, curve = run_backtest(df, c, signal_fn=fn)
        rows.append(summarize(f"{name}", tr, eq, curve, c, yrs))
        pooled += [t.pnl_pct_capital for t in tr]
    p = np.array(pooled)
    if not len(p):
        return rows, {"트레이드": 0}
    w, l = p[p > 0], p[p <= 0]
    agg = dict(트레이드=len(p), 승률=round((p > 0).mean() * 100, 1),
               PF=round(w.sum() / -l.sum(), 2) if len(l) and l.sum() < 0 else float("inf"),
               평균손익=round(p.mean(), 3))
    return rows, agg

if __name__ == "__main__":
    pd.set_option("display.width", 260)
    syms = ["BTC", "ETH", "LTC", "XRP", "EOS"]
    d30 = {s: load_30m(s) for s in syms}
    d15 = {p.split("/")[-1].replace("-5m.json", ""): resample(load_ft5m(p), "15min")
           for p in sorted(glob.glob(f"{DATA}/ft5m/*.json"))}

    # 수수료 시나리오: 테이커 왕복 / 메이커 진입+테이커 청산 평균 / 메이커 왕복
    FEES = [("테이커 0.055%", 0.00055), ("혼합 0.0375%", 0.000375), ("메이커 0.02%", 0.0002)]

    candidates = [
        ("A1 RSI2<10 추세게이트", make_connors(2, 10, True)),
        ("A2 RSI2<5 추세게이트", make_connors(2, 5, True)),
        ("A3 RSI2<10 게이트없음", make_connors(2, 10, False)),
        ("B1 BB페이드+RSI7<25", make_bbfade(25, False)),
        ("B2 BB페이드+추세게이트", make_bbfade(25, True)),
    ]
    exits = [
        ("TP 0.5R·시간12봉", {"tp2_r": 0.5, "time_stop_bars": 12}),
        ("TP 1.0R·시간24봉", {"tp2_r": 1.0, "time_stop_bars": 24}),
    ]

    print("════ 30m 5심볼 풀링 (2017-10~2019-10) ════")
    results = []
    for cname, fn in candidates:
        for ename, ex in exits:
            row = {"후보": f"{cname} | {ename}"}
            for fname, fee in FEES:
                _, agg = run_pool(d30, fn, ex, fee)
                row[f"PF({fname})"] = agg.get("PF")
                if fname == "테이커 0.055%":
                    row["트레이드"] = agg.get("트레이드")
                    row["승률"] = agg.get("승률")
            results.append(row)
    print(pd.DataFrame(results).to_string(index=False))

    print("\n════ 15m 알트 10페어 (2018-01, 보조) — 상위 후보만 ════")
    for cname, fn in candidates[:3]:
        for ename, ex in exits:
            _, agg = run_pool(d15, fn, ex, 0.000375)
            print(f"{cname} | {ename} | 혼합수수료: {agg}")
