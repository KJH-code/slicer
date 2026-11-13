"""analyze_t4_robustness.py — T4: 작은 교란에 각도 결정이 흔들리나.

한 축씩만 움직여 자동 균일(J)·자동 밴드2 가 고른 각도(°)와 미지지 mm 의 변화를 잰다.
사전 등록: `docs/test_t1_t4.md` §1.2.

| 축 | 값 |
|---|---|
| 메시 해상도 | 세분화 ×4 (중점 분할, 형상 불변) / 단순화 ×0.5 (quadric decimation) |
| 축 정렬 오차 | 중심 0.1·0.5mm 이동 (재센터링 없음) / 축 1°·3° 기울임 (→ center_on_axis) |
| 임계각 | 40·45·50° (선택기만) |
| 층고 | 0.2·0.3·0.4 (선택기에는 입력 없음 → mm 만) |

    python3 analyze_t4_robustness.py --jobs 4           # 약 30~40 분 (4 코어)
"""

import argparse
import json
import sys
import time
from multiprocessing import Pool

import numpy as np
import trimesh

import conical.varangle as varangle
from analyze_gap_sample import measure
from analyze_t1_conventional import all_specs, model_context, select_auto, slim
from conical.analytic import support_fraction
from conical.config import (
    ANGLE_STEP,
    BLEND_COST_K,
    BLEND_SHIFT_RATIO,
    DEFAULT_K,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.meshio import center_on_axis
from conical.profile import AngleProfile

LAYER_HS = (0.3, 0.4)
EXTRA_LH = 0.2
FLAT_J = DEFAULT_K * ANGLE_STEP        # 0.4 %p — 격자 한 칸의 각도 비용
PERTURB = [
    ("res", "subdiv4"), ("res", "simplify0.5"),
    ("align", "shift0.1"), ("align", "shift0.5"),
    ("align", "tilt1"), ("align", "tilt3"),
    ("threshold", "thr40"), ("threshold", "thr50"),
]


def perturb(mesh, key):
    """교란 메시와 그 선택에 쓸 임계각."""
    m = mesh.copy()
    thr = THRESHOLD_DEG
    if key == "subdiv4":
        m = m.subdivide()
    elif key == "simplify0.5":
        m = m.simplify_quadric_decimation(face_count=max(len(m.faces) // 2, 4))
        m.fix_normals()
        m = center_on_axis(m)
    elif key.startswith("shift"):
        m.apply_translation([float(key[5:]), 0.0, 0.0])
    elif key.startswith("tilt"):
        rot = trimesh.transformations.rotation_matrix(np.radians(float(key[4:])), [1, 0, 0])
        m.apply_transform(rot)
        m = center_on_axis(m)
    elif key.startswith("thr"):
        thr = float(key[3:])
    else:
        raise ValueError(key)
    return m, thr


def j_of(mesh, rp, r_max, thetas, thr):
    """교란 메시에서 주어진 각도의 J — 튐이 평평한 목적함수 위의 것인지 보려고.

    선택기(`select_banded_j`)의 점수 경로와 같다: from_bands → profile_objective.
    """
    _labels, edges = varangle.assign_height_bands(mesh, len(thetas))
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    try:
        prof = AngleProfile.from_bands(varangle._merge_bands(edges, list(thetas)), r_max,
                                       radius_profile=rp, spacing_limit=MAX_SPACING_FACTOR,
                                       max_shift=shift)
    except ValueError:
        return None
    base = support_fraction(mesh, 0.0, "outward", thr)
    return float(varangle.profile_objective(mesh, prof, base, DEFAULT_K, BLEND_COST_K, rp,
                                            MAX_SPACING_FACTOR, thr)["J"])


def choose(mesh, thr):
    rp, r_max = model_context(mesh)
    su, sb = select_auto(mesh, rp, r_max, threshold_deg=thr)
    return {"uniform": [float(su["thetas"][0]) + 0.0],
            "band2": [float(t) + 0.0 for t in sb["thetas"]],
            "J_uniform": float(su["J"]) if "J" in su else None,
            "J_band2": float(sb["J"]) if "J" in sb else None,
            "_prof_b": sb["profile_obj"], "_rp": rp, "_r_max": r_max}


def run_task(task):
    idx, key = task
    t0 = time.perf_counter()
    name, build = all_specs()[idx]
    base_mesh = build()
    if key == "base":
        mesh, thr = base_mesh, THRESHOLD_DEG
    else:
        mesh, thr = perturb(base_mesh, key)
    ch = choose(mesh, thr)
    lhs = LAYER_HS + ((EXTRA_LH,) if key == "base" else ())
    meas = {}
    for lh in lhs:
        meas[f"{lh:g}"] = {
            "uniform": slim(measure(mesh, AngleProfile.constant(ch["uniform"][0]), lh)),
            "band2": slim(measure(mesh, ch["_prof_b"], lh))}
    out = {"model": name, "key": key, "threshold_deg": thr,
           "faces": int(len(mesh.faces)), "watertight": bool(mesh.is_watertight),
           "uniform": ch["uniform"], "band2": ch["band2"],
           "J_uniform": ch["J_uniform"], "J_band2": ch["J_band2"],
           "measure": meas, "seconds": time.perf_counter() - t0}
    return out


def flat_check(task):
    """튐 후보: 교란 메시에서 원래 각도의 J 대 새 각도의 J."""
    idx, key, th_old, th_new = task
    name, build = all_specs()[idx]
    mesh, thr = perturb(build(), key) if key != "base" else (build(), THRESHOLD_DEG)
    rp, r_max = model_context(mesh)
    return idx, key, len(th_old), j_of(mesh, rp, r_max, th_old, thr), \
        j_of(mesh, rp, r_max, th_new, thr)


def mean_abs_mesh(row, lh="0.4"):
    return row["measure"][lh]["band2"]["angle"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--models", type=int, nargs="*", default=None)
    ap.add_argument("--json", default="t4_robustness_results.json")
    args = ap.parse_args()

    specs = all_specs()
    idxs = args.models if args.models else list(range(len(specs)))
    keys = ["base"] + [k for _a, k in PERTURB]
    tasks = [(i, k) for i in idxs for k in keys]
    t0 = time.perf_counter()
    res = {}
    with Pool(args.jobs) as pool:
        for r in pool.imap_unordered(run_task, tasks):
            res[(r["model"], r["key"])] = r
            print(f"  끝: {r['model']} {r['key']} ({r['seconds']:.0f}s) "
                  f"균일 {r['uniform']} 밴드2 {r['band2']}", flush=True)

    names = [specs[i][0] for i in idxs]
    axis_of = dict((k, a) for a, k in PERTURB)
    # 각도 변화
    rows = []
    flat_tasks = []
    for i, n in zip(idxs, names, strict=True):
        b = res[(n, "base")]
        for _a, k in PERTURB:
            p = res[(n, k)]
            du = abs(p["uniform"][0] - b["uniform"][0])
            db = max(abs(x - y) for x, y in zip(p["band2"], b["band2"], strict=True))
            row = {"model": n, "key": k, "axis": axis_of[k],
                   "uniform": p["uniform"], "band2": p["band2"],
                   "d_uniform": du, "d_band2": db,
                   "d_mm": {lh: {arm: p["measure"][lh][arm]["mm"] - b["measure"][lh][arm]["mm"]
                                 for arm in ("uniform", "band2")} for lh in ("0.3", "0.4")}}
            rows.append(row)
            if axis_of[k] in ("res", "align"):
                if du > ANGLE_STEP + 1e-9:
                    flat_tasks.append((i, k, b["uniform"], p["uniform"]))
                if db > ANGLE_STEP + 1e-9:
                    flat_tasks.append((i, k, b["band2"], p["band2"]))
    flat = {}
    if flat_tasks:
        with Pool(args.jobs) as pool:
            for idx, k, nb, j_old, j_new in pool.imap_unordered(flat_check, flat_tasks):
                flat[(specs[idx][0], k, "uniform" if nb == 1 else "band2")] = (j_old, j_new)
    for r in rows:
        for arm in ("uniform", "band2"):
            f = flat.get((r["model"], r["key"], arm))
            if f:
                j_old, j_new = f
                r[f"jump_{arm}"] = {"J_old_angle": j_old, "J_new_angle": j_new,
                                    "flat": (j_old is not None and j_new - j_old <= FLAT_J)}

    # 요약: 교란별 ≤2° 비율
    summary = {}
    print(f"\n{'교란':<14}{'축':<10}{'균일 ≤2°':>10}{'밴드2 ≤2°':>11}{'튐(평평)':>10}"
          f"{'Δmm 중앙 0.3/0.4 (균일)':>26}")
    for a, k in PERTURB:
        sub = [r for r in rows if r["key"] == k]
        nu = sum(r["d_uniform"] <= ANGLE_STEP + 1e-9 for r in sub)
        nb = sum(r["d_band2"] <= ANGLE_STEP + 1e-9 for r in sub)
        jumps = [r for r in sub for arm in ("uniform", "band2") if f"jump_{arm}" in r]
        nflat = sum(r[f"jump_{arm}"]["flat"] for r in sub for arm in ("uniform", "band2")
                    if f"jump_{arm}" in r)
        dmm = {lh: float(np.median([r["d_mm"][lh]["uniform"] for r in sub]))
               for lh in ("0.3", "0.4")}
        dmm_b = {lh: float(np.median([r["d_mm"][lh]["band2"] for r in sub]))
                 for lh in ("0.3", "0.4")}
        summary[k] = {"axis": a, "n": len(sub), "uniform_le2": nu, "band2_le2": nb,
                      "uniform_le2_frac": nu / len(sub), "band2_le2_frac": nb / len(sub),
                      "n_jumps": len(jumps), "n_flat_jumps": nflat,
                      "violators_uniform": [r["model"] for r in sub
                                            if r["d_uniform"] > ANGLE_STEP + 1e-9],
                      "violators_band2": [r["model"] for r in sub
                                          if r["d_band2"] > ANGLE_STEP + 1e-9],
                      "median_d_mm_uniform": dmm, "median_d_mm_band2": dmm_b}
        print(f"{k:<14}{a:<10}{nu:>5}/{len(sub):<4}{nb:>6}/{len(sub):<4}{nflat:>5}/{len(jumps):<4}"
              f"{dmm['0.3']:>12.1f}/{dmm['0.4']:.1f}")
    robust = {}
    for a in ("res", "align"):
        ks = [k for aa, k in PERTURB if aa == a]
        robust[a] = {arm: all(summary[k][f"{arm}_le2_frac"] >= 0.9 for k in ks)
                     for arm in ("uniform", "band2")}
    subdiv_defect = [r["model"] for r in rows if r["key"] == "subdiv4"
                     and (r["d_uniform"] > 0 or r["d_band2"] > 0)]

    # 임계각 방향: θ(40) ≥ θ(45) ≥ θ(50)
    direction = {"uniform": [], "band2_mean_abs": []}
    for n in names:
        u = [res[(n, k)]["uniform"][0] for k in ("thr40", "base", "thr50")]
        direction["uniform"].append({"model": n, "thetas": u,
                                     "ok": abs(u[0]) >= abs(u[1]) >= abs(u[2])})
        bm = [mean_abs_mesh(res[(n, k)]) for k in ("thr40", "base", "thr50")]
        direction["band2_mean_abs"].append({"model": n, "mean_abs": bm,
                                            "ok": bm[0] >= bm[1] - 1e-9 and bm[1] >= bm[2] - 1e-9})
    n_dir_u = sum(d["ok"] for d in direction["uniform"])
    n_dir_b = sum(d["ok"] for d in direction["band2_mean_abs"])
    # 층고
    lh_rows = []
    for n in names:
        b = res[(n, "base")]
        lh_rows.append({"model": n, **{f"mm_{arm}_{lh}": b["measure"][lh][arm]["mm"]
                                       for arm in ("uniform", "band2")
                                       for lh in ("0.2", "0.3", "0.4")}})
    print(f"\n견고(≥90%): {robust}")
    print(f"세분화 ×4 에서 각도가 바뀐 모델 (결함 신호): {subdiv_defect or '없음'}")
    print(f"임계각 방향 맞음: 균일 {n_dir_u}/{len(names)}, 밴드2 평균|θ| {n_dir_b}/{len(names)}")
    for d in direction["uniform"]:
        if not d["ok"]:
            print(f"   균일 방향 어김: {d['model']} θ(40,45,50) = {d['thetas']}")
    print("층고별 미지지 mm (균일 J; 0.2/0.3/0.4):")
    for r in lh_rows:
        print(f"   {r['model']:<14}{r['mm_uniform_0.2']:>7.1f}{r['mm_uniform_0.3']:>7.1f}"
              f"{r['mm_uniform_0.4']:>7.1f}")
    elapsed = time.perf_counter() - t0
    print(f"실행 시간 {elapsed / 60:.1f} 분")
    with open(args.json, "w") as fh:
        json.dump({"raw": [res[(n, k)] for n in names for k in keys],
                   "rows": rows, "summary": summary, "robust_ge90": robust,
                   "subdiv_defect": subdiv_defect,
                   "threshold_direction": direction,
                   "threshold_direction_ok": {"uniform": n_dir_u, "band2_mean_abs": n_dir_b,
                                              "n": len(names)},
                   "layer_height_mm": lh_rows,
                   "meta": {"perturbations": PERTURB, "layer_heights": LAYER_HS,
                            "extra_layer_height": EXTRA_LH, "flat_J_pp": FLAT_J,
                            "grid_deg": ANGLE_STEP, "elapsed_s": elapsed,
                            "jobs": args.jobs, "prereg": "docs/test_t1_t4.md §1.2"}},
                  fh, ensure_ascii=False, indent=1)
    print(f"저장: {args.json}")


if __name__ == "__main__":
    sys.exit(main())
