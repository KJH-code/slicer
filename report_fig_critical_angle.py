"""report_fig_critical_angle.py — 면별 임계각 θ* 분포와 고른 각도 (보고서 그림 A).

사전 등록: `docs/test_report_figs_acefg.md` §1.1.

1. 재현 확인: `critical_angle_hist` (happy-ptolemy `tools/report_figs/critical_angle_hist.py`) 의
   모델별 면적 몫 need0 · in44 · beyond44 · never 를 같은 알고리즘(아래 두 함수는 그 스크립트에서
   그대로 옮김)과 지금 코드로 다시 계산해, 그 브랜치 manifest 값과 비교한다.
2. 21 모델(T1 표본): 0° 에서 서포트가 필요한 면의 부호 있는 θ* (outward +, inward −, 작은 쪽) 의
   면적 분포를 높이 밴드(2 등분, 선택기와 같은 `assign_height_bands`)별로, 그리고 고른 각도
   (`t1_conventional_results.json`: 자동 균일·밴드2·상한 균일·상한 밴드2) 와 정확 균일각.
3. 판정: θ_J > 0 인 모델마다 [θ_J − 2°, θ_J] 안에 (같은 방향) 면적 > 0 인 θ* 가 있는가.

    python3 report_fig_critical_angle.py
"""

import argparse
import json
import subprocess

import numpy as np
import trimesh

import conical.varangle as varangle
from analyze_t1_conventional import all_specs
from compare_ceiling import demo_models
from conical import analytic
from conical.config import ANGLE_STEP, DEFAULT_K, MAX_ANGLE_DEG
from conical.exact_angle import select_uniform_exact
from conical.meshio import center_on_axis

BED_CAP = 22.79
OLD_BRANCH = "origin/claude/happy-ptolemy-v6vsmp"
BINS = np.arange(-MAX_ANGLE_DEG, MAX_ANGLE_DEG + 1e-9, 1.0)


# ── happy-ptolemy critical_angle_hist.py 에서 그대로 옮김 ─────────────────────
def signed_theta_star(mesh, amax):
    to = analytic.critical_angle(mesh, "outward", angle_max=amax)
    ti = analytic.critical_angle(mesh, "inward", angle_max=amax)
    need = ~(to == 0.0)                          # 0° 에서 이미 지지되면 두 방향 모두 0
    o = np.where(np.isnan(to), np.inf, to)
    i = np.where(np.isnan(ti), np.inf, ti)
    s = np.where(o <= i, o, -i)
    s[~np.isfinite(o) & ~np.isfinite(i)] = np.nan
    return need, s


def solvable_beyond(mesh, faces, lo, hi=90.0, step=0.05):
    kappa = -np.sin(np.radians(45.0))
    ok = np.zeros(int(faces.sum()), dtype=bool)
    for d in ("outward", "inward"):
        for t in np.arange(lo, hi + 1e-9, step):
            g = analytic.overhang_score(mesh, float(t), d)[faces]
            ok |= g >= kappa
    return ok
# ───────────────────────────────────────────────────────────────────────────


def shares(mesh):
    A = mesh.area_faces
    tot = A.sum()
    need, s44 = signed_theta_star(mesh, float(MAX_ANGLE_DEG))
    ok = need & np.isfinite(s44)
    rest = need & ~np.isfinite(s44)
    late = np.zeros_like(rest)
    late[rest] = solvable_beyond(mesh, rest, float(MAX_ANGLE_DEG))
    return {"need0": float(A[need].sum() / tot * 100), "in44": float(A[ok].sum() / tot * 100),
            "beyond44": float(A[late].sum() / tot * 100),
            "never": float(A[rest & ~late].sum() / tot * 100)}


def recheck_old():
    try:
        old = json.loads(subprocess.check_output(
            ["git", "show", f"{OLD_BRANCH}:docs/report/figures/manifest.json"], text=True))
    except Exception as e:                       # 브랜치를 못 읽으면 비교 없이 값만 남긴다
        old, err = [], str(e)
    else:
        err = None
    old = next((e for e in old if e.get("slug") == "critical_angle_hist"), {}).get("numbers", {})
    d = demo_models()
    ms = {k: d[k] for k in ("sphere", "funnel", "torus", "mushroom")}
    ms["lamp"] = trimesh.load("examples/lamp.stl", force="mesh")
    out = {}
    for k, m in ms.items():
        new = shares(center_on_axis(m.copy()))
        diff = {q: (new[q] - old[k][q]) if k in old else None for q in new}
        out[k] = {"new": new, "old": old.get(k), "diff": diff,
                  "match_0p1": all(v is not None and abs(v) <= 0.1 for v in diff.values())}
    return out, err


def model_row(name, mesh, sel):
    A = mesh.area_faces
    tot = A.sum()
    need, s = signed_theta_star(mesh, float(MAX_ANGLE_DEG))
    labels, edges = varangle.assign_height_bands(mesh, 2)
    ok = need & np.isfinite(s)
    hist = {}
    for b in (0, 1):
        m = ok & (labels == b)
        h, _ = np.histogram(s[m], bins=BINS, weights=A[m] / tot * 100)
        hist[str(b)] = h.tolist()
    unsolved = need & ~np.isfinite(s)
    need_area = A[need].sum()
    over_cap = need & (~np.isfinite(s) | (np.abs(s) > BED_CAP + 1e-9))
    ex, _ = select_uniform_exact(mesh, DEFAULT_K)
    ex_t = float(ex["angle"]) if ex["direction"] == "outward" else -float(ex["angle"])
    # 판정: θ_J > 0 이면 [θ_J − 2, θ_J] 안에 같은 방향 θ* (면적 > 0)
    tj = float(sel["auto_uniform"])
    check = None
    if tj != 0:
        d = "outward" if tj > 0 else "inward"
        ts = analytic.critical_angle(mesh, d, angle_max=float(MAX_ANGLE_DEG))
        win = need & np.isfinite(ts) & (ts >= abs(tj) - ANGLE_STEP - 1e-9) & (ts <= abs(tj) + 1e-9)
        check = {"area_pct_in_window": float(A[win].sum() / tot * 100), "pass": bool(win.any()),
                 "max_theta_star_below": float(ts[need & np.isfinite(ts) & (ts <= abs(tj) + 1e-9)].max())
                 if (need & np.isfinite(ts) & (ts <= abs(tj) + 1e-9)).any() else None}
    return {"model": name, "need0_pct": float(need_area / tot * 100),
            "unsolved44_pct": float(A[unsolved].sum() / tot * 100),
            "over_cap_share_of_need0": float(A[over_cap].sum() / need_area * 100) if need_area else 0.0,
            "band_edges": [float(e) for e in edges], "hist_by_band": hist,
            "auto_uniform": tj, "auto_band2": sel["auto_band2"],
            "cap_uniform": sel["cap_uniform"], "cap_band2": sel["cap_band2"],
            "exact_uniform": ex_t, "exact_minus_grid": ex_t - tj, "why_check": check}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="report_fig_critical_angle_results.json")
    args = ap.parse_args()
    old, err = recheck_old()
    for k, v in old.items():
        print(f"[재현] {k:9s} {'일치' if v['match_0p1'] else '불일치'} "
              + " ".join(f"{q}={v['new'][q]:.2f}" for q in v["new"]))
    t1 = json.load(open("t1_conventional_results.json"))
    sel = {r["model"]: r for r in t1["rows"] if r["layer_height"] == 0.4}
    rows = []
    for name, build in all_specs():
        r = model_row(name, build(), sel[name])
        rows.append(r)
        c = r["why_check"]
        print(f"{name:14s} θJ={r['auto_uniform']:+5.1f} 정확={r['exact_uniform']:+6.2f} "
              f"밴드2={r['auto_band2']} 0°필요 {r['need0_pct']:.1f}% "
              f"상한초과몫 {r['over_cap_share_of_need0']:.0f}% "
              f"검산 {'—' if c is None else ('통과' if c['pass'] else '실패')}")
    checked = [r for r in rows if r["why_check"] is not None]
    out = {"recheck_critical_angle_hist": old, "recheck_error": err,
           "bins_deg": BINS.tolist(), "rows": rows,
           "why_criterion": {"n_checked": len(checked),
                             "n_pass": sum(r["why_check"]["pass"] for r in checked),
                             "failed": [r["model"] for r in checked if not r["why_check"]["pass"]]},
           "exact_vs_grid_within_2deg": sum(abs(r["exact_minus_grid"]) <= ANGLE_STEP + 1e-9
                                            for r in rows),
           "meta": {"bed_cap_deg": BED_CAP, "k": DEFAULT_K, "selections": "t1_conventional_results.json (층고 0.4 행)",
                    "prereg": "docs/test_report_figs_acefg.md §1.1"}}
    with open(args.json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("판정:", out["why_criterion"], "| 정확-격자 ≤2°:", out["exact_vs_grid_within_2deg"], "/ 21")
    print("저장:", args.json)


if __name__ == "__main__":
    main()
