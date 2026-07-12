#!/usr/bin/env python3
"""개편안 최종 검증: ADX<25 레인지 필터 + TP1 30% 청산 (지표/전략 기본값과 동일).

전 데이터셋에 대해 개편 전/후를 나란히 비교하고,
실전 운용 대상인 BTC 1h는 연도별 성과와 전체 트레이드 내역을 출력한다.
"""
import numpy as np
import pandas as pd

from experiments import build_datasets, run_all

REVISED = {"adx_max": 25.0, "tp1_exit_frac": 0.3}

if __name__ == "__main__":
    pd.set_option("display.width", 260)
    ds = build_datasets()

    print("════ 개편 전(기존 권장) vs 개편 후(ADX<25 + TP1 30%) ════")
    rows_old, agg_old = run_all(ds, {}, "개편전")
    rows_new, agg_new = run_all(ds, REVISED, "개편후")
    print(pd.DataFrame(rows_old).to_string(index=False))
    print()
    print(pd.DataFrame(rows_new).to_string(index=False))
    print(f"\n풀링 개편전: {agg_old}")
    print(f"풀링 개편후: {agg_new}")

    # ── 크립토 실전 대상(BTC 1h/4h)만 따로 풀링 ──
    crypto_ds = {k: v for k, v in ds.items() if k.startswith("BTC") and "1D" not in k}
    _, agg_c_old = run_all(crypto_ds, {}, "c")
    _, agg_c_new = run_all(crypto_ds, REVISED, "c")
    print(f"\n크립토 인트라데이(BTC 1h+4h) 풀링 개편전: {agg_c_old}")
    print(f"크립토 인트라데이(BTC 1h+4h) 풀링 개편후: {agg_c_new}")

    # ── BTC 1h 상세 (실전 주력 타임프레임) ──
    from backtest import Config, run_backtest
    from experiments import BASE
    df = ds["BTC 1h 17-19"][0]
    c = Config(**{**BASE, **REVISED, "taker_fee": 0.00055})
    trades, eq, curve = run_backtest(df, c)
    print(f"\n════ BTC 1h 개편안 상세 (최종 자본 {eq:,.0f} / 초기 1,000 USDT) ════")
    tdf = pd.DataFrame([(t.entry_time.year, t.side, t.pnl_pct_capital, t.outcome) for t in trades],
                       columns=["year", "side", "pnl", "outcome"])
    g = tdf.groupby("year").agg(트레이드=("pnl", "size"),
                                승률=("pnl", lambda x: round((x > 0).mean() * 100, 1)),
                                합계손익=("pnl", lambda x: round(x.sum(), 1)))
    print(g.to_string())
    print("\n[결과 유형 분포]", tdf["outcome"].value_counts().to_dict())
    print("[롱/숏 성과] ", tdf.groupby("side")["pnl"].agg(["size", "sum"]).round(1).to_dict("index"))
    print("\n[전체 트레이드 내역]")
    for t in trades:
        print(f"{t.entry_time:%Y-%m-%d %H:%M} {t.side:5s} 진입 {t.entry:9.1f} SL {t.sl:9.1f} "
              f"TP1 {t.tp1:9.1f} TP2 {t.tp2:9.1f} → {t.outcome:8s} {t.pnl_pct_capital:+.2f}%")

    # ── 연속 손실 스트레스: 트레이드 순서 셔플 몬테카를로 (풀링 개편안) ──
    rng = np.random.default_rng(42)
    pooled = []
    for name, (d, fee) in ds.items():
        cc = Config(**{**BASE, **REVISED, "taker_fee": fee})
        cc.warmup = min(250, max(210, len(d) // 10))
        if len(d) <= cc.warmup + 60:
            continue
        tr, _, _ = run_backtest(d, cc)
        pooled += [t.pnl_pct_capital / 100 for t in tr]
    pooled = np.array(pooled)
    mdds, finals = [], []
    for _ in range(5000):
        seq = rng.permutation(pooled)
        eqc = np.cumprod(1 + seq)
        peak = np.maximum.accumulate(np.concatenate([[1], eqc]))
        mdds.append(((np.concatenate([[1], eqc]) - peak) / peak).min())
        finals.append(eqc[-1])
    mdds, finals = np.array(mdds), np.array(finals)
    print(f"\n════ 몬테카를로 (풀링 {len(pooled)}개 트레이드 순서 셔플 5,000회) ════")
    print(f"최종 자본 배수: 중앙값 {np.median(finals):.2f}x / 5%ile {np.percentile(finals,5):.2f}x / 95%ile {np.percentile(finals,95):.2f}x")
    print(f"MDD: 중앙값 {np.median(mdds)*100:.1f}% / 최악 5%ile {np.percentile(mdds,5)*100:.1f}%")
    print(f"손실 시나리오 비율 (최종<1.0x): {(finals<1).mean()*100:.1f}%")
