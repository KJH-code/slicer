"""analyze_exact_angle.py — 균일각 정확 탐색 vs 2° 격자 (docs/exact_angle.md).

사전 등록한 판정 기준 (a)(b)(b′)(c) 를 모든 모델에서 재고, 격자 대비 각도·J 차이,
후보 수, 실행 시간, λ 축의 argmax 점프를 표로 낸다. 해석식 범위(툴패스 재측정 없음).

모델: 데모 6 (compare_ceiling.demo_models) + 17 (analyze_blend_ratio.build_specs(asym=True))
      + λ 축 10 (허리3 widen, analyze_angle_grid.LAMBDAS)

실행:
    python3 analyze_exact_angle.py                 # 전부 (몇 분)
    python3 analyze_exact_angle.py --skip-fine     # (c) 미세 격자 생략
"""

import argparse
import json
import math
import time

import numpy as np

from analyze_angle_grid import LAMBDAS
from analyze_blend_ratio import build_specs, widen
from compare_ceiling import demo_models
from compare_waist import waisted_model
from conical.analytic import critical_angle, radial_normal, support_fraction
from conical.config import DEFAULT_K, MAX_ANGLE_DEG, MAX_SPACING_FACTOR, THRESHOLD_DEG
from conical.exact_angle import EPS_DEG, select_uniform_exact
from conical.meshio import RadiusProfile, center_on_axis
from conical.selector import select_cone
from conical.varangle import angle_candidates, select_banded_j

FINE_STEP = 0.001
TOL = 1e-6


def fine_grid_best(mesh, k, step=FINE_STEP, max_angle=MAX_ANGLE_DEG,
                   threshold_deg=THRESHOLD_DEG, chunk=400):
    """0.001° 격자 전수. 판정식은 analytic 과 같은 식을 벡터로 (엄격 부등호)."""
    nz = mesh.face_normals[:, 2]
    nr = radial_normal(mesh)
    w = mesh.area_faces / mesh.area_faces.sum() * 100.0
    kappa = -math.sin(math.radians(threshold_deg))
    angs = np.array(angle_candidates(max_angle, step))
    base = float(w[nz < kappa].sum())
    best = (-np.inf, None, None)
    for direction, d in (("outward", 1.0), ("inward", -1.0)):
        b = d * nr
        for i in range(0, len(angs), chunk):
            a = angs[i:i + chunk]
            ar = np.radians(a)[:, None]
            g = nz[None, :] * np.cos(ar) + b[None, :] * np.sin(ar)
            S = (g < kappa).astype(float) @ w
            J = (base - S) - k * a
            j = int(np.argmax(J))
            if J[j] > best[0] + 1e-12:
                best = (float(J[j]), float(a[j]), direction)
    return {"J": best[0], "angle": best[1], "direction": best[2], "n": 2 * len(angs)}


def critical_gap(mesh, best_dir, threshold_deg=THRESHOLD_DEG):
    """analytic.critical_angle 이 '못 고침'(nan) 으로 둔 면 중 support_step 상으로는
    [0, MAX] 안에서 고쳐지는 근이 있는 면의 넓이(%) — 두 함수의 어긋남."""
    out = {}
    w = mesh.area_faces / mesh.area_faces.sum() * 100.0
    for direction in ("outward", "inward"):
        th = critical_angle(mesh, direction, threshold_deg)
        # 실제로 MAX 에서 통과하는가 (support_fraction 과 같은 식)
        nz = mesh.face_normals[:, 2]
        nr = radial_normal(mesh)
        d = 1.0 if direction == "outward" else -1.0
        kappa = -math.sin(math.radians(threshold_deg))
        a = math.radians(MAX_ANGLE_DEG)
        ok_any = np.zeros(len(nz), dtype=bool)
        for t in np.linspace(0, a, 441):
            ok_any |= (nz * math.cos(t) + d * nr * math.sin(t)) >= kappa
        miss = np.isnan(th) & ok_any
        out[direction] = float(w[miss].sum())
    return out


def run(name, mesh, k, do_fine, lam_mesh=False):
    row = {"model": name, "faces": int(len(mesh.faces))}

    t0 = time.perf_counter()
    g, _ = select_cone(mesh, k, verbose=False, method="grid")
    row["t_grid"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    e, info = select_uniform_exact(mesh, k)
    row["t_exact"] = time.perf_counter() - t0

    row.update(grid_angle=float(g["angle"]), grid_dir=g["direction"], grid_J=float(g["J"]),
               grid_S=float(g["support"]),
               exact_angle=e["angle"], exact_dir=e["direction"], exact_J=e["J"],
               exact_S=e["support"], exact_width=e["width_deg"],
               n_cand_exact=info["n_candidates"], n_face_roots=info["n_face_roots"],
               n_cand_grid=2 * len(angle_candidates(MAX_ANGLE_DEG, 2)),
               baseline=info["baseline"])

    # (a)
    row["crit_a"] = bool(e["J"] >= g["J"] - TOL)
    # (b) 해석식 재측정
    s_re = support_fraction(mesh, e["angle"], e["direction"], THRESHOLD_DEG)
    row["S_remeasure"] = float(s_re)
    row["crit_b"] = bool(abs(s_re - e["support"]) <= 1e-9)
    # (b′) 계단함수 vs support_fraction, 2° 격자 × 2 방향
    worst = 0.0
    for direction in ("outward", "inward"):
        st = info["steps"][direction]
        for a in angle_candidates(MAX_ANGLE_DEG, 2):
            worst = max(worst, abs(float(st["eval"]([a])[0])
                                   - support_fraction(mesh, a, direction, THRESHOLD_DEG)))
    row["bprime_worst"] = worst
    row["crit_bprime"] = bool(worst <= 1e-9)
    # (c)
    if do_fine:
        t0 = time.perf_counter()
        f = fine_grid_best(mesh, k)
        row["t_fine"] = time.perf_counter() - t0
        row.update(fine_J=f["J"], fine_angle=f["angle"], fine_dir=f["direction"])
        c1 = f["J"] <= e["J"] + TOL
        c2 = e["J"] - f["J"] <= k * FINE_STEP + TOL
        row["crit_c1"] = bool(c1)
        row["crit_c2"] = bool(c2)
        row["c2_exempt"] = bool((not c2) and e["width_deg"] < FINE_STEP)
    row["crit_gap"] = critical_gap(mesh, e["direction"])

    if lam_mesh:
        rp = RadiusProfile(mesh)
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        r = select_banded_j(mesh, k, 1, r_max, rp, MAX_SPACING_FACTOR)
        row["bandj_theta"] = float(r["thetas"][0])
        row["bandj_J"] = float(r["J"])
    return row


def signed(a, d):
    return a if d == "outward" else -a


def lam_dense(k, step=0.002):
    """λ 1.16~1.30 을 촘촘히(기본 0.002, 71 점) — 정확/격자 각각 1° 넘는 점프를 센다.
    점프 양쪽에서 두 경쟁 후보의 J 를 같이 적는다(argmax 가 갈아타는 지점)."""
    base = waisted_model(3.0)
    lams = np.round(np.arange(LAMBDAS[0], LAMBDAS[-1] + 1e-9, step), 6)
    E, G, R = [], [], []
    for lam in lams:
        m = widen(base, float(lam))
        e, info = select_uniform_exact(m, k)
        g, _ = select_cone(m, k, verbose=False)
        E.append(signed(e["angle"], e["direction"]))
        G.append(signed(g["angle"], g["direction"]))
        # 다른 계단(1° 넘게 떨어진 후보) 중 J 최댓값 = 2 위 경쟁자
        best_other = -np.inf
        for direction, st in info["steps"].items():
            for a, sv in zip(st["cand_deg"], st["S_cand"], strict=True):
                if abs(signed(a, direction) - E[-1]) > 1.0:
                    best_other = max(best_other, (info["baseline"] - sv) - k * a)
        R.append(e["J"] - best_other)
    out = {"lams": lams.tolist(), "exact": E, "grid": G, "runner_up_gap": R}
    for name, A in (("정확", np.array(E)), ("격자 2°", np.array(G))):
        j = np.nonzero(np.abs(np.diff(A)) > 1.0)[0]
        print(f"  {name}: 1° 넘는 점프 {len(j)} 회 "
              + ", ".join(f"λ {lams[i]:.3f}→{lams[i + 1]:.3f}: {A[i]:.3f}→{A[i + 1]:.3f}"
                          for i in j))
    print(f"  정확 θ 범위 {min(E):.3f} ~ {max(E):.3f}; 1·2 위 J 차 중앙 {np.median(R):.4f}, "
          f"최소 {min(R):.4f} (λ {lams[int(np.argmin(R))]:.3f})")
    return out


def fmt_dir(a, d):
    return f"{'+' if d == 'outward' else '−'}{a:.3f}" if a else "0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=float, default=DEFAULT_K)
    ap.add_argument("--skip-fine", action="store_true")
    ap.add_argument("--lam-step", type=float, default=0.002,
                    help="λ 촘촘 스캔 간격 (0 이면 생략)")
    ap.add_argument("--json", default="exact_angle_results.json")
    args = ap.parse_args()

    models = [(f"demo:{n}", center_on_axis(m.copy())) for n, m in demo_models().items()]
    models += [(n, b()) for n, b in build_specs(asym=True)]
    lam_models = [(f"λ={lam:.2f}", widen(waisted_model(3.0), lam)) for lam in LAMBDAS]

    rows = []
    for name, mesh in models:
        rows.append(run(name, mesh, args.k, not args.skip_fine))
        print(f"  끝: {name}", flush=True)
    lam_rows = []
    for name, mesh in lam_models:
        lam_rows.append(run(name, mesh, args.k, not args.skip_fine, lam_mesh=True))
        print(f"  끝: {name}", flush=True)

    allr = rows + lam_rows
    print("\n| 모델 | 면 | 격자 θ | 격자 J | 정확 θ | 정확 J | ΔJ | 정확 S | 재측정 S | "
          "미세 J | 계단 폭° | 후보 정확/격자 | 시간 격자/정확 ms |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in allr:
        print(f"| {r['model']} | {r['faces']} | {fmt_dir(r['grid_angle'], r['grid_dir'])} "
              f"| {r['grid_J']:.4f} | {fmt_dir(r['exact_angle'], r['exact_dir'])} "
              f"| {r['exact_J']:.4f} | {r['exact_J'] - r['grid_J']:+.4f} "
              f"| {r['exact_S']:.4f} | {r['S_remeasure']:.4f} "
              f"| {r.get('fine_J', float('nan')):.4f} | {r['exact_width']:.3f} "
              f"| {r['n_cand_exact']}/{r['n_cand_grid']} "
              f"| {r['t_grid'] * 1000:.0f}/{r['t_exact'] * 1000:.0f} |")

    print("\n판정 기준")
    for key in ("crit_a", "crit_b", "crit_bprime", "crit_c1", "crit_c2"):
        vals = [r[key] for r in allr if key in r]
        print(f"  {key}: {sum(vals)}/{len(vals)} 통과")
    ex = [r["model"] for r in allr if r.get("c2_exempt")]
    print(f"  (c2) 사전 등록 예외(계단 폭 < {FINE_STEP}°): {ex}")
    print(f"  (b′) 최악 차이: {max(r['bprime_worst'] for r in allr):.3e}")
    print(f"  (b) 최악 차이: {max(abs(r['S_remeasure'] - r['exact_S']) for r in allr):.3e}")
    if not args.skip_fine:
        print(f"  (c) J_exact − J_fine 범위: "
              f"{min(r['exact_J'] - r['fine_J'] for r in allr):+.3e} ~ "
              f"{max(r['exact_J'] - r['fine_J'] for r in allr):+.3e}  "
              f"(허용 k·{FINE_STEP} = {args.k * FINE_STEP:.0e}, ε 손실 ≤ {args.k * EPS_DEG:.0e})")

    diff_ang = [r["model"] for r in allr
                if abs(r["exact_angle"] - r["grid_angle"]) > 1e-6
                or (r["exact_angle"] > 0 and r["exact_dir"] != r["grid_dir"])]
    diff_J = [r["model"] for r in allr if r["exact_J"] - r["grid_J"] > TOL]
    big = [r["model"] for r in allr if abs(r["exact_angle"] - r["grid_angle"]) > 2.0]
    print(f"\n격자 대비 각도가 다른 모델: {len(diff_ang)}/{len(allr)}")
    print(f"격자 대비 J 가 오른 모델: {len(diff_J)}/{len(allr)}")
    print(f"각도 차이 > 2° (격자 한 칸 넘게): {big}")
    tg = sum(r["t_grid"] for r in allr)
    te = sum(r["t_exact"] for r in allr)
    print(f"시간 합: 격자 {tg:.2f}s, 정확 {te:.2f}s  (×{tg / te:.1f})")

    print("\nλ 축 (허리3 widen)")
    print("| λ | select_cone 격자 | select_banded_j(n=1) 격자 | 정확 θ | 정확 J | 격자 J |")
    print("|---|---|---|---|---|---|")
    for r in lam_rows:
        print(f"| {r['model']} | {fmt_dir(r['grid_angle'], r['grid_dir'])} "
              f"| {r['bandj_theta']:+.1f} (J {r['bandj_J']:.4f}) "
              f"| {fmt_dir(r['exact_angle'], r['exact_dir'])} | {r['exact_J']:.4f} "
              f"| {r['grid_J']:.4f} |")
    ea = [r["exact_angle"] * (1 if r["exact_dir"] == "outward" else -1) for r in lam_rows]
    jumps = [(lam_rows[i]["model"], lam_rows[i + 1]["model"], ea[i + 1] - ea[i])
             for i in range(len(ea) - 1)]
    print("정확 θ 의 이웃 차:", [(a, b, round(dv, 3)) for a, b, dv in jumps])

    dense = None
    if args.lam_step > 0:
        print(f"\nλ 촘촘 스캔 (간격 {args.lam_step})")
        dense = lam_dense(args.k, args.lam_step)

    print("\ncritical_angle 이 '못 고침' 으로 둔 면 중 실제로 고쳐지는 면의 넓이(%):")
    for r in allr:
        cg = r["crit_gap"]
        if cg["outward"] > 1e-9 or cg["inward"] > 1e-9:
            print(f"  {r['model']}: outward {cg['outward']:.4f}  inward {cg['inward']:.4f}")

    with open(args.json, "w", encoding="utf-8") as f:
        json.dump({"rows": allr, "lam_dense": dense}, f, ensure_ascii=False, indent=1, default=float)
    print(f"\n저장: {args.json}")


if __name__ == "__main__":
    main()
