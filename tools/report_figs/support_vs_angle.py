"""support_vs_angle — 서포트 면적 S(θ) 와 평가함수 J(θ) = ΔS − k·|θ| (k = config.DEFAULT_K).

S(θ) = analytic.support_fraction (해석식) 을 0~60°, 0.25° 간격으로 outward/inward 모두 계산.
가로축은 부호 있는 각: + = outward, − = inward. 알고리즘이 고른 각 = selector.select_cone(k)
(기본 격자 0~44°, 2° 간격). 모델: compare_ceiling.demo_models() 의 sphere·funnel·torus·mushroom + lamp.stl.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from conical import analytic  # noqa: E402
from conical.config import DEFAULT_K, MAX_ANGLE_DEG  # noqa: E402
from conical.selector import select_cone  # noqa: E402
from tools.report_figs.critical_angle_hist import NAMES, models  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    COLORS,
    figure,
    panel_label,
    save,
    setup,
)


def main():
    setup()
    ms = models()
    th = np.arange(0.0, 60.0 + 1e-9, 0.25)
    fig, axs = figure("full", 9.0, nrows=2, ncols=5, sharex=True)
    info = {}
    for j, (key, mesh) in enumerate(ms.items()):
        so = np.array([analytic.support_fraction(mesh, float(t), "outward") for t in th])
        si = np.array([analytic.support_fraction(mesh, float(t), "inward") for t in th])
        x = np.concatenate([-th[::-1], th[1:]])
        s = np.concatenate([si[::-1], so[1:]])
        base = so[0]
        J = (base - s) - DEFAULT_K * np.abs(x)
        best, _ = select_cone(mesh, DEFAULT_K, verbose=False)
        bx = best["angle"] * (1 if best["direction"] == "outward" else -1)
        a, b = axs[0, j], axs[1, j]
        a.plot(x, s, color=COLORS[0], lw=1.0, drawstyle="steps-mid")
        b.plot(x, J, color=COLORS[2], lw=1.0, drawstyle="steps-mid")
        for ax in (a, b):
            ax.axvspan(-60, -MAX_ANGLE_DEG, color="0.85", lw=0)
            ax.axvspan(MAX_ANGLE_DEG, 60, color="0.85", lw=0)
            ax.axvline(bx, color=COLORS[3], lw=0.8, ls="--")
        a.plot([bx], [best["support"]], "o", color=COLORS[3], ms=3.5, zorder=5)
        b.plot([bx], [best["J"]], "o", color=COLORS[3], ms=3.5, zorder=5)
        a.text(0.5, 0.97, f"{bx:+.0f}°" if bx else "0°", transform=a.transAxes, ha="center", va="top",
               color=COLORS[3], fontsize=8,
               bbox={"fc": "white", "ec": "none", "pad": 1})
        a.set_title(NAMES[key].split("(")[0], fontsize=9)
        a.set_ylim(bottom=0)
        b.set_xlabel("θ (°)")
        b.set_xlim(-60, 60)
        b.set_xticks([-44, 0, 44])
        info[key] = {"base": float(base), "chosen": float(bx), "S_chosen": float(best["support"]),
                     "J": float(best["J"]), "S_min": float(s.min())}
        if j == 0:
            a.set_ylabel("서포트 면적 S (%)")
            b.set_ylabel(f"J = ΔS - {DEFAULT_K}|θ| (%p)")
            panel_label(a, "a")
            panel_label(b, "b")
    txt = "; ".join(f"{NAMES[k].split('(')[0]}: S(0)={v['base']:.1f}% → 선택 {v['chosen']:+.0f}° "
                    f"S={v['S_chosen']:.1f}% J={v['J']:.1f}" for k, v in info.items())
    save(fig, "support_vs_angle", __file__,
         ["compare_ceiling.py", "conical/analytic.py", "conical/selector.py", "examples/lamp.stl"],
         "(a) 해석식 서포트 면적 S(θ) (+ outward / − inward, 0.25° 간격), (b) J(θ)=ΔS−k|θ|, "
         f"k={DEFAULT_K}; 빨간 점선 = select_cone 이 고른 각(2° 격자, ≤{MAX_ANGLE_DEG}°), 회색 = 탐색 범위 밖",
         txt, extra={"numbers": info})
    for k, v in info.items():
        print(k, v)


if __name__ == "__main__":
    main()
