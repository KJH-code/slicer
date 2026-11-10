"""analyze_t1_conventional.py — T1: 관례 원뿔각 대 자동 결정.

사람들이 쓰던 고정 원뿔각(RotBot 45°, ZHAW·Slicer4RTN 3축 15~25°)이 모델마다 다른 최적각을
얼마나 놓치고, 자동 결정(J 선택기)이 얼마나 되찾는가. 사전 등록: `docs/test_t1_t4.md` §1.1.

팔: 고정 15·20·25·45° / 자동 균일(J) / 자동 밴드2 / 균일(밴드2 아랫각) / 사후 최적 균일(정답지).
지표: 툴패스 검사기 A(낙관) 미지지 mm, 평균|θ|, 후회 = 팔 mm − 사후 최적 mm.
베드 상한(22.79°) 유무 두 판. 측정 경로는 `analyze_gap_sample.measure` 그대로.

    python3 analyze_t1_conventional.py --jobs 4          # 약 40 분 (4 코어)
"""

import argparse
import json
import sys
import time
from multiprocessing import Pool

import numpy as np

import conical.varangle as varangle
from analyze_blend_ratio import build_specs
from analyze_gap_sample import BED_CAP, measure, select_capped
from compare_ceiling import demo_models
from conical.analytic import support_fraction
from conical.config import (
    ANGLE_STEP,
    DEFAULT_K,
    MAX_ANGLE_DEG,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.meshio import RadiusProfile, center_on_axis
from conical.profile import AngleProfile
from conical.rep5x import bed_safe_profile

FIXED = (15.0, 20.0, 25.0, 45.0)
LAYER_HS = (0.3, 0.4)
TIE_MM = 0.5
SPOT_NEG = -20.0
DEMO = ("sphere", "funnel", "torus", "mushroom")


def all_specs():
    """표본 21개: 17 모델 + 데모 4개. (이름, 빌더) — 워커에서 인덱스로 다시 만든다."""
    specs = list(build_specs(asym=True))
    for name in DEMO:
        specs.append((name, (lambda n: lambda: center_on_axis(demo_models()[n].copy()))(name)))
    return specs


def model_context(mesh):
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    return rp, r_max


def select_auto(mesh, rp, r_max, threshold_deg=THRESHOLD_DEG):
    su = varangle.select_banded_j(mesh, DEFAULT_K, 1, r_max, rp, MAX_SPACING_FACTOR,
                                  threshold_deg=threshold_deg)
    sb = varangle.select_banded_j(mesh, DEFAULT_K, 2, r_max, rp, MAX_SPACING_FACTOR,
                                  threshold_deg=threshold_deg)
    return su, sb


def negative_allowed(mesh):
    """사전 등록한 가지치기: 어떤 음수 격자각의 해석식 서포트가 0° 보다 작으면 음수 격자를 넣는다."""
    s0 = support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    for a in varangle.angle_candidates(MAX_ANGLE_DEG, ANGLE_STEP)[1:]:
        if support_fraction(mesh, float(a), "inward", THRESHOLD_DEG) < s0 - 1e-12:
            return True
    return False


def candidates(theta_j, neg):
    grid = [float(a) for a in varangle.angle_candidates(MAX_ANGLE_DEG, ANGLE_STEP)]
    c = set(grid) | set(FIXED) | {float(theta_j)}
    if neg:
        c |= {-a for a in grid if a > 0}
    return sorted(c)


def slim(m):
    return {k: m[k] for k in ("mm", "mm_pes", "pct", "angle", "near_mm", "perimeter_mm")}


def run_model(task):
    idx, lh = task
    t0 = time.perf_counter()
    name, build = all_specs()[idx]
    mesh = build()
    rp, r_max = model_context(mesh)
    su, sb = select_auto(mesh, rp, r_max)
    tu, tb = float(su["thetas"][0]) + 0.0, [float(t) + 0.0 for t in sb["thetas"]]
    prof_b = sb["profile_obj"]
    th_cu, th_cb, prof_cb, rejected = select_capped(mesh, rp, r_max, BED_CAP)
    th_cu, th_cb = float(th_cu) + 0.0, [float(t) + 0.0 for t in th_cb]
    neg = negative_allowed(mesh)
    cands = candidates(tu, neg)
    for t in (tb[0], th_cu, th_cb[0]):
        if t not in cands:
            cands.append(float(t))
    cands = sorted(set(cands))

    uni = {}
    for a in cands:
        uni[f"{a:g}"] = slim(measure(mesh, AngleProfile.constant(a), lh))
    arms = {
        "band2": slim(measure(mesh, prof_b, lh)),
        "cap_band2": slim(measure(mesh, prof_cb, lh)),
    }
    ramps = {}
    for a in (25.0, 45.0):
        rprof, info = bed_safe_profile(AngleProfile.constant(a), rp, lh)
        ramps[f"{a:g}"] = dict(slim(measure(mesh, rprof, lh)),
                               theta_bed=float(info["theta_bed"]),
                               changed=bool(info["changed"]))
    spot = None
    if lh == 0.4 and f"{SPOT_NEG:g}" not in uni:
        spot = slim(measure(mesh, AngleProfile.constant(SPOT_NEG), lh))
    return {"model": name, "layer_height": lh,
            "auto_uniform": tu, "auto_band2": tb,
            "auto_band2_blend": [[round(a, 2), round(b, 2)] for a, b in prof_b.blend_intervals()],
            "cap_uniform": float(th_cu), "cap_band2": [float(t) for t in th_cb],
            "cap_band2_rejected_by_bed": rejected,
            "negative_in_oracle": neg, "uniform": uni, "arms": arms,
            "ramps": ramps, "spot_neg20": spot,
            "seconds": time.perf_counter() - t0}


# ─────────────────────────────────────────────────────────────
# 집계
# ─────────────────────────────────────────────────────────────
def oracle(row, cap):
    best = None
    for k, m in row["uniform"].items():
        a = float(k)
        if cap is not None and abs(a) > cap + 1e-9:
            continue
        key = (m["mm"], abs(a))
        if best is None or m["mm"] < best[0][0] - 1e-6 or \
                (abs(m["mm"] - best[0][0]) <= 1e-6 and abs(a) < best[0][1]):
            best = (key, a)
    return best[1], row["uniform"][f"{best[1]:g}"]["mm"]


def arm_values(row, cap):
    """판 하나에서 팔별 (mm, 평균|θ|, 각도 표기). 실현 불가는 None."""
    u = row["uniform"]
    out = {}
    for a in FIXED:
        if cap is not None and a > cap + 1e-9:
            out[f"fixed{a:g}"] = None
        else:
            m = u[f"{a:g}"]
            out[f"fixed{a:g}"] = (m["mm"], m["angle"], f"{a:g}")
    if cap is None:
        m = u[f"{row['auto_uniform']:g}"]
        out["auto_uniform"] = (m["mm"], m["angle"], f"{row['auto_uniform']:g}")
        b = row["arms"]["band2"]
        out["auto_band2"] = (b["mm"], b["angle"], fmt(row["auto_band2"]))
        m = u[f"{row['auto_band2'][0]:g}"]
        out["uniform_band2_bottom"] = (m["mm"], m["angle"], f"{row['auto_band2'][0]:g}")
    else:
        m = u[f"{row['cap_uniform']:g}"]
        out["auto_uniform"] = (m["mm"], m["angle"], f"{row['cap_uniform']:g}")
        b = row["arms"]["cap_band2"]
        out["auto_band2"] = (b["mm"], b["angle"], fmt(row["cap_band2"]))
        m = u[f"{row['cap_band2'][0]:g}"]
        out["uniform_band2_bottom"] = (m["mm"], m["angle"], f"{row['cap_band2'][0]:g}")
    oa, omm = oracle(row, cap)
    out["oracle"] = (omm, abs(oa), f"{oa:g}")
    return out


def fmt(ts):
    return "[" + ",".join(f"{t:g}" for t in ts) + "]"


ARM_ORDER = ("fixed15", "fixed20", "fixed25", "fixed45", "auto_uniform", "auto_band2",
             "uniform_band2_bottom", "oracle")
ARM_LABEL = {"fixed15": "고정15", "fixed20": "고정20", "fixed25": "고정25", "fixed45": "고정45",
             "auto_uniform": "자동균일J", "auto_band2": "자동밴드2",
             "uniform_band2_bottom": "균일(아랫각)", "oracle": "사후최적"}


def summarize(rows, cap):
    per_model = []
    for r in rows:
        av = arm_values(r, cap)
        omm = av["oracle"][0]
        per_model.append({"model": r["model"],
                          "arms": {k: (None if v is None else
                                       {"mm": v[0], "mean_abs_theta": v[1], "theta": v[2],
                                        "regret_mm": v[0] - omm})
                                   for k, v in av.items()}})
    stats = {}
    for k in ARM_ORDER:
        vals = [p["arms"][k] for p in per_model]
        if any(v is None for v in vals):
            stats[k] = {"feasible": False}
            continue
        reg = np.array([v["regret_mm"] for v in vals])
        stats[k] = {"feasible": True,
                    "regret_median": float(np.median(reg)),
                    "regret_mean": float(reg.mean()),
                    "regret_max": float(reg.max()),
                    "n_regret_le_tie": int((reg <= TIE_MM).sum()),
                    "mm_median": float(np.median([v["mm"] for v in vals])),
                    "mean_abs_theta_median": float(np.median([v["mean_abs_theta"]
                                                              for v in vals]))}
    fixed_ok = [k for k in ("fixed15", "fixed20", "fixed25", "fixed45")
                if stats[k]["feasible"]]
    crit = {}
    for auto in ("auto_uniform", "auto_band2"):
        a = stats[auto]["regret_median"]
        beaten_by = [k for k in fixed_ok if stats[k]["regret_median"] <= a]
        crit[auto] = {"pass": not beaten_by, "fixed_equal_or_better": beaten_by}
    # 보조: 파레토 비지배 — 자동 균일이 고정각 대비 mm(0.5 무승부)·평균|θ| 둘 다 같거나 나은 모델 수
    pareto = {}
    for auto in ("auto_uniform", "auto_band2"):
        pareto[auto] = {}
        for k in fixed_ok:
            n_nd, n_dom = 0, 0
            for p in per_model:
                A, F = p["arms"][auto], p["arms"][k]
                mm_ok = A["mm"] <= F["mm"] + TIE_MM
                th_ok = A["mean_abs_theta"] <= F["mean_abs_theta"] + 1e-9
                n_nd += mm_ok and th_ok
                n_dom += (F["mm"] <= A["mm"] + TIE_MM and
                          F["mean_abs_theta"] <= A["mean_abs_theta"] + 1e-9 and
                          not (mm_ok and th_ok))
            pareto[auto][k] = {"auto_no_worse_both": n_nd, "fixed_strictly_dominates": n_dom}
    oracle_angles = [float(p["arms"]["oracle"]["theta"]) for p in per_model]
    return {"per_model": per_model, "stats": stats, "criterion": crit, "pareto": pareto,
            "oracle_angles": oracle_angles}


def print_summary(lh, cap, s):
    tag = "상한 없음" if cap is None else f"베드 상한 {cap:g}°"
    print(f"\n━━ 층고 {lh:g}mm · {tag} ━━  (mm / 후회)")
    head = f"{'모델':<14}" + "".join(f"{ARM_LABEL[k]:>16}" for k in ARM_ORDER)
    print(head)
    for p in s["per_model"]:
        line = f"{p['model']:<14}"
        for k in ARM_ORDER:
            v = p["arms"][k]
            line += f"{'실현불가':>16}" if v is None else \
                f"{v['theta']:>7}{v['mm']:>5.0f}/{v['regret_mm']:<3.0f}"
        print(line)
    print(f"{'후회 중앙값':<14}" + "".join(
        f"{'—':>16}" if not s['stats'][k]['feasible'] else
        f"{s['stats'][k]['regret_median']:>16.1f}" for k in ARM_ORDER))
    print(f"{'평균|θ| 중앙':<14}" + "".join(
        f"{'—':>16}" if not s['stats'][k]['feasible'] else
        f"{s['stats'][k]['mean_abs_theta_median']:>16.1f}" for k in ARM_ORDER))
    for auto, c in s["criterion"].items():
        print(f"  기준[{auto}]: {'통과' if c['pass'] else '불통과'}"
              + ("" if c["pass"] else f" — 같거나 나은 고정각: {c['fixed_equal_or_better']}"))
    print(f"  사후 최적 각 분포: {sorted(s['oracle_angles'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--models", type=int, nargs="*", default=None,
                    help="모델 인덱스만 (디버그용)")
    ap.add_argument("--json", default="t1_conventional_results.json")
    args = ap.parse_args()

    specs = all_specs()
    idxs = args.models if args.models else list(range(len(specs)))
    tasks = [(i, lh) for i in idxs for lh in LAYER_HS]
    t0 = time.perf_counter()
    rows = []
    with Pool(args.jobs) as pool:
        for r in pool.imap_unordered(run_model, tasks):
            rows.append(r)
            print(f"  끝: {r['model']} 층고 {r['layer_height']:g} "
                  f"({r['seconds']:.0f}s, 후보 {len(r['uniform'])})", flush=True)
    order = {name: i for i, (name, _) in enumerate(specs)}
    rows.sort(key=lambda r: (r["layer_height"], order[r["model"]]))

    summary = {}
    for lh in LAYER_HS:
        sub = [r for r in rows if r["layer_height"] == lh]
        for cap in (None, BED_CAP):
            s = summarize(sub, cap)
            summary[f"{lh:g}|{'none' if cap is None else 'cap'}"] = s
            print_summary(lh, cap, s)
    passed_all = {a: all(summary[k]["criterion"][a]["pass"] for k in summary)
                  for a in ("auto_uniform", "auto_band2")}
    print(f"\n사전 기준(4 셀 모두): {passed_all}")
    spots = [(r["model"], r["spot_neg20"]["mm"], r["uniform"]["0"]["mm"])
             for r in rows if r["spot_neg20"]]
    print("가지치기 확인 (층고 0.4, −20° mm 대 0° mm):",
          ", ".join(f"{m} {a:.0f}/{b:.0f}" for m, a, b in spots))
    elapsed = time.perf_counter() - t0
    print(f"실행 시간 {elapsed / 60:.1f} 분")
    with open(args.json, "w") as fh:
        json.dump({"rows": rows, "summary": summary, "criterion_all_cells": passed_all,
                   "meta": {"fixed_deg": FIXED, "layer_heights": LAYER_HS,
                            "bed_cap_deg": BED_CAP, "tie_mm": TIE_MM,
                            "k": DEFAULT_K, "grid_deg": ANGLE_STEP,
                            "max_angle_deg": MAX_ANGLE_DEG,
                            "elapsed_s": elapsed, "jobs": args.jobs,
                            "prereg": "docs/test_t1_t4.md §1.1"}},
                  fh, ensure_ascii=False, indent=1)
    print(f"저장: {args.json}")


if __name__ == "__main__":
    sys.exit(main())
