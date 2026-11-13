"""g_theta_funnel — (a) 오버행 면의 g(θ) 곡선과 문턱, (b) 변환공간에서 잰 오버행 대 실제 유효 오버행.

g(θ) = n_z·cosθ + n_r·sinθ (conical/analytic.py). 축대칭 벽의 오버행 α(연직에서 잰 각)이면
n = (n_r, n_z) = (cosα, −sinα) 이라 g(θ) = −sin(α−θ). 판정: g < κ = -sin45° 이면 서포트.
funnel 벽: R=14, h=5 → α = atan(R/h) = 70.35°.
(b) 변환공간 벽 기울기 m = h·cosθ/R + sinθ (docs/warped_threshold_finding.md) → 그 공간의
오버행 90° − atan(m). 오른쪽 축: examples/funnel.stl 의 analytic.support_fraction(θ, outward).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

from conical import analytic  # noqa: E402
from conical.meshio import center_on_axis  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    COLORS,
    ROOT,
    figure,
    panel_label,
    save,
    setup,
)

R_F, H_F = 14.0, 5.0
STL = "examples/funnel.stl"


def main():
    setup()
    kappa = -np.sin(np.radians(45.0))
    alpha = np.degrees(np.arctan(R_F / H_F))
    th = np.linspace(0, 60, 1201)
    fig, (a1, a2) = figure("full", 7.0, ncols=2)

    # (a)
    for i, al in enumerate((50.0, 60.0, alpha, 80.0)):
        g = -np.sin(np.radians(al - th))
        main_curve = abs(al - alpha) < 1e-9
        a1.plot(th, g, color=COLORS[3] if main_curve else COLORS[[0, 1, 0, 4][i]],
                lw=1.6 if main_curve else 1.0, alpha=1 if main_curve else 0.7,
                label=f"α = {al:.1f}° (funnel 벽)" if main_curve else f"α = {al:.0f}°")
    a1.axhline(kappa, color="k", ls="--", lw=1.0, label="문턱 κ = -sin45°")
    ts = alpha - 45.0
    a1.plot([ts], [kappa], "o", color=COLORS[3], ms=4, zorder=5)
    a1.annotate(f"θ* = {ts:.1f}°", xy=(ts, kappa), xytext=(ts + 6, kappa - 0.12),
                fontsize=8, arrowprops={"arrowstyle": "-", "lw": 0.6})
    a1.set_xlabel("원뿔각 θ (°)")
    a1.set_ylabel(r"$g(\theta)=n_z\cos\theta+n_r\sin\theta$")
    a1.set_xlim(0, 60)
    a1.legend(loc="upper left", fontsize=7)
    panel_label(a1, "a")

    # (b)
    eff = alpha - th
    warped = 90.0 - np.degrees(np.arctan(H_F * np.cos(np.radians(th)) / R_F
                                         + np.sin(np.radians(th))))
    t_eff = alpha - 45.0
    t_w = brentq(lambda t: 90.0 - np.degrees(np.arctan(H_F * np.cos(np.radians(t)) / R_F
                                                       + np.sin(np.radians(t)))) - 45.0, 0, 89)
    a2.plot(th, eff, color=COLORS[3], label="실제 유효 오버행 α - θ")
    a2.plot(th, warped, color=COLORS[7], ls="-.", label="변환공간에서 잰 오버행")
    a2.axhline(45, color="k", ls="--", lw=1.0)
    for t, c in ((t_eff, COLORS[3]), (t_w, COLORS[7])):
        a2.axvline(t, color=c, lw=0.7, ls=":")
        a2.plot([t], [45], "o", color=c, ms=4, zorder=5)
        a2.text(t + 0.8, 47, f"{t:.1f}°", color=c, fontsize=8)
    a2.set_xlabel("원뿔각 θ (°)")
    a2.set_ylabel("벽 오버행 (°, 연직 기준)")
    a2.set_xlim(0, 60)
    a2.set_ylim(0, 75)
    panel_label(a2, "b")

    mesh = center_on_axis(trimesh.load(ROOT / STL, force="mesh"))
    tg = np.arange(0, 60.01, 0.5)
    sf = np.array([analytic.support_fraction(mesh, float(t), "outward") for t in tg])
    ax3 = a2.twinx()
    ax3.plot(tg, sf, color=COLORS[0], lw=1.0, alpha=0.8, label="funnel.stl 서포트 면적 (해석식)")
    ax3.set_ylabel("서포트 필요 면적 (%)", color=COLORS[0])
    ax3.tick_params(axis="y", colors=COLORS[0])
    ax3.grid(False)
    ax3.set_ylim(0, max(60, sf.max() * 1.1))
    h1, l1 = a2.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    a2.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=7)
    first_zero = float(tg[np.argmax(sf <= 1e-9)]) if (sf <= 1e-9).any() else None

    save(fig, "g_theta_funnel", __file__, [STL],
         "(a) 오버행 α 면의 g(θ)=−sin(α−θ) 와 문턱 −sin45°, (b) funnel 벽의 변환공간 오버행 대 실제 유효 오버행",
         f"funnel α={alpha:.2f}°, θ*={ts:.2f}°; 45° 통과 각 실제 {t_eff:.1f}° 대 변환공간 {t_w:.1f}°; "
         f"funnel.stl 해석식 서포트 0° {sf[0]:.1f}% → 0% 첫 각 {first_zero}° (0.5° 격자)")
    print(alpha, ts, t_w, sf[0], first_zero)


if __name__ == "__main__":
    main()
