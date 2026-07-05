#!/usr/bin/env python3
"""개편 2라운드: ADX 레인지 필터(추세장에서 역추세 진입 차단) + TP1 30% 조합 검증."""
import pandas as pd
from experiments import build_datasets, run_all

if __name__ == "__main__":
    pd.set_option("display.width", 250)
    ds = build_datasets()
    experiments = [
        ("기준 (현행 규칙)", {}),
        ("ADX<20 필터", {"adx_max": 20.0}),
        ("ADX<25 필터", {"adx_max": 25.0}),
        ("ADX<30 필터", {"adx_max": 30.0}),
        ("TP1 30%", {"tp1_exit_frac": 0.3}),
        ("ADX<25 + TP1 30%", {"adx_max": 25.0, "tp1_exit_frac": 0.3}),
        ("ADX<30 + TP1 30%", {"adx_max": 30.0, "tp1_exit_frac": 0.3}),
    ]
    agg_rows = []
    detail = {}
    for label, over in experiments:
        rows, agg = run_all(ds, over, label)
        agg_rows.append({"실험": label, **(agg or {})})
        detail[label] = rows
    print(pd.DataFrame(agg_rows).to_string(index=False))
    for label in ["ADX<25 필터", "TP1 30%", "ADX<25 + TP1 30%"]:
        print(f"\n-- {label}")
        print(pd.DataFrame(detail[label]).to_string(index=False))
