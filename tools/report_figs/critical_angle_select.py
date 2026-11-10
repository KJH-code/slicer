"""critical_angle_select — 21 모델의 면별 임계각 θ* 분포 위에 고른 각도와 베드 상한 (보고서 그림 A).

데이터: report_fig_critical_angle_results.json (python3 report_fig_critical_angle.py)
행마다: 0° 에서 서포트가 필요한 면의 부호 있는 θ* (outward +, inward -, 1° 칸, 면적 가중, 행 안에서 최대=1 로
정규화) 를 그리고 (높이 밴드로 나눠 보면 21 모델 모두 0° 필요 면이 전부 아래 밴드에 있다 — 위 밴드 몫 0), 자동 균일 θ_J(▼), 밴드2 의 θ1·θ2(세로 막대), 베드 상한 22.79° 를 표시.
오른쪽 숫자: 0° 필요 면적(모델 면적 %) / 그중 θ* > 22.79° 이거나 44° 안에서 못 푸는 몫(%).

    python3 tools/report_figs/critical_angle_select.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, plt, save, setup  # noqa: E402

NAME = {"sphere": "구(ico)", "funnel": "깔때기", "torus": "토러스", "mushroom": "버섯"}


def main():
    setup()
    d = json.load(open(os.path.join(ROOT, "report_fig_critical_angle_results.json")))
    cap = d["meta"]["bed_cap_deg"]
    bins = np.array(d["bins_deg"])
    left = bins[:-1]
    rows = d["rows"]
    n = len(rows)
    fig, ax = plt.subplots(figsize=(FULL_W, 13.0 / 2.54))
    ax.grid(False)
    for i, r in enumerate(rows):
        y0 = n - 1 - i
        lo = np.array(r["hist_by_band"]["0"])
        hi = np.array(r["hist_by_band"]["1"])
        tot = lo + hi
        s = 0.82 / tot.max() if tot.max() > 0 else 0
        ax.bar(left, tot * s, width=1.0, bottom=y0, align="edge", color="0.55", lw=0)
        ax.axhline(y0, color="0.75", lw=0.4)
        tj = r["auto_uniform"]
        ax.plot(tj, y0 + 0.9, "v", color="k", ms=4.2, zorder=5)
        for t, c in zip(r["auto_band2"], (TAB10[0], TAB10[1]), strict=True):
            ax.plot([t, t], [y0, y0 + 0.86], color=c, lw=1.1, ls=(0, (2, 1)), zorder=4)
        if tot.max() == 0:
            ax.text(-20, y0 + 0.4, "0~44° 로 풀리는 면 없음 (평평한 아랫면만)", fontsize=6.5,
                    color="0.4", ha="center", va="center")
        ax.text(45.5, y0 + 0.4, f"{r['need0_pct']:.1f} / {r['over_cap_share_of_need0']:.0f}",
                fontsize=6.5, va="center", ha="left")
    ax.axvline(cap, color=TAB10[3], ls="--", lw=0.8)
    ax.axvline(0, color="0.4", lw=0.5)
    ax.text(cap + 0.4, n + 0.05, f"베드 상한 {cap:g}°", color=TAB10[3], fontsize=7, va="bottom")
    ax.text(45.5, n + 0.05, "0°필요% / 상한초과몫%", fontsize=6.5, va="bottom")
    ax.set_yticks(np.arange(n) + 0.4)
    ax.set_yticklabels([NAME.get(r["model"], r["model"]) for r in rows][::-1], fontsize=7)
    ax.set_ylim(-0.1, n + 0.6)
    ax.set_xlim(-42, 45)
    ax.set_xlabel("면별 임계각 θ* (°)   + outward / - inward, 두 방향 중 작은 쪽")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    h = [plt.Rectangle((0, 0), 1, 1, color="0.55", label="θ* 면적 분포"),
         plt.Line2D([], [], marker="v", ls="", color="k", label="자동 균일 θ_J"),
         plt.Line2D([], [], color=TAB10[0], ls=(0, (2, 1)), label="밴드2 θ1 (아래)"),
         plt.Line2D([], [], color=TAB10[1], ls=(0, (2, 1)), label="밴드2 θ2 (위)")]
    ax.legend(handles=h, fontsize=6.5, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=5,
              handlelength=1.4, columnspacing=1.0, borderaxespad=0.3)
    fig.tight_layout()
    rc = d["recheck_critical_angle_hist"]
    save(fig, "critical_angle_select", __file__,
         ["report_fig_critical_angle_results.json", "t1_conventional_results.json",
          "conical/analytic.py", "conical/exact_angle.py"],
         "A: 21 모델 면별 임계각 θ* 분포(0° 필요 면은 전부 아래 밴드)와 자동 균일·밴드2 각, 베드 상한 22.79°",
         {"recheck_old_hist_all_match_0p1": all(v["match_0p1"] for v in rc.values()),
          "why_check_pass": f"{d['why_criterion']['n_pass']}/{d['why_criterion']['n_checked']}",
          "exact_vs_grid_within_2deg": f"{d['exact_vs_grid_within_2deg']}/{n}",
          "over_cap_share_median_pct": round(float(np.median(
              [r["over_cap_share_of_need0"] for r in rows])), 1),
          "upper_band_need0_area_pct_max": round(max(sum(r["hist_by_band"]["1"]) for r in rows), 3)})


if __name__ == "__main__":
    main()
