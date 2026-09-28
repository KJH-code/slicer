"""analyze_j_vs_optimum.py — J 가 고른 해는 **진짜 최적해와 얼마나 먼가**.

## 왜

계통이 J 로 모였다 (docs/verification.md 2026-09-28):

| 축 | J 로 고르면 | 언제 |
|---|---|---|
| 밴드 수 N | 오버행이 달성 가능한 최소보다 나쁘다 (5/6 모델) | 09-19 |
| 각도 격자 | 격자를 촘촘히 하면 J↑ 인데 오버행↓ | 09-28 |
| 형상 파라미터 | argmax 가 튄다 (λ 0.02 에 각도 8° 점프) | 09-28 |

그래서 ρ 반증도 "지표를 잘못 골랐다" 가 아니라 **"J 가 오버행을 대표하지 못한다"**
쪽으로 읽힌다. 그런데 그건 아직 **간접 증거**다. 직접 재야 한다.

## 설계 — J 를 바꾸는 대신 **최적해를 전수로 찾는다**

"J 를 오버행 직접 최적화로 교체" 를 그대로 하면 툴패스를 좌표하강 루프 안에 넣어야
해서 모델당 1.5 시간이다. 대신:

1. 밴드2 각도 조합 `(θ₁, θ₂)` 를 **격자 전수**로 훑는다 (0~44°, 4° 간격)
2. 각 조합의 프로필을 만들고(층간격 제약 포함, 불가는 건너뜀) **툴패스로 오버행**을 잰다
3. 동시에 그 조합의 **J** 도 계산한다 (해석식이라 싸다)
4. → 지형 전체에서 **J vs 오버행**을 비교할 수 있다

이게 "J 가 고른 해 vs 최적해" 두 점 비교보다 강하다 — **J 가 오버행 순위를 따라가는지
자체**를 잰다.

## 판정 기준 (**결과 보기 전에** 적는다)

* **스피어만 ρ(J, 오버행) ≈ −1** → J 가 오버행 순위를 잘 따라간다. J 는 문제가 아니고
  비단조성의 원인은 다른 곳이다 (J 는 클수록 좋고 오버행은 작을수록 좋으니 음의 상관)
* **|ρ| 가 작거나 부호가 이상** → **J 가 오버행 순위를 안 따라간다.** 계통이 확정된다
* **J-argmax 의 오버행 vs 전수 최소의 격차가 크다** → 그 격차가 우리가 잃고 있는 양이다
* **전수 최적해가 균일(θ₁=θ₂)** → 그 모델에서는 밴드가 **애초에 이길 수 없다.**
  J 와 무관한 사실이고, 이게 나오면 '밴드 우세' 주장의 범위가 다시 좁아진다

⚠ 전수 격자는 4° 다. **그 사이는 모른다.** 그리고 밴드 수는 2 로 고정이다.

실행:
    python3 analyze_j_vs_optimum.py            # 대표 4 모델
    python3 analyze_j_vs_optimum.py --quick    # 2 모델, 격자 8°
"""

import argparse
import json
import sys
import time

import numpy as np
from scipy.stats import spearmanr

from conical.meshio import RadiusProfile
from conical.profile import AngleProfile
from conical.varangle import (assign_height_bands, select_banded_j,
                              profile_objective, _merge_bands)
from conical.analytic import support_fraction
from conical.config import (DEFAULT_K, MAX_SPACING_FACTOR, BLEND_SHIFT_RATIO,
                            BLEND_COST_K, THRESHOLD_DEG)
from compare_waist import waisted_model, run_pipeline, mean_abs_angle

from analyze_blend_ratio import _sphere, widen


def models(quick):
    out = [("허리 r=3", lambda: waisted_model(3.0)),
           ("램프 (허리 r=2)", lambda: waisted_model(2.0))]
    if not quick:
        out += [("구", _sphere),
                # λ=1.24 는 격자에 따라 판정이 뒤집힌 자리다 (analyze_angle_grid.py)
                ("허리3 ×1.24", lambda: widen(waisted_model(3.0), 1.24))]
    return out


def enumerate_profiles(mesh, step, k, k_blend=BLEND_COST_K):
    """(θ₁, θ₂) 격자 전수 → 만들 수 있는 프로필과 그 J. 못 만드는 조합은 건너뛴다."""
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    H = float(mesh.bounds[1][2] - mesh.bounds[0][2])
    _labels, edges = assign_height_bands(mesh, 2)
    base_pct = support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    grid = [float(a) for a in np.arange(0.0, 44.0 + 1e-9, step)]

    out = []
    for t1 in grid:
        for t2 in grid:
            try:
                prof = AngleProfile.from_bands(
                    _merge_bands(edges, [t1, t2]), r_max, radius_profile=rp,
                    spacing_limit=MAX_SPACING_FACTOR,
                    max_shift=BLEND_SHIFT_RATIO * H)
            except ValueError:
                continue
            if prof.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp):
                continue          # 층간격 제약 위반 — 못 찍는 프로필
            m = profile_objective(mesh, prof, base_pct, k, k_blend, rp,
                                  MAX_SPACING_FACTOR, THRESHOLD_DEG)
            out.append(dict(t1=t1, t2=t2, prof=prof, J=m["J"],
                            uniform=bool(abs(t1 - t2) < 1e-9)))
    return out, rp, r_max


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--step", type=float, default=None)
    ap.add_argument("--k", type=float, default=DEFAULT_K)
    ap.add_argument("--json", default="j_vs_optimum_results.json")
    args = ap.parse_args()
    step = args.step if args.step else (8.0 if args.quick else 4.0)

    allrows = []
    for name, build in models(args.quick):
        mesh = build()
        combos, rp, r_max = enumerate_profiles(mesh, step, args.k)
        print(f"\n[{name}]  격자 {step:g}°  만들 수 있는 조합 {len(combos)}개 "
              f"(균일 {sum(c['uniform'] for c in combos)}개)")

        t0 = time.time()
        for c in combos:
            _p, _t, _f, oh, _i, _g = run_pipeline(mesh, c["prof"], breakdown=True)
            c["overhang"] = oh
            c["angle"] = mean_abs_angle(mesh, c["prof"])
        print(f"  툴패스 {len(combos)}회 측정 ({time.time()-t0:.0f}s)")

        # J 가 고른 해 (출하 선택기)
        sel = select_banded_j(mesh, args.k, 2, r_max, rp, MAX_SPACING_FACTOR)
        _p, _t, _f, oh_sel, _i, _g = run_pipeline(mesh, sel["profile_obj"],
                                                  breakdown=True)
        th_sel = [round(t, 1) for t in sel["thetas"]]

        # ⚠ 오버행 단독 최소는 **J 를 탓하는 근거가 못 된다** — J 는 각도를 일부러
        #   벌한다(− k·평균|θ|). 고각 균일은 오버행이 낮지만 왜곡이 크다.
        #   진짜 질문은 **J 의 해가 (오버행, 왜곡) 파레토 전선 위에 있나** 다.
        def dominates(a, b):
            # a 가 b 를 두 축 모두에서 이기나 (하나는 엄격히)
            return (a["overhang"] <= b["overhang"] + 1e-12
                    and a["angle"] <= b["angle"] + 1e-9
                    and (a["overhang"] < b["overhang"] - 1e-12
                         or a["angle"] < b["angle"] - 1e-9))

        front = [c for c in combos
                 if not any(dominates(o, c) for o in combos if o is not c)]

        best_oh = min(combos, key=lambda c: c["overhang"])
        best_J = max(combos, key=lambda c: c["J"])
        best_uni = min((c for c in combos if c["uniform"]),
                       key=lambda c: c["overhang"])
        rho, pval = spearmanr([c["J"] for c in combos],
                             [c["overhang"] for c in combos])

        print(f"  J 가 고른 해        θ={th_sel}  오버행 {oh_sel:.3f}%p")
        print(f"  격자 J 최대         θ=[{best_J['t1']:g}, {best_J['t2']:g}]"
              f"  오버행 {best_J['overhang']:.3f}%p  J={best_J['J']:.3f}")
        print(f"  **오버행 최소**      θ=[{best_oh['t1']:g}, {best_oh['t2']:g}]"
              f"  오버행 {best_oh['overhang']:.3f}%p  J={best_oh['J']:.3f}"
              f"  {'← 균일' if best_oh['uniform'] else '← 밴드'}")
        print(f"  최선 균일           θ={best_uni['t1']:g}"
              f"  오버행 {best_uni['overhang']:.3f}%p")
        gap = oh_sel - best_oh["overhang"]
        print(f"  → J 의 손해 {gap:+.3f}%p"
              f" ({oh_sel/max(best_oh['overhang'],1e-9):.1f}배)"
              if best_oh["overhang"] > 1e-9 else f"  → J 의 손해 {gap:+.3f}%p")
        print(f"  → 스피어만 ρ(J, 오버행) = **{rho:+.3f}** (p={pval:.1e})"
              "   [−1 이면 J 가 순위를 잘 따라간다]")
        band_wins = best_oh["overhang"] < best_uni["overhang"] - 1e-9
        print(f"  → 오버행 단독 최적해가 밴드인가: "
              f"**{'예' if band_wins else '아니오 (균일 고각이 최적)'}**")

        # J 의 해가 파레토 전선 위에 있나 — 여기가 핵심 질문이다.
        sel_pt = dict(overhang=oh_sel,
                      angle=mean_abs_angle(mesh, sel["profile_obj"]))
        dom = [c for c in combos if dominates(c, sel_pt)]
        print(f"  파레토 전선 {len(front)}개 / 조합 {len(combos)}개")
        print(f"  → **J 의 해가 전선 위에 있나: {'예' if not dom else '아니오'}**"
              f"  (지배하는 조합 {len(dom)}개)")
        if dom:
            w = min(dom, key=lambda c: (c["overhang"], c["angle"]))
            print(f"     가장 세게 지배: θ=[{w['t1']:g}, {w['t2']:g}] "
                  f"오버행 {w['overhang']:.3f} (J 해 {oh_sel:.3f}) / "
                  f"왜곡 {w['angle']:.1f}° (J 해 {sel_pt['angle']:.1f}°)")
        print(f"     (J 해: 오버행 {oh_sel:.3f}%p, 왜곡 {sel_pt['angle']:.1f}°  |  "
              f"오버행 최소: {best_oh['overhang']:.3f}%p, 왜곡 {best_oh['angle']:.1f}°)")

        allrows.append(dict(
            model=name, step=step, n_combos=len(combos), spearman=float(rho),
            j_pick=th_sel, j_pick_oh=oh_sel,
            best_oh=[best_oh["t1"], best_oh["t2"]], best_oh_val=best_oh["overhang"],
            best_J=[best_J["t1"], best_J["t2"]], best_J_oh=best_J["overhang"],
            best_uniform=best_uni["t1"], best_uniform_oh=best_uni["overhang"],
            band_beats_uniform=bool(band_wins),
            j_pick_angle=sel_pt["angle"], best_oh_angle=best_oh["angle"],
            n_front=len(front), j_on_front=bool(not dom), n_dominating=len(dom),
            grid=[{kk: c[kk] for kk in ("t1", "t2", "J", "overhang", "angle", "uniform")}
                  for c in combos]))

    print("\n" + "=" * 68)
    print(f"{'모델':<16}{'스피어만':>9}{'J해 전선위?':>12}{'지배조합':>9}"
          f"{'오버행최소해':>14}{'밴드최적?':>10}")
    print("-" * 74)
    for r in allrows:
        print(f"{r['model']:<16}{r['spearman']:>+9.3f}"
              f"{('예' if r['j_on_front'] else '아니오'):>12}{r['n_dominating']:>9}"
              f"{str([f'{v:g}' for v in r['best_oh']]):>14}"
              f"{'예' if r['band_beats_uniform'] else '아니오':>10}")
    nf = sum(1 for r in allrows if not r["j_on_front"])
    print(f"\n[파레토 판정] J 의 해가 전선 **밖**인 모델 {nf}/{len(allrows)}")
    if nf == 0:
        print("  → J 는 전선 위의 한 점을 고른다. **'J 가 틀렸다' 가 아니라 '다른 교환점을")
        print("    고른다' 다.** 오버행 단독 비교로 J 를 탓하면 안 된다.")
    else:
        print("  → ⚠ J 가 전선 밖의 해를 고른다. 두 축 모두에서 더 나은 조합이 있는데")
        print("    못 찾는다는 뜻이고, 이건 순수한 손해다.")
    rs = [r["spearman"] for r in allrows]
    print(f"\n[판정] 스피어만 ρ(J, 오버행) 범위 {min(rs):+.3f} ~ {max(rs):+.3f}")
    if max(rs) < -0.8:
        print("  → J 가 오버행 순위를 **잘 따라간다.** J 는 문제가 아니다.")
    elif min(rs) > -0.4:
        print("  → J 가 오버행 순위를 **거의 못 따라간다.** 계통이 확정된다 —")
        print("    문제는 지표가 아니라 **목적함수 J** 다.")
    else:
        print("  → 모델마다 다르다. J 가 어떤 형상에서 어긋나는지 따로 봐야 한다.")
    nb = sum(1 for r in allrows if not r["band_beats_uniform"])
    if nb:
        print(f"  ⚠ {nb}/{len(allrows)} 모델에서 **전수 최적해가 균일**이다 —")
        print("    거기서는 밴드가 애초에 이길 수 없다 (J 와 무관한 사실).")

    if args.json:
        json.dump(allrows, open(args.json, "w"), ensure_ascii=False, indent=1)
        print(f"\n저장: {args.json}")


if __name__ == "__main__":
    sys.exit(main())
