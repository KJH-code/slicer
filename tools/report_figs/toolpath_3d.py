"""toolpath_3d — L3b(램프, 밴드 22°→0°) G-code 의 압출 경로 3D, 색 = |B| (노즐 기울기).

REP5X 는 극(축) 통과 때 B 부호를 뒤집고 C 를 180° 돌린다(같은 물리 기울기) — 그래서 색은 |B|.
(b) 층 번호 대 그 층의 B: |B| (선) 과 부호 있는 B (점).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection  # noqa: E402

from tools.report_figs import gcodeio  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    CM,
    COLORS,
    FULL,
    ROOT,
    panel_label,
    save,
    setup,
)

G = "examples/rep5x_ladder/L3b_lamp_band22to0.gcode"


def main():
    setup()
    _, L = gcodeio.read(ROOT / G)
    ks = sorted(L)
    seg = np.concatenate([L[k]["seg"] for k in ks])
    b = np.concatenate([L[k]["b"] for k in ks])
    fig = plt.figure(figsize=(FULL, 8.5 * CM), constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1])
    ax = fig.add_subplot(gs[0], projection="3d")
    lc = Line3DCollection(seg, cmap="viridis", linewidths=0.35)
    lc.set_array(np.abs(b))
    lc.set_clim(0, 22)
    ax.add_collection3d(lc)
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_zlim(0, 18)
    ax.set_box_aspect((10, 10, 18))
    ax.set_xlabel("x (mm)", labelpad=-6)
    ax.set_ylabel("y (mm)", labelpad=-6)
    ax.set_zlabel("z (mm)", labelpad=-4)
    ax.tick_params(labelsize=6, pad=-2)
    ax.view_init(elev=18, azim=-60)
    cb = fig.colorbar(lc, ax=ax, shrink=0.6, pad=0.0)
    cb.set_label("|B| (°)")
    ax.text2D(0.0, 1.0, "(a)", transform=ax.transAxes, fontsize=10, va="top")

    a2 = fig.add_subplot(gs[1])
    bl = np.array([np.abs(L[k]["b"]).mean() for k in ks])
    a2.plot(ks, bl, color=COLORS[0], label="|B| (층 평균)")
    for k in ks:
        u = np.unique(L[k]["b"])
        a2.plot(np.full(len(u), k), u, ".", color=COLORS[1], ms=3,
                label="B 값 (부호 있음)" if k == ks[0] else None)
    a2.axhline(0, color="0.5", lw=0.5)
    a2.set_xlabel("층 번호")
    a2.set_ylabel("B (°)")
    a2.legend(fontsize=7, loc="center left")
    panel_label(a2, "b")
    blend = [k for k, v in zip(ks, bl, strict=True) if 0.01 < v < 21.99]
    blend_b = ", ".join(f"{np.abs(L[k]['b']).mean():.2f}" for k in blend)
    save(fig, "toolpath_3d", __file__, [G],
         "L3b(램프 밴드 22°→0°) 압출 경로 3D (색 = |B|) 와 층별 B 각",
         f"층 {len(ks)}개, 압출 선분 {len(seg)}개; |B| 22° 층 {int(np.sum(bl > 21.99))}, "
         f"블렌드 층 {blend} (|B| {blend_b}°), "
         f"0° 층 {int(np.sum(bl < 0.01))}")
    print(len(ks), blend)


if __name__ == "__main__":
    main()
