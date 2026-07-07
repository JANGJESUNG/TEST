#!/usr/bin/env python3
"""개편 3라운드: 트레이딩뷰 실전 검증(2024~2026 BTC 1h/4h)에서 드러난 약점 대응.

관찰된 약점:
  ① 수수료 드래그 — 분할 익절 구조상 체결이 많아 순이익을 잠식 (PF 1.0 부근)
  ② 완만한 상승 추세(ADX<25인데 우상향)에서 역추세 숏이 지속 손실

후보 수정안을 전 데이터셋 풀링으로 검증하되, 수수료를 0.055%→0.08%로 올린
스트레스 조건에서도 개선이 유지되는 변경만 채택한다.
"""
import pandas as pd
from experiments import build_datasets, run_all

BASE_REV = {"adx_max": 25.0, "tp1_exit_frac": 0.3}  # 현행 개편안 (파인 기본값)

def stress(ds, extra_fee):
    """크립토 데이터셋 수수료에 슬리피지 가산한 데이터셋 사전 반환."""
    out = {}
    for k, (df, fee) in ds.items():
        out[k] = (df, fee + extra_fee if fee >= 0.0005 else fee)
    return out

if __name__ == "__main__":
    pd.set_option("display.width", 260)
    ds = build_datasets()
    ds_stress = stress(ds, 0.00025)  # 크립토 0.055% → 0.08%

    experiments = [
        ("현행 개편안 (ADX25+TP1 30%)", BASE_REV),
        ("A. ADX 20", {**BASE_REV, "adx_max": 20.0}),
        ("B. TP1을 1.5R로", {**BASE_REV, "tp1_r": 1.5}),
        ("C. TP1 제거 (1R서 본절만 이동, 전량 3R)", {**BASE_REV, "tp1_exit_frac": 0.0}),
        ("D. RSI 25/75 (더 깊은 과열만)", {**BASE_REV, "rsi_os": 25.0, "rsi_ob": 75.0}),
        ("E. 다이버전스 AND 과매도", {**BASE_REV, "require_oversold_too": True}),
        ("F. 숏만 EMA200 아래 허용", {**BASE_REV, "short_only_trend": True}),
        ("G. 쿨다운 15봉", {**BASE_REV, "cooldown": 15}),
        ("A+C", {**BASE_REV, "adx_max": 20.0, "tp1_exit_frac": 0.0}),
        ("A+F", {**BASE_REV, "adx_max": 20.0, "short_only_trend": True}),
        ("C+F", {**BASE_REV, "tp1_exit_frac": 0.0, "short_only_trend": True}),
        ("A+C+F", {**BASE_REV, "adx_max": 20.0, "tp1_exit_frac": 0.0, "short_only_trend": True}),
    ]

    rows = []
    detail = {}
    for label, over in experiments:
        _, agg_n = run_all(ds, over, label)
        d, agg_s = run_all(ds_stress, over, label)
        rows.append({"실험": label,
                     "트레이드": agg_n["트레이드"], "승률": agg_n["승률"],
                     "PF(0.055%)": agg_n["PF"], "평균손익": agg_n["평균손익"],
                     "PF(0.08%)": agg_s["PF"], "평균손익(스트레스)": agg_s["평균손익"]})
        detail[label] = d
    print(pd.DataFrame(rows).to_string(index=False))
