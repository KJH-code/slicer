"""layer_height_blend — 층고와 블렌드 팽창: 검사기 경계식과 재실행 측정 (보고서 그림 F).

데이터: report_fig_layer_blend_results.json (python3 report_fig_layer_blend.py [--analytic-only])

(a) 경계식 h_c(θ, m) = w·(cot(θ+45°) + tanθ)/m — 이 층고를 넘으면 검사기(수평 ≤ w)가 선택기(θ+45°)보다
    엄격해진다. m 은 층간격 배율(블렌드 안 최대 1.5, 측정 중앙 1.37).
(b) 재실행 측정: 낙관 진짜 오버행 미지지 mm, 균일(J) 실선 / 밴드2 파선 / 밴드2 중 블렌드 층 몫 점선.
(c) 사후 해석: '선택기 통과 & 경계식 실패' 면적 (mm²).

    python3 tools/report_figs/layer_height_blend.py
"""

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

SHORT = {"램프 (=허리 r=2)": "램프(허리 r=2)", "허리 r=3": "허리 r=3", "구": "구"}


def h_c(theta_deg, m, w=0.45):
    t = np.radians(theta_deg)
    return w * (1.0 / np.tan(t + math.pi / 4) + np.tan(t)) / m


def main():
    setup()
    d = json.load(open(os.path.join(ROOT, "report_fig_layer_blend_results.json")))
    w = d["meta"]["width_mm"]
    rows = d["rows"]
    models = list(dict.fromkeys(r["model"] for r in rows))
    fig, axes = plt.subplots(1, 3, figsize=(FULL_W, 6.4 / 2.54))

    # (a) 경계식
    ax = axes[0]
    th = np.linspace(0, 44, 200)
    for m, c, ls in ((1.0, "k", "-"), (1.25, "0.45", "--"), (1.5, TAB10[3], "-")):
        ax.plot(th, h_c(th, m, w), color=c, ls=ls, label=f"m = {m:g}")
    ax.fill_between(th, h_c(th, 1.0, w), 0.6, color="0.85", lw=0)
    for hh in (0.3, 0.4):
        ax.axhline(hh, color=TAB10[0], lw=0.6, ls=":")
        ax.text(0.8, hh + 0.005, f"h = {hh:g}", color=TAB10[0], fontsize=7, ha="left", va="bottom")
    ax.text(22, 0.48, "검사기가 더 엄격\n(m = 1 기준)", fontsize=6.5, ha="center", color="0.3")
    ax.set_xlim(0, 44)
    ax.set_ylim(0.15, 0.55)
    ax.set_xlabel("국소 원뿔각 θ (°)")
    ax.set_ylabel("경계 층고 h_c (mm)")
    ax.legend(fontsize=6.5, loc="lower right")
    panel_label(ax, "(a)")

    # (b) 측정
    ax = axes[1]
    for i, mname in enumerate(models):
        sub = sorted((r for r in rows if r["model"] == mname), key=lambda r: r["layer_height"])
        hs = [r["layer_height"] for r in sub]
        c = TAB10[i]
        ax.plot(hs, [r["uniform"]["mm"] for r in sub], "-o", color=c, ms=2.5)
        ax.plot(hs, [r["band2"]["mm"] for r in sub], "--s", color=c, ms=2.5, mfc="white")
        if any(r["band2"]["blend_mm"] > 0 for r in sub):
            ax.plot(hs, [r["band2"]["blend_mm"] for r in sub], ":", color=c, lw=1.4)
    ax.axvspan(0.37, 0.39, color="0.85", lw=0)
    ax.plot([], [], "-", color="0.3", label="균일(J)")
    ax.plot([], [], "--", color="0.3", label="밴드2")
    ax.plot([], [], ":", color="0.3", lw=1.4, label="밴드2 중 블렌드 층")
    ax.set_xlabel("층고 h (mm)")
    ax.set_ylabel("미지지 길이 (mm, 낙관)")
    ax.legend(fontsize=6, loc="center left", bbox_to_anchor=(0.0, 0.62), handlelength=1.8)
    panel_label(ax, "(b)")

    # (c) 해석식 불일치 면적
    ax = axes[2]
    an = d["analytic_mismatch"]
    for i, mname in enumerate(models):
        v = an[mname]
        ax.plot(v["heights"], v["uniform"]["mismatch_mm2"], "-", color=TAB10[i], label=SHORT[mname])
        ax.plot(v["heights"], v["band2"]["mismatch_mm2"], "--", color=TAB10[i])
    ax.axvspan(0.37, 0.39, color="0.85", lw=0)
    ax.text(0.365, 95, "시작\n0.37~0.39", fontsize=6.5, ha="right", va="center")
    ax.legend(fontsize=6.5, loc="upper left", title="색 = 모델", title_fontsize=6.5)
    ax.set_xlabel("층고 h (mm)")
    ax.set_ylabel(r"선택기 통과·검사기 실패 면적 ($\mathrm{mm}^2$)")
    panel_label(ax, "(c)")
    fig.tight_layout()

    key = {"vertical_window_boundary": "m > 1.5 (층고 무관)",
           "h_c_theta0_m1.5": round(float(h_c(0, 1.5, w)), 3),
           "h_c_min_m1": round(float(h_c(th, 1.0, w).min()), 3),
           "h_c_min_m1.5": round(float(h_c(th, 1.5, w).min()), 3),
           "analytic_onset_h": {SHORT[m]: [an[m]["uniform"]["onset_h"], an[m]["band2"]["onset_h"]]
                                for m in models},
           "blend_m_max_measured": round(max(r["band2"]["blend_m_max_all"] or 0 for r in rows), 3)}
    for r in rows:
        if r["layer_height"] in (0.3, 0.4):
            key[f"{SHORT[r['model']]}@{r['layer_height']:g}:uni/band2/blend_mm"] = [
                round(r["uniform"]["mm"], 1), round(r["band2"]["mm"], 1),
                round(r["band2"]["blend_mm"], 1)]
    save(fig, "layer_height_blend", __file__, ["report_fig_layer_blend_results.json",
                                                "report_figs_exp2_rerun.json"],
         "F: 층고별 검사기-선택기 경계식, 재실행 미지지(블렌드 층 몫), 해석식 불일치 면적", key)


if __name__ == "__main__":
    main()
