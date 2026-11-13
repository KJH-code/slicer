"""k_estimate — k 추정: 손실 곡선, 부트스트랩 분포, 표본 밖(LOFO) 후회, 비용 포함 k̂(λ).

    python3 tools/report_figs/k_estimate.py [--json k_estimate_results.json]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

CELL_LAB = {"0.3|none": "0.3·상한 없음", "0.3|cap": "0.3·상한", "0.4|none": "0.4·상한 없음",
            "0.4|cap": "0.4·상한"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "k_estimate_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    kg = np.array(d["k_grid"])
    e = d["estimates"]
    fig, axes = plt.subplots(2, 2, figsize=(FULL_W, 11.0 / 2.54))

    ax = axes[0, 0]
    for i, (c, lab) in enumerate(CELL_LAB.items()):
        ax.plot(kg, d["median_regret_curves"][c], color=TAB10[i], label=lab)
    lo, hi = e["all"]["boot_model"]["k_1se_ci"]
    ax.axvspan(lo, hi, color="0.6", alpha=0.3, lw=0, label="추정 k 95% 구간")
    ax.axvline(e["all"]["k_1se"], color="k", lw=0.9)
    ax.axvline(0.2, color="0.4", ls=":", lw=0.9)
    ax.text(0.205, 60, "현재 0.2", fontsize=7, color="0.4")
    ax.set_xlim(0, 0.3)
    ax.set_ylim(-2, 80)
    ax.set_xlabel("k (%p/°)")
    ax.set_ylabel("후회 중앙값 (mm)")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    panel_label(ax, f"(a) 셀별 후회 · 추정 k = {e['all']['k_1se']:.3f}")

    ax = axes[0, 1]
    bins = np.arange(0, 0.5075, 0.01)
    centers = bins[:-1] + 0.005
    for i, (key, lab) in enumerate((("all", "전체"), ("0.3", "층고 0.3 만"), ("0.4", "층고 0.4 만"))):
        h = np.array(e[key]["boot_model"]["k_1se_hist"], dtype=float)
        ax.step(centers, h / h.sum(), where="mid", color=TAB10[i + 4] if i else "k", label=lab)
    ax.axvline(0.2, color="0.4", ls=":", lw=0.9)
    ax.set_xlim(0, 0.3)
    ax.set_xlabel("부트스트랩 추정 k (1-SE 규칙)")
    ax.set_ylabel("비율")
    ax.legend(frameon=False, fontsize=7)
    panel_label(ax, "(b) 모델 부트스트랩 2000 회")

    ax = axes[1, 0]
    cells = list(CELL_LAB)
    x = np.arange(len(cells))
    w = 0.2
    lofo = d["lofo"]["cells"]
    ax.bar(x - 1.5 * w, [lofo[c]["held_out_regret_median"] for c in cells], w, color="k",
           label="자동 균일, k 를 표본 밖에서 고름(LOFO)")
    ax.bar(x - 0.5 * w, [lofo[c]["k0.2_regret_median"] for c in cells], w, color="0.6",
           label="자동 균일, k = 0.2")
    for xi, c in zip(x, cells, strict=True):
        v = lofo[c]["held_out_regret_median"]
        ax.text(xi - 1.5 * w, v + 0.15, f"{v:.1f}", ha="center", fontsize=6.5)
    best = [min(lofo[c]["fixed_regret_median"].values()) for c in cells]
    besta = [min(lofo[c]["fixed_regret_median"], key=lofo[c]["fixed_regret_median"].get)
             for c in cells]
    ax.bar(x + 0.5 * w, best, w, color=TAB10[3], label="최선 고정각")
    for xi, b, a in zip(x, best, besta, strict=True):
        ax.text(xi + 0.5 * w, b + 1, f"{a}°", ha="center", fontsize=6.5, color=TAB10[3])
    ax.set_xticks(x)
    ax.set_xticklabels([CELL_LAB[c] for c in cells], fontsize=7)
    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_ylim(0, 100)
    ax.set_ylabel("후회 중앙값 (mm)")
    ax.legend(frameon=False, fontsize=6.5, loc="upper left")
    panel_label(ax, "(c) 표본 밖 검증 (가족 제외 5 겹)")

    ax = axes[1, 1]
    lam = d["k_by_lambda_posthoc"]
    ls_ = [float(v) for v in lam]
    ax.plot(ls_, list(lam.values()), "o-", color=TAB10[0], ms=3)
    ax.axhline(0.2, color="0.4", ls=":", lw=0.9)
    ax.set_xscale("symlog", linthresh=1.0)
    ax.set_xlabel("λ (미지지 mm / 평균 기울기 1°)")
    ax.set_ylabel("추정 k (%p/°, 최소 손실)")
    panel_label(ax, "(d) 각도 비용을 넣으면 (판정 밖)")
    fig.tight_layout()
    v = d["verdict"]
    save(fig, "k_estimate", __file__, [os.path.relpath(args.json, ROOT), "docs/test_k_estimate.md"],
         "k 추정: 셀별 후회 곡선과 k̂(1-SE) 95% 구간, 부트스트랩 분포(전체/층고별), 가족 제외 교차검증 후회, "
         "각도 비용 λ 에 따른 추정 k",
         {"k_1se": v["k_1se"], "ci95_model": v["ci95_model"],
          "k_1se_0.3": e["0.3"]["k_1se"], "ci95_0.3": e["0.3"]["boot_model"]["k_1se_ci"],
          "k_1se_0.4": e["0.4"]["k_1se"], "ci95_0.4": e["0.4"]["boot_model"]["k_1se_ci"],
          "lofo_k": d["lofo"]["k_per_fold"], "reliable": v["reliable"],
          "k_by_lambda": lam})


if __name__ == "__main__":
    main()
