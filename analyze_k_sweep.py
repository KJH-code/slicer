"""analyze_k_sweep.py — 각도 비용 k 스윕 (사전 등록: `docs/test_k_sweep.md` §1).

T1(`analyze_t1_conventional.py`) 과 같은 21 모델 · 층고 0.3/0.4 · 베드 상한 유무 4 셀에서
k ∈ {0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0} 마다 자동 균일·자동 밴드2 를 다시 고르고,
툴패스 검사기 A(낙관) 미지지 mm 와 후회(사후 최적 대비)를 잰다.

`t1_conventional_results.json` 의 각도별 툴패스 값을 재사용하고 **없는 각도·프로필만** 잰다.
선택 단계와 측정 단계를 나눠 캐시한다(`k_sweep_cache/`).

    python3 analyze_k_sweep.py --jobs 4                 # 선택 → 측정 → 요약
    (다시 돌리면 캐시로 요약만 새로 만든다)

기본 동작(`conical/`)은 바꾸지 않는다. §1.5 의 대안 지표(연속 대리 지표, 정규화 k)는
이 스크립트 안에서만 계산하는 사후 민감도다(판정 밖).
"""

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

import conical.varangle as varangle
from analyze_gap_sample import BED_CAP, BED_CAP_LAYER_H, measure, profile_from
from analyze_t1_conventional import FIXED, LAYER_HS, TIE_MM, all_specs, model_context
from conical.analytic import overhang_score, support_fraction
from conical.config import (
    ANGLE_STEP,
    BLEND_COST_K,
    BLEND_SHIFT_RATIO,
    MAX_ANGLE_DEG,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.profile import AngleProfile
from conical.rep5x import bed_safe_profile

KS = (0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0)
CACHE = "k_sweep_cache"
T1_JSON = "t1_conventional_results.json"
# §1.5 사후 민감도의 손잡이 격자 (판정 밖)
KC = (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1)        # 연속 대리 지표, °/°
KREL = (0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0)                   # 정규화 k′, %(자기 서포트)/°


def kkey(k):
    return f"{k:g}"


def signed_grid():
    return sorted({float(s * a) for s in (1, -1)
                   for a in varangle.angle_candidates(MAX_ANGLE_DEG, ANGLE_STEP)})


def _cache_path(*parts):
    return os.path.join(CACHE, "_".join(str(p) for p in parts) + ".json")


def _cached(path, fn):
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    out = fn()
    os.makedirs(CACHE, exist_ok=True)
    with open(path + ".tmp", "w") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    return out


# ─────────────────────────────────────────────────────────────
# 1단계: 선택 (층고와 무관 — 모델마다 한 번)
# ─────────────────────────────────────────────────────────────
def capped_table(mesh, rp, r_max, cap):
    """`select_capped` 의 점수표를 k 와 무관한 성분으로 한 번만 만든다.

    J(k) = (base − sup) − k·avg − k_blend·pen 이고 `profile_objective` 와 **같은 연산 순서**로
    다시 조립하므로 k 마다 `select_capped(k)` 를 부른 것과 비트 단위로 같은 J 가 나온다.
    """
    _labels, edges = varangle.assign_height_bands(mesh, 2)
    base = support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    grid = signed_grid()
    low = [t for t in grid if abs(t) <= cap + 1e-9]
    profs = {}

    def comp(thetas):
        try:
            prof = AngleProfile.from_bands(
                varangle._merge_bands(edges, thetas), r_max, radius_profile=rp,
                spacing_limit=MAX_SPACING_FACTOR, max_shift=shift)
        except ValueError:
            return None
        if prof.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp):
            return None
        m = varangle.profile_objective(mesh, prof, base, 0.0, BLEND_COST_K, rp,
                                       MAX_SPACING_FACTOR, THRESHOLD_DEG)
        profs[tuple(thetas)] = prof
        return (base, m["support_pct"], m["avg_angle"], m["blend_penalty"])

    uni = [(comp([t, t]), t) for t in low]
    pairs = []
    for t1 in low:
        for t2 in grid:
            c = comp([t1, t2])
            if c is not None:
                pairs.append((c, t1, t2))
    return uni, pairs, profs, rp


def _j(c, k):
    base, sup, avg, pen = c
    return (base - sup) - k * avg - BLEND_COST_K * pen


def select_capped_k(uni, pairs, profs, rp, k, bed_cache):
    """`analyze_gap_sample.select_capped` 와 같은 규칙 (같은 정렬 키·같은 베드 검사)."""
    u = [(_j(c, k), t) for c, t in uni if c is not None]
    theta_u = max(u, key=lambda x: (round(x[0], 9), -abs(x[1])))[1]
    cands = [(_j(c, k), t1, t2) for c, t1, t2 in pairs]
    cands.sort(key=lambda c: (-round(c[0], 9), abs(c[1]) + abs(c[2])))
    rejected = 0
    for _, t1, t2 in cands:
        key = (t1, t2)
        if key not in bed_cache:
            bed_cache[key] = not bed_safe_profile(profs[key], rp, BED_CAP_LAYER_H)[1]["changed"]
        if bed_cache[key]:
            return theta_u, [t1, t2], rejected
        rejected += 1
    return theta_u, [theta_u, theta_u], rejected


def analytic_curves(mesh):
    """부호 있는 격자에서 해석식 S(θ), 연속 대리 C(θ) (§1.5 A)."""
    areas = mesh.area_faces
    kappa = -np.sin(np.radians(THRESHOLD_DEG))
    S, C = {}, {}
    for t in signed_grid():
        d = "outward" if t >= 0 else "inward"
        g = overhang_score(mesh, abs(t), d)
        S[kkey(t)] = float(areas[g < kappa].sum() / areas.sum() * 100.0)
        phi = np.degrees(np.arcsin(np.clip(-g, 0.0, 1.0)))
        C[kkey(t)] = float((np.maximum(0.0, phi - THRESHOLD_DEG) * areas).sum() / areas.sum())
    return S, C


def run_select(idx):
    def work():
        t0 = time.perf_counter()
        name, build = all_specs()[idx]
        mesh = build()
        rp, r_max = model_context(mesh)
        out = {"model": name, "idx": idx, "sel": {}}
        uni, pairs, profs, _ = capped_table(mesh, rp, r_max, BED_CAP)
        bed_cache = {}
        for k in KS:
            su = varangle.select_banded_j(mesh, k, 1, r_max, rp, MAX_SPACING_FACTOR)
            sb = varangle.select_banded_j(mesh, k, 2, r_max, rp, MAX_SPACING_FACTOR)
            cu, cb, rej = select_capped_k(uni, pairs, profs, rp, k, bed_cache)
            out["sel"][kkey(k)] = {
                "uniform": float(su["thetas"][0]) + 0.0,
                "band2": [float(t) + 0.0 for t in sb["thetas"]],
                "band2_J": float(sb["J"]), "uniform_J": float(su["J"]),
                "cap_uniform": float(cu) + 0.0, "cap_band2": [float(t) + 0.0 for t in cb],
                "cap_rejected": rej}
        out["S"], out["C"] = analytic_curves(mesh)
        out["seconds"] = time.perf_counter() - t0
        return out
    return _cached(_cache_path("sel", idx), work)


# ─────────────────────────────────────────────────────────────
# 2단계: 측정 (T1 에 없는 것만)
# ─────────────────────────────────────────────────────────────
def t1_lookup(t1_rows):
    """(모델, 층고) → {'u': {각: 측정}, 'b': {(θ₁,θ₂): 측정}} — T1 에서 이미 잰 것."""
    lut = {}
    for r in t1_rows:
        u = dict(r["uniform"])
        u.update(r.get("uniform_neg_sensitivity") or {})
        b = {tuple(r["auto_band2"]): r["arms"]["band2"],
             tuple(r["cap_band2"]): r["arms"]["cap_band2"]}
        lut[(r["model"], r["layer_height"])] = {"u": u, "b": b}
    return lut


def band_key(ts):
    return "b" + ",".join(f"{t:g}" for t in ts)


def needed_angles(sel):
    """선택 결과 → 재야 할 균일각 집합 · 밴드2 집합 (k 와 판 전부, 민감도 포함)."""
    us, bs = set(), set()
    for s in sel["sel"].values():
        us |= {s["uniform"], s["cap_uniform"], s["band2"][0], s["cap_band2"][0]}
        for ts in (s["band2"], s["cap_band2"]):
            if ts[0] == ts[1]:
                us.add(ts[0])
            else:
                bs.add(tuple(ts))
    for t in sensitivity_choices(sel):
        us.add(t)
    return us, bs


def run_measure(task):
    idx, lh, todo_u, todo_b = task
    name, build = all_specs()[idx]
    mesh = None
    out = {}
    for a in todo_u:
        def work(a=a):
            nonlocal mesh
            if mesh is None:
                mesh = build()
            return measure(mesh, AngleProfile.constant(a), lh)
        out[f"{a:g}"] = _cached(_cache_path("m", idx, f"{lh:g}", f"u{a:g}"), work)
    for ts in todo_b:
        def work(ts=ts):
            nonlocal mesh
            if mesh is None:
                mesh = build()
            rp, r_max = model_context(mesh)
            return measure(mesh, profile_from(mesh, list(ts), rp, r_max), lh)
        out[band_key(ts)] = _cached(_cache_path("m", idx, f"{lh:g}", band_key(ts)), work)
    return name, lh, out


# ─────────────────────────────────────────────────────────────
# §1.5 사후 민감도 (판정 밖): 균일 선택을 다른 목적함수로
# ─────────────────────────────────────────────────────────────
def _argmax_uniform(score, cap):
    """J 최대, 동점(1e-9)은 |θ| 작은 쪽, 그다음 outward."""
    best = None
    for t in signed_grid():
        if cap is not None and abs(t) > cap + 1e-9:
            continue
        j = score(t)
        key = (round(j, 9), -abs(t), t >= 0)
        if best is None or key > best[0]:
            best = (key, t)
    return best[1]


def sensitivity_select(sel):
    S, C = sel["S"], sel["C"]
    s0, c0 = S["0"], C["0"]
    out = {"C": {}, "rel": {}}
    for kc in KC:
        for cap in (None, BED_CAP):
            out["C"][f"{kc:g}|{'cap' if cap else 'none'}"] = _argmax_uniform(
                lambda t, kc=kc: (c0 - C[kkey(t)]) - kc * abs(t), cap)
    for kr in KREL:
        for cap in (None, BED_CAP):
            out["rel"][f"{kr:g}|{'cap' if cap else 'none'}"] = _argmax_uniform(
                lambda t, kr=kr: (100.0 * (s0 - S[kkey(t)]) / s0 if s0 > 0 else 0.0)
                - kr * abs(t), cap)
    return out


def sensitivity_choices(sel):
    s = sensitivity_select(sel)
    return {t for d in s.values() for t in d.values()}


# ─────────────────────────────────────────────────────────────
# 3단계: 집계
# ─────────────────────────────────────────────────────────────
def build_tables(sels, t1_rows, meas):
    """(모델, 층고) → 균일 측정 dict, 밴드 측정 dict (T1 ∪ 새 측정)."""
    lut = t1_lookup(t1_rows)
    for (name, lh), new in meas.items():
        for key, m in new.items():
            if key.startswith("b"):
                ts = tuple(float(x) for x in key[1:].split(","))
                lut[(name, lh)]["b"][ts] = m
            else:
                lut[(name, lh)]["u"].setdefault(key, m)
    return lut


def oracle_pool(t1_row, sel):
    """사전 등록 §1.0: T1 의 후보 집합 ∪ 이 스윕에서 고른 균일각 전부."""
    pool = set(t1_row["uniform"].keys())
    for s in sel["sel"].values():
        pool |= {f"{s['uniform']:g}", f"{s['cap_uniform']:g}",
                 f"{s['band2'][0]:g}", f"{s['cap_band2'][0]:g}"}
    return pool


def oracle(lutu, pool, cap):
    best = None
    for key in pool:
        a = float(key)
        if cap is not None and abs(a) > cap + 1e-9:
            continue
        mm = lutu[key]["mm"]
        if best is None or mm < best[1] - 1e-6 or (abs(mm - best[1]) <= 1e-6 and abs(a) < abs(best[0])):
            best = (a, mm)
    return best


def get_band(lut_entry, ts):
    if ts[0] == ts[1]:
        return lut_entry["u"][f"{ts[0]:g}"]
    return lut_entry["b"][tuple(ts)]


def summarize(sels, t1_rows, lut):
    t1_by = {(r["model"], r["layer_height"]): r for r in t1_rows}
    cells = {}
    for lh in LAYER_HS:
        for cap in (None, BED_CAP):
            ctag = f"{lh:g}|{'cap' if cap else 'none'}"
            per_model = []
            for sel in sels:
                name = sel["model"]
                e = lut[(name, lh)]
                pool = oracle_pool(t1_by[(name, lh)], sel)
                oa, omm = oracle(e["u"], pool, cap)
                pm = {"model": name, "oracle_theta": oa, "oracle_mm": omm, "fixed": {}, "k": {}}
                for a in FIXED:
                    if cap is not None and a > cap + 1e-9:
                        pm["fixed"][f"{a:g}"] = None
                    else:
                        m = e["u"][f"{a:g}"]
                        pm["fixed"][f"{a:g}"] = {"mm": m["mm"], "theta": m["angle"],
                                                 "regret": m["mm"] - omm}
                for k in KS:
                    s = sel["sel"][kkey(k)]
                    tu = s["uniform"] if cap is None else s["cap_uniform"]
                    tb = s["band2"] if cap is None else s["cap_band2"]
                    mu = e["u"][f"{tu:g}"]
                    mb = get_band(e, tb)
                    mbu = e["u"][f"{tb[0]:g}"]
                    S0 = sel["S"]["0"]
                    pm["k"][kkey(k)] = {
                        "uniform": {"theta": tu, "mm": mu["mm"], "mean_abs": mu["angle"],
                                    "regret": mu["mm"] - omm,
                                    "S": sel["S"][f"{tu:g}"], "dS": S0 - sel["S"][f"{tu:g}"]},
                        "band2": {"theta": tb, "mm": mb["mm"], "mean_abs": mb["angle"],
                                  "regret": mb["mm"] - omm},
                        "uniform_band2_bottom": {"theta": tb[0], "mm": mbu["mm"],
                                                 "mean_abs": mbu["angle"],
                                                 "regret": mbu["mm"] - omm}}
                per_model.append(pm)
            cells[ctag] = cell_stats(per_model, cap)
            cells[ctag]["per_model"] = per_model
    return cells


def cell_stats(per_model, cap):
    fixed_med = {}
    for a in FIXED:
        vals = [p["fixed"][f"{a:g}"] for p in per_model]
        fixed_med[f"{a:g}"] = None if any(v is None for v in vals) else \
            float(np.median([v["regret"] for v in vals]))
    feas = {a: v for a, v in fixed_med.items() if v is not None}
    best_fixed = min(feas.values())
    by_k = {}
    for k in KS:
        row = {}
        for arm in ("uniform", "band2", "uniform_band2_bottom"):
            reg = np.array([p["k"][kkey(k)][arm]["regret"] for p in per_model])
            mm = np.array([p["k"][kkey(k)][arm]["mm"] for p in per_model])
            ang = np.array([p["k"][kkey(k)][arm]["mean_abs"] for p in per_model])
            row[arm] = {"regret_median": float(np.median(reg)), "regret_mean": float(reg.mean()),
                        "mm_median": float(np.median(mm)), "mm_sum": float(mm.sum()),
                        "mean_abs_median": float(np.median(ang)),
                        "mean_abs_mean": float(ang.mean())}
            if arm != "uniform_band2_bottom":
                med = row[arm]["regret_median"]
                row[arm]["strict_pass"] = all(med < v for v in feas.values())
                row[arm]["beaten_by"] = [a for a, v in feas.items() if v <= med]
                row[arm]["aux_pass"] = med <= best_fixed + TIE_MM
        th = [p["k"][kkey(k)]["uniform"]["theta"] for p in per_model]
        row["uniform_theta_median"] = float(np.median(th))
        row["uniform_theta_list"] = th
        by_k[kkey(k)] = row
    return {"fixed_regret_median": fixed_med, "best_fixed_regret_median": best_fixed,
            "by_k": by_k,
            "oracle_theta_list": [p["oracle_theta"] for p in per_model]}


def pareto(cells, lut, sels):
    """§1.3 교환 곡선: 고정각 곡선(0~44° 2°) 대 k 별 자동 점, 합 mm · 평균|θ| 평균."""
    grid = [float(a) for a in varangle.angle_candidates(MAX_ANGLE_DEG, ANGLE_STEP)]
    out = {}
    tie_sum = TIE_MM * len(sels)
    for lh in LAYER_HS:
        for cap in (None, BED_CAP):
            ctag = f"{lh:g}|{'cap' if cap else 'none'}"
            g = [a for a in grid if cap is None or a <= cap + 1e-9]
            per = {s["model"]: lut[(s["model"], lh)]["u"] for s in sels}
            curve_x = [float(np.mean([per[n][f"{a:g}"]["angle"] for n in per])) for a in g]
            curve_y = [float(np.sum([per[n][f"{a:g}"]["mm"] for n in per])) for a in g]
            pts = {}
            for k in KS:
                for arm in ("uniform", "band2"):
                    pms = cells[ctag]["per_model"]
                    x = float(np.mean([p["k"][kkey(k)][arm]["mean_abs"] for p in pms]))
                    y = float(np.sum([p["k"][kkey(k)][arm]["mm"] for p in pms]))
                    if x < curve_x[0] - 1e-9 or x > curve_x[-1] + 1e-9:
                        verdict, yint = "범위 밖", None
                    else:
                        yint = float(np.interp(x, curve_x, curve_y))
                        verdict = "자동 승" if y < yint - tie_sum else \
                            ("자동 패" if y > yint + tie_sum else "무승부")
                    dominated = [a for a, cx, cy in zip(g, curve_x, curve_y, strict=True)
                                 if cx <= x + 1e-9 and cy <= y + tie_sum
                                 and (cx < x - 1e-9 or cy < y - tie_sum)]
                    # 모델별: 그 모델 자신의 고정각 곡선 보간과 비교 (0.5 mm)
                    w = d = lo = 0
                    for p in pms:
                        xs = [per[p["model"]][f"{a:g}"]["angle"] for a in g]
                        ys = [per[p["model"]][f"{a:g}"]["mm"] for a in g]
                        px, py = p["k"][kkey(k)][arm]["mean_abs"], p["k"][kkey(k)][arm]["mm"]
                        yi = float(np.interp(px, xs, ys))
                        if py < yi - TIE_MM:
                            w += 1
                        elif py > yi + TIE_MM:
                            lo += 1
                        else:
                            d += 1
                    pts[f"{arm}|{kkey(k)}"] = {"x": x, "y": y, "y_fixed_interp": yint,
                                               "verdict": verdict,
                                               "dominated_by_fixed": dominated,
                                               "per_model_win_tie_loss": [w, d, lo]}
            out[ctag] = {"fixed_theta": g, "fixed_x": curve_x, "fixed_y": curve_y,
                         "auto": pts, "tie_sum_mm": tie_sum}
    return out


def sensitivity_summary(sels, lut, cells):
    out = {}
    for lh in LAYER_HS:
        for cap in (None, BED_CAP):
            ctag = f"{lh:g}|{'cap' if cap else 'none'}"
            omm = {p["model"]: p["oracle_mm"] for p in cells[ctag]["per_model"]}
            res = {}
            for kind, grid in (("C", KC), ("rel", KREL)):
                for kv in grid:
                    th, reg = [], []
                    for sel in sels:
                        t = sensitivity_select(sel)[kind][f"{kv:g}|{'cap' if cap else 'none'}"]
                        mm = lut[(sel["model"], lh)]["u"][f"{t:g}"]["mm"]
                        th.append(t)
                        reg.append(mm - omm[sel["model"]])
                    res[f"{kind}|{kv:g}"] = {"theta_median": float(np.median(th)),
                                             "regret_median": float(np.median(reg)),
                                             "thetas": th}
            out[ctag] = res
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--json", default="k_sweep_results.json")
    args = ap.parse_args()
    t0 = time.perf_counter()
    with open(T1_JSON) as fh:
        t1 = json.load(fh)
    t1_rows = t1["rows"]
    n = len(all_specs())
    with Pool(args.jobs) as pool:
        sels = []
        for s in pool.imap(run_select, range(n)):
            sels.append(s)
            print(f"  선택 끝: {s['model']} ({s['seconds']:.0f}s)", flush=True)
        # k = 0.2 의 선택이 T1 과 같은지 (사전 등록 §1.0 확인)
        t1_by = {(r["model"], r["layer_height"]): r for r in t1_rows}
        mism = []
        for s in sels:
            r = t1_by[(s["model"], 0.3)]
            q = s["sel"]["0.2"]
            if (q["uniform"], q["band2"], q["cap_uniform"], q["cap_band2"]) != \
                    (r["auto_uniform"], r["auto_band2"], r["cap_uniform"], r["cap_band2"]):
                mism.append((s["model"], q, [r["auto_uniform"], r["auto_band2"],
                                             r["cap_uniform"], r["cap_band2"]]))
        print(f"k=0.2 선택이 T1 과 다른 모델: {len(mism)}", mism[:3])
        lut0 = t1_lookup(t1_rows)
        tasks = []
        for s in sels:
            us, bs = needed_angles(s)
            for lh in LAYER_HS:
                e = lut0[(s["model"], lh)]
                tu = sorted(a for a in us if f"{a:g}" not in e["u"])
                tb = sorted(ts for ts in bs if ts not in e["b"])
                if tu or tb:
                    tasks.append((s["idx"], lh, tu, tb))
        n_meas = sum(len(t[2]) + len(t[3]) for t in tasks)
        print(f"새로 잴 측정: {n_meas} (작업 {len(tasks)})", flush=True)
        meas = {}
        for name, lh, out in pool.imap_unordered(run_measure, tasks):
            meas[(name, lh)] = out
            print(f"  측정 끝: {name} 층고 {lh:g} ({len(out)})", flush=True)
    lut = build_tables(sels, t1_rows, meas)
    cells = summarize(sels, t1_rows, lut)
    par = pareto(cells, lut, sels)
    sens = sensitivity_summary(sels, lut, cells)
    report(cells, par, sens)
    elapsed = time.perf_counter() - t0
    with open(args.json, "w") as fh:
        json.dump({"cells": cells, "pareto": par, "sensitivity_posthoc": sens,
                   "selections": [{k: v for k, v in s.items()} for s in sels],
                   "k0_2_mismatch_vs_t1": mism,
                   "meta": {"ks": KS, "fixed_deg": FIXED, "layer_heights": LAYER_HS,
                            "bed_cap_deg": BED_CAP, "tie_mm": TIE_MM, "k_blend": BLEND_COST_K,
                            "grid_deg": ANGLE_STEP, "max_angle_deg": MAX_ANGLE_DEG,
                            "kc_grid": KC, "krel_grid": KREL, "new_measurements": n_meas,
                            "elapsed_s": elapsed, "prereg": "docs/test_k_sweep.md §1"}},
                  fh, ensure_ascii=False, indent=1)
    print(f"저장: {args.json} ({elapsed / 60:.1f} 분)")


def report(cells, par, sens):
    for ctag, c in cells.items():
        print(f"\n━━ {ctag} ━━ 고정각 후회 중앙: "
              + ", ".join(f"{a}°={'—' if v is None else f'{v:.1f}'}"
                          for a, v in c["fixed_regret_median"].items()))
        print(f"{'k':>6} {'균일θ중앙':>9} {'균일후회':>8} {'엄격':>4} {'보조':>4} "
              f"{'밴드2후회':>9} {'엄격':>4} {'아랫각균일':>9}  파레토(균일/밴드2)")
        for k in KS:
            r = c["by_k"][kkey(k)]
            pu = par[ctag]["auto"][f"uniform|{kkey(k)}"]
            pb = par[ctag]["auto"][f"band2|{kkey(k)}"]
            print(f"{k:>6g} {r['uniform_theta_median']:>9.0f} "
                  f"{r['uniform']['regret_median']:>8.1f} {'O' if r['uniform']['strict_pass'] else 'X':>4} "
                  f"{'O' if r['uniform']['aux_pass'] else 'X':>4} "
                  f"{r['band2']['regret_median']:>9.1f} {'O' if r['band2']['strict_pass'] else 'X':>4} "
                  f"{r['uniform_band2_bottom']['regret_median']:>9.1f}  "
                  f"{pu['verdict']} {pu['per_model_win_tie_loss']} / "
                  f"{pb['verdict']} {pb['per_model_win_tie_loss']}")
    print("\n[사후 민감도, 판정 밖]")
    for ctag, r in sens.items():
        print(ctag, {k: (v["theta_median"], round(v["regret_median"], 1)) for k, v in r.items()})


if __name__ == "__main__":
    sys.exit(main())
