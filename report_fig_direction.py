"""report_fig_direction.py — 원뿔 방향(outward/inward) 자동 결정 (보고서 그림 C).

사전 등록: `docs/test_report_figs_acefg.md` §1.2.

1. 표본 21 개(T1 과 같은 것)에서 inward(θ<0)를 고른 횟수 — 격자 균일 `select_uniform`,
   정확 균일 `select_uniform_exact`, 그리고 `t1_conventional_results.json` 의 자동 균일·밴드2·
   상한 균일·상한 밴드2 (지금 코드로 고른 값).
2. 데모 그릇 두 개(`vessel`): 안쪽 오버행(inner) / 바깥 오버행(outer). 두 방향의 S(θ) 계단과
   J(θ) = S(0) − S(θ) − kθ, 선택기의 답, 그리고 검사기 A(낙관, 진짜 오버행 mm)로 두 방향을 같은 |θ| 에서 잰 값.

    python3 report_fig_direction.py          # 약 15 분

⚠ 검사기 A 의 '진짜 오버행' 분류(`classify_unsupported`)는 아랫층 단면을 페리미터의 **바깥 고리만 채워**
복원한다(`layer_cross_sections` docstring 의 ⚠). 그래서 그릇 속 빈 공간 위로 나오는 안쪽 오버행은 늘
'단면 안' 으로 빠진다 — inner 그릇의 안쪽 오버행을 그 지표로는 볼 수 없다. **사후 진단**(판정 밖, 기본 동작
불변)으로 같은 툴패스에서 두 값을 더 적는다:
  * `raw_mm`  — 지지 판정만의 미지지 페리미터 길이 (단면 분류 전)
  * `hole_mm` — 단면을 **짝홀 규칙**(페리미터 고리들의 바깥 고리 XOR + 띠)으로 다시 만들어 구멍을 살린 뒤의
                진짜 오버행 (`hole_aware_sections`)
"""

import argparse
import json
import time

import numpy as np
import trimesh
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

import conical.varangle as varangle
from analyze_t1_conventional import all_specs
from conical.analytic import support_fraction
from conical.backtransform import backtransform
from conical.config import DEFAULT_K, MAX_ANGLE_DEG, MAX_SPACING_FACTOR, THRESHOLD_DEG
from conical.exact_angle import select_uniform_exact, support_step
from conical.meshio import RadiusProfile, center_on_axis
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile
from conical.toolpath import (
    check_support,
    classify_unsupported,
    sample_extrusions,
)
from conical.transform import transform_cone_profile

# 사전 등록 §1.2.1 의 단면 (r, z), 연직 기준 60° 어깨
SECTIONS = {
    "inner": [(0, 0), (12, 0), (12, 8), (6.8, 11), (6.8, 16), (4.8, 16), (4.8, 9.844),
              (10, 6.844), (10, 2), (0, 2)],
    "outer": [(0, 0), (8, 0), (8, 8), (13.2, 11), (13.2, 16), (11.2, 16), (11.2, 12.156),
              (6, 9.156), (6, 2), (0, 2)],
}
SWEEP = (0.0, 10.0, 14.0, 16.0, 20.0, 26.0, 30.0)
TIE_MM = 0.5


def vessel(name, sections=128):
    p = np.array(SECTIONS[name] + [SECTIONS[name][0]], dtype=float)
    return center_on_axis(trimesh.creation.revolve(p, sections=sections))


def signed(angle, direction):
    return float(angle) if direction == "outward" else -float(angle)


def sample_counts():
    t1 = json.load(open("t1_conventional_results.json"))
    rows = {r["model"]: r for r in t1["rows"] if r["layer_height"] == 0.4}
    out = []
    for name, build in all_specs():
        mesh = build()
        g = varangle.select_uniform(mesh, DEFAULT_K)
        a_g, d_g = g["profile"][0]
        ex, _ = select_uniform_exact(mesh, DEFAULT_K)
        r = rows[name]
        out.append({"model": name,
                    "grid_uniform": signed(a_g, d_g),
                    "exact_uniform": signed(ex["angle"], ex["direction"]),
                    "auto_uniform": r["auto_uniform"], "auto_band2": r["auto_band2"],
                    "cap_uniform": r["cap_uniform"], "cap_band2": r["cap_band2"]})
    arms = ("grid_uniform", "exact_uniform", "auto_uniform", "auto_band2",
            "cap_uniform", "cap_band2")
    tally = {}
    for a in arms:
        neg = [o["model"] for o in out
               if any(t < 0 for t in np.atleast_1d(o[a]))]
        tally[a] = {"n_inward": len(neg), "models": neg}
    return out, tally


def hole_aware_sections(pts, move_id, kinds, layer, width=0.45):
    """`toolpath.layer_cross_sections` 와 같되 고리의 바깥 경계를 짝홀(XOR)로 합쳐 구멍을 살린다."""
    out = {}
    peri = kinds == 0
    for L in np.unique(layer[peri]):
        if L < 0:
            continue
        sel = peri & (layer == L)
        segs = []
        for mv in np.unique(move_id[sel]):
            q = pts[sel & (move_id == mv)][:, :2]
            if len(q) >= 2:
                segs.append(LineString(q))
        if not segs:
            continue
        band = unary_union([g.buffer(width * 0.5 + 1e-4) for g in segs])
        geoms = band.geoms if isinstance(band, MultiPolygon) else [band]
        acc = None
        for g in geoms:
            f = Polygon(g.exterior)
            acc = f if acc is None else acc.symmetric_difference(f)
        out[int(L)] = acc.union(band) if acc is not None else band
    return out


def measure_dir(mesh, theta, lh):
    """검사기 A(낙관) 한 번 → 진짜 오버행 mm(기본 분류) + raw_mm + hole_mm (사후 진단)."""
    prof = AngleProfile.constant(theta)
    v = transform_cone_profile(mesh.vertices, prof, "outward")
    warped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=lh), prof, "outward")
    pts, mid, w, kinds, lay = sample_extrusions(real, return_types=True, return_layers=True)
    sup, _ = check_support(pts, mid, w, layer_height=lh)
    over = classify_unsupported(pts, mid, kinds, lay, sup) == 0
    raw = (kinds == 0) & ~sup
    secs = hole_aware_sections(pts, mid, kinds, lay)
    hole = np.zeros(len(pts), dtype=bool)
    for i in np.where(raw)[0]:
        below = secs.get(int(lay[i]) - 1)
        hole[i] = below is None or not below.contains(Point(pts[i, 0], pts[i, 1]))
    z0 = float(mesh.bounds[0][2])
    loc = lambda m: ([float(pts[m, 2].min() - z0), float(pts[m, 2].max() - z0),  # noqa: E731
                      float(np.hypot(pts[m, 0], pts[m, 1]).min()),
                      float(np.hypot(pts[m, 0], pts[m, 1]).max())] if m.any() else None)
    return {"mm": float(w[over].sum()), "raw_mm": float(w[raw].sum()),
            "hole_mm": float(w[hole].sum()), "over_zr": loc(over), "hole_zr": loc(hole),
            "perimeter_mm": float(w[kinds == 0].sum())}


def curves(mesh, k=DEFAULT_K):
    th = np.round(np.arange(0.0, MAX_ANGLE_DEG + 1e-9, 0.1), 3)
    res = {"theta": th.tolist()}
    s0 = None
    for d in ("outward", "inward"):
        st = support_step(mesh, d)
        s = st["eval"](th)
        if s0 is None:
            s0 = float(st["S0"])
        res[d] = {"S": s.tolist(), "J": ((s0 - s) - k * th).tolist(),
                  "roots_deg": [float(x) for x in st["roots_deg"]]}
    res["S0"] = s0
    return res


def demo(name, layer_heights):
    mesh = vessel(name)
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    g = varangle.select_uniform(mesh, DEFAULT_K)
    a_g, d_g = g["profile"][0]
    ex, _ = select_uniform_exact(mesh, DEFAULT_K)
    sb1 = varangle.select_banded_j(mesh, DEFAULT_K, 1, r_max, rp, MAX_SPACING_FACTOR)
    sb2 = varangle.select_banded_j(mesh, DEFAULT_K, 2, r_max, rp, MAX_SPACING_FACTOR)
    sel = {"grid_uniform": signed(a_g, d_g),
           "exact_uniform": signed(ex["angle"], ex["direction"]),
           "exact_J": float(ex["J"]),
           "banded_j_N1": [float(t) + 0.0 for t in sb1["thetas"]],
           "banded_j_N2": [float(t) + 0.0 for t in sb2["thetas"]]}
    analytic = {f"{d}_{a:g}": float(support_fraction(mesh, a, d, THRESHOLD_DEG))
                for d in ("outward", "inward") for a in SWEEP}
    chk = {}
    for lh in layer_heights:
        rows = {}
        for a in SWEEP:
            for sgn in ((1,) if a == 0 else (1, -1)):
                t = sgn * a
                rows[f"{t:g}"] = m = measure_dir(mesh, t, lh)
                print(f"  {name} h={lh} θ={t:+g}: 진짜 {m['mm']:.1f} / raw {m['raw_mm']:.1f}"
                      f" / 구멍살림 {m['hole_mm']:.1f} mm", flush=True)
        chk[f"{lh:g}"] = rows
    # 판정 C2: 고른 |θ| 에서 고른 방향 대 반대 방향 (사전 등록)
    t_sel = sel["grid_uniform"]
    c2 = {}
    for lh in layer_heights:
        key = f"{lh:g}"
        if f"{t_sel:g}" not in chk[key]:
            chk[key][f"{t_sel:g}"] = measure_dir(mesh, t_sel, lh)
        if t_sel != 0 and f"{-t_sel:g}" not in chk[key]:
            chk[key][f"{-t_sel:g}"] = measure_dir(mesh, -t_sel, lh)
        if t_sel == 0:
            c2[key] = None
            continue
        mine, other = chk[key][f"{t_sel:g}"]["mm"], chk[key][f"{-t_sel:g}"]["mm"]
        hm, ho = chk[key][f"{t_sel:g}"]["hole_mm"], chk[key][f"{-t_sel:g}"]["hole_mm"]
        c2[key] = {"chosen_mm": mine, "opposite_mm": other,
                   "pass": bool(mine < other - TIE_MM),
                   "post_hoc_hole_aware": {"chosen_mm": hm, "opposite_mm": ho,
                                           "chosen_better": bool(hm < ho - TIE_MM)}}
    return {"selection": sel, "analytic_support_pct": analytic, "curves": curves(mesh),
            "checker": chk, "C2": c2, "n_faces": int(len(mesh.faces))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="report_fig_direction_results.json")
    ap.add_argument("--lh", type=float, nargs="+", default=[0.3, 0.4])
    args = ap.parse_args()
    t0 = time.perf_counter()
    samples, tally = sample_counts()
    print("표본 inward 횟수:", {k: v["n_inward"] for k, v in tally.items()}, flush=True)
    demos = {n: demo(n, args.lh) for n in SECTIONS}
    c1 = {n: {"grid": demos[n]["selection"]["grid_uniform"],
              "exact": demos[n]["selection"]["exact_uniform"]} for n in demos}
    c1_pass = (c1["inner"]["grid"] < 0 and c1["inner"]["exact"] < 0
               and c1["outer"]["grid"] > 0 and c1["outer"]["exact"] > 0)
    out = {"sample": samples, "sample_inward_tally": tally, "demos": demos,
           "C1": {"by_model": c1, "pass": bool(c1_pass)},
           "meta": {"sections": SECTIONS, "k": DEFAULT_K, "tie_mm": TIE_MM,
                    "sweep_deg": SWEEP, "layer_heights": args.lh,
                    "prereg": "docs/test_report_figs_acefg.md §1.2",
                    "elapsed_s": round(time.perf_counter() - t0, 1)}}
    with open(args.json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("C1:", c1, "통과" if c1_pass else "실패")
    print("C2:", {n: d["C2"] for n, d in demos.items()})
    print("저장:", args.json)


if __name__ == "__main__":
    main()
