"""report_fig_layer_blend.py — 층고별 미지지를 블렌드 층 안/밖으로 가른다 (보고서 그림 F).

사전 등록: `docs/test_report_figs_acefg.md` §1.4.

`analyze_layer_height.py` 와 같은 세 모델(램프=허리 r=2, 허리 r=3, 구)을 같은 선택(층고와 무관,
모델당 한 번)으로 자르되, 층고 0.20~0.50 의 7 점에서 균일(J)·밴드2(J) 프로필의

* 낙관(검사기 A 기본) 진짜 오버행 미지지 mm — 전체 / 블렌드 층 안
* 블렌드 층 안 미지지 점의 층간격 배율 m (점별 `AngleProfile.spacing_factor`)
* 비관(연쇄) 진짜 오버행 %p — `analyze_layer_height` 표와 대조용

를 잰다. 점이 블렌드 층에 드는가는 정변환으로 Z′ 를 풀어(`solve_forward`) Z′ 가 블렌드 구간
[lo, hi] 안인지로 본다 (= 닫힌 식 lo − r·tanθ₁ ≤ z ≤ hi − r·tanθ₂).

    python3 report_fig_layer_blend.py --jobs 3        # 약 3 분 (4 코어)
    python3 report_fig_layer_blend.py --analytic-only # 해석식 불일치 면적만 JSON 에 덧붙임 (수 초)

**사후 추가 (결과를 본 뒤, 판정 밖)** `analytic_mismatch`: 사전 등록 §1.4 의 경계식을 면마다 적용해
"선택기(해석식)는 통과인데 검사기 기준(수평 폭 w, 수직 창 1.5h)으로는 실패" 인 면의 넓이를 층고별로 센다.
밖을 보는 오버행 면(n_r > 0, n_z < 0)만 — 표본의 오버행이 전부 이쪽이다. 면 중심의 Z′ 를 정변환으로 풀어
그 자리의 θ·m 을 쓴다:  검사기 통과 ⟺ tanψ·(m·h − w·tanθ) ≤ w  그리고  m/(1 + tanθ·tanψ) ≤ 1.5,
ψ = atan2(−n_z, n_r) (연직 기준 벽 기울기). 베드 판정 높이 안의 면도 넣는다 — 측정된 실패가 바로 그 위
(베드 위 0.4~1mm)의 고리라서, 그 고리가 놓이는 면을 빼면 실패 자리를 못 본다(빼 본 판: 램프 밴드2 0.4 에서 0).
"""

import argparse
import json
import time
from multiprocessing import Pool

import numpy as np
import trimesh

from analyze_blend_ratio import _sphere
from compare_waist import waisted_model
from conical.backtransform import backtransform
from conical.config import DEFAULT_K, MAX_SPACING_FACTOR
from conical.meshio import RadiusProfile
from conical.planar_slicer import slice_mesh
from conical.toolpath import check_support, classify_unsupported, sample_extrusions
from conical.transform import transform_cone_profile
from conical.varangle import select_banded_j

HEIGHTS = (0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5)
MODELS = (("램프 (=허리 r=2)", lambda: waisted_model(2.0)),
          ("허리 r=3", lambda: waisted_model(3.0)),
          ("구", _sphere))
WIDTH = 0.45


def select(mesh):
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    out = {}
    for n in (1, 2):
        r = select_banded_j(mesh, DEFAULT_K, n, r_max, rp, MAX_SPACING_FACTOR)
        out[n] = r
    return out, rp, r_max


def measure(mesh, prof, h, rp, r_max):
    v = transform_cone_profile(mesh.vertices, prof, "outward")
    warped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=h), prof, "outward")
    pts, mid, w, kinds, lay = sample_extrusions(real, return_types=True, return_layers=True)
    peri = kinds == 0
    tot = float(w[peri].sum())
    r = np.hypot(pts[:, 0], pts[:, 1])
    blends = prof.blend_intervals()
    if blends:
        zw = prof.solve_forward(pts[:, 2], r, "outward")
        inb = np.zeros(len(pts), dtype=bool)
        for lo, hi in blends:
            inb |= (zw >= lo - 1e-9) & (zw <= hi + 1e-9)
        m = prof.spacing_factor(zw, r, "outward")
    else:
        inb = np.zeros(len(pts), dtype=bool)
        m = np.ones(len(pts))
    out = {"perimeter_mm": tot, "blend_perimeter_mm": float(w[peri & inb].sum())}
    for suffix, chained in (("", False), ("_pes", True)):
        sup, _ = check_support(pts, mid, w, layer_height=h, require_supported_below=chained)
        over = classify_unsupported(pts, mid, kinds, lay, sup) == 0
        out["mm" + suffix] = float(w[over].sum())
        out["pct" + suffix] = float(w[over].sum() / tot * 100.0)
        out["blend_mm" + suffix] = float(w[over & inb].sum())
        if suffix == "":
            sel = over & inb
            out["blend_m_median"] = float(np.median(m[sel])) if sel.any() else None
            out["blend_m_max_all"] = float(m[peri & inb].max()) if (peri & inb).any() else None
            zs = pts[sel, 2] - float(mesh.bounds[0][2])
            out["blend_over_z"] = [float(zs.min()), float(zs.max())] if sel.any() else None
    return out


def analytic_mismatch(mesh, prof, h, w=WIDTH, vwin=1.5):
    """선택기 통과 & 검사기 경계식 실패 면적(mm²) — 전체 / 블렌드 층 안. 사후 추가 분석."""
    from conical.analytic import radial_normal
    kappa = -np.sin(np.radians(45.0))
    n = mesh.face_normals
    nr, nz = radial_normal(mesh), n[:, 2]
    c = mesh.triangles_center
    r = np.hypot(c[:, 0], c[:, 1])
    zw = prof.solve_forward(c[:, 2], r, "outward")
    th = np.radians(prof.theta_at(zw))
    T = np.tan(th)
    m = prof.spacing_factor(zw, r, "outward")
    A = mesh.area_faces
    out_face = (nr > 1e-9) & (nz < -1e-9)
    tpsi = np.where(out_face, -nz / np.where(nr > 1e-9, nr, 1.0), 0.0)
    sel_ok = nz * np.cos(th) + nr * np.sin(th) >= kappa
    chk_ok = (tpsi * (m * h - w * T) <= w) & (m / (1.0 + T * tpsi) <= vwin + 1e-12)
    inb = np.zeros(len(A), dtype=bool)
    for lo, hi in prof.blend_intervals():
        inb |= (zw >= lo) & (zw <= hi)
    mis = out_face & sel_ok & ~chk_ok
    return {"mismatch_mm2": float(A[mis].sum()), "mismatch_blend_mm2": float(A[mis & inb].sum()),
            "selector_fail_mm2": float(A[out_face & ~sel_ok].sum())}


def add_analytic(path):
    heights = np.round(np.arange(0.20, 0.501, 0.01), 3)
    with open(path) as fh:
        d = json.load(fh)
    res = {}
    for name, build in MODELS:
        mesh = build()
        sel, rp, r_max = select(mesh)
        res[name] = {"heights": heights.tolist()}
        for n, key in ((1, "uniform"), (2, "band2")):
            rows = [analytic_mismatch(mesh, sel[n]["profile_obj"], float(h)) for h in heights]
            res[name][key] = {q: [row[q] for row in rows] for q in rows[0]}
            on = [float(h) for h, row in zip(heights, rows, strict=True) if row["mismatch_mm2"] > 0]
            res[name][key]["onset_h"] = on[0] if on else None
        print(name, "불일치 mm² 균일/밴드2 @0.3:",
              round(res[name]["uniform"]["mismatch_mm2"][10], 1),
              round(res[name]["band2"]["mismatch_mm2"][10], 1), "@0.4:",
              round(res[name]["uniform"]["mismatch_mm2"][20], 1),
              round(res[name]["band2"]["mismatch_mm2"][20], 1), flush=True)
    d["analytic_mismatch"] = res
    d["meta"]["analytic_note"] = "사후 추가(결과 본 뒤, 판정 밖): 선택기 통과 & 검사기 경계식 실패 면적"
    with open(path, "w") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    print("덧붙임:", path)


def run(task):
    mi, h = task
    name, build = MODELS[mi]
    t0 = time.perf_counter()
    mesh = build()
    sel, rp, r_max = select(mesh)
    row = {"model": name, "layer_height": h}
    for n, key in ((1, "uniform"), (2, "band2")):
        prof = sel[n]["profile_obj"]
        row[key + "_thetas"] = [float(t) + 0.0 for t in sel[n]["thetas"]]
        row[key + "_blend"] = [[float(a), float(b)] for a, b in prof.blend_intervals()]
        row[key + "_m_planner"] = float(prof.max_spacing_factor(r_max, "outward", rp))
        row[key] = measure(mesh, prof, h, rp, r_max)
    row["seconds"] = round(time.perf_counter() - t0, 1)
    print(f"{name} h={h}: 균일 {row['uniform']['mm']:.1f}mm  밴드2 {row['band2']['mm']:.1f}mm"
          f" (블렌드 {row['band2']['blend_mm']:.1f}, m중앙 {row['band2']['blend_m_median']})",
          flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--json", default="report_fig_layer_blend_results.json")
    ap.add_argument("--analytic-only", action="store_true")
    args = ap.parse_args()
    if args.analytic_only:
        add_analytic(args.json)
        return
    tasks = [(mi, h) for mi in range(len(MODELS)) for h in HEIGHTS]
    t0 = time.perf_counter()
    with Pool(args.jobs) as pool:
        rows = pool.map(run, tasks, chunksize=1)
    out = {"rows": rows,
           "meta": {"heights": HEIGHTS, "k": DEFAULT_K, "width_mm": WIDTH,
                    "vwin_factor": 1.5, "spacing_limit": MAX_SPACING_FACTOR,
                    "prereg": "docs/test_report_figs_acefg.md §1.4",
                    "elapsed_s": round(time.perf_counter() - t0, 1)}}
    with open(args.json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("저장:", args.json)


if __name__ == "__main__":
    main()
