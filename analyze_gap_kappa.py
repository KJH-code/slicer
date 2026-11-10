"""analyze_gap_kappa.py — 판정식의 숨은 가정을 흔들면 '밴드 vs 균일' 이 유지되는가.

판정식은 그대로 `analytic.py` 의 g(θ) = n_z·cosθ + d·n_r·sinθ 하나다. 이 스크립트는
**g 는 건드리지 않고** 그 식에 들어가는 두 수 — 문턱 κ 와 각도 θ — 에 박혀 있는
가정만 바꿔 본다. 새 판정 기준을 제안하는 것이 아니라 **민감도**를 재는 것이다.

## 흔드는 가정 셋

1. **κ = −sin45° 고정** — 45° 는 슬라이서 관례다(Cura 50°, Orca 60° — config.py 주석).
   → 문턱을 35~60° 로 훑는다 (`threshold_deg` 인자 그대로).
2. **κ 가 층 두께와 무관** — 45° 규칙의 물리는 '한 층에 비드가 옆으로 밀리는 양 ÷
   비드 폭' 이다. 층 법선 두께가 t_n = h·m·cosθ 이면 같은 겹침을 주는 각은
   `tanα* = tan45° / (m·cosθ)` 다. 균일 원뿔은 느슨해지고(cosθ<1) 팽창 블렌드(m=1.5)는
   빡빡해진다. → '두께 반영 κ'.
3. **'아래' = 층 법선** — 헤드 틸트식에서는 층이 중력에 대해 θ 만큼 기운 채 쌓인다.
   비드 접착은 층 기준이지만 처짐은 중력 기준이다. 처짐이 지배한다면 원뿔각의
   효과는 줄어든다. → θ_eff = (1−λ)·θ, λ = 0(현행) … 1(원뿔 효과 없음).
   λ 의 참값은 계산으로 알 수 없다 — **실물이 정한다.**

## 무엇을 내나 (17 모델: 구 + 허리 6 + XY 스케일 5 + 로브 5)

* 현행 선택(균일 J 최선 / 밴드2 J 최선)을 **대안 판정으로 다시 채점**
* 대안 판정으로 **다시 선택**(J 안의 서포트 항만 교체)했을 때 고르는 각도와 승패
* 선택된 밴드2 프로필의 **실제 층간격 배율** — 명목(`max_spacing_factor`)과
  면 중심의 정확 Z′ 로 잰 값을 나란히

'승' = 파레토 우세(예측 서포트 %·평균|θ| 둘 다 낫거나 같고 하나는 엄격히 낫다).
⚠ 여기 서포트 % 는 **메시 면적 비율**(예측)이다. 툴패스 오버행 %p 가 아니다.

    python3 analyze_gap_kappa.py            # 약 10 분
    python3 analyze_gap_kappa.py --quick    # 다시 선택 생략 (약 2 분)
"""

import argparse
import json
import sys
import time

import numpy as np

import conical.varangle as varangle
from analyze_blend_ratio import build_specs
from conical.analytic import radial_normal, support_fraction
from conical.config import DEFAULT_K, MAX_SPACING_FACTOR, THRESHOLD_DEG
from conical.meshio import RadiusProfile

THRESHOLDS = (35.0, 40.0, 45.0, 50.0, 55.0, 60.0)
LAMBDAS = (0.25, 0.5, 1.0)


class Faces:
    """면 중심·법선·면적을 한 번만 뽑아 둔다."""

    def __init__(self, mesh):
        c = mesh.vertices[mesh.faces].mean(axis=1)
        self.z = c[:, 2]
        self.r = np.hypot(c[:, 0], c[:, 1])
        self.nz = mesh.face_normals[:, 2]
        self.nr = radial_normal(mesh)
        self.area = mesh.area_faces
        self.total = float(self.area.sum())

    def local(self, prof):
        """면마다 정확 Z′ 로 조회한 (θ rad, m)."""
        zw = prof.solve_forward(self.z, self.r, "outward")
        th = np.radians(prof.theta_at(zw))
        return th, prof.spacing_factor(zw, self.r, "outward"), zw

    def support(self, prof, mode="fixed", thr=THRESHOLD_DEG, lam=0.0):
        th, m, _ = self.local(prof)
        if mode == "gravity":
            th = (1.0 - lam) * th
        g = self.nz * np.cos(th) + self.nr * np.sin(th)
        if mode == "thick":
            crit = np.arctan(np.tan(np.radians(thr))
                             / np.maximum(m * np.cos(th), 1e-6))
            kappa = -np.sin(crit)
        else:
            kappa = -np.sin(np.radians(thr))
        return float(self.area[g < kappa].sum() / self.total * 100.0)

    def mean_abs(self, prof):
        return float((np.abs(prof.theta_at(self.z)) * self.area).sum() / self.total)

    def spacing(self, prof, limit=MAX_SPACING_FACTOR):
        """블렌드 Z′ 구간에 실제로 걸린 면들의 층간격 배율."""
        th, m, zw = self.local(prof)
        inb = np.zeros(len(zw), dtype=bool)
        for a, b in prof.blend_intervals():
            inb |= (zw > a) & (zw < b)
        if not inb.any():
            return None
        bad = inb & ((m > limit + 1e-6) | (m < 1.0 / limit - 1e-6))
        # J 의 blend_penalty 가 세는 면(실공간 z 로 블렌드 안)
        inz = np.zeros(len(zw), dtype=bool)
        for a, b in prof.blend_intervals():
            inz |= (self.z >= a) & (self.z <= b)
        return {"m_max": float(m[inb].max()), "m_min": float(m[inb].min()),
                "r_max_in_blend": float(self.r[inb].max()),
                "area_in_blend_pct": float(self.area[inb].sum() / self.total * 100),
                "area_violating_pct": float(self.area[bad].sum() / self.total * 100),
                "area_counted_by_J_pct": float(self.area[inz].sum() / self.total * 100)}


def select(mesh, rp, r_max, n, thr=THRESHOLD_DEG, alt=None):
    """`select_banded_j` 를 그대로 쓰되, alt 가 있으면 J 의 서포트 항만 바꾼다."""
    orig = varangle.support_fraction_profile
    if alt is not None:
        varangle.support_fraction_profile = alt
    try:
        r = varangle.select_banded_j(mesh, DEFAULT_K, n, r_max, rp,
                                     MAX_SPACING_FACTOR, threshold_deg=thr)
    finally:
        varangle.support_fraction_profile = orig
    return r["profile_obj"], [round(float(t), 1) for t in r["thetas"]]


def verdict(su, au, sb, ab, tol=1e-9):
    if abs(su - sb) < tol and abs(au - ab) < tol:
        return "동일"
    if sb <= su + tol and ab <= au + tol:
        return "밴드"
    if su <= sb + tol and au <= ab + tol:
        return "균일"
    return "교환"


def tally(vs):
    return {k: vs.count(k) for k in ("밴드", "균일", "교환", "동일")}


def criteria():
    out = [(f"문턱 {t:g}°" + (" (현행)" if t == THRESHOLD_DEG else ""),
            dict(mode="fixed", thr=t)) for t in THRESHOLDS]
    out.append(("두께 반영 κ(m,θ)", dict(mode="thick")))
    out += [(f"중력 혼합 λ={lam:g}", dict(mode="gravity", lam=lam)) for lam in LAMBDAS]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    specs = build_specs(asym=True)
    crits = criteria()
    reselect = [] if args.quick else [
        ("문턱 40°", dict(mode="fixed", thr=40.0)),
        ("문턱 50°", dict(mode="fixed", thr=50.0)),
        ("문턱 60°", dict(mode="fixed", thr=60.0)),
        ("두께 반영 κ(m,θ)", dict(mode="thick")),
        ("중력 혼합 λ=0.25", dict(mode="gravity", lam=0.25)),
    ]
    rows = []
    for name, build in specs:
        t0 = time.time()
        mesh = build()
        fc = Faces(mesh)
        rp = RadiusProfile(mesh)
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        pu, tu = select(mesh, rp, r_max, 1)
        pb, tb = select(mesh, rp, r_max, 2)
        row = {"model": name, "uniform": tu, "band2": tb,
               "planar_support": support_fraction(mesh, 0.0, "outward"),
               "nominal_m": pb.max_spacing_factor(r_max, "outward", rp),
               "spacing": fc.spacing(pb), "rescored": {}, "reselected": {}}
        au, ab = fc.mean_abs(pu), fc.mean_abs(pb)
        for cname, kw in crits:
            su, sb = fc.support(pu, **kw), fc.support(pb, **kw)
            row["rescored"][cname] = {"S_uniform": su, "S_band2": sb,
                                      "verdict": verdict(su, au, sb, ab)}
        for cname, kw in reselect:
            if kw["mode"] == "fixed":
                qu, t1 = select(mesh, rp, r_max, 1, thr=kw["thr"])
                qb, t2 = select(mesh, rp, r_max, 2, thr=kw["thr"])
            else:
                def alt(_mesh, prof, _thr=THRESHOLD_DEG, _kw=kw, _fc=fc):
                    return _fc.support(prof, **_kw)
                qu, t1 = select(mesh, rp, r_max, 1, alt=alt)
                qb, t2 = select(mesh, rp, r_max, 2, alt=alt)
            su, sb = fc.support(qu, **kw), fc.support(qb, **kw)
            row["reselected"][cname] = {
                "uniform": t1, "band2": t2, "S_uniform": su, "S_band2": sb,
                "verdict": verdict(su, fc.mean_abs(qu), sb, fc.mean_abs(qb))}
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        sp = row["spacing"]
        print(f"{name:<14} 균일 {tu}  밴드2 {tb}  "
              + (f"층간격 명목 {row['nominal_m']:.2f} / 실제 "
                 f"{sp['m_min']:.2f}~{sp['m_max']:.2f} (r≤{sp['r_max_in_blend']:.1f})"
                 if sp else "블렌드 없음") + f"  [{row['seconds']}s]", flush=True)

    print("\n[A] 현행 선택을 대안 판정으로 다시 채점 — 17 모델 판정 집계")
    print(f"{'판정':<22}{'밴드':>5}{'균일':>5}{'교환':>5}{'동일':>5}   램프(허리 r=2): 균일 S → 밴드2 S")
    lamp = next(r for r in rows if r["model"] == "허리 r=2")
    for cname, _kw in crits:
        t = tally([r["rescored"][cname]["verdict"] for r in rows])
        lr = lamp["rescored"][cname]
        print(f"{cname:<22}{t['밴드']:>5}{t['균일']:>5}{t['교환']:>5}{t['동일']:>5}   "
              f"{lr['S_uniform']:.2f} → {lr['S_band2']:.2f} ({lr['verdict']})")
    if reselect:
        print("\n[B] 대안 판정으로 다시 선택 — 17 모델 판정 집계")
        print(f"{'판정':<22}{'밴드':>5}{'균일':>5}{'교환':>5}{'동일':>5}   램프: 균일 → 밴드2")
        for cname, _kw in reselect:
            t = tally([r["reselected"][cname]["verdict"] for r in rows])
            lr = lamp["reselected"][cname]
            print(f"{cname:<22}{t['밴드']:>5}{t['균일']:>5}{t['교환']:>5}{t['동일']:>5}   "
                  f"{lr['uniform']} {lr['S_uniform']:.2f} → {lr['band2']} "
                  f"{lr['S_band2']:.2f} ({lr['verdict']})")

    print("\n[C] 선택된 밴드2 프로필의 층간격 배율 — 명목 vs 실제(정확 Z′)")
    print(f"{'모델':<14}{'밴드2':>14}{'명목 m':>8}{'실제 m 범위':>14}{'블렌드 r 최대':>12}"
          f"{'위반 면적%':>10}{'J 가 센 면적%':>12}{'실제 블렌드 면적%':>14}")
    nviol = 0
    for r in rows:
        sp = r["spacing"]
        if sp is None:
            print(f"{r['model']:<14}{str(r['band2']):>14}   (균일로 수렴 — 블렌드 없음)")
            continue
        nviol += sp["area_violating_pct"] > 0
        print(f"{r['model']:<14}{str(r['band2']):>14}{r['nominal_m']:>8.2f}"
              f"{sp['m_min']:>7.2f}~{sp['m_max']:<5.2f}{sp['r_max_in_blend']:>12.1f}"
              f"{sp['area_violating_pct']:>10.2f}{sp['area_counted_by_J_pct']:>12.2f}"
              f"{sp['area_in_blend_pct']:>14.2f}")
    nb = sum(r["spacing"] is not None for r in rows)
    print(f"→ 블렌드가 있는 {nb} 모델 중 {nviol} 개에서 실제 배율이 "
          f"[1/{MAX_SPACING_FACTOR}, {MAX_SPACING_FACTOR}] 를 벗어난다")

    with open("gap_kappa_results.json", "w") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print("\n저장: gap_kappa_results.json")


if __name__ == "__main__":
    sys.exit(main())
