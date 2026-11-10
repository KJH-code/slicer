"""checker_criterion — 툴패스 검사기 A 의 '지지됨' 정의 모식도 + 합성 시험 계단 (보고서 그림 G).

데이터: report_fig_checker_results.json (python3 report_fig_checker.py)

    python3 tools/report_figs/checker_criterion.py
"""

import json
import os
import sys

from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402


def main():
    setup()
    d = json.load(open(os.path.join(ROOT, "report_fig_checker_results.json")))
    w = d["defaults"]["width"]
    vf = d["defaults"]["vwin_factor"]
    h = d["sweep"]["layer_height"]
    fig, axes = plt.subplots(1, 3, figsize=(FULL_W, 5.6 / 2.54),
                             gridspec_kw={"width_ratios": [1.9, 1, 1]})

    # (a) 모식도 — 단면(연직 프레임), 층고 h, 압출폭 w
    ax = axes[0]
    ax.grid(False)
    bead = dict(boxstyle="round,pad=0,rounding_size=0.06")
    for i in range(3):                                 # 베드 층 (z ≤ h)
        ax.add_patch(FancyBboxPatch((i * w, 0), w, h, fc="0.85", ec="0.5", lw=0.6, **bead))
    for i in range(3):                                 # 둘째 층
        ax.add_patch(FancyBboxPatch((i * w + 0.0, h), w, h, fc="0.85", ec="0.5", lw=0.6, **bead))
    p = (3 * w + 0.33, 2 * h + h / 2)                  # 새 점
    ax.add_patch(Rectangle((p[0] - w, p[1] - vf * h), 2 * w, vf * h, fc=TAB10[0],
                           alpha=0.18, ec=TAB10[0], lw=0.8, ls="--"))
    ax.add_patch(FancyBboxPatch((p[0] - w / 2, p[1] - h / 2), w, h, fc="white",
                                ec=TAB10[3], lw=0.9, **bead))
    ax.plot(*p, "o", ms=3, color=TAB10[3])
    q = (2 * w + w / 2, h + h / 2)
    ax.plot(*q, "o", ms=3, color="0.3")
    ax.axhline(0, color="k", lw=1.0)
    ax.annotate("", xy=(p[0] + w, p[1] + h / 2 + 0.06), xytext=(p[0] - w, p[1] + h / 2 + 0.06),
                arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(p[0], p[1] + h / 2 + 0.09, f"수평 ≤ {w:g} mm (압출폭)", ha="center", va="bottom", fontsize=7)
    ax.annotate("", xy=(p[0] + w + 0.06, p[1]), xytext=(p[0] + w + 0.06, p[1] - vf * h),
                arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(p[0] + w + 0.1, p[1] - vf * h / 2, f"수직\n(0, {vf:g}h]", ha="left",
            va="center", fontsize=7)
    ax.text(0.02, -0.05, "베드: z ≤ h 이면 지지", fontsize=6.5, va="top", ha="left")
    ax.text(0.02, 3 * h + 0.46, "● 새 점 p", fontsize=6.5, color=TAB10[3], va="top")
    ax.text(0.02, 3 * h + 0.32, "● 먼저 쌓인 점 (지지 후보)", fontsize=6.5, color="0.3", va="top")
    ax.text(p[0] + w + 0.08, p[1] - vf * h - 0.02, "창 안에 먼저 쌓인\n점이 있으면 지지", ha="left",
            va="top", fontsize=6.5, color=TAB10[0])
    ax.set_xlim(-0.05, p[0] + w + 0.75)
    ax.set_ylim(-0.2, 3 * h + 0.5)
    ax.set_yticks([0, h, 2 * h, 3 * h])
    ax.set_yticklabels(["0", "h", "2h", "3h"])
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_xlabel("수평 방향 (연직 프레임 단면)")
    ax.set_ylabel("z")
    panel_label(ax, "(a)")

    # (b) Δr 스윕
    ax = axes[1]
    ax.step(d["sweep"]["dr"], d["sweep"]["dr_supported"], where="mid", color=TAB10[0])
    ax.axvline(w, color="0.4", ls="--", lw=0.7)
    ax.text(w + 0.01, 0.5, f"w = {w:g}", fontsize=7, color="0.3")
    ax.set_xlabel("층당 바깥 이동 Δr (mm)")
    ax.set_ylabel("둘째 고리 지지 비율")
    ax.set_ylim(-0.05, 1.08)
    panel_label(ax, "(b)")

    # (c) 수직 간격 스윕
    ax = axes[2]
    ax.step(d["sweep"]["gap_over_h"], d["sweep"]["gap_supported"], where="mid", color=TAB10[1])
    ax.axvline(vf, color="0.4", ls="--", lw=0.7)
    ax.text(vf + 0.02, 0.5, f"{vf:g}h", fontsize=7, color="0.3")
    ax.set_xlabel(f"층 수직 간격 / h (h={h:g})")
    ax.set_ylim(-0.05, 1.08)
    ax.set_yticklabels([])
    panel_label(ax, "(c)")
    fig.tight_layout()
    save(fig, "checker_criterion", __file__, ["report_fig_checker_results.json",
                                               "conical/toolpath.py"],
         "G: 검사기 A 지지 정의(수평 ≤ 0.45mm, 수직 (0,1.5h], 베드 z ≤ h) 모식도와 합성 고리 시험",
         {"width_mm": w, "vwin_factor": vf, "bed_factor": d["defaults"]["bed_factor"],
          "sample_spacing_mm": d["defaults"]["sample_spacing"],
          "six_cases_match": d["all_match"],
          "implied_planar_deg": {k: round(v, 1) for k, v in
                                 d["implied_planar_overhang_deg"].items()}})


if __name__ == "__main__":
    main()
