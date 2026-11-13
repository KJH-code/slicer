"""analyze_t3_band_optimum.py — T3: 밴드 수 N 의 **전수 탐색 최선해** 곡선.

사전 등록: docs/test_t3_t5_t7.md §1.1 (결과 보기 전에 커밋). 여기 숫자·후보는 그 문서 그대로다.

J 가 고른 해가 아니라, N = 1, 2, 3 마다 (경계 후보 × 4° 각도 격자) 를 **전수**로 훑어
두 목적의 최선해를 찾는다.

  ① 서포트 최소 (해석식, `support_fraction_profile`) — 동점은 평균|θ| 작은 쪽
  ② 기준선 (a)(J 균일) 의 서포트 이하에서 평균|θ| 최소

N 밴드의 탐색 공간은 N+1 밴드의 탐색 공간에 정확히 들어간다(같은 경계 후보 집합 B 에서 뽑고,
같은 각도의 이웃 밴드는 `_merge_bands` 가 합치므로 같은 프로필이 된다). 그래서 최선값은 N 에
비증가해야 한다(증명 E(i)). 어기면 탐색 결함이다 — `--report` 가 검사한다.

N = 4 는 제한 탐색(N=3 최선해의 한 밴드를 둘로 나누는 이웃)이다. 문서 §1.1 참고.

단계 (각 단계는 모델별 JSON 을 남기고, 이미 있으면 건너뛴다 → 재개 가능)

    python3 analyze_t3_band_optimum.py [--jobs 4] [--models 0,3,20]   # 해석식 탐색
    python3 analyze_t3_band_optimum.py --measure [--jobs 4]           # 최선해 툴패스
    python3 analyze_t3_band_optimum.py --report                       # 표·그림·요약
    python3 analyze_t3_band_optimum.py --check-signs                  # 각도 부호 제한 대조
"""

import argparse
import itertools
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import conical.varangle as varangle
from analyze_blend_ratio import build_specs
from compare_ceiling import demo_models
from conical.analytic import critical_angle, radial_normal, support_fraction_profile
from conical.config import (
    BLEND_SHIFT_RATIO,
    DEFAULT_K,
    MAX_ANGLE_DEG,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.meshio import RadiusProfile, center_on_axis
from conical.profile import AngleProfile

STEP = 4                        # 각도 격자 (°)
N_FRAC = 12                     # 경계 후보: 높이 범위의 i/12
LAYER_HEIGHTS = (0.3, 0.4)
TIE_MM = 0.5                    # 툴패스 무승부 폭
SAT_MM = 0.5                    # 포화: 미지지 감소 < 0.5mm
SAT_DEG = 1.0                   # 포화: 평균|θ| 감소 < 1°
EPS = 1e-9

ROOT = Path(__file__).resolve().parent
SEARCH_DIR = ROOT / "t3_search"
MEASURE_DIR = ROOT / "t3_measure"
SUMMARY_JSON = ROOT / "t3_band_optimum_results.json"
FIG = ROOT / "t3_band_optimum.png"


# ─────────────────────────────────────────────────────────────
# 표본 (21 = 17 축대칭 + 데모 4)
# ─────────────────────────────────────────────────────────────
DEMO_NAMES = ("sphere", "funnel", "torus", "mushroom")


def model_specs():
    """[(이름, 생성함수)] — 순서가 곧 모델 번호다 (JSON 파일 이름)."""
    specs = list(build_specs(asym=True))
    for nm in DEMO_NAMES:
        specs.append((nm, (lambda n: lambda: center_on_axis(demo_models()[n]))(nm)))
    return specs


def load_model(idx):
    name, build = model_specs()[idx]
    return name, build()


# ─────────────────────────────────────────────────────────────
# 문제 하나 (모델 하나) — 프로필 생성과 빠른 평가
# ─────────────────────────────────────────────────────────────
class Problem:
    def __init__(self, mesh):
        self.mesh = mesh
        self.rp = RadiusProfile(mesh)
        self.r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        self.H = float(mesh.bounds[1][2] - mesh.bounds[0][2])
        self.shift = BLEND_SHIFT_RATIO * self.H
        fz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
        self.fz = fz
        self.nz = mesh.face_normals[:, 2]
        self.nr = radial_normal(mesh)
        self.area = mesh.area_faces
        self.total = float(self.area.sum())
        self.kappa = -np.sin(np.radians(THRESHOLD_DEG))
        self.z_lo, self.z_hi = float(fz.min()), float(fz.max())
        self._cache = {}

    # 경계 후보 B
    def boundary_candidates(self):
        span = self.z_hi - self.z_lo
        cands = [self.z_lo + span * i / N_FRAC for i in range(1, N_FRAC)]
        w = self.waist_z()
        if w is not None and all(abs(w - c) > 1e-6 for c in cands):
            cands.append(w)
        return sorted(round(c, 9) for c in cands)

    def waist_z(self):
        """허리 위치: 높이 범위 10~90% 안에서 그 높이의 최대 반경이 가장 작은 높이."""
        span = self.z_hi - self.z_lo
        zs = np.linspace(self.z_lo + 0.1 * span, self.z_lo + 0.9 * span, 161)
        rs = np.array([self.rp.max_between(z, z) for z in zs])
        return float(zs[int(np.argmin(rs))])

    # 각도 후보 A (부호 제한 — 문서 §1.1)
    def angle_candidates(self, restrict=True):
        mags = varangle.angle_candidates(MAX_ANGLE_DEG, STEP)
        signs = []
        for sgn, d in ((1, "outward"), (-1, "inward")):
            if not restrict:
                signs.append(sgn)
                continue
            th = critical_angle(self.mesh, d)
            if np.any(np.nan_to_num(th, nan=0.0) > 0):
                signs.append(sgn)
        if not signs:
            signs = [1]
        return sorted({float(s * a) for s in signs for a in mags})

    def edges(self, bounds):
        return [self.z_lo, *bounds, self.z_hi]

    def build(self, bounds, thetas):
        """선택기와 같은 경로로 프로필. 실현 불가면 None. 병합 후 밴드로 캐시."""
        bands = tuple(varangle._merge_bands(self.edges(bounds), list(thetas)))
        if bands in self._cache:
            return self._cache[bands]
        out = None
        try:
            if len(bands) == 1:
                prof = AngleProfile.constant(bands[0][2])
            else:
                prof = AngleProfile.from_bands(
                    list(bands), self.r_max, radius_profile=self.rp,
                    spacing_limit=MAX_SPACING_FACTOR, max_shift=self.shift)
            if not prof.check_spacing(self.r_max, "outward", MAX_SPACING_FACTOR,
                                      self.rp):
                out = (prof, *self.evaluate(prof))
        except ValueError:
            out = None
        self._cache[bands] = out
        return out

    def evaluate(self, prof):
        """(해석식 서포트 %, 면적가중 평균|θ|) — support_fraction_profile 과 같은 식."""
        th = np.radians(prof.theta_at(self.fz))
        g = self.nz * np.cos(th) + self.nr * np.sin(th)
        sup = float(self.area[g < self.kappa].sum() / self.total * 100.0)
        mean_abs = float((np.abs(np.degrees(th)) * self.area).sum() / self.total)
        return sup, mean_abs


def key1(sup, ang, thetas, bounds):
    return (round(sup, 9), round(ang, 9), tuple(thetas), tuple(bounds))


def key2(sup, ang, thetas, bounds):
    return (round(ang, 9), round(sup, 9), tuple(thetas), tuple(bounds))


def record(prob, prof, sup, ang, thetas, bounds):
    return {"bounds": [float(b) for b in bounds], "thetas": [float(t) for t in thetas],
            "support_pct": sup, "mean_abs_deg": ang,
            "distinct_bands": len(varangle._merge_bands(prob.edges(bounds), list(thetas))),
            "breakpoints": [[float(z), float(t)]
                            for z, t in zip(prof.zs, prof.thetas_deg, strict=True)],
            "notes": list(prof.notes)}


def search_space(prob, n, bcands, angles):
    for bounds in itertools.combinations(bcands, n - 1):
        for thetas in itertools.product(angles, repeat=n):
            yield bounds, thetas


def best_over(prob, gen, s_ref):
    """gen 의 (경계, 각도) 를 전부 평가 → 목적 ①·② 최선과 집계."""
    b1 = b2 = None
    n_eval = n_bad = 0
    for bounds, thetas in gen:
        n_eval += 1
        r = prob.build(bounds, thetas)
        if r is None:
            n_bad += 1
            continue
        prof, sup, ang = r
        k1 = key1(sup, ang, thetas, bounds)
        if b1 is None or k1 < b1[0]:
            b1 = (k1, prof, sup, ang, thetas, bounds)
        if sup <= s_ref + EPS:
            k2 = key2(sup, ang, thetas, bounds)
            if b2 is None or k2 < b2[0]:
                b2 = (k2, prof, sup, ang, thetas, bounds)
    out = {"evaluated": n_eval, "infeasible": n_bad}
    for tag, b in (("obj1", b1), ("obj2", b2)):
        out[tag] = None if b is None else record(prob, b[1], *b[2:])
    return out


def n4_neighbourhood(best, bcands, angles):
    """N=3 최선해의 한 밴드를 B 의 한 점으로 나눔: 나뉜 둘은 A 전수, 나머지는 ±STEP."""
    bounds3, th3 = list(best["bounds"]), list(best["thetas"])
    edges3 = [-np.inf, *bounds3, np.inf]
    seen = set()
    for b in bcands:
        if any(abs(b - x) < 1e-9 for x in bounds3):
            continue
        j = next(i for i in range(3) if edges3[i] < b < edges3[i + 1])
        bounds4 = tuple(sorted([*bounds3, b]))
        others = [i for i in range(3) if i != j]
        near = {i: [t for t in angles if abs(t - th3[i]) <= STEP + 1e-9] for i in others}
        for ta, tb in itertools.product(angles, repeat=2):
            for combo in itertools.product(*(near[i] for i in others)):
                th = []
                for i in range(3):
                    if i == j:
                        th += [ta, tb]
                    else:
                        th.append(combo[others.index(i)])
                key = (bounds4, tuple(th))
                if key not in seen:
                    seen.add(key)
                    yield bounds4, tuple(th)


def run_search(idx, n_max=3, restrict=True, out_dir=SEARCH_DIR):
    out_path = out_dir / f"{idx:02d}.json"
    if out_path.exists():
        return str(out_path)
    t0 = time.perf_counter()
    name, mesh = load_model(idx)
    prob = Problem(mesh)
    # 기준선 (a): J 가 고른 균일 (선택기 그대로, 2° 격자)
    su = varangle.select_banded_j(mesh, DEFAULT_K, 1, prob.r_max, prob.rp,
                                  MAX_SPACING_FACTOR)
    theta_j = float(su["thetas"][0])
    prof_j = AngleProfile.constant(theta_j)
    s_ref, ang_j = prob.evaluate(prof_j)
    bcands = prob.boundary_candidates()
    angles = prob.angle_candidates(restrict)
    res = {"model": name, "index": idx, "faces": int(len(mesh.faces)),
           "height": prob.H, "r_max": prob.r_max, "z_range": [prob.z_lo, prob.z_hi],
           "waist_z": prob.waist_z(), "boundary_candidates": bcands, "angles": angles,
           "restrict_signs": restrict, "uniform_J": {"theta": theta_j,
                                                     "support_pct": s_ref,
                                                     "mean_abs_deg": ang_j},
           "base_support_pct": prob.evaluate(AngleProfile.constant(0.0))[0],
           "N": {}}
    for n in range(1, n_max + 1):
        t = time.perf_counter()
        r = best_over(prob, search_space(prob, n, bcands, angles), s_ref)
        r["seconds"] = time.perf_counter() - t
        res["N"][str(n)] = r
        print(f"[{idx:02d} {name}] N={n}: {r['evaluated']} 평가, "
              f"{r['seconds']:.0f}s, ① {r['obj1']['support_pct']:.3f}% "
              f"{r['obj1']['mean_abs_deg']:.2f}°", flush=True)
    if n_max >= 3:
        t = time.perf_counter()
        r4 = {}
        for tag in ("obj1", "obj2"):
            best3 = res["N"]["3"][tag]
            if best3 is None:
                r4[tag] = None
                continue
            sub = best_over(prob, n4_neighbourhood(best3, bcands, angles), s_ref)
            r4[tag] = sub[tag]
            r4[f"{tag}_evaluated"] = sub["evaluated"]
        r4["seconds"] = time.perf_counter() - t
        r4["restricted"] = True
        res["N"]["4"] = r4
    # 빠른 평가가 저장소 판정식과 같은지 (최선해마다)
    worst = 0.0
    for r in res["N"].values():
        for tag in ("obj1", "obj2"):
            rec = r.get(tag)
            if rec is None:
                continue
            prof = prob.build(rec["bounds"], rec["thetas"])[0]
            ref = support_fraction_profile(mesh, prof, THRESHOLD_DEG)
            obj = varangle.profile_objective(mesh, prof, 0.0, 0.0, 0.0, prob.rp)
            worst = max(worst, abs(ref - rec["support_pct"]),
                        abs(obj["avg_angle"] - rec["mean_abs_deg"]))
    res["fast_eval_max_abs_diff"] = worst
    res["seconds_total"] = time.perf_counter() - t0
    out_dir.mkdir(exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    os.replace(tmp, out_path)
    return str(out_path)


# ─────────────────────────────────────────────────────────────
# 툴패스 측정 — 최선해와 기준선 (a)·(b) 만
# ─────────────────────────────────────────────────────────────
def profile_key(prof):
    return json.dumps([[round(float(z), 6), round(float(t), 6)]
                       for z, t in zip(prof.zs, prof.thetas_deg, strict=True)])


def arms_of(prob, res):
    """(라벨, 프로필) 목록: (a) J 균일, N·목적별 최선해, 그 해의 아랫각 균일 (b)."""
    arms = [("uniform_J", AngleProfile.constant(res["uniform_J"]["theta"]))]
    for n, r in sorted(res["N"].items()):
        for tag in ("obj1", "obj2"):
            rec = r.get(tag)
            if rec is None:
                continue
            built = prob.build(rec["bounds"], rec["thetas"])
            prof = built[0]
            got = [[float(z), float(t)] for z, t in
                   zip(prof.zs, prof.thetas_deg, strict=True)]
            if not np.allclose(np.array(got), np.array(rec["breakpoints"])):
                raise RuntimeError(f"{res['model']} N={n} {tag}: 프로필 재생성 불일치")
            arms.append((f"N{n}_{tag}", prof))
            arms.append((f"N{n}_{tag}_bottom_uniform",
                         AngleProfile.constant(rec["thetas"][0])))
    return arms


def run_measure(idx):
    from analyze_gap_sample import measure  # 무거운 import 는 여기서

    out_path = MEASURE_DIR / f"{idx:02d}.json"
    if out_path.exists():
        return str(out_path)
    res = json.loads((SEARCH_DIR / f"{idx:02d}.json").read_text())
    name, mesh = load_model(idx)
    prob = Problem(mesh)
    t0 = time.perf_counter()
    profiles, labels = {}, {}
    for label, prof in arms_of(prob, res):
        k = profile_key(prof)
        profiles[k] = prof
        labels[label] = k
    meas = {}
    for k, prof in profiles.items():
        meas[k] = {}
        for lh in LAYER_HEIGHTS:
            m = measure(mesh, prof, lh)
            meas[k][str(lh)] = {f: m[f] for f in ("mm", "pct", "near_mm", "mm_pes",
                                                  "perimeter_mm", "angle", "over_z")}
    out = {"model": name, "index": idx, "labels": labels, "measured": meas,
           "seconds": time.perf_counter() - t0}
    MEASURE_DIR.mkdir(exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    os.replace(tmp, out_path)
    print(f"[{idx:02d} {name}] 측정 {len(profiles)} 프로필 × {len(LAYER_HEIGHTS)} 층고, "
          f"{out['seconds']:.0f}s", flush=True)
    return str(out_path)


# ─────────────────────────────────────────────────────────────
# 부호 제한 대조 (문서 §1.1: 3 모델에서 N=2 를 23 값 전수로)
# ─────────────────────────────────────────────────────────────
def run_sign_check(idx):
    out_dir = ROOT / "t3_signcheck"
    path = run_search(idx, n_max=2, restrict=False, out_dir=out_dir)
    full = json.loads(Path(path).read_text())
    lim = json.loads((SEARCH_DIR / f"{idx:02d}.json").read_text())
    same = True
    for n in ("1", "2"):
        for tag in ("obj1", "obj2"):
            a, b = full["N"][n][tag], lim["N"][n][tag]
            if (a is None) != (b is None):
                same = False
            elif a is not None and (abs(a["support_pct"] - b["support_pct"]) > EPS or
                                    abs(a["mean_abs_deg"] - b["mean_abs_deg"]) > EPS):
                same = False
    return {"model": full["model"], "index": idx, "angles_full": len(full["angles"]),
            "angles_restricted": len(lim["angles"]), "same_optimum": same}


# ─────────────────────────────────────────────────────────────
# 보고 — 사전 기준 그대로
# ─────────────────────────────────────────────────────────────
def saturation(u, a):
    """u[N], a[N] (N=1..4) → N*: (u_N − u_{N+1} < 0.5) 그리고 (a_N − a_{N+1} < 1) 인 첫 N."""
    ns = sorted(u)
    for n in ns[:-1]:
        if (u[n] - u[n + 1] < SAT_MM) and (a[n] - a[n + 1] < SAT_DEG):
            return n
    return f">={ns[-1]}"


def verdict_mm(a, b):
    """a = 균일 팔, b = 밴드 팔 (미지지 mm). 0.5mm 안 무승부."""
    return "band" if b < a - TIE_MM else ("uniform" if a < b - TIE_MM else "tie")


def run_report():
    rows = []
    mono_fail = []
    for idx in range(len(model_specs())):
        sp, mp = SEARCH_DIR / f"{idx:02d}.json", MEASURE_DIR / f"{idx:02d}.json"
        if not sp.exists() or not mp.exists():
            print(f"[{idx:02d}] 결과 없음 — 건너뜀")
            continue
        s, m = json.loads(sp.read_text()), json.loads(mp.read_text())
        N = s["N"]
        # 사전 기준 1: 단조성
        for tag in ("obj1", "obj2"):
            prev = None
            for n in ("1", "2", "3", "4"):
                rec = N[n].get(tag) if n in N else None
                if rec is None:
                    continue
                cur = ((rec["support_pct"], rec["mean_abs_deg"]) if tag == "obj1"
                       else (rec["mean_abs_deg"],))
                if prev is not None and tuple(round(c, 9) for c in cur) > \
                        tuple(round(p, 9) for p in prev):
                    mono_fail.append((s["model"], tag, n, prev, cur))
                prev = cur

        def mm(label, lh, m=m):
            return m["measured"][m["labels"][label]][str(lh)]["mm"]

        row = {"model": s["model"], "index": idx, "faces": s["faces"],
               "uniform_J": s["uniform_J"], "base_support_pct": s["base_support_pct"],
               "search_seconds": s["seconds_total"],
               "evaluated": {n: N[n].get("evaluated", N[n].get("obj1_evaluated"))
                             for n in N},
               "fast_eval_max_abs_diff": s["fast_eval_max_abs_diff"],
               "best": {}, "nstar": {}, "vs_baselines": {}}
        for tag in ("obj1", "obj2"):
            best = {n: N[n].get(tag) for n in N}
            row["best"][tag] = {n: (None if b is None else {
                "thetas": b["thetas"], "bounds": b["bounds"],
                "distinct_bands": b["distinct_bands"],
                "support_pct": b["support_pct"], "mean_abs_deg": b["mean_abs_deg"],
                "mm": {str(lh): mm(f"N{n}_{tag}", lh) for lh in LAYER_HEIGHTS},
                "bottom_uniform_mm": {str(lh): mm(f"N{n}_{tag}_bottom_uniform", lh)
                                      for lh in LAYER_HEIGHTS}})
                for n, b in best.items()}
            for lh in LAYER_HEIGHTS:
                ok = {int(n): b for n, b in best.items() if b is not None}
                if len(ok) < 2:
                    row["nstar"][f"{tag}_{lh}"] = None
                    continue
                u = {n: mm(f"N{n}_{tag}", lh) for n in ok}
                a = {n: ok[n]["mean_abs_deg"] for n in ok}
                row["nstar"][f"{tag}_{lh}"] = saturation(u, a)
                if 2 in ok:
                    b2 = mm(f"N2_{tag}", lh)
                    row["vs_baselines"][f"{tag}_{lh}"] = {
                        "a_uniform_J": verdict_mm(mm("uniform_J", lh), b2),
                        "b_bottom_uniform": verdict_mm(
                            mm(f"N2_{tag}_bottom_uniform", lh), b2)}
        row["uniform_J_mm"] = {str(lh): mm("uniform_J", lh) for lh in LAYER_HEIGHTS}
        rows.append(row)

    tally = {}
    for key in (f"{t}_{lh}" for t in ("obj1", "obj2") for lh in LAYER_HEIGHTS):
        c = {}
        for r in rows:
            v = str(r["nstar"].get(key))
            c[v] = c.get(v, 0) + 1
        tally[key] = dict(sorted(c.items()))
    vs = {}
    for key in (f"{t}_{lh}" for t in ("obj1", "obj2") for lh in LAYER_HEIGHTS):
        for base in ("a_uniform_J", "b_bottom_uniform"):
            c = {"band": 0, "uniform": 0, "tie": 0}
            for r in rows:
                v = r["vs_baselines"].get(key)
                if v:
                    c[v[base]] += 1
            vs[f"{key}_{base}"] = c
    summary = {"models": len(rows), "monotonic_violations": mono_fail,
               "monotonic_pass": not mono_fail, "nstar_tally": tally,
               "n2_vs_baselines": vs, "rows": rows}
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print_tables(summary)
    plot(summary)
    return summary


def fmt_th(th):
    return "[" + ",".join(f"{t:g}" for t in th) + "]"


def print_tables(summary):
    print(f"\n단조성(E(i)) 위반: {len(summary['monotonic_violations'])} 건")
    for v in summary["monotonic_violations"]:
        print("   ", v)
    for tag, title in (("obj1", "① 서포트 최소"), ("obj2", "② (a) 서포트 이하에서 평균|θ| 최소")):
        print(f"\n## {title}")
        print("| 모델 | J균일 | N | 각도 | 서포트% | 평균|θ| | mm 0.3 | mm 0.4 | N* 0.3 | N* 0.4 |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for r in summary["rows"]:
            for n, b in r["best"][tag].items():
                if b is None:
                    continue
                first = n == "1"
                print(f"| {r['model'] if first else ''} | "
                      f"{(str(r['uniform_J']['theta']) + '°') if first else ''} | "
                      f"{n}{'*' if n == '4' else ''} | {fmt_th(b['thetas'])} | "
                      f"{b['support_pct']:.3f} | {b['mean_abs_deg']:.2f} | "
                      f"{b['mm']['0.3']:.1f} | {b['mm']['0.4']:.1f} | "
                      f"{r['nstar'][tag + '_0.3'] if first else ''} | "
                      f"{r['nstar'][tag + '_0.4'] if first else ''} |")
    print("\nN* 분포:", json.dumps(summary["nstar_tally"], ensure_ascii=False))
    print("N=2 최선해 대 기준선:", json.dumps(summary["n2_vs_baselines"], ensure_ascii=False))


def plot(summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from conical.plotstyle import L

    rows = summary["rows"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    ns = [1, 2, 3, 4]
    for r in rows:
        b = r["best"]["obj1"]
        a = [b[str(n)]["mean_abs_deg"] for n in ns if b.get(str(n))]
        axes[0].plot(ns[:len(a)], a, color="#4c72b0", alpha=0.5, marker="o", ms=3)
        u = [b[str(n)]["mm"]["0.3"] for n in ns if b.get(str(n))]
        axes[1].plot(ns[:len(u)], u, color="#4c72b0", alpha=0.5, marker="o", ms=3)
    axes[0].set_xlabel(L("bands N", "밴드 수 N"))
    axes[0].set_ylabel(L("mean |θ| of best (°)", "최선해 평균 |θ| (°)"))
    axes[0].set_title(L("objective ①: min support", "목적 ①: 서포트 최소"))
    axes[1].set_xlabel(L("bands N", "밴드 수 N"))
    axes[1].set_ylabel(L("toolpath unsupported (mm, lh 0.3)", "툴패스 미지지 (mm, 층고 0.3)"))
    axes[1].set_yscale("symlog", linthresh=1.0)
    for ax in axes[:2]:
        ax.set_xticks(ns)
        ax.set_xticklabels(["1", "2", "3", "4*"])
        ax.grid(alpha=0.3)
    labels = ["1", "2", "3", ">=4"]
    w = 0.2
    for i, key in enumerate(("obj1_0.3", "obj1_0.4", "obj2_0.3", "obj2_0.4")):
        t = summary["nstar_tally"][key]
        axes[2].bar(np.arange(4) + (i - 1.5) * w, [t.get(k, 0) for k in labels], w,
                    label=key, color=["#4c72b0", "#8fa8d0", "#c44e52", "#e09a9c"][i])
    axes[2].set_xticks(range(4))
    axes[2].set_xticklabels(["N*=1", "2", "3", "≥4"])
    axes[2].set_ylabel(L("models", "모델 수"))
    axes[2].legend(fontsize=7)
    axes[2].set_title(L("saturation N*", "포화 N*"))
    fig.tight_layout()
    fig.savefig(FIG, dpi=130)
    print(f"저장: {FIG.name}")


# ─────────────────────────────────────────────────────────────
def parse_models(text):
    n = len(model_specs())
    if not text:
        return list(range(n))
    return [int(x) for x in text.split(",")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--models", default="", help="모델 번호 쉼표 목록 (기본 전부)")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--check-signs", action="store_true")
    args = ap.parse_args()
    idxs = parse_models(args.models)
    if args.report:
        run_report()
        return 0
    if args.check_signs:
        with Pool(args.jobs) as pool:
            out = pool.map(run_sign_check, idxs)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        (ROOT / "t3_signcheck" / "summary.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    fn = run_measure if args.measure else run_search
    # 큰 작업부터 (torus 가 가장 오래 걸린다)
    with Pool(args.jobs) as pool:
        for p in pool.imap_unordered(fn, idxs):
            print("완료:", p, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
