#!/usr/bin/env python3
"""타임프레임 × 신호모드 × 레버리지(손절폭) × 익절배수 파라미터 스윕."""
import numpy as np
import pandas as pd
from backtest import Config, run_backtest, summarize, load_cdd_csv

def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    o = df.resample(rule).agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last"),
                              volume=("volume", "sum")).dropna()
    return o

df1h = load_cdd_csv("data/Coinbase_BTCUSD_1h.csv")
frames = {
    "1h": df1h,
    "4h": resample(df1h, "4h"),
    "1D(17-19)": resample(df1h, "1D"),
}
dfd = load_cdd_csv("data/Coinbase_BTCUSD_d.csv")
frames["1D(전체)"] = dfd  # 일봉 원본 (커버리지 더 김)

rows = []
for tf, df in frames.items():
    years = max((df.index[-1] - df.index[0]).days / 365.25, 0.1)
    warm = 250 if len(df) > 400 else 210
    for mode, req in [("기본", False), ("Div필수", True)]:
        for lev in [5.0, 3.0, 2.0]:
            for tp2 in [2.0, 3.0]:
                c = Config(require_div=req, leverage=lev, tp2_r=tp2, warmup=warm)
                if len(df) <= c.warmup + 50:
                    continue
                tr, eq, curve = run_backtest(df, c)
                s = summarize(f"{tf}|{mode}|{lev:g}x|TP2={tp2:g}R", tr, eq, curve, c, years)
                rows.append(s)

res = pd.DataFrame(rows)
pd.set_option("display.width", 250)
res = res.sort_values("누적수익%", ascending=False)
print(res.to_string(index=False))
print(f"\n일봉 원본 커버리지: {dfd.index[0]} ~ {dfd.index[-1]} ({len(dfd)}일)")
