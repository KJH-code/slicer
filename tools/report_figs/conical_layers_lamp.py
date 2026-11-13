"""conical_layers_lamp — 램프 실제 층의 r–z 단면: (a) 균일 22°, (b) 밴드 22°→0°, + 밴드 단독(라벨 없음).

데이터: examples/rep5x_ladder/L3a_lamp_u22.gcode, L3b_lamp_band22to0.gcode (압출 끝점의
r=√(x²+y²), z), 외곽선은 lamp_small.stl 의 y=0 단면(x≥0 반쪽).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from conical.profile import AngleProfile  # noqa: E402
from tools.report_figs import gcodeio  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    COLORS,
    ROOT,
    figure,
    panel_label,
    save,
    setup,
)

D = "examples/rep5x_ladder"
GA = f"{D}/L3a_lamp_u22.gcode"
GB = f"{D}/L3b_lamp_band22to0.gcode"
STL = f"{D}/lamp_small.stl"


def outline(ax, mesh):
    sec = mesh.section(plane_origin=[0, 0, 0], plane_normal=[0, 1, 0])
    for ent in sec.entities:
        p = sec.vertices[ent.points]
        x, z = p[:, 0], p[:, 2]
        ax.plot(x, z, color="k", lw=1.2, zorder=5)


def layers_rz(path):
    meta, L = gcodeio.read(ROOT / path)
    out = []
    for k in sorted(L):
        seg = L[k]["seg"]                   # 압출 선분 (실제 노즐 직선 이동)
        t = np.linspace(0.0, 1.0, 21)[None, :, None]
        p = (seg[:, :1, :] * (1 - t) + seg[:, 1:, :] * t).reshape(-1, 3)
        r = np.hypot(p[:, 0], p[:, 1])
        o = np.argsort(r)
        out.append((k, L[k]["zp"], r[o], p[o, 2], float(np.abs(L[k]["b"]).mean())))
    return meta, out


def draw(ax, mesh, path):
    """한 패널: 층을 각도 구간 색으로 그리고 외곽선·블렌드 띠를 얹는다. 층 통계를 돌려준다."""
    meta, lays = layers_rz(path)
    prof = AngleProfile([(z, t) for z, t in meta["profile"]])
    blends = prof.blend_intervals()
    n_blend = 0
    for _k, zp, r, z, b in lays:
        in_blend = any(a - 1e-9 <= zp <= c + 1e-9 for a, c in blends)
        n_blend += in_blend
        col = COLORS[3] if in_blend else (COLORS[0] if b > 1e-6 else COLORS[2])
        ax.plot(r, z, color=col, lw=0.6, alpha=0.9)
        ax.plot(-r, z, color=col, lw=0.6, alpha=0.9)
    outline(ax, mesh)
    ax.set_xlim(-5.3, 5.3)
    ax.set_ylim(-0.3, 18.8)
    ax.set_aspect("equal")
    # 블렌드 구간: 축(r=0)에서 Z′ 와 같음 — 축 위 Z′ 범위를 띠로
    for a, c in blends:
        ax.axhspan(a, c, color=COLORS[3], alpha=0.12, lw=0)
        ax.text(-5.1, (a + c) / 2, "블렌드", fontsize=7.5, va="center", ha="left")
    return {"layers": len(lays), "blend_layers": n_blend, "blends": blends}


def main():
    setup()
    mesh = trimesh.load(ROOT / STL, force="mesh")
    fig, axs = figure("full", 9.5, ncols=2, sharey=True)
    keys = {}
    for ax, path, letter in ((axs[0], GA, "a"), (axs[1], GB, "b")):
        keys[letter] = draw(ax, mesh, path)
        ax.set_xlabel("반경 r (mm)  (축대칭 — 좌우는 같은 값)")
        panel_label(ax, letter)
    axs[0].set_ylabel("높이 z (mm)")
    from matplotlib.lines import Line2D
    h = [Line2D([], [], color=COLORS[0], lw=1.2, label="θ = 22° 층"),
         Line2D([], [], color=COLORS[3], lw=1.2, label="블렌드 층 (22°→0°)"),
         Line2D([], [], color=COLORS[2], lw=1.2, label="θ = 0° 층"),
         Line2D([], [], color="k", lw=1.2, label="모델 외곽 (STL 단면)")]
    fig.legend(handles=h, loc="outside lower center", ncols=4)
    kb = keys["b"]
    save(fig, "conical_layers_lamp", __file__, [GA, GB, STL],
         "램프(lamp_small) 실제 G-code 층의 r–z 단면(압출 선분을 21점씩 샘플, 축대칭이라 ±r 로 펼침): (a) 균일 22°, (b) 밴드 22°→0°. 블렌드 띠는 축 위 Z′ 범위",
         f"층 수 (a) {keys['a']['layers']} / (b) {kb['layers']}; (b) 블렌드 Z′ "
         f"{kb['blends'][0][0]:.2f}~{kb['blends'][0][1]:.2f} mm, 블렌드 층 {kb['blend_layers']}개")

    # 밴드 패널 단독 — 다른 그림(band_vs_radius 의 (a)~(d)) 옆에 붙여 쓰는 용도라
    # 패널 라벨을 넣지 않고, 잘라 쓰지 않아도 되게 축 이름·눈금을 다 갖춘다.
    fig, ax = figure("half", 9.5)
    kb = draw(ax, mesh, GB)
    ax.set_xlabel("반경 r (mm)")
    ax.set_ylabel("높이 z (mm)")
    save(fig, "conical_layers_lamp_band", __file__, [GB, STL],
         "램프(lamp_small) 밴드 22°→0° 실제 G-code 층의 r–z 단면, 패널 라벨 없음(다른 그림과 합쳐 쓰는 용도). "
         "파랑 22°, 빨강 블렌드, 초록 0°, 검정 STL 외곽. 축대칭이라 ±r 로 펼침",
         f"층 수 {kb['layers']}; 블렌드 Z′ {kb['blends'][0][0]:.2f}~{kb['blends'][0][1]:.2f} mm, "
         f"블렌드 층 {kb['blend_layers']}개")


if __name__ == "__main__":
    main()
