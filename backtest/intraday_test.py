#!/usr/bin/env python3
"""저타임프레임(30m/15m) 검증: 눌림목 전략이 1시간 아래에서도 유지되는가.

데이터:
  · 30m: BTC/ETH/LTC/XRP/EOS 2017-10 ~ 2019-10 (gym-crypto 번들, 각 ~35,000봉)
  · 15m: freqtrade 5m 실데이터(2018-01, 알트/BTC 10페어) 리샘플 — 보조 검증
  · 1h : 동일 30m 데이터 리샘플 — 기존 1h 결과와 교차 확인

검증 질문:
  Q1. 기본 설정이 30m에서 유지되는가? (TF 하향 시 엣지 붕괴 여부)
  Q2. 저TF 조정(스탑 폭·쿨다운·TP2·수수료 스트레스) 중 무엇이 필요한가?
"""
import glob
import json

import numpy as np
import pandas as pd

from backtest import Config, run_backtest, summarize
from experiments import BASE, resample
from trend_strategy import compute_signals_trend

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

def run_pool(datasets, over, label, fee=0.00055, warm=250):
    rows, pooled, stops = [], [], []
    for name, df in datasets.items():
        c = Config(**{**BASE, **over, "taker_fee": fee})
        c.warmup = warm
        if len(df) <= c.warmup + 60:
            continue
        yrs = max((df.index[-1] - df.index[0]).days / 365.25, 0.05)
        tr, eq, curve = run_backtest(df, c, signal_fn=compute_signals_trend)
        rows.append(summarize(f"{label}|{name}", tr, eq, curve, c, yrs))
        pooled += [t.pnl_pct_capital for t in tr]
        stops += [abs(t.entry - t.sl) / t.entry * 100 for t in tr]
    p = np.array(pooled)
    if not len(p):
        return rows, {"트레이드": 0}
    w, l = p[p > 0], p[p <= 0]
    agg = dict(트레이드=len(p), 승률=round((p > 0).mean() * 100, 1),
               PF=round(w.sum() / -l.sum(), 2) if len(l) and l.sum() < 0 else float("inf"),
               평균손익=round(p.mean(), 2),
               평균손절폭=round(np.mean(stops), 3))
    return rows, agg

if __name__ == "__main__":
    pd.set_option("display.width", 260)
    syms = ["BTC", "ETH", "LTC", "XRP", "EOS"]
    d30 = {s: load_30m(s) for s in syms}
    d1h = {s: resample(df, "1h") for s, df in d30.items()}
    d15 = {p.split("/")[-1].replace("-5m.json", ""): resample(load_ft5m(p), "15min")
           for p in sorted(glob.glob(f"{DATA}/ft5m/*.json"))}

    base = {"adx_max": 0.0, "tp1_exit_frac": 0.3, "tp2_r": 4.0}

    print("════ Q1. 기본 설정의 TF 스케일링 (5개 심볼 풀링, 2017-10~2019-10) ════")
    for tfname, ds in [("1h(리샘플)", d1h), ("30m(원본)", d30)]:
        rows, agg = run_pool(ds, base, tfname)
        _, aggs = run_pool(ds, base, tfname, fee=0.0008)
        print(f"\n── {tfname} | 풀링: {agg} | 수수료 0.08% PF: {aggs.get('PF')}")
        print(pd.DataFrame(rows).to_string(index=False))

    print("\n════ Q2. 저TF 조정안 (30m 풀링 비교) ════")
    tweaks = [
        ("기본", {}),
        ("스윙 20봉 (넓은 스탑)", {"swing_len": 20}),
        ("쿨다운 20봉", {"cooldown": 20}),
        ("TP2=6R", {"tp2_r": 6.0}),
        ("스윙20 + 쿨다운20", {"swing_len": 20, "cooldown": 20}),
        ("스윙20 + TP2=6R", {"swing_len": 20, "tp2_r": 6.0}),
    ]
    rows = []
    for label, tw in tweaks:
        _, agg = run_pool(d30, {**base, **tw}, label)
        _, aggs = run_pool(d30, {**base, **tw}, label, fee=0.0008)
        rows.append({"조정": label, **agg, "PF(0.08%)": aggs.get("PF")})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n════ 보조: 15m (freqtrade 알트/BTC 10페어, 2018-01, 20일 — 약한 표본) ════")
    for label, tw in [("기본", {}), ("스윙20", {"swing_len": 20})]:
        rows, agg = run_pool(d15, {**base, **tw}, f"15m {label}", warm=210)
        print(f"{label}: {agg}")
