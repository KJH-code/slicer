"""
run_s4_ceiling.py — S4 Slicer(S³ 의 파이썬 재구현, Joshua Bird, GPL-3.0)를 **우리 모델**에
돌려 자유도 사다리의 천장을 만든다 (docs/dof_ladder.md). 결과는 JSON 하나다.

    python3 tools/run_s4_ceiling.py sphere lamp waist:3 funnel -o s4_results.json
    python3 compare_dof_ladder.py --reanalyze dof_ladder_results.json --s4 s4_results.json

왜 이렇게 하나:
  · S³ 본체는 못 돌리고(Windows GUI), S³ 결과물은 **그들 모델**에만 있다. 우리 모델
    (구·램프·허리·funnel)의 천장은 직접 돌려야 한다.
  · S4 는 GPL-3.0 이고 이 저장소는 MIT 다. 그래서 코드를 **저장소에 넣지 않고**
    실행 시 고정 커밋에서 노트북을 받아 셀의 **함수 정의**만 실행한다. 노트북의
    최상위 문장(모델 로드·그림·GIF)은 쓰지 않는다 — 아래 `_load_s4_functions`.

S4 가 사다리에서 어디에 놓이나 (노트북 `calculate_rotation_matrices` 로 확인):
  셀마다 **접선축**(ẑ × r̂) 둘레로 **스칼라 각**만큼 돌린다. 균일 원뿔은 이 스칼라가
  상수 θ 인 경우이고, 우리 θ(z) 는 z 만의 함수인 경우다. S4 는 그 스칼라를 셀마다
  자유롭게(이웃 차이 벌점으로 매끈하게) 둔다 — 즉 **θ(x,y,z)** 다. S³ 는 축 자체도
  자유(쿼터니언장). 그래서 사다리는
      평면 0 → θ 1 → θ(z) N → θ(x,y,z) [S4] → 쿼터니언장 [S³]
  이고 S4 는 우리 방법의 **직접 일반화**다.

자 (docs/dof_ladder.md §2): 변형된 사면체에서 평면 레이어(법선 ẑ)를 원래 공간으로
되돌리면 셀의 변형 기울기 F 에 대해 법선이 Fᵀẑ 로 당겨진다. 표면 삼각형이 속한
셀의 그 방향을 b̂ 로 쓰고 g = n̂·b̂ < −sin45° 로 센다. 바닥 접촉 면 제외.

⚠ S4 기본 MAX_OVERHANG=30 은 우리 관례로 30°(수직 기준) 라 45° 보다 엄격하다.
  같은 자로 재려고 **45 로 둔다.** 다른 손잡이는 노트북 기본값 그대로이고 결과
  JSON 에 적는다.
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

S4_REPO = "jyjblrd/S4_Slicer"
S4_REV = "bc4b8d90e57beccb8394078b0bda3d60101846a0"      # 2025-04-27 main
S4_NB_URL = f"https://raw.githubusercontent.com/{S4_REPO}/{S4_REV}/main.ipynb"

# 노트북 기본값 (셀 4). MAX_OVERHANG 만 45 로 바꾼다 (자 통일).
S4_PARAMS = dict(NEIGHBOUR_LOSS_WEIGHT=20, MAX_OVERHANG=45, ROTATION_MULTIPLIER=2,
                 SET_INITIAL_ROTATION_TO_ZERO=False, INITIAL_ROTATION_FIELD_SMOOTHING=30,
                 MAX_POS_ROTATION=np.deg2rad(3600), MAX_NEG_ROTATION=np.deg2rad(-3600),
                 ROT_ITERATIONS=100, DEF_ITERATIONS=1000, STEEP_OVERHANG_COMPENSATION=True)


def _fetch_notebook(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, f"s4_main_{S4_REV[:8]}.ipynb")
    if not os.path.exists(p):
        with urllib.request.urlopen(S4_NB_URL, timeout=120) as r:
            open(p, "wb").write(r.read())
    return json.load(open(p))


class _NoPlotter:
    """pyvista.Plotter 대역 — 렌더링 없이 호출만 받아넘긴다 (헤드리스)."""
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def _load_s4_functions(nb):
    """셀 2·3·4·7 의 **def/import 만** 실행한 전역 dict. 최상위 실행문은 버린다.

    셀 2 의 `cell_neighbour_graph`, `cell_neighbour_dict`, `bottom_cells`, `up_vector`
    는 함수들이 전역으로 참조하므로 호출 쪽(`run_model`)이 같은 이름으로 채운다.
    """
    import ast
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    g = {"__name__": "s4"}
    for idx in (2, 3, 4, 7):
        src = "".join(code_cells[idx]["source"])
        src = re.sub(r"^\s*[!%].*$", "", src, flags=re.M)          # !pip, %magic
        tree = ast.parse(src)
        keep = [n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom))
                and not (isinstance(n, ast.Import)
                         and any(a.name == "open3d" for a in n.names))]
        # open3d 는 STL 읽기에만 쓰여 함수에는 안 나온다 — 렌더링 라이브러리(libEGL)
        # 없는 환경에서 import 가 죽으므로 뺀다. 메시는 우리가 trimesh 로 준다.
        mod = ast.Module(body=keep, type_ignores=[])
        exec(compile(mod, f"<s4 cell {idx}>", "exec"), g)   # noqa: S102 — 고정 커밋의 코드
    # 전역 상수 (셀 2·7 최상위에서 정의됨)
    g["up_vector"] = np.array([0, 0, 1])
    g["N"] = np.eye(4) - 1 / 4 * np.ones((4, 4))
    g["save_gif_i"] = 0
    g["model_name"] = "model"
    g["pv"].Plotter = _NoPlotter
    return g


def _build_tet(g, mesh):
    import networkx as nx
    import tetgen
    tg = tetgen.TetGen(np.asarray(mesh.vertices, dtype=float),
                       np.asarray(mesh.faces, dtype=np.int64))
    tg.tetrahedralize()
    tet = tg.grid
    x0, x1, y0, y1, z0, z1 = tet.bounds
    tet.points -= np.array([(x0 + x1) / 2, (y0 + y1) / 2, z0])

    # 셀 2 최상위: 이웃 사전·그래프 (함수들이 전역으로 쓴다)
    nbr = {t: {c: [] for c in range(tet.number_of_cells)} for t in ("point", "edge", "face")}
    for t in ("point", "edge", "face"):
        pairs = []
        for c in range(tet.number_of_cells):
            for n in tet.cell_neighbors(c, f"{t}s"):
                if n > c:
                    pairs.append((c, n))
        for a, b in np.array(pairs):
            nbr[t][a].append(b)
            nbr[t][b].append(a)
        tet.field_data[f"cell_{t}_neighbours"] = np.array(pairs)
    graph = nx.Graph()
    cc = tet.cell_centers().points
    for a, b in tet.field_data["cell_point_neighbours"]:
        graph.add_weighted_edges_from([(a, b, float(np.linalg.norm(cc[a] - cc[b])))])
    g["cell_neighbour_dict"] = nbr
    g["cell_neighbour_graph"] = graph
    tet, bottom_mask, bottom_cells = g["calculate_tet_attributes"](tet)
    g["bottom_cells_mask"] = bottom_mask
    g["bottom_cells"] = bottom_cells
    return tet


def _deformation_gradients(tet, new_pts):
    cells = tet.cells.reshape(-1, 5)[:, 1:]
    old = tet.points[cells]                      # (C,4,3)
    new = new_pts[cells]
    D0 = (old[:, 1:] - old[:, :1]).transpose(0, 2, 1)   # (C,3,3) 열 = 모서리
    D1 = (new[:, 1:] - new[:, :1]).transpose(0, 2, 1)
    return D1 @ np.linalg.inv(D0)               # F : old → new


def _surface_build_dirs(tet, F):
    """경계 삼각형과 그 소유 셀 → (경계 trimesh, 면별 b̂ = normalize(Fᵀ ẑ))."""
    import trimesh

    from conical.s3io import boundary_mesh
    cells = tet.cells.reshape(-1, 5)[:, 1:]
    bm = boundary_mesh(np.asarray(tet.points, dtype=float), cells)
    # 면 → 소유 셀: 정렬한 정점 3개 키로 찾는다
    face_idx = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
    allf = np.sort(cells[:, face_idx].reshape(-1, 3), axis=1)
    owner = np.repeat(np.arange(len(cells)), 4)
    key = {tuple(k): o for k, o in zip(map(tuple, allf), owner, strict=True)}
    own = np.array([key[tuple(sorted(f))] for f in bm.faces])
    b = np.einsum("cji,j->ci", F[own], np.array([0.0, 0.0, 1.0]))   # Fᵀ ẑ
    b /= np.linalg.norm(b, axis=1, keepdims=True)
    return trimesh.Trimesh(vertices=bm.vertices, faces=bm.faces, process=False), b


def run_model(g, spec, mesh, params):
    from conical.s3io import bed_contact_mask, support_fraction_dirs
    t0 = time.time()
    tet = _build_tet(g, mesh)
    und = tet.copy()
    rot = g["optimize_rotations"](
        und, params["NEIGHBOUR_LOSS_WEIGHT"], params["MAX_OVERHANG"],
        params["ROTATION_MULTIPLIER"], params["ROT_ITERATIONS"], False,
        params["STEEP_OVERHANG_COMPENSATION"], params["INITIAL_ROTATION_FIELD_SMOOTHING"],
        params["SET_INITIAL_ROTATION_TO_ZERO"], params["MAX_POS_ROTATION"],
        params["MAX_NEG_ROTATION"])
    new_pts = g["calculate_deformation"](und, rot, params["DEF_ITERATIONS"], False)
    F = _deformation_gradients(und, new_pts)
    surf, b = _surface_build_dirs(und, F)
    bed = bed_contact_mask(surf)
    s = support_fraction_dirs(surf, b, exclude=bed)
    planar = support_fraction_dirs(surf, np.tile([0.0, 0.0, 1.0], (len(surf.faces), 1)),
                                   exclude=bed)
    # 회전장 자체로도 잰다 (변형 전 목표): b = Rᵀ ẑ. 변형이 목표를 얼마나 실현했나
    Rm = g["calculate_rotation_matrices"](und, rot)
    cells = und.cells.reshape(-1, 5)[:, 1:]
    _, b_rot = _surface_build_dirs(und, Rm)     # R 을 F 자리에 넣으면 Rᵀẑ
    s_rot = support_fraction_dirs(surf, b_rot, exclude=bed)
    tilt = np.degrees(np.arccos(np.clip(b[:, 2], -1, 1)))
    return {
        "support": float(s), "support_rotation_target": float(s_rot),
        "planar_on_tet_surface": float(planar), "valid": True,
        "n_tets": int(len(cells)), "n_surface_faces": int(len(surf.faces)),
        "mean_tilt_deg": float((tilt * surf.area_faces).sum() / surf.area_faces.sum()),
        "max_tilt_deg": float(tilt.max()),
        "rotation_field_deg": {"mean_abs": float(np.degrees(np.abs(rot)).mean()),
                               "max_abs": float(np.degrees(np.abs(rot)).max())},
        "params": {k: (float(v) if isinstance(v, (float, np.floating)) else v)
                   for k, v in params.items()},
        "s4_rev": S4_REV, "t_sec": time.time() - t0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("-o", "--out", default="s4_results.json")
    ap.add_argument("--cache", default=os.path.join(os.path.dirname(__file__), "..", ".s4cache"))
    ap.add_argument("--max-overhang", type=float, default=S4_PARAMS["MAX_OVERHANG"])
    a = ap.parse_args()

    from compare_dof_ladder import build_model
    params = dict(S4_PARAMS, MAX_OVERHANG=a.max_overhang)
    g = _load_s4_functions(_fetch_notebook(a.cache))
    out = json.load(open(a.out)) if os.path.exists(a.out) else {}
    for spec in a.models:
        mesh = build_model(spec, None)
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf                         # least_squares verbose=2 를 삼킨다
        try:
            row = run_model(g, spec, mesh, params)
        finally:
            sys.stdout = old
        out[spec] = row
        json.dump(out, open(a.out, "w"), indent=1)
        print(f"[{spec}] S4 support {row['support']:.2f}% (회전 목표만 {row['support_rotation_target']:.2f}%, "
              f"평면 {row['planar_on_tet_surface']:.2f}%)  tets={row['n_tets']}  "
              f"tilt mean {row['mean_tilt_deg']:.1f}° max {row['max_tilt_deg']:.1f}°  {row['t_sec']:.0f}s",
              flush=True)
    print(f"→ {a.out}")


if __name__ == "__main__":
    main()
