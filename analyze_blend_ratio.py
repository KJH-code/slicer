"""analyze_blend_ratio.py — 밴드가 균일각을 이기는 조건을 '형상' 이 아니라
'비용/이득 비' 로 쓴다.

## 왜 (문제)

지금까지 이 조건은 **허리 두드러짐**(`meshio.waist_prominence`) 이라는 **형상 지표**
로 말해 왔다 — "허리가 있으면 밴드가 이긴다, 문턱은 0.29~0.57". 그런데 이 지표는
반경의 **비율**이라 **반경 스케일에 눈이 먼다.** 같은 허리 모델을 XY 로만 λ 배 하면
prominence 는 그대로인데 블렌드 폭 `w = r_b·|Δtanθ|/(limit−1)` 은 `r_b ∝ λ` 로
비싸진다. 즉 **같은 prominence 에서 승패가 갈릴 수 있다** — 그리고 실제로 갈린다
(아래 ⑤, 0.571 이 승 3건·패 3건 양쪽에 나온다).

## 무엇을 대신 쓰나

블렌드 비용과 잠재 이득이 **같은 단위(표면적 %)** 라는 점을 쓴다:

    ΔS_ideal = (균일 최적 서포트 %) − (블렌드를 무시한 밴드 최적 서포트 %)   ← 이득
    cost     = varangle.blend_penalty(그 이상적 밴드로 만든 실제 프로필)      ← 비용
    ρ        = cost / ΔS_ideal                                              ← 무차원

`ΔS_ideal` 은 "부위별로 각도를 다르게 주고 **싶은** 정도"이고, `cost` 는 "그러려면
실제로 치러야 하는 값"이다. 둘 다 **밴드 문제를 다 풀기 전에** 해석식으로 싸게
나오므로 ρ 는 사후 설명이 아니라 **예측기**다.

⚠ ρ 는 `select_banded`(블렌드를 모르는 이상적 선택) 와 `blend_penalty` 만 쓴다 —
  실제 출하 선택기 `select_banded_j` 를 돌리지 않는다. 그래야 예측기와 피예측
  대상이 분리된다.

## 표기 (docs/verification.md 의 4단계)

* **증명됨**  : 블렌드 폭 하한 `w ≥ r_b·|Δtanθ|/(limit−1)` (profile.py 에서 유도 닫힘)
* **계산적 관찰** : ρ 가 승패를 예외 없이 분리한다. **문턱 ∈ (5.40, 8.14)**.
                범위 = 아래 `SPECS` 의 12 케이스. **범위 밖은 주장하지 않는다.**
* **반증됨**  : `waist_prominence` 단독은 판정 기준이 **아니다** (⑤ 반례 3건)

⚠ ρ 가 `cost` **단독**보다 나은지는 이 표본으로 **아직 못 가린다** — 둘 다 예외 없이
  분리한다(간격비 ρ 1.51배 vs cost 1.39배). 구별하려면 '이득이 아주 큰데 비용도 큰'
  모델이 필요하다. 지금 표본은 이득이 전부 0.7~2.9%p 라 비용이 판을 지배한다.

실행:
    python3 analyze_blend_ratio.py              # 예측기만 (빠름, 툴패스 없음)
    python3 analyze_blend_ratio.py --measure    # + 툴패스 실측으로 승패 판정 (느림)
    python3 analyze_blend_ratio.py --measure --json out.json
"""

import argparse
import json
import sys
import time

import numpy as np
import trimesh

from conical.meshio import center_on_axis, RadiusProfile, waist_prominence
from conical.varangle import (select_uniform, select_banded, select_banded_j,
                              blend_penalty)
from conical.profile import AngleProfile
from conical.config import (DEFAULT_K, MAX_SPACING_FACTOR, BLEND_SHIFT_RATIO)
from compare_waist import waisted_model, run_pipeline, mean_abs_angle


# ─────────────────────────────────────────────────────────────
# 표본 — 두 축으로 움직인다
#   ① 목 반경 r  : 허리를 깊게 (prominence 가 **움직이는** 축)
#   ② XY 스케일 λ: 허리 깊이는 그대로 두고 뚱뚱하게 (prominence 가 **안 움직이는** 축)
# ②가 이 실험의 핵심이다 — 형상 지표가 못 보는 축이기 때문이다.
# ─────────────────────────────────────────────────────────────
def _sphere(subdiv=3, radius=10.0):
    """⚠ subdivisions=3 은 compare_bands/compare_waist 와 **같은 값이어야 한다** —
    메시 해상도가 면적 비율을 바꿔서 기존 측정값과 비교가 깨진다 (실제로 4 로 두고
    한 번 어긋났다)."""
    return center_on_axis(trimesh.creation.icosphere(subdivisions=subdiv,
                                                     radius=radius))


def widen(mesh, lam):
    """XY 로만 λ 배. 허리 두드러짐은 반경의 비율이라 **불변**이다."""
    m = mesh.copy()
    m.vertices[:, 0] *= lam
    m.vertices[:, 1] *= lam
    m.fix_normals()
    return center_on_axis(m)


def build_specs():
    specs = [("구", _sphere)]
    for r in (7, 5, 4, 3, 2, 1):
        specs.append((f"허리 r={r:g}", (lambda rr: lambda: waisted_model(rr))(r)))
    for lam in (1.1, 1.2, 1.3, 1.5, 2.0):
        specs.append((f"허리3 ×{lam:g}",
                      (lambda l: lambda: widen(waisted_model(3.0), l))(lam)))
    return specs


# ─────────────────────────────────────────────────────────────
# 예측기 — 밴드 문제를 풀기 전에 계산된다
# ─────────────────────────────────────────────────────────────
def predictors(mesh, k=DEFAULT_K):
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    H = float(mesh.bounds[1][2] - mesh.bounds[0][2])
    prom, _, _ = waist_prominence(mesh, radius_profile=rp)

    uni = select_uniform(mesh, k)
    band = select_banded(mesh, k, 2)          # ← 블렌드를 **모르는** 이상적 선택
    dS = uni["support_pct"] - band["support_pct"]

    prof = AngleProfile.from_banded_result(
        band, r_max, radius_profile=rp, spacing_limit=MAX_SPACING_FACTOR,
        max_shift=BLEND_SHIFT_RATIO * H)
    cost = blend_penalty(mesh, prof, rp, MAX_SPACING_FACTOR)
    rho = cost / dS if dS > 1e-9 else float("inf")
    blend_mm = sum(b - a for a, b in prof.blend_intervals())

    return dict(prominence=prom, r_max=r_max, H=H, dS_ideal=dS,
                cost=cost, rho=rho, blend_mm=blend_mm,
                theta_uniform=uni["profile"], theta_ideal=band["profile"],
                _rp=rp, _r_max=r_max)


# ─────────────────────────────────────────────────────────────
# 실측 — 출하 선택기(select_banded_j) + 툴패스 검사기
# ─────────────────────────────────────────────────────────────
def measure(mesh, rp, r_max, k=DEFAULT_K):
    """n=1(균일) vs n=2(밴드) 를 툴패스로 재고 파레토 우세를 판정한다."""
    got = {}
    for n in (1, 2):
        r = select_banded_j(mesh, k, n, r_max, rp, MAX_SPACING_FACTOR)
        prof = r["profile_obj"]
        _peri, _tot, _fill, oh, _ins, _gz = run_pipeline(mesh, prof, breakdown=True)
        got[n] = dict(overhang=oh, angle=mean_abs_angle(mesh, prof),
                      thetas=[round(t, 1) for t in r["thetas"]])
    oh1, oh2 = got[1]["overhang"], got[2]["overhang"]
    a1, a2 = got[1]["angle"], got[2]["angle"]
    return dict(uniform=got[1], banded=got[2],
                ratio=(oh1 / oh2 if oh2 > 0 else float("inf")),
                # '승' = 두 축(오버행·왜곡) 모두에서 밴드가 낫다 (파레토 우세).
                # 오버행만 보면 '왜곡을 더 써서 산 것' 과 구별이 안 된다.
                pareto=bool(oh2 < oh1 and a2 <= a1 + 1e-9))


def separation(rows, key, higher_is_lose=True):
    """이 예측기가 승/패를 겹침 없이 가르나 + 그 경계 구간."""
    win = [r[key] for r in rows if r.get("pareto") is True]
    lose = [r[key] for r in rows if r.get("pareto") is False]
    if not win or not lose:
        return None
    if higher_is_lose:
        lo, hi = max(win), min(lose)
    else:
        lo, hi = max(lose), min(win)
    ok = lo < hi
    gap = (hi / lo) if (ok and lo > 0 and np.isfinite(hi)) else float("nan")
    return dict(separates=ok, low=lo, high=hi, gap_ratio=gap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true",
                    help="툴패스로 실제 승패까지 판정 (느림)")
    ap.add_argument("--k", type=float, default=DEFAULT_K)
    ap.add_argument("--json", default=None, help="결과 JSON 저장 경로")
    args = ap.parse_args()

    rows = []
    for name, build in build_specs():
        mesh = build()
        t0 = time.time()
        p = predictors(mesh, args.k)
        rp, r_max = p.pop("_rp"), p.pop("_r_max")
        rec = dict(name=name, **p)
        if args.measure:
            rec.update(measure(mesh, rp, r_max, args.k))
        rec["seconds"] = round(time.time() - t0, 1)
        rows.append(rec)
        tail = ""
        if args.measure:
            tail = (f"  균일 {rec['uniform']['overhang']:.3f}%p/"
                    f"{rec['uniform']['angle']:.1f}°  밴드2 "
                    f"{rec['banded']['overhang']:.3f}%p/{rec['banded']['angle']:.1f}°"
                    f"  {'승' if rec['pareto'] else '패'}")
        print(f"{name:<12} prom={rec['prominence']:.3f} ΔS={rec['dS_ideal']:>6.2f} "
              f"cost={rec['cost']:>7.2f} ρ={rec['rho']:>8.2f}"
              f" blend={rec['blend_mm']:>6.2f}mm{tail}", flush=True)

    print()
    hdr = (f"{'모델':<12}{'prom':>7}{'ΔS':>7}{'cost':>8}{'ρ':>9}{'blend':>8}"
           + ("  판정" if args.measure else ""))
    print(hdr)
    print("-" * (len(hdr) + 4))
    for r in sorted(rows, key=lambda x: x["rho"]):
        v = ("  " + ("승" if r["pareto"] else "패")) if args.measure else ""
        print(f"{r['name']:<12}{r['prominence']:>7.3f}{r['dS_ideal']:>7.2f}"
              f"{r['cost']:>8.2f}{r['rho']:>9.2f}{r['blend_mm']:>8.2f}{v}")

    if args.measure:
        print("\n[분리 검정]  이 예측기가 승/패를 겹침 없이 가르나")
        for key, label, hil in (("prominence", "waist_prominence", False),
                                ("cost", "blend cost 단독", True),
                                ("rho", "ρ = cost/ΔS", True)):
            s = separation(rows, key, hil)
            if s is None:
                print(f"  {label:<20} 판정 불가 (한쪽 그룹이 비었다)")
                continue
            mark = "분리함" if s["separates"] else "**겹침 — 기준 아님**"
            print(f"  {label:<20} {mark:<22} 경계 {s['low']:.3f} ~ {s['high']:.3f}"
                  + (f"  (간격비 {s['gap_ratio']:.2f}배)"
                     if np.isfinite(s["gap_ratio"]) else ""))
        print("\n  ⚠ 겹침이 나오면 그 지표는 이 표본에서 반증된 것이다.")
        print("  ⚠ 분리해도 '문턱을 그 구간으로 좁혔다' 까지다 — 값을 못 박지 않는다.")

    if args.json:
        json.dump(rows, open(args.json, "w"), ensure_ascii=False, indent=1,
                  default=str)
        print(f"\n저장: {args.json}")


if __name__ == "__main__":
    sys.exit(main())
