"""
tools/s4_compare.py — S4 곡면 슬라이서(헤드리스) vs 원뿔족 사다리, 같은 지표로.

    python3 tools/s4_compare.py --s4 /path/to/S4_Slicer \
        --models sphere funnel torus mushroom lamp --res R1 R2 --params P1 P2 \
        --out s4_comparison_results.json

S4(github.com/jyjblrd/S4_Slicer, GPL-3.0)의 코드는 이 저장소에 없다. `--s4` 로 받은
클론의 `main.ipynb` 에서 셀을 **내용으로 찾아** 꺼내 실행한다(셀 번호에 기대지 않음).
사전 등록·판정 기준은 docs/s4_comparison.md §1.

평가(G-code 없이): 사면체마다 F = D_y·D_x⁻¹, 층 함수 z′ 의 기울기 = F 의 3행,
빌드 방향 d = ∇z′/|∇z′|. 표면 면 n 에 대해 g = n·d < κ = −sin45° 이면 서포트.
원뿔족(평면·균일·밴드·천장)은 **같은 사면체 표면 메시**에서 conical 의 함수로 잰다.

의존성: tetgen, pyvista, networkx (open3d·pygcode 불필요 — 쓰지 않는다).
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from compare_ceiling import demo_models, uniform_best  # noqa: E402
from conical import analytic  # noqa: E402
from conical.bandplan import evaluate_band_plan, plan_bands  # noqa: E402
from conical.clusters import adaptive_ceiling  # noqa: E402
from conical.config import THRESHOLD_DEG  # noqa: E402
from conical.meshio import center_on_axis  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# 해상도 = 표면 메시 세분 단계 (docs §1.2 정정 — maxvolume 'a' 스위치는 부피를 잃어서 뺐다)
RES = {"R1": 0, "R2": 1}                # 기준 표면에 trimesh.subdivide() 를 몇 번 더 하나
TETGEN_SWITCHES = "pq1.5/10Q"
P_BASE = dict(NEIGHBOUR_LOSS_WEIGHT=20, MAX_OVERHANG=30, ROTATION_MULTIPLIER=2,
              SET_INITIAL_ROTATION_TO_ZERO=False, INITIAL_ROTATION_FIELD_SMOOTHING=30,
              ITERATIONS=100, STEEP_OVERHANG_COMPENSATION=True)
PARAMS = {"P1": dict(P_BASE),
          "P2": dict(P_BASE, NEIGHBOUR_LOSS_WEIGHT=10),
          "P3": dict(P_BASE, MAX_OVERHANG=45)}
DEFORM_ITERATIONS = 1000
BED_NZ = -0.99
BED_DZ = 0.3


# ─────────────────────────────────────────────────────────────
# 1) 노트북 셀 꺼내기·패치
# ─────────────────────────────────────────────────────────────
def _cells(nb_path):
    nb = json.load(open(nb_path, encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def _find(cells, marker):
    hits = [c for c in cells if marker in c]
    if len(hits) != 1:
        raise RuntimeError(f"S4 노트북에서 '{marker}' 셀을 하나로 못 찾음 ({len(hits)}개)")
    return hits[0]


def _replace_once(src, old, new):
    if src.count(old) != 1:
        raise RuntimeError(f"S4 패치 실패: {old!r} 가 {src.count(old)}번 나옴")
    return src.replace(old, new)


def _cut_before(src, marker):
    i = src.find(marker)
    if i < 0:
        raise RuntimeError(f"S4 패치 실패: '{marker}' 없음")
    return src[:i]


def load_s4_sources(s4_dir):
    cells = _cells(os.path.join(s4_dir, "main.ipynb"))
    c2 = _find(cells, "def calculate_tet_attributes")
    c3 = _find(cells, "def calculate_path_length_to_base_gradient")
    c4 = _find(cells, "def optimize_rotations")
    c7 = _find(cells, "def calculate_deformation")

    drop = ("import open3d", "pv.set_jupyter_backend", "pv.global_theme.notebook",
            "pv.start_xvfb")
    c2 = "\n".join(ln for ln in c2.splitlines() if not ln.strip().startswith(drop))
    c2 = _replace_once(c2, "mesh = o3d.io.read_triangle_mesh(f'input_models/{model_name}.stl')",
                       "mesh = _S4_INPUT_MESH")
    c2 = _replace_once(c2, "np.asarray(mesh.triangles)", "np.asarray(mesh.faces)")
    c2 = _replace_once(c2, "input_tet.tetrahedralize()",
                       "_t0 = time.time(); input_tet.tetrahedralize(**_S4_TET_OPTS); "
                       "_S4_TIMES['tetgen'] = time.time() - _t0")
    c4 = _cut_before(c4, "NEIGHBOUR_LOSS_WEIGHT = 20")
    # numpy 2 는 2차원 벡터 np.cross 를 없앴다. 옛 동작(z=0 으로 채움)과 같은 식으로 바꾼다
    c4 = _replace_once(
        c4, 'np.cross( np.array([0, 0, 1]), tet.cell_data["cell_center"][:, :2])',
        'np.cross(np.array([0, 0, 1]), np.hstack((tet.cell_data["cell_center"][:, :2], '
        'np.zeros((tet.number_of_cells, 1)))))')
    c7 = _cut_before(c7, "ITERATIONS = 1000")
    return c2, c3, c4, c7


class _NullPlotter:
    """pv.Plotter 대역 — 아무것도 그리지 않는다."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def run_s4(srcs, mesh, params):
    """S4 한 번 실행. 반환: (undeformed_tet, new_vertices, info)."""
    import pyvista as pv
    from scipy.optimize import least_squares as _ls

    pv.Plotter = _NullPlotter
    c2, c3, c4, c7 = srcs
    results = []

    def ls_wrap(*a, **k):
        k["verbose"] = 0
        r = _ls(*a, **k)
        results.append({"status": int(r.status), "cost": float(r.cost),
                        "nfev": int(r.nfev), "message": str(r.message)})
        return r

    times = {}
    ns = {"__name__": "s4", "_S4_INPUT_MESH": mesh, "_S4_TIMES": times,
          "_S4_TET_OPTS": dict(switches=TETGEN_SWITCHES),
          "model_name": "s4cmp"}
    t0 = time.perf_counter()
    exec(compile(c2, "s4_cell2", "exec"), ns)
    times["tet_and_attributes"] = time.perf_counter() - t0
    ns["least_squares"] = ls_wrap
    exec(compile(c3, "s4_cell3", "exec"), ns)
    exec(compile(c4, "s4_cell4", "exec"), ns)
    exec(compile(c7, "s4_cell7", "exec"), ns)
    ns["least_squares"] = ls_wrap

    tet = ns["undeformed_tet"]
    t0 = time.perf_counter()
    rot = ns["optimize_rotations"](
        tet, params["NEIGHBOUR_LOSS_WEIGHT"], params["MAX_OVERHANG"],
        params["ROTATION_MULTIPLIER"], params["ITERATIONS"], False,
        params["STEEP_OVERHANG_COMPENSATION"], params["INITIAL_ROTATION_FIELD_SMOOTHING"],
        params["SET_INITIAL_ROTATION_TO_ZERO"], np.deg2rad(3600), np.deg2rad(-3600))
    times["rotation_field"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    new_v = ns["calculate_deformation"](tet, rot, DEFORM_ITERATIONS, False)
    times["deformation"] = time.perf_counter() - t0
    info = {"times_s": times, "opt_rotation": results[0], "opt_deformation": results[1],
            "n_tets": int(tet.number_of_cells), "n_points": int(tet.number_of_points),
            "rotation_field_deg": {"min": float(np.degrees(np.nanmin(rot))),
                                   "max": float(np.degrees(np.nanmax(rot)))}}
    return tet, np.asarray(new_v), info


# ─────────────────────────────────────────────────────────────
# 2) 평가 — S4 와 원뿔족을 같은 표면에서
# ─────────────────────────────────────────────────────────────
def boundary_surface(points, cells):
    """사면체 경계 삼각형(바깥 법선 방향으로 정렬)과 각 면의 소속 사면체."""
    local = np.array([[1, 2, 3, 0], [0, 3, 2, 1], [0, 1, 3, 2], [0, 2, 1, 3]])
    tri = cells[:, local[:, :3]].reshape(-1, 3)
    opp = cells[:, local[:, 3]].reshape(-1)
    owner = np.repeat(np.arange(len(cells)), 4)
    key = np.sort(tri, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    once = cnt[inv.ravel()] == 1
    tri, opp, owner = tri[once], opp[once], owner[once]
    p = points
    n = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])
    flip = np.einsum("ij,ij->i", n, p[opp] - p[tri[:, 0]]) > 0     # 법선이 안쪽을 보면 뒤집기
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri, owner


def deformation_gradients(X, Y, cells):
    Dx = np.stack([X[cells[:, i]] - X[cells[:, 0]] for i in (1, 2, 3)], axis=2)
    Dy = np.stack([Y[cells[:, i]] - Y[cells[:, 0]] for i in (1, 2, 3)], axis=2)
    return Dy @ np.linalg.inv(Dx), Dx


def frac_from_dirs(mesh, d, mask=None, threshold_deg=THRESHOLD_DEG):
    """g = n·d < κ 의 면적 비율(%). mask 가 있으면 그 면만 분모·분자에 넣는다."""
    g = np.einsum("ij,ij->i", mesh.face_normals, d)
    need = g < -np.sin(np.radians(threshold_deg))
    a = mesh.area_faces if mask is None else mesh.area_faces * mask
    return float(a[need].sum() / a.sum() * 100.0)


def cone_dirs(mesh, angle_deg, direction):
    c = mesh.vertices[mesh.faces].mean(axis=1)
    r = np.hypot(c[:, 0], c[:, 1])
    safe = np.where(r > 1e-9, r, 1.0)
    rhat = np.stack([c[:, 0] / safe, c[:, 1] / safe, np.zeros(len(c))], axis=1)
    rhat[r <= 1e-9] = 0.0
    s = 1.0 if direction == "outward" else -1.0
    a = np.radians(angle_deg)
    return s * np.sin(a) * rhat + np.cos(a) * np.array([0.0, 0.0, 1.0])


def bed_mask(mesh):
    c = mesh.vertices[mesh.faces].mean(axis=1)
    bed = (mesh.face_normals[:, 2] < BED_NZ) & (c[:, 2] < mesh.bounds[0][2] + BED_DZ)
    return (~bed).astype(float)


def masked_mesh(mesh, keep):
    m = mesh.submesh([np.where(keep > 0)[0]], append=True)
    return m


def cone_ladder(mesh):
    """평면·균일·밴드·천장 (compare_ceiling 과 같은 함수) + 시간."""
    out = {}
    out["planar"] = analytic.support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    t0 = time.perf_counter()
    s, ang, dirn = uniform_best(mesh)
    out["uniform"], out["uniform_angle"], out["uniform_dir"] = s, ang, dirn
    out["t_uniform_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    bands = plan_bands(mesh)
    out["banded"] = evaluate_band_plan(mesh, bands) if bands else out["planar"]
    out["n_bands"] = len(bands)
    out["band_profile"] = [f"{b['angle']:.0f}{b['direction'][:3]}" for b in bands]
    out["t_banded_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    out["ceiling"] = adaptive_ceiling(mesh)[0]
    out["t_ceiling_s"] = time.perf_counter() - t0
    return out


def curvature_stats(X, cells, F, Dx, Y):
    """층 경선 곡률 κ_m = ∇θ·τ 와 층 내 θ 산포 (docs §1.4)."""
    grad = F[:, 2, :]
    d = grad / np.linalg.norm(grad, axis=1)[:, None]
    cen = X[cells].mean(axis=1)
    vol = np.abs(np.linalg.det(Dx)) / 6.0
    r = np.hypot(cen[:, 0], cen[:, 1])
    rmax = float(r.max())
    ok = r > 0.05 * rmax
    rhat = np.zeros_like(cen)
    rhat[ok, 0] = cen[ok, 0] / r[ok]
    rhat[ok, 1] = cen[ok, 1] / r[ok]
    that = np.stack([-rhat[:, 1], rhat[:, 0], np.zeros(len(cen))], axis=1)
    dr = np.einsum("ij,ij->i", d, rhat)
    dt = np.einsum("ij,ij->i", d, that)
    theta = np.arctan2(dr, d[:, 2])

    # 정점 θ (부피가중 평균, 축 근처 사면체 제외) → P1 기울기
    nv = len(X)
    num = np.zeros(nv)
    den = np.zeros(nv)
    w = vol * ok
    for i in range(4):
        np.add.at(num, cells[:, i], w * theta)
        np.add.at(den, cells[:, i], w)
    th_v = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    dth = np.stack([th_v[cells[:, i]] - th_v[cells[:, 0]] for i in (1, 2, 3)], axis=1)
    gth = np.einsum("nij,nj->ni", np.linalg.inv(np.transpose(Dx, (0, 2, 1))), dth)
    # 경선 평면 안에서 d 에 수직인 층 접선
    tau = d[:, 2:3] * rhat - dr[:, None] * np.array([0.0, 0.0, 1.0])
    tau /= np.maximum(np.linalg.norm(tau, axis=1), 1e-12)[:, None]
    kap = np.abs(np.einsum("ij,ij->i", gth, tau))
    good = ok & np.isfinite(kap)

    def wq(v, wt, q):
        o = np.argsort(v)
        cw = np.cumsum(wt[o])
        return float(v[o][np.searchsorted(cw, q * cw[-1])])

    # 층 내 θ 산포: 변형공간 z′ 를 1 mm 층으로
    zc = Y[cells].mean(axis=1)[:, 2]
    bins = np.floor((zc - zc.min()) / 1.0).astype(int)
    sds = []
    for b in np.unique(bins[good]):
        m = good & (bins == b)
        if w[m].sum() <= 0 or m.sum() < 5:
            continue
        mu = np.average(theta[m], weights=w[m])
        sds.append(np.sqrt(np.average((theta[m] - mu) ** 2, weights=w[m])))
    return {
        "r_max": rmax,
        "kappa_m_r_median": wq(kap[good] * rmax, w[good], 0.5),
        "kappa_m_r_p90": wq(kap[good] * rmax, w[good], 0.9),
        "theta_layer_sd_deg": float(np.degrees(np.mean(sds))) if sds else None,
        "theta_deg_p05": float(np.degrees(wq(theta[good], w[good], 0.05))),
        "theta_deg_p95": float(np.degrees(wq(theta[good], w[good], 0.95))),
        "tangential_mean": float(np.average(np.abs(dt[good]), weights=w[good])),
    }


def evaluate(tet, new_v):
    cells = tet.cells.reshape(-1, 5)[:, 1:]
    X = np.asarray(tet.points, dtype=float)
    F, Dx = deformation_gradients(X, new_v, cells)
    det = np.linalg.det(F)
    tri, owner = boundary_surface(X, cells)
    surf = trimesh.Trimesh(X, tri, process=False)
    grad = F[owner, 2, :]
    d = grad / np.linalg.norm(grad, axis=1)[:, None]
    keep = bed_mask(surf)

    res = {"n_inverted": int((det <= 0).sum()), "det_min": float(det.min()),
           "tet_volume": float(surf.volume),
           "n_surface_faces": int(len(tri)),
           "s4": frac_from_dirs(surf, d), "s4_nobed": frac_from_dirs(surf, d, keep)}
    # 검산: g=n·d 에 원뿔 d 를 넣으면 analytic 과 같아야 한다
    chk = []
    for ang, dirn in ((0.0, "outward"), (20.0, "outward"), (30.0, "inward")):
        a = analytic.support_fraction(surf, ang, dirn, THRESHOLD_DEG)
        b = frac_from_dirs(surf, cone_dirs(surf, ang, dirn))
        chk.append(abs(a - b))
    res["consistency_max_abs_diff"] = float(max(chk))
    res["cone"] = cone_ladder(surf)
    sub = masked_mesh(surf, keep)
    res["cone_nobed"] = {k: v for k, v in cone_ladder(sub).items() if not k.startswith("t_")}
    res["curvature"] = curvature_stats(X, cells, F, Dx, new_v)
    return res


# ─────────────────────────────────────────────────────────────
# 3) 모델
# ─────────────────────────────────────────────────────────────
def get_model(name, res="R1"):
    """S4 비교용 기준 표면 (R1) 과 그 세분 (R2). 기준 표면은 docs §1.2 정정 참고."""
    if name == "sphere":
        # R1 = icosphere sub3, R2 = sub4 (= compare_ceiling 데모 구)
        m = trimesh.creation.icosphere(subdivisions=3 + RES[res], radius=10)
        return center_on_axis(m)
    m = _base_model(name)
    if name == "funnel":
        m = m.subdivide()        # 64면 원본은 tetgen 'q' 에서 부피를 잃는다 (1011.6 vs 1019.7)
    for _ in range(RES[res]):
        m = m.subdivide()
    return center_on_axis(m)


def _base_model(name):
    if name == "lamp":
        m = trimesh.load(os.path.join(ROOT, "examples", "lamp.stl"), force="mesh")
    elif name == "mushroom":
        # compare_ceiling 의 mushroom 은 기둥·갓 두 메시를 겹쳐 붙인 것(자기교차) →
        # tetgen 이 거부한다. 같은 치수의 합집합을 회전체로 만든다
        # (기둥 r2 h14 + 갓 r8 h3, z 14~17). 갓 아래 원판 중 기둥이 덮는 4π 가 빠져
        # 평면 서포트가 28.3% → 27.6% 로 조금 다르다.
        prof = np.array([[0, 0], [2, 0], [2, 14], [8, 14], [8, 17], [0, 17]], float)
        m = trimesh.creation.revolve(prof, sections=32)
    else:
        m = demo_models()[name]
    return m.copy()


def selftest(models, res_list):
    """S4 없이 지표 검산: 같은 tetgen 메시에 알려진 층 함수를 넣는다.

    · 원뿔 사상 z′ = z + c·r·tanθ → F-경로 서포트%가 analytic 과 같아야 한다.
    · 그때의 곡률·층 내 산포 = 이 측정의 **바닥(noise floor)**. 원뿔 층의 참값은 0 이고,
      0 이 아닌 만큼은 축 근처 사상의 비선형성(P1 근사)·정점 평균 탓이다.
    """
    import tetgen
    out = []
    for name in models:
        for res in res_list:
            m = get_model(name, res)
            t = tetgen.TetGen(np.asarray(m.vertices), np.asarray(m.faces))
            t.tetrahedralize(switches=TETGEN_SWITCHES)
            g = t.grid
            X = np.asarray(g.points, float)
            cells = g.cells.reshape(-1, 5)[:, 1:]
            tri, owner = boundary_surface(X, cells)
            surf = trimesh.Trimesh(X, tri, process=False)
            r = np.hypot(X[:, 0], X[:, 1])
            row = {"model": name, "res": res, "n_tets": int(len(cells)),
                   "volume_tet": float(surf.volume), "volume_in": float(m.volume)}
            for ang, dirn in ((0.0, "outward"), (20.0, "outward"), (30.0, "inward")):
                c = 1.0 if dirn == "outward" else -1.0
                Y = X.copy()
                Y[:, 2] = X[:, 2] + c * r * np.tan(np.radians(ang))
                F, Dx = deformation_gradients(X, Y, cells)
                grad = F[owner, 2, :]
                d = grad / np.linalg.norm(grad, axis=1)[:, None]
                key = f"{ang:.0f}{dirn[:3]}"
                row[key] = {"analytic": analytic.support_fraction(surf, ang, dirn),
                            "f_route": frac_from_dirs(surf, d)}
                if ang == 20.0:
                    row["curvature_floor"] = curvature_stats(X, cells, F, Dx, Y)
            out.append(row)
            cf = row["curvature_floor"]
            print(f"{name:9s} {res} tets={row['n_tets']:6d} vol {row['volume_tet']:.1f}/"
                  f"{row['volume_in']:.1f} | " + " ".join(
                      f"{k}: {row[k]['analytic']:.2f}/{row[k]['f_route']:.2f}"
                      for k in ("0out", "20out", "30inw"))
                  + f" | floor κr med {cf['kappa_m_r_median']:.3f} p90 {cf['kappa_m_r_p90']:.3f}"
                  f" sd {cf['theta_layer_sd_deg']:.2f}°", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--s4", help="S4_Slicer 클론 경로 (main.ipynb 가 있는 곳)")
    ap.add_argument("--selftest", action="store_true",
                    help="S4 없이 지표만 검산 (원뿔 사상) → --out 에 저장")
    ap.add_argument("--models", nargs="+", default=["sphere", "funnel", "torus", "mushroom"])
    ap.add_argument("--res", nargs="+", default=["R1", "R2"])
    ap.add_argument("--params", nargs="+", default=["P1", "P2"])
    ap.add_argument("--out", default="s4_comparison_results.json")
    ap.add_argument("--save-fields", default=None,
                    help="이 폴더에 실행별 npz(원본 점·사면체·변형 점) 저장 — 그림용")
    a = ap.parse_args()
    if a.selftest:
        out = selftest(a.models, a.res)
        json.dump(out, open(a.out, "w"), indent=1, ensure_ascii=False)
        return
    if not a.s4:
        ap.error("--s4 가 필요하다 (또는 --selftest)")

    srcs = load_s4_sources(a.s4)
    rows = json.load(open(a.out)) if os.path.exists(a.out) else []
    done = {(r["model"], r["res"], r["params"]) for r in rows}
    for name in a.models:
        for res in a.res:
            mesh = get_model(name, res)
            orig = cone_ladder(mesh)
            for pk in a.params:
                if (name, res, pk) in done:
                    continue
                row = {"model": name, "res": res, "params": pk,
                       "param_values": PARAMS[pk], "n_input_faces": int(len(mesh.faces)),
                       "input_volume": float(mesh.volume),
                       "cone_on_input_mesh": {k: v for k, v in orig.items()
                                              if not k.startswith("t_")}}
                t0 = time.perf_counter()
                try:
                    tet, new_v, info = run_s4(srcs, mesh.copy(), PARAMS[pk])
                    row.update(info)
                    row.update(evaluate(tet, new_v))
                    if a.save_fields:
                        os.makedirs(a.save_fields, exist_ok=True)
                        np.savez_compressed(
                            os.path.join(a.save_fields, f"{name}_{res}_{pk}.npz"),
                            X=np.asarray(tet.points), cells=tet.cells.reshape(-1, 5)[:, 1:],
                            Y=new_v)
                    row["ok"] = True
                except Exception as e:  # 실패한 설정도 결과로 남긴다
                    row["ok"] = False
                    row["error"] = f"{type(e).__name__}: {e}"
                row["wall_s"] = time.perf_counter() - t0
                rows.append(row)
                json.dump(rows, open(a.out, "w"), indent=1, ensure_ascii=False)
                if row["ok"]:
                    c = row["cone"]
                    print(f"{name:9s} {res} {pk} tets={row['n_tets']:6d} "
                          f"plan {c['planar']:5.1f} uni {c['uniform']:5.1f} "
                          f"band {c['banded']:5.1f} ceil {c['ceiling']:5.1f} | "
                          f"S4 {row['s4']:5.1f} (nobed {row['s4_nobed']:5.1f}) "
                          f"inv={row['n_inverted']} st={row['opt_rotation']['status']}/"
                          f"{row['opt_deformation']['status']} "
                          f"t={row['wall_s']:.0f}s", flush=True)
                else:
                    print(f"{name:9s} {res} {pk} FAILED: {row['error']}", flush=True)


if __name__ == "__main__":
    main()
