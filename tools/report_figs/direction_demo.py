"""direction_demo — 원뿔 방향(outward/inward) 자동 결정 예시 (보고서 그림 C).

데이터: report_fig_direction_results.json (python3 report_fig_direction.py)
행: 안쪽 오버행 그릇(inner) / 바깥 오버행 그릇(outer).
열: (단면) 연직 기준 60° 어깨, 0° 에서 서포트가 필요한 면을 빨강으로 · S(θ) 두 방향 · J(θ) = S(0) - S(θ) - kθ ·
    검사기 A 미지지 mm (구멍을 살린 단면으로 분류한 사후 진단, 층고 0.3/0.4) — 가로축은 부호 있는 θ (+ outward).

    python3 tools/report_figs/direction_demo.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, plt, save, setup  # noqa: E402

TITLE = {"inner": "안쪽 오버행", "outer": "바깥 오버행"}
# 0° 에서 오버행인 변 (단면 꼭짓점 번호 i → i+1)
OVER_EDGE = {"inner": 6, "outer": 2}
OUT_C, IN_C = TAB10[0], TAB10[1]


def main():
    setup()
    d = json.load(open(os.path.join(ROOT, "report_fig_direction_results.json")))
    k = d["meta"]["k"]
    fig, axes = plt.subplots(2, 4, figsize=(FULL_W, 9.0 / 2.54),
                             gridspec_kw={"width_ratios": [0.8, 1, 1, 1.15]})
    letters = iter("abcdefgh")
    for row, name in enumerate(("inner", "outer")):
        dm = d["demos"][name]
        sec = np.array(d["meta"]["sections"][name] + [d["meta"]["sections"][name][0]])
        sel = dm["selection"]["grid_uniform"]

        ax = axes[row, 0]
        ax.fill(sec[:, 0], sec[:, 1], color="0.85", lw=0)
        ax.fill(-sec[:, 0], sec[:, 1], color="0.85", lw=0)
        ax.plot(sec[:, 0], sec[:, 1], color="0.4", lw=0.6)
        ax.plot(-sec[:, 0], sec[:, 1], color="0.4", lw=0.6)
        i = OVER_EDGE[name]
        for sgn in (1, -1):
            ax.plot(sgn * sec[i:i + 2, 0], sec[i:i + 2, 1], color=TAB10[3], lw=2.0)
        ax.axvline(0, color="0.5", lw=0.5, ls="-.")
        ax.set_aspect("equal")
        ax.set_xlim(-14.5, 14.5)
        ax.set_ylim(-1, 17)
        ax.grid(False)
        ax.set_xticks([-10, 0, 10])
        ax.set_yticks([0, 8, 16])
        ax.set_ylabel("z (mm)")
        if row == 1:
            ax.set_xlabel("r (mm)")
        ax.text(0.0, 1.03, f"({next(letters)}) {TITLE[name]}", transform=ax.transAxes,
                fontsize=7.5, fontweight="bold")

        c = dm["curves"]
        th = np.array(c["theta"])
        ax = axes[row, 1]
        ax.plot(th, c["outward"]["S"], color=OUT_C, label="outward")
        ax.plot(th, c["inward"]["S"], color=IN_C, ls="--", label="inward")
        ax.set_ylabel("남은 서포트 S (%)")
        ax.set_ylim(0, 30)
        if row == 1:
            ax.set_xlabel("원뿔각 |θ| (°)")
        ax.legend(fontsize=6.5, loc="lower left")
        ax.text(0.0, 1.03, f"({next(letters)})", transform=ax.transAxes, fontsize=9,
                fontweight="bold")

        ax = axes[row, 2]
        ax.plot(th, c["outward"]["J"], color=OUT_C)
        ax.plot(th, c["inward"]["J"], color=IN_C, ls="--")
        ax.axhline(0, color="0.5", lw=0.5)
        t_ex = abs(dm["selection"]["exact_uniform"])
        ax.plot(abs(sel), np.interp(abs(sel), th, c["inward" if sel < 0 else "outward"]["J"]),
                "v", color="k", ms=5)
        ax.text(17, 15,
                f"선택 {'inward' if sel < 0 else 'outward'} {abs(sel):g}°\n(정확 {t_ex:.1f}°)",
                fontsize=6.5, va="center")
        ax.set_ylabel(f"J = S(0) - S(θ) - {k:g}θ")
        ax.set_ylim(-10, 20)
        if row == 1:
            ax.set_xlabel("원뿔각 |θ| (°)")
        ax.text(0.0, 1.03, f"({next(letters)})", transform=ax.transAxes, fontsize=9,
                fontweight="bold")

        ax = axes[row, 3]
        for lh, col, mk in (("0.3", TAB10[2], "o"), ("0.4", TAB10[4], "D")):
            rows = dm["checker"][lh]
            ts = sorted(rows, key=float)
            ax.plot([float(t) for t in ts], [rows[t]["hole_mm"] for t in ts], "-" + mk, color=col,
                    ms=2.8, label=f"층고 {lh}")
        ax.axvline(sel, color="k", lw=0.7, ls=":")
        ax.axvline(0, color="0.5", lw=0.5)
        ax.set_ylabel("미지지 mm (구멍 살림)")
        ax.set_ylim(-20, 820)
        ax.text(0.02, 0.99, "inward", transform=ax.transAxes, fontsize=6.5, va="top", color=IN_C)
        ax.text(0.98, 0.99, "outward", transform=ax.transAxes, fontsize=6.5, va="top",
                ha="right", color=OUT_C)
        if row == 1:
            ax.set_xlabel("부호 있는 θ (°)")
            ax.legend(fontsize=6.5, loc="lower right", bbox_to_anchor=(1.0, 0.1))
        if row == 0:
            ax.annotate("바닥 가장자리 한 고리\n(z≈0.5, 어깨와 무관)", xy=(-26, 80), xytext=(-31, 640),
                        fontsize=6, color="0.35", arrowprops=dict(arrowstyle="-", lw=0.5, color="0.5"))
        ax.text(0.0, 1.03, f"({next(letters)})", transform=ax.transAxes, fontsize=9,
                fontweight="bold")
    fig.tight_layout(w_pad=0.6, h_pad=0.8)
    key = {"sample_inward_counts": {a: v["n_inward"] for a, v in d["sample_inward_tally"].items()},
           "C1_pass": d["C1"]["pass"],
           "selection": {n: d["demos"][n]["selection"] for n in ("inner", "outer")},
           "C2_prereg": {n: {lh: (v and v["pass"]) for lh, v in d["demos"][n]["C2"].items()}
                         for n in ("inner", "outer")},
           "C2_hole_aware": {n: {lh: (v and v["post_hoc_hole_aware"]["chosen_better"])
                                 for lh, v in d["demos"][n]["C2"].items()}
                             for n in ("inner", "outer")}}
    save(fig, "direction_demo", __file__, ["report_fig_direction_results.json",
                                            "conical/exact_angle.py", "conical/toolpath.py"],
         "C: 안쪽/바깥 오버행 그릇에서 방향 자동 결정 — 단면, S(θ)·J(θ) 두 방향, 검사기 미지지(구멍 살린 분류)",
         key)


if __name__ == "__main__":
    main()
