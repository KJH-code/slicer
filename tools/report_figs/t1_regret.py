"""t1_regret — 팔별 후회(mm) 상자그림, (a) 베드 상한 없음 (b) 상한 22.79°. 층고 0.4 기본.

    python3 tools/report_figs/t1_regret.py [--json t1_conventional_results.json] [--lh 0.4]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

ARMS = [("fixed15", "고정 15°"), ("fixed20", "고정 20°"), ("fixed25", "고정 25°"),
        ("fixed45", "고정 45°"), ("auto_uniform", "자동 균일(J)"), ("auto_band2", "자동 밴드2")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "t1_conventional_results.json"))
    ap.add_argument("--lh", default="0.4")
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 6.0 / 2.54), sharey=True)
    key_numbers = {}
    for ax, (cap, title, lab) in zip(axes, [("none", "베드 상한 없음", "(a)"),
                                             ("cap", "베드 상한 22.79°", "(b)")], strict=True):
        s = d["summary"][f"{args.lh}|{cap}"]
        data, labels, colors, pos = [], [], [], []
        for i, (k, name) in enumerate(ARMS):
            vals = [p["arms"][k] for p in s["per_model"]]
            labels.append(name)
            if any(v is None for v in vals):
                ax.text(i, 0.5, "실현\n불가", ha="center", va="bottom", fontsize=7,
                        color="0.4", transform=ax.get_xaxis_transform())
                continue
            reg = [v["regret_mm"] for v in vals]
            data.append(reg)
            pos.append(i)
            colors.append(TAB10[i])
            key_numbers[f"{cap}:{k}:median_regret_mm"] = round(float(np.median(reg)), 1)
        bp = ax.boxplot(data, positions=pos, widths=0.55, patch_artist=True,
                        showfliers=True, medianprops={"color": "black", "linewidth": 1.2},
                        flierprops={"marker": "o", "markersize": 3, "markeredgewidth": 0.5},
                        whiskerprops={"linewidth": 0.7}, capprops={"linewidth": 0.7},
                        boxprops={"linewidth": 0.7})
        for patch, c in zip(bp["boxes"], colors, strict=True):
            patch.set_facecolor(c)
            patch.set_alpha(0.55)
        rng = np.random.default_rng(0)
        for p, reg, c in zip(pos, data, colors, strict=True):
            ax.scatter(p + rng.uniform(-0.12, 0.12, len(reg)), reg, s=6, color=c,
                       edgecolor="none", alpha=0.9, zorder=3)
        ax.set_xticks(range(len(ARMS)))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_xlim(-0.6, len(ARMS) - 0.4)
        ax.set_yscale("symlog", linthresh=1.0)
        ax.grid(axis="x", visible=False)
        ax.set_ylim(bottom=0)
        panel_label(ax, f"{lab} {title}")
    axes[0].set_ylabel(f"후회 (mm, 층고 {args.lh} mm)")
    fig.tight_layout()
    save(fig, "t1_regret", __file__,
         [os.path.relpath(args.json, ROOT), "docs/test_t1_t4.md"],
         f"T1: 관례 고정각·자동 결정의 후회(미지지 mm − 사후 최적 균일) 분포, 층고 {args.lh}mm, "
         "(a) 베드 상한 없음 (b) 22.79° 상한", key_numbers)


if __name__ == "__main__":
    main()
