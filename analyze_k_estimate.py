"""analyze_k_estimate.py — k 를 데이터에서 추정하고, 신뢰구간·표본 밖 검증으로 믿을 만한지 판정한다.

사전 등록: `docs/test_k_estimate.md` §1. 앞 시험 `analyze_k_sweep.py` 의 캐시(`k_sweep_cache/`)와
`t1_conventional_results.json` 을 재사용하고, 고른 각 중 아직 안 잰 것만 잰다.

    python3 analyze_k_estimate.py --jobs 4
"""

import argparse
import json
import sys
import time
from multiprocessing import Pool

import numpy as np

import conical.varangle as varangle
from analyze_gap_sample import BED_CAP, measure, profile_from
from analyze_k_sweep import (
    KS,
    T1_JSON,
    _cache_path,
    _cached,
    capped_table,
    run_measure,
    run_select,
    select_capped_k,
    signed_grid,
    t1_lookup,
)
from analyze_t1_conventional import FIXED, LAYER_HS, TIE_MM, all_specs, model_context
from conical.config import MAX_SPACING_FACTOR

KGRID = np.round(np.arange(0.005, 0.5 + 1e-9, 0.005), 3)
B = 2000
B_FOLD = 500
LAMBDAS = (0.0, 1.0, 2.0, 5.0, 10.0, 20.0)
CELLS = [(lh, cap) for lh in LAYER_HS for cap in ("none", "cap")]
S3_KSTAR = {"ring": 0.1635, "topopt_new4": 0.0965, "armadillo4": 0.1527}


def family(name):
    if name == "구":
        return "구"
    if name.startswith("허리 r="):
        return "허리 r"
    if "로브" in name:
        return "허리3 로브"
    if name.startswith("허리3"):
        return "허리3 배율"
    return "데모"


def choose_uniform(S, k, cap):
    """J(θ) = ΔS(θ) − k|θ| 최대 (부호 있는 2° 격자). 동점(1e-9)은 |θ| 작은 쪽, 그다음 outward."""
    s0 = S["0"]
    best = None
    for t in signed_grid():
        if cap and abs(t) > BED_CAP + 1e-9:
            continue
        j = (s0 - S[f"{t:g}"]) - k * abs(t)
        key = (round(j, 9), -abs(t), t >= 0)
        if best is None or key > best[0]:
            best = (key, t)
    return best[1] + 0.0


def verify_against_selector(sels):
    """사전 등록 §1.1 확인: k 스윕의 0 아닌 k 에서 실제 선택기와 같은가."""
    bad = []
    for s in sels:
        for k in KS:
            if k == 0:
                continue
            q = s["sel"][f"{k:g}"]
            a, b = choose_uniform(s["S"], k, False), choose_uniform(s["S"], k, True)
            if a != q["uniform"] or b != q["cap_uniform"]:
                bad.append({"model": s["model"], "k": k, "ours": [a, b],
                            "selector": [q["uniform"], q["cap_uniform"]]})
    return bad


def band_job(args):
    """k̂ 에서 밴드2 확인용 선택 (모델 하나)."""
    idx, k = args
    def work():
        name, build = all_specs()[idx]
        mesh = build()
        rp, r_max = model_context(mesh)
        sb = varangle.select_banded_j(mesh, k, 2, r_max, rp, MAX_SPACING_FACTOR)
        uni, pairs, profs, _ = capped_table(mesh, rp, r_max, BED_CAP)
        _cu, cb, _rej = select_capped_k(uni, pairs, profs, rp, k, {})
        return {"model": name, "idx": idx, "band2": [float(t) + 0.0 for t in sb["thetas"]],
                "cap_band2": [float(t) + 0.0 for t in cb]}
    return _cached(_cache_path("est_band", idx, f"{k:g}"), work)


def band_measure(args):
    idx, lh, ts = args
    def work():
        name, build = all_specs()[idx]
        mesh = build()
        rp, r_max = model_context(mesh)
        return measure(mesh, profile_from(mesh, list(ts), rp, r_max), lh)
    key = "b" + ",".join(f"{t:g}" for t in ts)
    return idx, lh, tuple(ts), _cached(_cache_path("m", idx, f"{lh:g}", key), work)


# ─────────────────────────────────────────────────────────────
# 행렬 만들기: R[cell] = (모델 × k) 후회, TH = 평균|θ|
# ─────────────────────────────────────────────────────────────
def build_matrices(sels, lut, choice):
    names = [s["model"] for s in sels]
    R, TH, F, ORA = {}, {}, {}, {}
    for lh, cap in CELLS:
        tag = f"{lh:g}|{cap}"
        r = np.zeros((len(sels), len(KGRID)))
        th = np.zeros_like(r)
        fx = {}
        ora = []
        for i, s in enumerate(sels):
            u = lut[(s["model"], lh)]["u"]
            pool = set(u.keys()) & POOL[s["model"]]
            best = None
            for key in pool:
                a = float(key)
                if cap == "cap" and abs(a) > BED_CAP + 1e-9:
                    continue
                mm = u[key]["mm"]
                if best is None or mm < best[1] - 1e-6 or \
                        (abs(mm - best[1]) <= 1e-6 and abs(a) < abs(best[0])):
                    best = (a, mm)
            ora.append(best)
            for j, k in enumerate(KGRID):
                t = choice[(s["model"], float(k), cap)]
                r[i, j] = u[f"{t:g}"]["mm"] - best[1]
                th[i, j] = abs(t)
            for a in FIXED:
                if cap == "cap" and a > BED_CAP:
                    continue
                fx.setdefault(f"{a:g}", []).append(u[f"{a:g}"]["mm"] - best[1])
        R[tag], TH[tag] = r, th
        F[tag] = {a: np.array(v) for a, v in fx.items()}
        ORA[tag] = ora
    return names, R, TH, F, ORA


POOL = {}


def loss(R, idx, cells=None, TH=None, lam=0.0):
    cells = cells or list(R)
    out = np.zeros(len(KGRID))
    for c in cells:
        m = R[c][idx]
        if lam:
            m = m + lam * TH[c][idx]
        out += np.median(m, axis=0)
    return out


def k_min(L):
    m = L.min()
    j = np.where(L <= m + 1e-9)[0].max()          # 동점이면 큰 k
    return j


def k_1se(L, se):
    return np.where(L <= L.min() + se)[0].max()


def estimate(R, idx, cells, rng, b):
    """k̂_min, k̂_1SE (+ SE) for 모델 부분집합 idx."""
    L = loss(R, idx, cells)
    jm = k_min(L)
    Lb = np.array([loss(R, rng.choice(idx, len(idx)), cells)[jm] for _ in range(b)])
    se = float(Lb.std(ddof=1))
    return jm, k_1se(L, se), se, L


def bootstrap(R, n, cells, rng, groups=None):
    km, k1 = [], []
    for _ in range(B):
        if groups is None:
            idx = rng.choice(n, n)
        else:
            gs = rng.choice(len(groups), len(groups))
            idx = np.concatenate([groups[g] for g in gs])
        L = loss(R, idx, cells)
        jm = k_min(L)
        # 1SE 의 SE 는 부트스트랩 안에서 다시 부트스트랩하지 않는다(비용) — 전체 표본 SE 를 쓴다
        km.append(KGRID[jm])
        k1.append(KGRID[k_1se(L, SE_FULL[tuple(cells)])])
    return np.array(km), np.array(k1)


SE_FULL = {}


def ci(x):
    return [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--json", default="k_estimate_results.json")
    args = ap.parse_args()
    t0 = time.perf_counter()
    with open(T1_JSON) as fh:
        t1_rows = json.load(fh)["rows"]
    n = len(all_specs())
    with Pool(args.jobs) as pool:
        sels = list(pool.imap(run_select, range(n)))           # 캐시에서 읽힌다
    mism = verify_against_selector(sels)
    print(f"선택기 재현 확인: 다른 경우 {len(mism)}", mism[:3])

    choice = {}
    for s in sels:
        for k in KGRID:
            for cap in ("none", "cap"):
                choice[(s["model"], float(k), cap)] = choose_uniform(s["S"], float(k), cap == "cap")
    # 정답지 후보 = T1 후보 ∪ k 스윕에서 고른 균일각 ∪ 여기서 고른 균일각
    by_t1 = {(r["model"], r["layer_height"]): r for r in t1_rows}
    for s in sels:
        p = set(by_t1[(s["model"], 0.3)]["uniform"].keys())
        for q in s["sel"].values():
            p |= {f"{q['uniform']:g}", f"{q['cap_uniform']:g}", f"{q['band2'][0]:g}",
                  f"{q['cap_band2'][0]:g}"}
        p |= {f"{choice[(s['model'], float(k), c)]:g}" for k in KGRID for c in ("none", "cap")}
        POOL[s["model"]] = p

    # 측정 테이블 (T1 + k 스윕 캐시 + 새로 필요한 것)
    lut = t1_lookup(t1_rows)
    tasks = []
    for s in sels:
        for lh in LAYER_HS:
            u = lut[(s["model"], lh)]["u"]
            need = sorted(float(a) for a in POOL[s["model"]] if a not in u)
            tasks.append((s["idx"], lh, need, []))
    n_new = sum(len(t[2]) for t in tasks)
    print(f"측정(캐시 포함) 대상: {n_new}", flush=True)
    with Pool(args.jobs) as pool:
        for name, lh, out in pool.imap_unordered(run_measure, tasks):
            lut[(name, lh)]["u"].update(out)

    names, R, TH, F, ORA = build_matrices(sels, lut, choice)
    fam = [family(m) for m in names]
    fams = sorted(set(fam))
    groups = [np.array([i for i, f in enumerate(fam) if f == g]) for g in fams]
    rng = np.random.default_rng(0)
    allidx = np.arange(len(names))
    cellsets = {"all": list(R), "0.3": ["0.3|none", "0.3|cap"], "0.4": ["0.4|none", "0.4|cap"]}

    est = {}
    for key, cells in cellsets.items():
        jm, j1, se, L = estimate(R, allidx, cells, rng, B)
        SE_FULL[tuple(cells)] = se
        km_b, k1_b = bootstrap(R, len(names), cells, rng)
        kmf_b, k1f_b = bootstrap(R, len(names), cells, rng, groups)
        est[key] = {"k_min": float(KGRID[jm]), "k_1se": float(KGRID[j1]), "se": se,
                    "L": L.tolist(), "L_min": float(L[jm]), "L_at_0.2": float(L[KGRID.tolist().index(0.2)]),
                    "boot_model": {"k_min_ci": ci(km_b), "k_1se_ci": ci(k1_b),
                                   "k_1se_median": float(np.median(k1_b)),
                                   "k_1se_hist": np.histogram(k1_b, bins=np.arange(0, 0.5075, 0.01))[0].tolist()},
                    "boot_family": {"k_min_ci": ci(kmf_b), "k_1se_ci": ci(k1f_b),
                                    "k_1se_median": float(np.median(k1f_b)),
                                    "k_1se_hist": np.histogram(k1f_b, bins=np.arange(0, 0.5075, 0.01))[0].tolist()},
                    "per_cell_median_regret_at_k1se": {c: float(np.median(R[c][:, j1])) for c in cells},
                    "per_cell_median_regret_at_kmin": {c: float(np.median(R[c][:, jm])) for c in cells}}
        print(f"[{key}] k̂_min {KGRID[jm]:.3f}  k̂_1SE {KGRID[j1]:.3f} (SE {se:.2f} mm)  "
              f"모델 부트 95%: min {ci(km_b)} 1SE {ci(k1_b)}  가족 부트: 1SE {ci(k1f_b)}", flush=True)

    # 표본 밖: 가족 제외(LOFO), 모델 제외(LOO)
    def cv(folds, tag):
        held = {c: np.full(len(names), np.nan) for c in R}
        ks = []
        for test in folds:
            train = np.setdiff1d(allidx, test)
            _jm, j1, _se, _L = estimate(R, train, list(R), rng, B_FOLD)
            ks.append(float(KGRID[j1]))
            for c in R:
                held[c][test] = R[c][test, j1]
        res = {"k_per_fold": ks, "cells": {}}
        for c in R:
            fixed = {a: float(np.median(v)) for a, v in F[c].items()}
            best = min(fixed.values())
            med = float(np.median(held[c]))
            res["cells"][c] = {"held_out_regret_median": med, "fixed_regret_median": fixed,
                               "k0.2_regret_median": float(np.median(R[c][:, KGRID.tolist().index(0.2)])),
                               "strict": all(med < v for v in fixed.values()),
                               "aux": med <= best + TIE_MM}
        print(f"[{tag}] 겹별 k̂: {ks}")
        for c, v in res["cells"].items():
            print(f"   {c}: held-out {v['held_out_regret_median']:.1f}  고정 {v['fixed_regret_median']}  "
                  f"k0.2 {v['k0.2_regret_median']:.1f}  엄격 {v['strict']} 보조 {v['aux']}")
        return res

    lofo = cv(groups, "LOFO")
    loo = cv([np.array([i]) for i in allidx], "LOO")

    # 판정 (사전 등록 §1.4)
    e = est["all"]
    lo, hi = e["boot_model"]["k_1se_ci"]
    R1 = hi - lo <= 0.10 + 1e-9
    R2 = all(lo - 1e-9 <= k <= hi + 1e-9 for k in lofo["k_per_fold"])
    R3 = all(v["aux"] for v in lofo["cells"].values())
    R3s = all(v["strict"] for v in lofo["cells"].values())
    a03, a04 = est["0.3"]["boot_model"]["k_1se_ci"], est["0.4"]["boot_model"]["k_1se_ci"]
    lh_dep = a03[1] < a04[0] or a04[1] < a03[0]
    verdict = {"k_1se": e["k_1se"], "ci95_model": [lo, hi], "R1_precision": R1, "R2_stability": R2,
               "R3_out_of_sample_aux": R3, "R3_out_of_sample_strict": R3s,
               "layer_height_dependent": lh_dep, "k0.2_outside_ci": not (lo <= 0.2 <= hi),
               "reliable": R1 and R2 and R3}
    print("판정:", verdict)

    # 비용 포함 k̂(λ) — 판정 밖
    lam = {}
    for lv in LAMBDAS:
        L = loss(R, allidx, list(R), TH, lv)
        lam[f"{lv:g}"] = float(KGRID[k_min(L)])
    print("k̂(λ):", lam)

    # 밴드2 확인 — k̂_1SE 에서 실제 선택기 (판정 밖)
    kb = e["k_1se"]
    with Pool(args.jobs) as pool:
        bands = list(pool.imap(band_job, [(i, kb) for i in range(n)]))
        mt = []
        for b in bands:
            for lh in LAYER_HS:
                for ts in (b["band2"], b["cap_band2"]):
                    if ts[0] != ts[1] and tuple(ts) not in lut[(b["model"], lh)]["b"]:
                        mt.append((b["idx"], lh, ts))
        names_by_idx = {s["idx"]: s["model"] for s in sels}
        for idx, lh, ts, m in pool.imap_unordered(band_measure, mt):
            lut[(names_by_idx[idx], lh)]["b"][ts] = m
    band_res = {}
    for lh, cap in CELLS:
        c = f"{lh:g}|{cap}"
        regs = []
        for i, b in enumerate(bands):
            ts = b["band2"] if cap == "none" else b["cap_band2"]
            e_ = lut[(b["model"], lh)]
            m = e_["u"][f"{ts[0]:g}"] if ts[0] == ts[1] else e_["b"][tuple(ts)]
            regs.append(m["mm"] - ORA[c][i][1])
        band_res[c] = {"regret_median": float(np.median(regs)),
                       "fixed_regret_median": {a: float(np.median(v)) for a, v in F[c].items()}}
    print(f"밴드2 @ k={kb}:", {c: round(v["regret_median"], 1) for c, v in band_res.items()})

    s3 = {m: {"k_star": ks_, "leaves_zero_at_k1se": kb < ks_} for m, ks_ in S3_KSTAR.items()}
    elapsed = time.perf_counter() - t0
    with open(args.json, "w") as fh:
        json.dump({"k_grid": KGRID.tolist(), "estimates": est, "lofo": lofo, "loo": loo,
                   "verdict": verdict, "k_by_lambda_posthoc": lam, "band2_at_k1se": band_res,
                   "s3_external": s3, "selector_mismatch": mism,
                   "families": dict(zip(names, fam, strict=True)),
                   "median_regret_curves": {c: np.median(R[c], axis=0).tolist() for c in R},
                   "fixed_regret_median": {c: {a: float(np.median(v)) for a, v in F[c].items()} for c in F},
                   "meta": {"B": B, "B_fold": B_FOLD, "seed": 0, "lambdas": LAMBDAS,
                            "tie_mm": TIE_MM, "elapsed_s": elapsed,
                            "prereg": "docs/test_k_estimate.md §1"}},
                  fh, ensure_ascii=False, indent=1)
    print(f"저장: {args.json} ({elapsed / 60:.1f} 분)")


if __name__ == "__main__":
    sys.exit(main())
