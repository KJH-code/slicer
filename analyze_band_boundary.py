"""analyze_band_boundary.py — 밴드 경계의 메시 의존성: 원인 · 옵션 수정 재측정 · 병합 민감도.

사전 등록: `docs/test_band_boundary.md` §1. 결과는 `band_boundary_results.json` 에 부분별로 쌓인다
(부분을 따로 돌려도 다른 부분 결과는 지워지지 않는다).

    python3 analyze_band_boundary.py --part cause            # 1. 원인 (세분화 ×4 절제 실험)
    python3 analyze_band_boundary.py --part rerun --jobs 4   # 2. T4 밴드2 행 재측정 (기본 / bounds)
    python3 analyze_band_boundary.py --part merge --jobs 4   # 3. 작은 Δθ 병합 민감도 (사후)

판정 계량: J 의 서포트 항은 `conical.analytic` 해석식, 미지지 mm 는 툴패스 검사기 A
(`analyze_gap_sample.measure`, 낙관 지지). `sweep.py`/`metrics.py` 는 쓰지 않는다.
"""

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from multiprocessing import Pool

import numpy as np
import trimesh

import conical.varangle as varangle
from analyze_blend_ratio import lobe, widen
from analyze_gap_sample import measure
from analyze_t1_conventional import all_specs, model_context, slim
from analyze_t4_robustness import PERTURB, perturb
from compare_waist import waisted_model
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

JSON = "band_boundary_results.json"
T4_JSON = "t4_robustness_results.json"
LAYER_HS = (0.3, 0.4)
FLAT_J = DEFAULT_K * ANGLE_STEP            # 0.4 %p
MODES = ("centroid", "bounds")
RES_ALIGN = [k for a, k in PERTURB if a in ("res", "align")]
CACHE_DIR = "band_boundary_cache"


# ─────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────
def select2(mesh, mode="centroid", threshold_deg=THRESHOLD_DEG):
    rp, r_max = model_context(mesh)
    return varangle.select_banded_j(mesh, DEFAULT_K, 2, r_max, rp, MAX_SPACING_FACTOR,
                                    threshold_deg=threshold_deg, band_edges=mode)


def j_eval(mesh, thetas, edges):
    """주어진 edges·각도로 선택기와 같은 경로(from_bands → profile_objective)의 J."""
    rp, r_max = model_context(mesh)
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    try:
        prof = AngleProfile.from_bands(varangle._merge_bands(edges, list(thetas)), r_max,
                                       radius_profile=rp, spacing_limit=MAX_SPACING_FACTOR,
                                       max_shift=shift)
    except ValueError:
        return None
    if prof.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp):
        return None
    base = support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    return float(varangle.profile_objective(mesh, prof, base, DEFAULT_K, BLEND_COST_K, rp,
                                            MAX_SPACING_FACTOR, THRESHOLD_DEG)["J"])


def edges_of(mesh, mode):
    return varangle.assign_height_bands(mesh, 2, mode)[1]


def fl(xs):
    return [float(x) + 0.0 for x in xs]


def dmax(a, b):
    return max(abs(x - y) for x, y in zip(a, b, strict=True))


@contextmanager
def forced(edges=None, starts=None):
    """절제 실험: select_banded_j 안의 경계 · 출발점을 원본 메시의 것으로 고정한다."""
    orig_assign, orig_best = varangle.assign_height_bands, varangle.best_angle_for_mask
    if edges is not None:
        def assign(mesh, n_bands, edges_from="centroid"):
            fz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
            e = np.asarray(edges, dtype=float)
            return np.clip(np.digitize(fz, e[1:-1]), 0, n_bands - 1), e
        varangle.assign_height_bands = assign
    if starts is not None:
        it = iter(starts)

        def best(*_a, **_k):
            t = next(it)
            return abs(t), ("outward" if t >= 0 else "inward")
        varangle.best_angle_for_mask = best
    try:
        yield
    finally:
        varangle.assign_height_bands, varangle.best_angle_for_mask = orig_assign, orig_best


def load_json():
    if os.path.exists(JSON):
        with open(JSON) as fh:
            return json.load(fh)
    return {}


def save_part(name, data):
    out = load_json()
    out[name] = data
    with open(JSON + ".tmp", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    os.replace(JSON + ".tmp", JSON)
    print(f"저장: {JSON} [{name}]")


# ─────────────────────────────────────────────────────────────
# 1. 원인 — 세분화 ×4 절제 실험
# ─────────────────────────────────────────────────────────────
def cause_task(idx):
    name, build = all_specs()[idx]
    m0 = build()
    m1 = m0.subdivide()
    s0, s1 = select2(m0), select2(m1)
    row = {"model": name, "faces": [len(m0.faces), len(m1.faces)],
           "edges": [fl(s0["edges"]), fl(s1["edges"])],
           "start": [fl(s0["start_thetas"]), fl(s1["start_thetas"])],
           "thetas": [fl(s0["thetas"]), fl(s1["thetas"])],
           "J": [float(s0["J"]), float(s1["J"])],
           "notes": [list(getattr(s0["profile_obj"], "notes", [])),
                     list(getattr(s1["profile_obj"], "notes", []))]}
    # (a) 경계만 원본으로
    with forced(edges=s0["edges"]):
        sa = select2(m1)
    # (b) 경계 + 출발점을 원본으로
    with forced(edges=s0["edges"], starts=s0["start_thetas"]):
        sb = select2(m1)
    row["ablate_edges"] = {"thetas": fl(sa["thetas"]), "start": fl(sa["start_thetas"]),
                           "J": float(sa["J"])}
    row["ablate_edges_start"] = {"thetas": fl(sb["thetas"]), "J": float(sb["J"])}
    # 메시 독립 경계 판 (bounds)
    b0, b1 = select2(m0, "bounds"), select2(m1, "bounds")
    row["bounds"] = {"edges": [fl(b0["edges"]), fl(b1["edges"])],
                     "start": [fl(b0["start_thetas"]), fl(b1["start_thetas"])],
                     "thetas": [fl(b0["thetas"]), fl(b1["thetas"])],
                     "J": [float(b0["J"]), float(b1["J"])]}
    # ΔJ: 원본 각도 대 세분화 각도를 세분화 메시(그 메시의 기본 edges)에서
    e1 = s1["edges"]
    row["J_on_sub"] = {"old_angles": j_eval(m1, s0["thetas"], e1),
                       "new_angles": j_eval(m1, s1["thetas"], e1)}
    # 같은 각도를 원본 메시에서 (J 손실)
    row["J_on_orig"] = {"old_angles": j_eval(m0, s0["thetas"], s0["edges"]),
                        "new_angles": j_eval(m0, s1["thetas"], s0["edges"])}
    # 출발점 차이의 원인: 경계를 걸친 면 — 원본 edges 로 세분화 메시 라벨을 매겼을 때 출발점
    row["start_sub_with_orig_edges"] = fl(sa["start_thetas"])
    return row


def classify(row):
    t0, t1 = row["thetas"]
    if dmax(t0, t1) == 0:
        return "불변"
    tags = []
    if dmax(row["ablate_edges"]["thetas"], t0) == 0:
        tags.append("E(경계)")
    elif dmax(row["ablate_edges_start"]["thetas"], t0) == 0:
        tags.append("S(출발점)")
    else:
        jo, jn = row["J_on_sub"]["old_angles"], row["J_on_sub"]["new_angles"]
        if jo is not None and jn - jo <= FLAT_J:
            tags.append("동점 깨기(Q, ΔJ≤0.4)")
        else:
            tags.append("구적 결함 의심(Q, ΔJ>0.4)")
    return "+".join(tags)


def part_cause(args):
    specs = all_specs()
    idxs = args.models if args.models else list(range(len(specs)))
    with Pool(args.jobs) as pool:
        rows = list(pool.imap(cause_task, idxs))
    for r in rows:
        r["class"] = classify(r)
        r["edges_moved"] = dmax(r["edges"][0], r["edges"][1])
        r["bounds_edges_moved"] = dmax(r["bounds"]["edges"][0], r["bounds"]["edges"][1])
        print(f"{r['model']:<14} 기본 {r['thetas'][0]}→{r['thetas'][1]} "
              f"경계 {np.round(r['edges'][0], 3)}→{np.round(r['edges'][1], 3)} "
              f"출발 {r['start'][0]}→{r['start'][1]} | (a) {r['ablate_edges']['thetas']} "
              f"(b) {r['ablate_edges_start']['thetas']} | J_sub 옛 {r['J_on_sub']['old_angles']} "
              f"새 {r['J_on_sub']['new_angles']} | bounds {r['bounds']['thetas'][0]}→"
              f"{r['bounds']['thetas'][1]} | {r['class']}")
    save_part("cause", {"rows": rows, "meta": {"flat_J_pp": FLAT_J,
                                               "prereg": "docs/test_band_boundary.md §1.1"}})


# ─────────────────────────────────────────────────────────────
# 2. 재측정 — T4 밴드2 행 (기본 / bounds), J 손실, 미지지 mm
# ─────────────────────────────────────────────────────────────
def cached(path, fn):
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    r = fn()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path + ".tmp", "w") as fh:
        json.dump(r, fh, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    return r


def rerun_task(task):
    idx, key, mode, do_measure = task

    def work():
        t0 = time.perf_counter()
        name, build = all_specs()[idx]
        m0 = build()
        mesh = m0 if key == "base" else perturb(m0, key)[0]
        s = select2(mesh, mode)
        out = {"model": name, "key": key, "mode": mode, "thetas": fl(s["thetas"]),
               "edges": fl(s["edges"]), "J": float(s["J"]),
               "start": fl(s["start_thetas"])}
        # J 손실: 이 각도를 원본 메시(같은 판의 edges)에서
        out["J_on_orig"] = j_eval(m0, s["thetas"], edges_of(m0, mode))
        if do_measure:
            out["measure"] = {f"{lh:g}": slim(measure(mesh, s["profile_obj"], lh))
                              for lh in LAYER_HS}
        out["seconds"] = time.perf_counter() - t0
        return out

    return cached(os.path.join(CACHE_DIR, f"rerun_{idx}_{key}_{mode}_{int(do_measure)}.json"),
                  work)


def part_rerun(args):
    specs = all_specs()
    idxs = args.models if args.models else list(range(len(specs)))
    with open(T4_JSON) as fh:
        t4 = json.load(fh)
    t4raw = {(r["model"], r["key"]): r for r in t4["raw"]}
    tasks = []
    for i in idxs:
        for key in ["base"] + RES_ALIGN:
            for mode in MODES:
                # 기본 판의 교란 mm 는 T4 에 있다(각도 재현을 확인하고 재사용). 원본 메시는 둘 다 잰다.
                tasks.append((i, key, mode, key == "base" or mode == "bounds"))
    t0 = time.perf_counter()
    res = {}
    with Pool(args.jobs) as pool:
        for r in pool.imap_unordered(rerun_task, tasks):
            res[(r["model"], r["key"], r["mode"])] = r
            print(f"  {r['model']} {r['key']} {r['mode']}: {r['thetas']} ({r['seconds']:.0f}s)",
                  flush=True)
    names = [specs[i][0] for i in idxs]
    # 재현 확인: 기본 판 각도 == T4
    repro = [(n, k) for n in names for k in ["base"] + RES_ALIGN
             if res[(n, k, "centroid")]["thetas"] != t4raw[(n, k)]["band2"]]
    for n in names:
        for k in ["base"] + RES_ALIGN:
            r = res[(n, k, "centroid")]
            if "measure" not in r and r["thetas"] == t4raw[(n, k)]["band2"]:
                r["measure"] = {lh: t4raw[(n, k)]["measure"][lh]["band2"] for lh in ("0.3", "0.4")}
                r["measure_from"] = "T4"
    rows, summary = [], {}
    for k in RES_ALIGN:
        summary[k] = {}
        for mode in MODES:
            sub = []
            for n in names:
                b, p = res[(n, "base", mode)], res[(n, k, mode)]
                loss = (None if b["J_on_orig"] is None or p["J_on_orig"] is None
                        else b["J_on_orig"] - p["J_on_orig"])
                row = {"model": n, "key": k, "mode": mode, "base": b["thetas"],
                       "pert": p["thetas"], "d": dmax(b["thetas"], p["thetas"]),
                       "edges_moved": dmax(b["edges"], p["edges"]), "J_loss": loss,
                       "d_mm": ({lh: p["measure"][lh]["mm"] - b["measure"][lh]["mm"]
                                 for lh in ("0.3", "0.4")} if "measure" in p else None)}
                sub.append(row)
            rows += sub
            losses = [r["J_loss"] for r in sub if r["J_loss"] is not None]
            dmm = {lh: [r["d_mm"][lh] for r in sub if r["d_mm"]] for lh in ("0.3", "0.4")}
            summary[k][mode] = {
                "n": len(sub), "le2": sum(r["d"] <= ANGLE_STEP + 1e-9 for r in sub),
                "eq0": sum(r["d"] == 0 for r in sub),
                "max_d": max(r["d"] for r in sub),
                "violators": [r["model"] for r in sub if r["d"] > ANGLE_STEP + 1e-9],
                "J_loss_median": float(np.median(losses)), "J_loss_max": float(max(losses)),
                "J_loss_le_flat": sum(x <= FLAT_J + 1e-12 for x in losses),
                "J_loss_n": len(losses),
                "edges_moved_max": max(r["edges_moved"] for r in sub),
                "median_d_mm": {lh: (float(np.median(v)) if v else None)
                                for lh, v in dmm.items()},
                "n_d_mm": {lh: len(v) for lh, v in dmm.items()}}
    # 원본 메시 품질: bounds 대 기본, 미지지 mm
    quality = []
    for n in names:
        a, b = res[(n, "base", "centroid")], res[(n, "base", "bounds")]
        q = {"model": n, "centroid": a["thetas"], "bounds": b["thetas"],
             "J": [a["J"], b["J"]]}
        for lh in ("0.3", "0.4"):
            q[f"mm_{lh}"] = [a["measure"][lh]["mm"], b["measure"][lh]["mm"]]
            q[f"mm_pes_{lh}"] = [a["measure"][lh]["mm_pes"], b["measure"][lh]["mm_pes"]]
        quality.append(q)
    worse = {lh: [q["model"] for q in quality if q[f"mm_{lh}"][1] - q[f"mm_{lh}"][0] > 0.5]
             for lh in ("0.3", "0.4")}
    better = {lh: [q["model"] for q in quality if q[f"mm_{lh}"][0] - q[f"mm_{lh}"][1] > 0.5]
              for lh in ("0.3", "0.4")}
    # 사전 기준
    sd = summary["subdiv4"]["bounds"]
    crit = {
        "1_subdiv_edges_same": sd["edges_moved_max"] <= 1e-9,
        "1_subdiv_le2_all": sd["le2"] == sd["n"], "1_subdiv_eq0_all": sd["eq0"] == sd["n"],
        "2_no_side_effect": {k: summary[k]["bounds"]["le2"] >= summary[k]["centroid"]["le2"] - 2
                             for k in RES_ALIGN if k != "subdiv4"},
        "3_quality_noninferior": {lh: len(worse[lh]) <= 2 for lh in ("0.3", "0.4")},
        "robust_ge90": {mode: {ax: all(summary[k][mode]["le2"] / summary[k][mode]["n"] >= 0.9
                                       for a, k in PERTURB if a == ax)
                               for ax in ("res", "align")} for mode in MODES},
    }
    print(f"\n{'교란':<13}" + "".join(f"{m + ' ≤2°':>14}{'=0':>5}{'max':>5}{'J손실 중앙/최대':>18}"
                                     f"{'≤0.4':>6}" for m in MODES))
    for k in RES_ALIGN:
        line = f"{k:<13}"
        for mode in MODES:
            s = summary[k][mode]
            line += (f"{s['le2']:>10}/{s['n']:<3}{s['eq0']:>5}{s['max_d']:>5.0f}"
                     f"{s['J_loss_median']:>10.3f}/{s['J_loss_max']:<7.3f}"
                     f"{s['J_loss_le_flat']:>4}/{s['J_loss_n']}")
        print(line)
    print(f"재현(기본 판 = T4) 어긋남: {repro or '없음'}")
    print(f"원본 mm 0.5 넘게 나빠짐: {worse}, 좋아짐: {better}")
    print(f"사전 기준: {crit}")
    save_part("rerun", {"rows": rows, "summary": summary, "quality": quality,
                        "quality_worse": worse, "quality_better": better,
                        "criteria": crit, "repro_mismatch": repro,
                        "meta": {"modes": MODES, "perturb": RES_ALIGN, "layer_heights": LAYER_HS,
                                 "flat_J_pp": FLAT_J, "elapsed_s": time.perf_counter() - t0,
                                 "centroid_perturbed_mm": "T4 재사용(각도 일치 시)",
                                 "prereg": "docs/test_band_boundary.md §1.2"}})


# ─────────────────────────────────────────────────────────────
# 3. 작은 Δθ 밴드 병합 — 민감도 (사후, 판정 밖)
# ─────────────────────────────────────────────────────────────
HELDOUT_SEED = 20261110


def random_model(seed, model_id):
    """`claude/serene-cray-u07dzk` report_experiments.random_model 을 그대로 옮김 (읽기 전용 참조).
    팀 저장소 wjd 의 generate_random_model 과 같은 규칙(SeedSequence([seed, id, 0]), 다섯 계열)."""
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(model_id), 0]))
    family = ("sphere", "cylinder", "box", "flaring_cone", "waisted_lobe")[
        int(rng.integers(0, 5))]
    if family == "sphere":
        p = {"radius": float(rng.uniform(4.0, 9.0))}
        m = trimesh.creation.icosphere(subdivisions=2, radius=p["radius"])
    elif family == "cylinder":
        p = {"radius": float(rng.uniform(4.0, 9.0)), "height": float(rng.uniform(8.0, 18.0))}
        m = trimesh.creation.cylinder(radius=p["radius"], height=p["height"], sections=48)
    elif family == "box":
        p = {"width": float(rng.uniform(7.0, 17.0)), "depth": float(rng.uniform(7.0, 17.0)),
             "height": float(rng.uniform(8.0, 18.0))}
        m = trimesh.creation.box(extents=(p["width"], p["depth"], p["height"]))
    elif family == "flaring_cone":
        p = {"bottom_radius": float(rng.uniform(3.5, 7.0)),
             "top_radius": float(rng.uniform(7.0, 11.0)),
             "height": float(rng.uniform(10.0, 20.0))}
        prof = np.array([[0, 0], [p["bottom_radius"], 0],
                         [p["top_radius"], p["height"]], [0, p["height"]]])
        m = trimesh.creation.revolve(prof, sections=48)
        m.merge_vertices()
        m.fix_normals()
    else:
        p = {"r_neck": float(rng.uniform(1.5, 5.5)), "xy_scale": float(rng.uniform(0.7, 1.3)),
             "lobe_amplitude": float(rng.uniform(0.0, 0.18))}
        m = lobe(widen(waisted_model(p["r_neck"]), p["xy_scale"]), p["lobe_amplitude"])
    return center_on_axis(m), family, p


MERGE_TH = (2.0, 4.0, 6.0)
MERGE_EXTRA = ("rand:5", "rand:10")


def build_named(name):
    if name.startswith("rand:"):
        return random_model(HELDOUT_SEED, int(name[5:]))[0]
    return dict(all_specs())[name]()


def merge_task(task):
    name, mode, do_measure = task

    def work():
        mesh = build_named(name)
        rp, r_max = model_context(mesh)
        su = varangle.select_banded_j(mesh, DEFAULT_K, 1, r_max, rp, MAX_SPACING_FACTOR,
                                      band_edges=mode)
        sb = select2(mesh, mode)
        out = {"model": name, "mode": mode, "uniform": fl(su["thetas"]), "J_uniform": su["J"],
               "band2": fl(sb["thetas"]), "J_band2": sb["J"],
               "dtheta": abs(sb["thetas"][0] - sb["thetas"][1]),
               "blends": [[float(a), float(b)] for a, b in sb["profile_obj"].blend_intervals()]}
        if do_measure:
            out["measure"] = {f"{lh:g}": {
                "uniform": slim(measure(mesh, AngleProfile.constant(su["thetas"][0]), lh)),
                "band2": slim(measure(mesh, sb["profile_obj"], lh))} for lh in LAYER_HS}
        return out

    return cached(os.path.join(CACHE_DIR, f"merge_{name.replace(':', '_')}_{mode}.json"), work)


def part_merge(args):
    names = list(MERGE_EXTRA) + [n for n, _ in all_specs()]
    tasks = [(n, mode, True) for n in names for mode in MODES]
    with Pool(args.jobs) as pool:
        rows = list(pool.imap(merge_task, tasks))
    for r in rows:
        r["merged_by"] = {f"{t:g}": (0.0 < r["dtheta"] < t) for t in MERGE_TH}
        print(f"{r['model']:<14}{r['mode']:<9} 균일 {r['uniform']} 밴드2 {r['band2']} "
              f"|Δθ| {r['dtheta']:.0f} " + " ".join(
                  f"{lh}: 밴드2 {r['measure'][lh]['band2']['mm']:.1f}/{r['measure'][lh]['band2']['mm_pes']:.1f}"
                  f" 균일 {r['measure'][lh]['uniform']['mm']:.1f}/{r['measure'][lh]['uniform']['mm_pes']:.1f}"
                  for lh in ("0.3", "0.4")))
    counts = {mode: {f"{t:g}": [r["model"] for r in rows if r["mode"] == mode
                               and r["merged_by"][f"{t:g}"]] for t in MERGE_TH} for mode in MODES}
    print(f"병합되는 모델: {counts}")
    save_part("merge", {"rows": rows, "merged_models": counts,
                        "meta": {"thresholds_deg": MERGE_TH, "seed": HELDOUT_SEED,
                                 "rule": "0 < |θ1−θ2| < 문턱 이면 밴드2 → 자동 균일(N=1)",
                                 "post_hoc": True, "prereg": "docs/test_band_boundary.md §1.3"}})


# ─────────────────────────────────────────────────────────────
# 4. 그림 D 데이터 — 반경 R(z), θ(Z′), 블렌드, r*
# ─────────────────────────────────────────────────────────────
FIGD_MODELS = ("램프", "허리 r=3", "torus", "구")


def figd_model(name):
    if name == "램프":
        return center_on_axis(trimesh.load("examples/lamp.stl", force="mesh"))
    return dict(all_specs())[name]()


def part_figd(args):
    m_max = MAX_SPACING_FACTOR
    out = {}
    for name in FIGD_MODELS:
        mesh = figd_model(name)
        rp, r_max = model_context(mesh)
        s = select2(mesh, args.mode)
        prof = s["profile_obj"]
        edges = [float(e) for e in s["edges"]]
        zs = rp._slab_zlo + rp._slab_h / 2
        zq = np.linspace(rp.z0, rp.z1, 400)
        blends = []
        for lo, hi in prof.blend_intervals():
            i = int(np.argmin(np.abs(np.asarray(prof.zs) - lo)))
            t1, t2 = float(prof.tans[i]), float(prof.tans[i + 1])
            dtan, w = t2 - t1, float(hi - lo)
            slope = dtan / w
            expand = dtan < 0                                   # c=+1: 각도 감소 = 팽창
            fac = (m_max - 1.0) if expand else (1.0 - 1.0 / m_max)
            r_star = fac / abs(slope)
            r_b = rp.max_in_slab(lo, hi, t1, t2)
            zb = edges[1]                                       # 등분 경계 (옮기기 전)
            r_orig = rp.max_in_slab(zb - w / 2, zb + w / 2, t1, t2)
            w_orig = r_orig * abs(dtan) / fac                   # 원위치에서 같은 Δtan 의 필요 폭(1회)
            blends.append({"lo": float(lo), "hi": float(hi), "w": w, "theta": [
                float(np.degrees(np.arctan(t1))), float(np.degrees(np.arctan(t2)))],
                "dtan": dtan, "s": slope, "expand": bool(expand), "r_star": float(r_star),
                "r_b": float(r_b), "r_at_center": float(rp.at(0.5 * (lo + hi))),
                "z_center": float(0.5 * (lo + hi)), "z_edge": zb,
                "r_at_edge": float(rp.at(zb)), "r_slab_edge_same_w": float(r_orig),
                "w_needed_at_edge_lower_bound": float(w_orig)})
        out[name] = {"mode": args.mode, "thetas": fl(s["thetas"]), "edges": edges,
                     "J": float(s["J"]), "notes": list(getattr(prof, "notes", [])),
                     "z0": rp.z0, "z1": rp.z1, "r_max": r_max,
                     "R_z": [fl(zs), fl(rp._slab_r)],
                     "theta_z": [fl(zq), fl(prof.theta_at(zq))],
                     "blends": blends, "m_max": m_max}
        print(name, s["thetas"], edges, blends, getattr(prof, "notes", []))
    save_part("figd", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("cause", "rerun", "merge", "figd"), required=True)
    ap.add_argument("--mode", choices=MODES, default="centroid", help="figd 의 경계 판")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--models", type=int, nargs="*", default=None)
    args = ap.parse_args()
    {"cause": part_cause, "rerun": part_rerun, "merge": part_merge,
     "figd": part_figd}[args.part](args)


if __name__ == "__main__":
    sys.exit(main())
