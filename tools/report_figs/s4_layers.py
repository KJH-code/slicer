"""s4_layers — S4 곡면 층(z′ 등위선) vs 균일 최선 원뿔 층, r–z 단면(y=0).

    python3 tools/report_figs/s4_layers.py --fields <s4_compare --save-fields 폴더>   # 단면 캐시 생성 + 그림
    python3 tools/report_figs/s4_layers.py                                            # 캐시로 그림만

데이터: S4 실행의 사면체·변형 점(npz, 저장소 밖) → y=0 단면을 잘라
`docs/report/figures/data/s4_layers_slices.json` 에 캐시(단면 삼각형, x, z, z′).
원뿔 층은 같은 단면에서 z′ = z + c·|x|·tanθ (θ·c = s4_comparison_results.json 의
균일 최선). 대표 실행 = R2·P1 (없으면 R1·P1). 등위선 간격은 각 층 함수 범위를 14등분.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import _s4style as st  # noqa: E402

sys.path.insert(0, os.path.join(st.ROOT, "tools"))
from s4_dof_ladder import MODELS, NAMES, pick  # noqa: E402

CACHE = os.path.join(st.FIG_DIR, "data", "s4_layers_slices.json")
N_LEVELS = 14


def build_cache(fields, rows):
    import pyvista as pv

    out = {}
    for m in MODELS:
        r = pick(rows, m)
        if r is None:
            continue
        f = os.path.join(fields, f"{m}_{r['res']}_{r['params']}.npz")
        if not os.path.exists(f):
            continue
        d = np.load(f)
        cells = d["cells"]
        cc = np.hstack([np.full((len(cells), 1), 4), cells]).ravel()
        g = pv.UnstructuredGrid(cc, np.full(len(cells), pv.CellType.TETRA), d["X"])
        g.point_data["zp"] = d["Y"][:, 2]
        s = g.slice(normal="y", origin=(0, 0, 0)).triangulate()
        tri = s.faces.reshape(-1, 4)[:, 1:]
        # 모델 외곽 = 사면체 경계 표면을 y=0 평면으로 자른 선분
        import trimesh
        from s4_compare import boundary_surface
        btri, _ = boundary_surface(d["X"], cells)
        sec = trimesh.Trimesh(d["X"], btri, process=False).section(
            plane_origin=[0, 0, 0], plane_normal=[0, 1, 0])
        segs = sec.vertices[sec.vertex_nodes][:, :, [0, 2]] if sec is not None else []
        out[m] = {"outline": np.round(np.asarray(segs), 4).tolist(),"run": f"{m}_{r['res']}_{r['params']}",
                  "x": np.round(s.points[:, 0], 4).tolist(),
                  "z": np.round(s.points[:, 2], 4).tolist(),
                  "zp": np.round(s.point_data["zp"], 4).tolist(),
                  "tri": tri.tolist()}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(out, open(CACHE, "w"), separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", default=None)
    a = ap.parse_args()
    st.setup()
    rows = json.load(open(os.path.join(st.ROOT, "s4_comparison_results.json"), encoding="utf-8"))
    if a.fields:
        build_cache(a.fields, rows)
    data = json.load(open(CACHE))
    models = [m for m in MODELS if m in data]
    ncol = 3 if len(models) > 4 else 2
    nrow = int(np.ceil(len(models) / ncol))
    fig, axes = st.plt.subplots(nrow, ncol, figsize=(st.FULL, 5.4 * st.CM * nrow))
    axes = np.atleast_1d(axes).ravel()
    key = {}
    import matplotlib.tri as mtri
    from matplotlib.lines import Line2D

    for i, m in enumerate(models):
        ax = axes[i]
        s = data[m]
        x, z, zp = np.array(s["x"]), np.array(s["z"]), np.array(s["zp"])
        tri = np.array(s["tri"])
        T = mtri.Triangulation(x, z, tri)
        r = pick(rows, m)
        th = np.radians(r["cone"]["uniform_angle"])
        c = 1.0 if r["cone"]["uniform_dir"] == "outward" else -1.0
        zc = z + c * np.abs(x) * np.tan(th)
        for vals, col in ((zc, st.TAB10[1]), (zp, st.TAB10[0])):
            lv = np.linspace(vals.min(), vals.max(), N_LEVELS + 2)[1:-1]
            ax.tricontour(T, vals, levels=lv, colors=[col], linewidths=0.7)
        from matplotlib.collections import LineCollection
        ax.add_collection(LineCollection(np.array(s["outline"]), colors="0.2", linewidths=0.7))
        ax.set_aspect("equal")
        ax.set_ylabel("z (mm)")
        cv = r["curvature"]
        ax.set_xlabel(f"x (mm)\n원뿔 {r['cone']['uniform_angle']:.0f}° "
                      f"{'바깥' if c > 0 else '안쪽'} · S4 θ {cv['theta_deg_p05']:.0f}~"
                      f"{cv['theta_deg_p95']:.0f}° (5–95%)", fontsize=7.5)
        ax.margins(0.03)
        st.panel(ax, f"{'abcdef'[i]}) {NAMES[m]}")
        key[f"{m}.cone_angle_deg"] = r["cone"]["uniform_angle"]
        key[f"{m}.cone_dir"] = r["cone"]["uniform_dir"]
        key[f"{m}.s4_theta_p05_p95_deg"] = [round(cv["theta_deg_p05"], 1),
                                            round(cv["theta_deg_p95"], 1)]
        key[f"{m}.kappa_m_r_median"] = round(cv["kappa_m_r_median"], 3)
    for ax in axes[len(models):]:
        ax.axis("off")
    fig.legend([Line2D([], [], color=st.TAB10[0]), Line2D([], [], color=st.TAB10[1]),
                Line2D([], [], color="0.2")],
               ["S4 곡면 층 (z′ 등위선)", "균일 최선 원뿔 층", "모델 단면 (y = 0)"],
               loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    st.save(fig, "s4_layers", __file__,
            ["s4_comparison_results.json", "docs/report/figures/data/s4_layers_slices.json"],
            "S4 곡면 층(z′ 등위선)과 균일 최선 원뿔 층을 y=0 단면에 겹친 그림(층 곡률 비교)", key)


if __name__ == "__main__":
    main()
