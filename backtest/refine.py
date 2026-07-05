#!/usr/bin/env python3
"""최적 후보(4h + 다이버전스 필수) 리스크 세부 튜닝.
가격 손절폭(= maxLoss/leverage)은 2% 수준으로 유지하되,
트레이드당 원금 리스크(maxLoss)를 낮춰 MDD를 통제할 수 있는지 검증."""
import numpy as np
import pandas as pd
from backtest import Config, run_backtest, summarize, load_cdd_csv
from sweep import resample

df1h = load_cdd_csv("data/Coinbase_BTCUSD_1h.csv")
df4h = resample(df1h, "4h")
years = (df4h.index[-1] - df4h.index[0]).days / 365.25

combos = [
    # (이름, leverage, maxLoss%) — 가격 손절폭 = maxLoss/lev
    ("5x, 리스크10% (기존)", 5, 10),
    ("3x, 리스크6%", 3, 6),
    ("2x, 리스크4%", 2, 4),
    ("2x, 리스크3%", 2, 3),
    ("1x, 리스크2%", 1, 2),
]
rows = []
best = None
for name, lev, ml in combos:
    c = Config(require_div=True, leverage=lev, max_loss_pct=ml, tp2_r=3.0)
    tr, eq, curve = run_backtest(df4h, c)
    s = summarize(f"4h|Div필수|{name}", tr, eq, curve, c, years)
    rows.append(s)
    if name.startswith("2x, 리스크4%"):
        best = tr

pd.set_option("display.width", 250)
print(pd.DataFrame(rows).to_string(index=False))

print("\n[권장 후보: 4h · Div필수 · 2x · 트레이드당 리스크 4% · TP2=3R — 연도별]")
tdf = pd.DataFrame([(t.entry_time.year, t.side, t.pnl_pct_capital, t.outcome) for t in best],
                   columns=["year", "side", "pnl", "outcome"])
g = tdf.groupby("year").agg(트레이드=("pnl", "size"), 승률=("pnl", lambda x: round((x > 0).mean() * 100, 1)),
                            합계손익=("pnl", lambda x: round(x.sum(), 1)))
print(g.to_string())
print("\n[동일 후보 — 전체 트레이드 내역]")
for t in best:
    print(f"{t.entry_time:%Y-%m-%d %H:%M} {t.side:5s} 진입 {t.entry:9.1f} SL {t.sl:9.1f} "
          f"TP1 {t.tp1:9.1f} TP2 {t.tp2:9.1f} → {t.outcome:8s} {t.pnl_pct_capital:+.2f}%")
