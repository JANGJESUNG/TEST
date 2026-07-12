#!/usr/bin/env python3
"""확장 백테스트: 데이터 다양화(자산·기간·시장) + 전략 개편 실험.

R1 일반화 검증: 권장 설정(Div필수·2x·리스크4%·TP1=1R/TP2=3R)을
   BTC 1h/4h(17-19), BTC 일봉(13-20), ETH/LTC 일봉(15-20),
   EURUSD 1h/4h(2017), GOOGL 일봉(09-18)에 그대로 적용.

R2 개편 실험 (ablation & 규칙 변형): 조건/관리 규칙을 하나씩 바꿔
   전 데이터셋에서 공통으로 개선되는 변경만 채택 근거로 삼는다.
"""
import sqlite3

import numpy as np
import pandas as pd

from backtest import Config, run_backtest, summarize, load_cdd_csv

DATA = "data"

def resample(df, rule):
    return df.resample(rule).agg(open=("open", "first"), high=("high", "max"),
                                 low=("low", "min"), close=("close", "last"),
                                 volume=("volume", "sum")).dropna()

def load_sqlite_daily(symbol, exchange):
    con = sqlite3.connect(f"{DATA}/crypto_daily_2013_2020.db")
    df = pd.read_sql("select day, open, high, low, close, volume from price "
                     "where symbol=? and exchange=? order by day", con, params=(symbol, exchange))
    df["day"] = pd.to_datetime(df["day"])
    return df.set_index("day").astype(float)

def load_eurusd_1h():
    df = pd.read_csv(f"{DATA}/FOREX_EURUSD_1H_ASK.csv")
    df["Time"] = pd.to_datetime(df["Time"], format="%d.%m.%Y %H:%M:%S.%f")
    df = df.set_index("Time").rename(columns=str.lower)
    return df[["open", "high", "low", "close", "volume"]].astype(float)

def load_googl():
    df = pd.read_csv(f"{DATA}/STOCKS_GOOGL.csv")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").rename(columns=str.lower)
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def build_datasets():
    btc1h = load_cdd_csv(f"{DATA}/Coinbase_BTCUSD_1h.csv")
    eur1h = load_eurusd_1h()
    return {
        # 이름: (df, 수수료/사이드) — 크립토는 테이커 0.055%, 외환/주식은 0.01% 가정
        "BTC 4h 17-19":   (resample(btc1h, "4h"), 0.00055),
        "BTC 1h 17-19":   (btc1h, 0.00055),
        "BTC 1D 13-20":   (load_sqlite_daily("btc", "bitstamp"), 0.00055),
        "ETH 1D 15-20":   (load_sqlite_daily("eth", "poloniex"), 0.00055),
        "LTC 1D 15-20":   (load_sqlite_daily("ltc", "poloniex"), 0.00055),
        "EURUSD 4h 2017": (resample(eur1h, "4h"), 0.0001),
        "EURUSD 1h 2017": (eur1h, 0.0001),
        "GOOGL 1D 09-18": (load_googl(), 0.0001),
    }

BASE = dict(require_div=True, leverage=2.0, max_loss_pct=4.0, tp1_r=1.0, tp2_r=3.0)

def run_all(datasets, cfg_over, label):
    rows = []
    pooled = []
    for name, (df, fee) in datasets.items():
        c = Config(**{**BASE, **cfg_over, "taker_fee": fee})
        c.warmup = min(250, max(210, len(df) // 10))
        if len(df) <= c.warmup + 60:
            continue
        years = max((df.index[-1] - df.index[0]).days / 365.25, 0.1)
        tr, eq, curve = run_backtest(df, c)
        s = summarize(f"{label}|{name}", tr, eq, curve, c, years)
        rows.append(s)
        pooled += [t.pnl_pct_capital for t in tr]
    # 전 데이터셋 합산(풀링) 지표
    p = np.array(pooled)
    agg = None
    if len(p):
        wins, losses = p[p > 0], p[p <= 0]
        agg = dict(트레이드=len(p), 승률=round((p > 0).mean() * 100, 1),
                   PF=round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else float("inf"),
                   평균손익=round(p.mean(), 2))
    return rows, agg


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    ds = build_datasets()
    for n, (df, _) in ds.items():
        print(f"{n:18s} {df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d}  {len(df):>6}봉")

    print("\n════ R1. 권장 설정 일반화 검증 ════")
    rows, agg = run_all(ds, {}, "권장")
    print(pd.DataFrame(rows).to_string(index=False))
    print("풀링:", agg)

    print("\n════ R2. 개편 실험 (전 데이터셋 풀링 성과로 비교) ════")
    experiments = [
        ("기준 (현행 규칙)", {}),
        ("MACD 조건 제거", {"disable_macd": True}),
        ("BB 조건 제거", {"disable_bb": True}),
        ("본절 이동 없음", {"be_mode": "none"}),
        ("본절+0.25R 버퍼", {"be_mode": "buffer"}),
        ("TP1 비중 30%", {"tp1_exit_frac": 0.3}),
        ("TP1 비중 70%", {"tp1_exit_frac": 0.7}),
        ("ATR 1.5배 스탑", {"atr_stop_mult": 1.5, "use_swing_sl": False}),
        ("ATR 2.0배 스탑", {"atr_stop_mult": 2.0, "use_swing_sl": False}),
        ("TP2=2R", {"tp2_r": 2.0}),
        ("TP2=4R", {"tp2_r": 4.0}),
        ("쿨다운 5봉", {"cooldown": 5}),
        ("추세필터 켬", {"use_trend_filter": True}),
    ]
    agg_rows = []
    detail = {}
    for label, over in experiments:
        rows, agg = run_all(ds, over, label)
        agg_rows.append({"실험": label, **(agg or {})})
        detail[label] = rows
    print(pd.DataFrame(agg_rows).to_string(index=False))

    print("\n[유망 실험 데이터셋별 상세]")
    for label in ["기준 (현행 규칙)", "본절 이동 없음", "본절+0.25R 버퍼", "ATR 2.0배 스탑", "TP2=2R"]:
        print(f"\n-- {label}")
        print(pd.DataFrame(detail[label]).to_string(index=False))
