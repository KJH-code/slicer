"""t4_robustness — 교란 축별 고른 각도 변화(°) 점 그림, ±2° 띠. (a) 자동 균일(J) (b) 자동 밴드2.

    python3 tools/report_figs/t4_robustness.py [--json t4_robustness_results.json]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

LABEL = {"subdiv4": "세분화 ×4", "simplify0.5": "단순화 ×0.5", "shift0.1": "중심 0.1mm",
         "shift0.5": "중심 0.5mm", "tilt1": "기울임 1°", "tilt3": "기울임 3°",
         "thr40": "임계각 40°", "thr50": "임계각 50°"}
AXIS_COLOR = {"res": TAB10[0], "align": TAB10[1], "threshold": TAB10[2]}
AXIS_NAME = {"res": "메시 해상도", "align": "축 정렬 오차", "threshold": "임계각"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "t4_robustness_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    keys = [k for _a, k in d["meta"]["perturbations"]]
    axis_of = {k: a for a, k in d["meta"]["perturbations"]}
    base = {r["model"]: r for r in d["raw"] if r["key"] == "base"}
    fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 6.0 / 2.54), sharey=True)
    rng = np.random.default_rng(0)
    key_numbers = {}
    for ax, arm, lab, title in zip(axes, ("uniform", "band2"), ("(a)", "(b)"),
                                   ("자동 균일(J)", "자동 밴드2 (밴드별 최대 |Δθ|)"), strict=True):
        ax.axhspan(-2, 2, color="0.85", zorder=0, linewidth=0)
        for i, k in enumerate(keys):
            rows = [r for r in d["rows"] if r["key"] == k]
            if arm == "uniform":
                dv = [r["uniform"][0] - base[r["model"]]["uniform"][0] for r in rows]
            else:
                dv = []
                for r in rows:
                    diffs = [x - y for x, y in zip(r["band2"], base[r["model"]]["band2"],
                                                   strict=True)]
                    dv.append(max(diffs, key=abs))
            dv = np.array(dv)
            ax.scatter(i + rng.uniform(-0.18, 0.18, len(dv)), dv, s=9,
                       color=AXIS_COLOR[axis_of[k]], edgecolor="white", linewidth=0.3,
                       zorder=3, label=AXIS_NAME[axis_of[k]])
            frac = float(np.mean(np.abs(dv) <= 2 + 1e-9))
            ax.text(i, 1.0, f"{frac * 100:.0f}%", transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=6.5)
            key_numbers[f"{arm}:{k}:frac_le2deg"] = round(frac, 3)
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels([LABEL[k] for k in keys], rotation=35, ha="right")
        ax.grid(axis="x", visible=False)
        panel_label(ax, f"{lab} {title}")
    axes[0].set_ylabel("고른 각도 변화 Δθ (°)")
    h, lb = axes[0].get_legend_handles_labels()
    uniq = dict(zip(lb, h, strict=True))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.legend(uniq.values(), uniq.keys(), loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 0.0))
    save(fig, "t4_robustness", __file__,
         [os.path.relpath(args.json, ROOT), "docs/test_t1_t4.md"],
         "T4: 교란 축별 자동 결정 각도 변화(점=모델, 회색 띠=±2° 격자 한 칸, 위 숫자=띠 안 비율)",
         key_numbers)


if __name__ == "__main__":
    main()
