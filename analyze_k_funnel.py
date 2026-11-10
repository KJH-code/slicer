"""analyze_k_funnel.py — funnel 이 베드 상한 아래에서 0° 를 고르는 원인 (사전 등록 `docs/test_k_sweep.md` §1.4).

가설 H-f: 해석식 S(θ) 는 면이 임계각 θ* 를 넘을 때만 변하는 계단함수(초안 식 (4))이고,
funnel 의 오버행 면은 θ* 가 모두 상한 22.79° 보다 크다 → [0, 상한] 에서 ΔS = 0 → J = −k|θ| → 0°.

확인 1: S(θ) 를 0~44° 0.1° 간격으로 — [0, 22.79] 에서 상수인가.
확인 2: 오버행 면의 θ* 를 식 (4) 로 **따로** 계산 — 최소가 22.79° 보다 큰가, S 가 처음 변하는 각과 같은가.
확인 3: 툴패스 미지지 mm (T1 값) 가 0~22° 에서 0.5mm 넘게 주는가.

S³ 모델 ring · topopt_new4 · armadillo4 (선택): `.tet` 가 있는 디렉토리를 주면 같은 S(θ) 곡선으로
'계단 문제' 와 'k 스케일 문제' 를 가른다. `.tet` 는 S³-Slicer 저장소
(github.com/zhangty019/S3_DeformFDM @ a77ef04, `DataSet/TET_MODEL/`) 의 외부 데이터라 커밋하지 않는다.
읽기 규약은 `claude/modest-wozniak-rftjyb` 의 `conical/s3io.py` 와 같다(Y-위 → Z-위, 경계면만, 바닥 z=0,
`center_on_axis`). 툴패스는 재지 않는다.

    python3 analyze_k_funnel.py [--s3-dir DIR]
"""

import argparse
import json
import os
import sys

import numpy as np
import trimesh

import conical.varangle as varangle
from analyze_gap_sample import BED_CAP
from analyze_k_sweep import KS, signed_grid
from analyze_t1_conventional import all_specs
from conical.analytic import radial_normal, support_fraction
from conical.config import MAX_SPACING_FACTOR, THRESHOLD_DEG
from conical.meshio import RadiusProfile, center_on_axis

FINE = np.round(np.arange(0.0, 44.0 + 1e-9, 0.1), 1)
S3_MODELS = ("ring", "topopt_new4", "armadillo4")


# ── S³ .tet 읽기 (s3io.py 와 같은 규약, 필요한 만큼만) ──────────────────────
def load_tet_surface(path):
    with open(path) as f:
        n_v = int(f.readline().split()[0])
        n_t = int(f.readline().split()[0])
        verts = np.loadtxt(f, max_rows=n_v, dtype=float)
        tets = np.loadtxt(f, max_rows=n_t, dtype=int)[:, 1:]
    face_idx = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
    faces = tets[:, face_idx].reshape(-1, 3)
    opposite = tets[:, [3, 2, 1, 0]].reshape(-1)
    key = np.sort(faces, axis=1)
    _, first, counts = np.unique(key, axis=0, return_index=True, return_counts=True)
    bf = faces[first[counts == 1]].copy()
    bo = opposite[first[counts == 1]]
    a, b, c = verts[bf[:, 0]], verts[bf[:, 1]], verts[bf[:, 2]]
    n = np.cross(b - a, c - a)
    flip = (n * (verts[bo] - a)).sum(axis=1) > 0           # 법선이 안쪽(남은 정점 쪽)을 보면 뒤집기
    bf[flip] = bf[flip][:, [0, 2, 1]]
    used = np.unique(bf)
    remap = -np.ones(len(verts), dtype=int)
    remap[used] = np.arange(len(used))
    v = verts[used]
    v = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])        # Y-위 → Z-위 (det +1)
    m = trimesh.Trimesh(vertices=v, faces=remap[bf], process=False)
    m.apply_translation([0.0, 0.0, -m.bounds[0][2]])
    return center_on_axis(m)


# ── 식 (4) 를 따로 옮긴 면별 임계각 ─────────────────────────────────────
def theta_star_outward(mesh, threshold_deg=THRESHOLD_DEG):
    """outward(d=+1) 에서 오버행 면이 처음 자기지지가 되는 각 θ* (°). 고칠 수 없으면 nan.

    g(θ) = n_z cosθ + n_r sinθ = R sin(θ + φ), φ = atan2(n_z, n_r). g = κ 의 근
    θ* = asin(κ/R) − φ (초안 식 (4), d=+1). |κ/R| > 1 이면 근이 없다.
    0° 에서 이미 지지되는 면은 nan 으로 둔다(오버행 면만 본다).
    """
    kappa = -np.sin(np.radians(threshold_deg))
    nz = mesh.face_normals[:, 2]
    nr = radial_normal(mesh)
    R = np.hypot(nz, nr)
    with np.errstate(invalid="ignore", divide="ignore"):
        ts = np.degrees(np.arcsin(kappa / R) - np.arctan2(nz, nr))
    ts = np.where(np.abs(kappa / np.maximum(R, 1e-12)) <= 1.0, ts, np.nan)
    over0 = nz < kappa                                       # g(0) = n_z
    # 근이 [0, 90) 밖이면 outward 로는 못 고친다
    ts = np.where(over0 & (ts >= 0) & (ts < 90), ts, np.nan)
    return ts, over0


def s_curve(mesh, thetas, direction="outward"):
    return [float(support_fraction(mesh, float(t), direction, THRESHOLD_DEG)) for t in thetas]


def funnel_part():
    names = [n for n, _ in all_specs()]
    mesh = all_specs()[names.index("funnel")][1]()
    S = np.array(s_curve(mesh, FINE))
    ts, over0 = theta_star_outward(mesh)
    areas = mesh.area_faces
    tot = areas.sum()
    fixable = ~np.isnan(ts)
    first_change = float(FINE[np.argmax(np.abs(S - S[0]) > 1e-9)]) \
        if np.any(np.abs(S - S[0]) > 1e-9) else None
    below = FINE <= BED_CAP + 1e-9
    # 독립 계산으로 다시 만든 S(θ): 0° 오버행 면적 − θ* ≤ θ 인 면적
    S_ind = np.array([(areas[over0].sum() - areas[fixable & (ts <= t + 1e-12)].sum()) / tot * 100
                      for t in FINE])
    with open("t1_conventional_results.json") as fh:
        t1 = json.load(fh)
    mm = {}
    for r in t1["rows"]:
        if r["model"] == "funnel":
            u = dict(r["uniform"])
            u.update(r.get("uniform_neg_sensitivity") or {})
            mm[f"{r['layer_height']:g}"] = {k: v["mm"] for k, v in
                                            sorted(u.items(), key=lambda kv: float(kv[0]))}
    k02 = 0.2
    J = (S[0] - S) - k02 * FINE
    check1 = bool(np.all(np.abs(S[below] - S[0]) <= 1e-9))
    check2 = bool(np.nanmin(ts) > BED_CAP and first_change is not None and
                  abs(first_change - np.nanmin(ts)) <= 0.1 + 1e-9)
    check3 = {lh: float(v["0"] - v["22"]) for lh, v in mm.items()}
    out = {
        "n_faces": int(len(mesh.faces)), "height_mm": float(mesh.extents[2]),
        "S_fine": {"theta": FINE.tolist(), "S": S.tolist(), "S_independent": S_ind.tolist(),
                   "J_k0.2": J.tolist()},
        "max_abs_S_vs_independent": float(np.max(np.abs(S - S_ind))),
        "S0": float(S[0]), "S_at_cap": float(S[below][-1]), "S_min": float(S.min()),
        "first_change_deg": first_change,
        "overhang_area_pct_0deg": float(areas[over0].sum() / tot * 100),
        "theta_star": {"min": float(np.nanmin(ts)), "max": float(np.nanmax(ts)),
                       "values": [float(x) for x in np.unique(np.round(ts[fixable], 3))],
                       "area_pct_by_value": {
                           f"{x:.3f}": float(areas[fixable & (np.round(ts, 3) == x)].sum()
                                             / tot * 100)
                           for x in np.unique(np.round(ts[fixable], 3))},
                       "n_unfixable_overhang": int((over0 & ~fixable).sum())},
        "toolpath_mm": mm,
        "checks": {"1_S_const_below_cap": check1,
                   "2_theta_star_above_cap_and_matches": check2,
                   "3_toolpath_drop_0_to_22_mm": check3,
                   "3_pass": all(v > 0.5 for v in check3.values())},
    }
    # 사후 관찰(판정 밖): 툴패스도 계단인가 — 0° 의 10% 아래로 처음 떨어지는 양의 각, 그 계단이
    # 뜻하는 '검사기 A 의 실효 임계각' = φ0 − θ_step (φ0 = θ* + 45° = 벽의 평면 기준 오버행각)
    phi0 = float(np.nanmin(ts)) + THRESHOLD_DEG
    steps = {}
    for lh, v in mm.items():
        pos = sorted((float(a), x) for a, x in v.items() if float(a) >= 0)
        prev = None
        for a, x in pos:
            if x < 0.1 * v["0"]:
                steps[lh] = {"theta_before": prev, "theta_after": a,
                             "implied_threshold_deg": [phi0 - a, phi0 - prev]}
                break
            prev = a
    out["toolpath_step_posthoc"] = {"wall_overhang_deg_planar": phi0, "by_layer_height": steps}
    out["verdict"] = ("H-f 성립 — 이진 판정 모형의 한계" if check1 and check2 and out["checks"]["3_pass"]
                      else "H-f 불성립 — 문서 참조")
    return out


def s3_part(s3_dir):
    res = {}
    grid = signed_grid()
    for name in S3_MODELS:
        path = os.path.join(s3_dir, f"{name}.tet")
        if not os.path.exists(path):
            res[name] = {"available": False}
            continue
        mesh = load_tet_surface(path)
        S = {f"{t:g}": float(support_fraction(mesh, abs(t), "outward" if t >= 0 else "inward",
                                              THRESHOLD_DEG)) for t in grid}
        s0 = S["0"]
        dS = {t: s0 - S[f"{t:g}"] for t in grid}
        pos = [t for t in grid if t != 0]
        ratio = {t: dS[t] / abs(t) for t in pos}
        t_best_ratio = max(ratio, key=ratio.get)
        t_best_dS = max(pos, key=lambda t: dS[t])
        rp = RadiusProfile(mesh)
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        sel = {}
        for k in KS:
            su = varangle.select_banded_j(mesh, k, 1, r_max, rp, MAX_SPACING_FACTOR)
            sel[f"{k:g}"] = float(su["thetas"][0]) + 0.0
        ts, over0 = theta_star_outward(mesh)
        areas = mesh.area_faces
        res[name] = {
            "available": True, "n_faces": int(len(mesh.faces)),
            "extents_mm": [float(x) for x in mesh.extents], "S": S, "S0": s0,
            "max_dS_pct": float(dS[t_best_dS]), "argmax_dS_deg": t_best_dS,
            "k_star": float(ratio[t_best_ratio]), "argmax_ratio_deg": t_best_ratio,
            "dS_at_10_20_30_44": {f"{t:g}": float(dS[t]) for t in (10.0, 20.0, 30.0, 44.0)},
            "uniform_selection_by_k": sel,
            "overhang_area_pct_0deg": float(areas[over0].sum() / areas.sum() * 100),
            "overhang_area_pct_fixable_outward_le44": float(
                areas[over0 & (ts <= 44)].sum() / areas.sum() * 100),
            "class": ("계단 문제" if dS[t_best_dS] <= 1e-9 else
                      ("k 스케일 문제" if all(dS[t] < 0.2 * abs(t) for t in pos) else
                       "해당 없음(k=0.2 에서도 0° 가 아닌 각이 이긴다)")),
        }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s3-dir", default=None)
    ap.add_argument("--json", default="k_funnel_results.json")
    args = ap.parse_args()
    f = funnel_part()
    print(f"funnel: 면 {f['n_faces']}, S0 {f['S0']:.3f}%, 상한에서 S {f['S_at_cap']:.3f}%, "
          f"처음 변하는 각 {f['first_change_deg']}°, θ* 최소 {f['theta_star']['min']:.2f}°, "
          f"독립식과 최대 차 {f['max_abs_S_vs_independent']:.2e}%p")
    print("  θ* 값/면적%:", f["theta_star"]["area_pct_by_value"])
    print("  확인:", f["checks"], "→", f["verdict"])
    print("  툴패스 계단(사후):", f["toolpath_step_posthoc"])
    out = {"funnel": f}
    if args.s3_dir:
        out["s3"] = s3_part(args.s3_dir)
        for n, r in out["s3"].items():
            if r["available"]:
                print(f"{n}: S0 {r['S0']:.2f}%, max ΔS {r['max_dS_pct']:.2f}%p @ {r['argmax_dS_deg']:g}°, "
                      f"k* {r['k_star']:.4f} @ {r['argmax_ratio_deg']:g}° → {r['class']}; "
                      f"선택 {r['uniform_selection_by_k']}")
    out["meta"] = {"bed_cap_deg": BED_CAP, "threshold_deg": THRESHOLD_DEG,
                   "s3_source": "github.com/zhangty019/S3_DeformFDM @ a77ef04 DataSet/TET_MODEL",
                   "prereg": "docs/test_k_sweep.md §1.4"}
    with open(args.json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"저장: {args.json}")


if __name__ == "__main__":
    sys.exit(main())
