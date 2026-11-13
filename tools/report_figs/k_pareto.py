"""k_pareto — 교환 곡선: 고정 균일각(0~44°) 곡선 대 k 별 자동 균일·밴드2 점.

x = 모델 평균 |θ| 의 21 모델 평균(°), y = 미지지 mm 의 21 모델 합.

    python3 tools/report_figs/k_pareto.py [--json k_sweep_results.json]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, panel_label, plt, save, setup  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "k_sweep_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    ks = [float(k) for k in d["meta"]["ks"]]
    cmap = plt.get_cmap("viridis")
    fig, axes = plt.subplots(2, 2, figsize=(FULL_W, 11.5 / 2.54))
    key_numbers = {}
    for r, cap in enumerate(("none", "cap")):
        for c, lh in enumerate(("0.3", "0.4")):
            ax = axes[r, c]
            p = d["pareto"][f"{lh}|{cap}"]
            ax.plot(p["fixed_x"], p["fixed_y"], "-", color="0.35", lw=1.0, zorder=1,
                    label="고정 균일각 (0~44°)")
            ax.scatter(p["fixed_x"], p["fixed_y"], s=6, color="0.35", zorder=2)
            for th, x, y in zip(p["fixed_theta"], p["fixed_x"], p["fixed_y"], strict=True):
                if th % 10 == 0 or th == p["fixed_theta"][-1]:
                    ax.annotate(f"{th:g}°", (x, y), textcoords="offset points", xytext=(2, 3),
                                fontsize=6.5, color="0.35")
            for i, k in enumerate(ks):
                col = cmap(i / (len(ks) - 1))
                u = p["auto"][f"uniform|{k:g}"]
                b = p["auto"][f"band2|{k:g}"]
                ax.scatter(u["x"], u["y"], marker="o", s=22, color=col, edgecolor="k",
                           linewidth=0.4, zorder=4, label=f"k={k:g}" if r == 0 and c == 0 else None)
                ax.scatter(b["x"], b["y"], marker="^", s=22, color=col, edgecolor="k",
                           linewidth=0.4, zorder=4)
                key_numbers[f"{lh}|{cap}:k{k:g}:uniform"] = [round(u["x"], 2), round(u["y"], 1),
                                                             u["verdict"]]
                key_numbers[f"{lh}|{cap}:k{k:g}:band2"] = [round(b["x"], 2), round(b["y"], 1),
                                                           b["verdict"]]
            ax.set_xlabel("평균 |θ| (°, 21 모델 평균)")
            ax.set_ylabel(f"미지지 합 (mm, 층고 {lh})")
            ax.set_yscale("log")
            tag = "상한 없음" if cap == "none" else "상한 22.79°"
            panel_label(ax, f"({'abcd'[r * 2 + c]}) 층고 {lh} · {tag}")
    h, lab = axes[0, 0].get_legend_handles_labels()
    from matplotlib.lines import Line2D
    h += [Line2D([], [], marker="o", ls="", color="w", markeredgecolor="k", label="자동 균일"),
          Line2D([], [], marker="^", ls="", color="w", markeredgecolor="k", label="자동 밴드2")]
    fig.legend(handles=h, loc="lower center", ncol=6, frameon=False, fontsize=7,
               bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, "k_pareto", __file__, [os.path.relpath(args.json, ROOT), "docs/test_k_sweep.md"],
         "교환 곡선: 고정 균일각 곡선(평균|θ| 대 미지지 합) 위에 k 별 자동 균일(●)·밴드2(▲) 점, "
         "21 모델, 층고 0.3/0.4, 베드 상한 유무", key_numbers)


if __name__ == "__main__":
    main()
