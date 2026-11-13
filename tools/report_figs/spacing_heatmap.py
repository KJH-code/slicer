"""spacing_heatmap — 램프 밴드 프로필(L3b)의 층간격 배율 m = 1 − c·r·s 를 (r, z) 평면에.

프로필은 examples/rep5x_ladder/L3b_lamp_band22to0.gcode 의 ;CONICAL_META 에서 읽는다.
m 은 AngleProfile.spacing_factor(Z′, r) — 변환높이 Z′ 에서 정의되므로 실공간 z = Z′ − c·r·tanθ(Z′)
로 옮겨 그린다. 모델 밖(r > 그 높이의 STL 반경)은 (a)에서 흐리게, (b)는 블렌드 부근을 넓은 r 로.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from conical.config import MAX_SPACING_FACTOR  # noqa: E402
from conical.profile import AngleProfile  # noqa: E402
from tools.report_figs import gcodeio  # noqa: E402
from tools.report_figs.style import ROOT, figure, panel_label, save, setup  # noqa: E402

G = "examples/rep5x_ladder/L3b_lamp_band22to0.gcode"
STL = "examples/rep5x_ladder/lamp_small.stl"


def section_xz(mesh):
    sec = mesh.section(plane_origin=[0, 0, 0], plane_normal=[0, 1, 0])
    return [sec.vertices[e.points][:, [0, 2]] for e in sec.entities]


def main():
    setup()
    meta, _ = gcodeio.read(ROOT / G)
    prof = AngleProfile([(z, t) for z, t in meta["profile"]])
    c = 1.0 if meta["direction"] == "outward" else -1.0
    mesh = trimesh.load(ROOT / STL, force="mesh")
    outl = section_xz(mesh)
    (a0, a1), = prof.blend_intervals()

    fig, (ax1, ax2) = figure("full", 9.0, ncols=2, gridspec_kw={"width_ratios": [1, 1.5]})
    norm = TwoSlopeNorm(vmin=0.5, vcenter=1.0, vmax=2.0)
    out = {}
    for ax, rmax, zw_lo, zw_hi in ((ax1, 5.3, -0.5, 19.5), (ax2, 3.0, a0 - 1.2, a1 + 1.2)):
        r = np.linspace(0, rmax, 400)
        zw = np.linspace(zw_lo, zw_hi, 800)
        R, ZW = np.meshgrid(r, zw)
        M = prof.spacing_factor(ZW, R, meta["direction"])
        Z = ZW - c * R * prof.tan_at(ZW)
        ax.pcolormesh(R, Z, M, cmap="RdBu_r", norm=norm, shading="gouraud",
                      rasterized=True, alpha=0.3)
        pc = ax.pcolormesh(R, Z, M, cmap="RdBu_r", norm=norm, shading="gouraud", rasterized=True)
        pc.set_clip_path(Polygon(outl[0], closed=True, transform=ax.transData))
        cs = ax.contour(R, Z, M, levels=[1 / MAX_SPACING_FACTOR, MAX_SPACING_FACTOR],
                        colors="#2ca02c", linewidths=1.2, linestyles=["--", "--"])
        ax.clabel(cs, fmt={1 / MAX_SPACING_FACTOR: "1/1.5", MAX_SPACING_FACTOR: "m=1.5"},
                  fontsize=7, colors="#2ca02c")
        for p in outl:
            keep = p[:, 0] >= -1e-6
            ax.plot(np.where(keep, p[:, 0], np.nan), p[:, 1], color="k", lw=1.2)
        ax.set_xlabel("반경 r (mm)")
        out[ax] = M
    # 모델 안에서의 최대 m: 실제 층 점 (G-code 압출 끝점) 위에서
    _, L = gcodeio.read(ROOT / G)
    mvals = []
    for d in L.values():
        p = d["seg"][:, 1, :]
        rr = np.hypot(p[:, 0], p[:, 1])
        mvals.append(prof.spacing_factor(np.full(len(rr), d["zp"]), rr, meta["direction"]))
    mvals = np.concatenate(mvals)
    ax1.set_xlim(0, 5.3)
    ax1.set_ylim(-0.3, 18.5)
    ax1.set_aspect("equal")
    ax1.set_ylabel("높이 z (mm)")
    ax2.set_xlim(0, 3.0)
    zlo = a0 - 3.0 * np.tan(np.radians(22.0)) - 0.2
    ax2.set_ylim(zlo, a1 + 0.8)
    ax2.set_ylabel("높이 z (mm)")
    ax1.add_patch(__import__("matplotlib").patches.Rectangle((0, zlo), 3.0, a1 + 0.8 - zlo,
                  fill=False, ec="0.3", lw=0.6, ls=":"))
    panel_label(ax1, "a")
    panel_label(ax2, "b")
    cb = fig.colorbar(pc, ax=[ax1, ax2], shrink=0.9, pad=0.02)
    cb.set_label("층간격 배율 m = 1 - c·r·s")
    save(fig, "spacing_heatmap", __file__, [G, STL, "conical/profile.py"],
         "램프 L3b(22°→0°) 프로필의 층간격 배율 m(r,z) 색지도, 허용 한계 1/1.5·1.5 등고선(초록 점선; 1/1.5 는 압축이 없어 나타나지 않음), "
         "검은 선 = 모델 외곽, 모델 밖은 흐리게. (b)는 블렌드 부근 확대",
         f"블렌드 Z′ {a0:.2f}~{a1:.2f} mm, s = {(prof.tans[2] - prof.tans[1]) / (a1 - a0):.4f}/mm, "
         f"m=1.5 반경 {0.5 / abs((prof.tans[2] - prof.tans[1]) / (a1 - a0)):.2f} mm; "
         f"G-code 압출점 위 m 최대 {mvals.max():.3f}, 최소 {mvals.min():.3f}")
    print(mvals.max(), mvals.min())


if __name__ == "__main__":
    main()
