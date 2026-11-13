"""analyze_gap_sample.py — 17 모델의 '밴드 우세' 는 어디서, 무엇과 비교해서 나오나.

## 왜

`analyze_gap_frame.py` 가 실험 A 파일에서 본 것: 대표 지표(진짜 오버행 %p, 낙관)가
**전부 구의 바닥 극점 바로 위**(층 2~5, 베드 위 0.4~1.0mm)에서 나온다. 그리고
밴드2 `[30°, 0°]` 는 그 자리에서 균일 24° 보다 각이 크다 — 밴드라서가 아니라
**아랫밴드가 30° 라서** 이긴 것일 수 있다.

표본 17 개는 전부 '구(또는 구 + 목 + 나팔)' 계열이라 **바닥이 모두 같은 모양**이다.
그렇다면 같은 일이 17 개 전체에서 일어나고 있을 것이다. 이 스크립트가 그걸 잰다.

## 재는 것 (모델마다, 기본 층고 0.4 — docs/verification.md 의 17 모델 표와 같은 경로)

* 균일(J 최선) · 밴드2(J 최선) · **균일(밴드2 의 아랫각)** 의 진짜 오버행 —
  %p(페리미터 총 길이 대비)와 **미지지 길이 mm** 를 둘 다. 원뿔각이 크면 층이 촘촘해져
  페리미터 총 길이(분모)가 늘어나므로, 같은 미지지 길이가 다른 %p 로 보고된다
* 그 오버행 중 **바닥에서 2mm 안**에 있는 몫
* 판정 두 가지(gap_audit J1 의 두 기준선): 밴드2 대 균일(J 최선) / 밴드2 대 균일(아랫각)
* 낙관(기본)과 비관(연쇄, `require_supported_below`) 지지 모형을 둘 다

각도는 **매번 지금 코드로 다시 고른다.** (2026-11-10 까지는 `gap_kappa_results.json` 에
저장된 선택을 읽었다. 블렌드 반경 조회를 고친 뒤(F1) 선택이 여럿 바뀌어서, 저장된
선택을 읽으면 **옛 프로필을 새 코드로 재는** 꼴이 된다.)
판정식·검사기는 저장소 것 그대로다. 새 기준은 없다 — **비교 상대만 더 둔다.**

그 앞에 해석식만으로 나오는 표 하나: **각도 비용을 0 으로 두면**(k=0) 균일 원뿔과
이상적 밴드(블렌드 무시, `select_banded`)가 도달하는 예측 서포트 최소값. 둘이 같다면
이 표본에서 밴드가 균일을 **서포트 축에서** 이길 여지는 원래 없고, '우세' 는 전부
J 의 각도 비용 항이 만든 것이다.

## `--bed-cap` — REP5X 베드 상한을 두 팔에 다 건다 (2026-11-10 추가)

헤드 틸트식(REP5X)은 기운 노즐 몸통이 베드를 치므로 **베드에 닿는 층**의 각도가
B_safe 를 넘을 수 없다(`conical.rep5x.b_safe`, 층고 0.3 에서 계획기 값 22.79° ≈ 22.8°).
표본의 균일(J) 각 17 개 중 다수와 밴드2 아랫각 대부분이 그보다 크다 — 지금까지의
승패표는 **이 기계에서 못 뽑는 프로필끼리의 비교**다. 그래서 팔마다 상한을 건 것을 같이 잰다:

* **균일(상한)** — |θ| ≤ B_safe 안에서 J 최선인 균일 원뿔. 진짜 균일이다(`--strict` 와 같은 뜻).
  각도 격자가 2° 라 실제로는 22° 이하다
* **밴드2(상한)** — 아랫밴드 |θ₁| ≤ B_safe 조건에서 J 최선인 밴드2 (격자 전수).
  위 밴드는 자유지만, 만들어진 프로필이 `bed_safe_profile` 을 그대로 통과해야 한다
  (위 밴드의 층이 베드까지 내려오면 탈락)
* **균일(상한 밴드2 의 아랫각)** — J1 의 둘째 기준선
* **계획기 램프** — 상한 없이 고른 프로필을 `bed_safe_profile` 에 넣어 나온 것
  (`--strict` 없이 `conical_slice.py --mode rep5x` 가 실제로 내는 프로필). 바닥만 B_safe 로
  낮추고 그 위에서 요청각으로 올린다. **균일 요청도 이 경로를 타면 균일이 아니다** —
  그래서 이름을 '균일 요청 + 램프' 로 따로 둔다

    python3 analyze_gap_sample.py                                  # 층고 0.4, 약 5 분
    python3 analyze_gap_sample.py --layer-height 0.4 0.3 --bed-cap --jobs 3
"""

import argparse
import json
import math
import sys
from multiprocessing import Pool

import numpy as np
import trimesh

import conical.varangle as varangle
from analyze_blend_ratio import build_specs
from compare_waist import mean_abs_angle
from conical.analytic import needs_support, support_fraction
from conical.backtransform import backtransform
from conical.config import (
    ANGLE_STEP,
    BLEND_COST_K,
    BLEND_SHIFT_RATIO,
    DEFAULT_K,
    MAX_ANGLE_DEG,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.meshio import RadiusProfile
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile
from conical.rep5x import bed_safe_profile
from conical.toolpath import check_support, classify_unsupported, sample_extrusions
from conical.transform import transform_cone_profile

LAYER_H = 0.4
NEAR_BED = 2.0
# REP5X 베드 상한: `bed_safe_profile` 이 층고 0.3 에서 쓰는 값
# (= floor(b_safe(팁 높이 0.15mm, 여유 0.2 + 계획 여유 0.05)), 공식 뷰어 핫엔드 모델 [추정]).
# 층고 0.4 의 계획기 값은 23.38° 라 이 값이 두 층고 모두에서 안전하다.
BED_CAP = 22.79
BED_CAP_LAYER_H = 0.3          # 상한 팔의 '베드 통과' 여부를 보는 층고 (가장 빡빡한 쪽)


def profile_from(mesh, thetas, rp, r_max):
    """밴드 각도 → 선택기가 만든 것과 같은 프로필."""
    if len(set(thetas)) == 1:
        return AngleProfile.constant(thetas[0])
    _labels, edges = varangle.assign_height_bands(mesh, len(thetas))
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    return AngleProfile.from_bands(varangle._merge_bands(edges, thetas), r_max,
                                   radius_profile=rp,
                                   spacing_limit=MAX_SPACING_FACTOR, max_shift=shift)


def measure(mesh, prof, layer_height=LAYER_H):
    """파이프라인 1회 → 진짜 오버행(낙관·비관)을 %p 와 mm 로, 평균|θ| 와 함께."""
    v = transform_cone_profile(mesh.vertices, prof, "outward")
    warped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=layer_height), prof,
                            "outward")
    pts, mid, w, kinds, lay = sample_extrusions(real, return_types=True,
                                               return_layers=True)
    tot = float(w[kinds == 0].sum())
    z0 = float(mesh.bounds[0][2])
    out = {"perimeter_mm": tot, "angle": mean_abs_angle(mesh, prof)}
    for suffix, chained in (("", False), ("_pes", True)):
        sup, _st = check_support(pts, mid, w, layer_height=layer_height,
                                 require_supported_below=chained)
        over = classify_unsupported(pts, mid, kinds, lay, sup) == 0
        out["pct" + suffix] = float(w[over].sum() / tot * 100.0)
        out["mm" + suffix] = float(w[over].sum())
        # 신호가 어디서 나오나: 바닥 2mm 안의 몫과, 오버행 표본의 높이 범위(바닥 기준)
        near = over & (pts[:, 2] < z0 + NEAR_BED)
        out["near_mm" + suffix] = float(w[near].sum())
        zs = pts[over, 2] - z0
        out["over_z" + suffix] = [float(zs.min()), float(zs.max())] if len(zs) else None
        # 지지 판정 자체의 미지지 몫(단면 안 포함) — 비관 모형이 포화하는지 보는 수
        peri = kinds == 0
        out["peri_unsupported_pct" + suffix] = float(
            w[peri & ~sup].sum() / tot * 100.0)
    return out


def verdict(a, b, tol=1e-9):
    return "밴드2" if b < a - tol else ("균일" if a < b - tol else "무승부")


def verdicts(uni, band):
    """균일 측정 대 밴드 측정 → 지표 넷(낙관·비관 × %p·mm)의 판정."""
    return {"pct": verdict(uni["pct"], band["pct"]),
            "mm": verdict(uni["mm"], band["mm"], 0.5),
            "pct_pes": verdict(uni["pct_pes"], band["pct_pes"]),
            "mm_pes": verdict(uni["mm_pes"], band["mm_pes"], 0.5)}


def zero_cost_table(specs):
    """k=0 에서 균일 / 이상적 밴드2·4 의 예측 서포트 최소 (%)."""
    rows = []
    print("[F] 각도 비용 0 (k=0) 일 때 예측 서포트 최소 % — 균일 vs 이상적 밴드")
    print("    + 서포트로 찍히는 면이 바닥에서 얼마나 높이까지 있나 (평면 / 균일 J 최선각)")
    print(f"{'모델':<14}{'평면':>7}{'균일 최선':>16}{'밴드2 이상':>11}{'밴드4 이상':>11}"
          f"{'밴드2 − 균일':>12}{'면 높이: 평면':>12}{'균일(J)':>14}")
    for name, build in specs:
        mesh = build()
        u = varangle.select_uniform(mesh, 0.0)
        b2 = varangle.select_banded(mesh, 0.0, 2)
        b4 = varangle.select_banded(mesh, 0.0, 4)
        p0 = support_fraction(mesh, 0.0, "outward")
        ang = u["profile"][0][0]
        uj = varangle.select_uniform(mesh, DEFAULT_K)["profile"][0][0]
        cz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2] - mesh.bounds[0][2]
        tops = []
        for a in (0.0, float(uj)):
            need = needs_support(mesh, a, "outward")
            tops.append(float(cz[need].max()) if need.any() else 0.0)
        rows.append({"model": name, "planar": p0, "uniform_angle": ang,
                     "uniform": u["support_pct"], "band2": b2["support_pct"],
                     "band4": b4["support_pct"], "flagged_top_planar_mm": tops[0],
                     "uniform_J_angle": float(uj),
                     "flagged_top_uniform_J_mm": tops[1]})
        print(f"{name:<14}{p0:>7.2f}{ang:>8.0f}° {u['support_pct']:>6.3f}"
              f"{b2['support_pct']:>11.3f}{b4['support_pct']:>11.3f}"
              f"{b2['support_pct'] - u['support_pct']:>12.3f}{tops[0]:>10.2f}mm"
              f"{uj:>6.0f}°{tops[1]:>6.2f}mm")
    n_gain = sum(r["band2"] < r["uniform"] - 1e-9 or r["band4"] < r["uniform"] - 1e-9
                 for r in rows)
    print(f"→ 밴드가 균일보다 예측 서포트를 더 줄이는 모델: {n_gain}/{len(rows)}.  "
          f"균일(J) 각에서 서포트 면의 최고 높이: 최대 "
          f"{max(r['flagged_top_uniform_J_mm'] for r in rows):.2f}mm\n")
    return rows


def select_capped(mesh, rp, r_max, cap, k=DEFAULT_K):
    """아랫밴드 |θ₁| ≤ cap 에서 J 최선인 균일각과 밴드2 를 **격자 전수**로 고른다.

    점수는 선택기(`select_banded_j`)와 같은 경로다: `from_bands` 로 실제 프로필을 만들고
    (층간격 제약 포함), `check_spacing` 에 걸리면 버리고, `profile_objective` 의 J.
    격자는 선택기의 후보(±0~44°, 2°) 그대로다 — 상한 22.79° 면 아랫각은 22° 까지다.
    (상한값 자체를 격자에 넣으면 `[22.79, 22]` 같은 0.79° 짜리 '밴드' 가 J 최선으로
    뽑힌다. 격자가 만든 허상이라 뺐다. 시험 사다리 L3 의 22° 와도 같은 값이 된다.)
    밴드2 는 J 가 큰 순서로 훑어 **`bed_safe_profile` 이 손대지 않는** 첫 프로필을 고른다 —
    위 밴드 각이 커서 그 층이 베드까지 내려오면 기계에서 못 쓰므로 탈락이다.

    반환: (균일각, [θ₁, θ₂], 밴드2 프로필, 탈락한 후보 수)
    """
    _labels, edges = varangle.assign_height_bands(mesh, 2)
    base = support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    grid = sorted({float(s * a) for s in (1, -1)
                   for a in varangle.angle_candidates(MAX_ANGLE_DEG, ANGLE_STEP)})
    low = [t for t in grid if abs(t) <= cap + 1e-9]

    def score(thetas):
        try:
            prof = AngleProfile.from_bands(
                varangle._merge_bands(edges, thetas), r_max, radius_profile=rp,
                spacing_limit=MAX_SPACING_FACTOR, max_shift=shift)
        except ValueError:
            return None
        if prof.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp):
            return None
        m = profile_objective_j(mesh, prof, base, k, rp)
        return m, prof

    def passes_bed(prof):
        return not bed_safe_profile(prof, rp, BED_CAP_LAYER_H)[1]["changed"]

    uni = [(score([t, t]), t) for t in low]
    uni = [(s[0], t) for s, t in uni if s is not None]
    theta_u = max(uni, key=lambda x: (round(x[0], 9), -abs(x[1])))[1]

    cands = []
    for t1 in low:
        for t2 in grid:
            s = score([t1, t2])
            if s is not None:
                cands.append((s[0], t1, t2, s[1]))
    cands.sort(key=lambda c: (-round(c[0], 9), abs(c[1]) + abs(c[2])))
    rejected = 0
    for _j, t1, t2, prof in cands:
        if passes_bed(prof):
            return theta_u, [t1, t2], prof, rejected
        rejected += 1
    return theta_u, [theta_u, theta_u], AngleProfile.constant(theta_u), rejected


def profile_objective_j(mesh, prof, base, k, rp):
    return varangle.profile_objective(mesh, prof, base, k, BLEND_COST_K, rp,
                                      MAX_SPACING_FACTOR, THRESHOLD_DEG)["J"]


def breakpoints(prof):
    return [[round(float(z), 3), round(float(t), 3)]
            for z, t in zip(prof.zs, prof.thetas_deg, strict=True)]


def run_model(task):
    """모델 하나 — 고르고, 층고마다 팔을 전부 잰다. (프로세스 풀에서 돈다.)"""
    idx, layer_heights, cap = task
    name, build = build_specs(asym=True)[idx]
    mesh = build()
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    su = varangle.select_banded_j(mesh, DEFAULT_K, 1, r_max, rp, MAX_SPACING_FACTOR)
    sb = varangle.select_banded_j(mesh, DEFAULT_K, 2, r_max, rp, MAX_SPACING_FACTOR)
    tu, tb = su["thetas"], sb["thetas"]
    prof_b = sb["profile_obj"]
    capped = select_capped(mesh, rp, r_max, cap) if cap else None

    cache = {}

    def m(prof, lh):
        key = (tuple(np.round(prof.zs, 6)), tuple(np.round(prof.thetas_deg, 6)), lh)
        if key not in cache:
            cache[key] = measure(mesh, prof, lh)
        return cache[key]

    out = []
    for lh in layer_heights:
        mu = m(AngleProfile.constant(tu[0]), lh)
        mb = m(prof_b, lh)
        mc = m(AngleProfile.constant(tb[0]), lh)
        allmm = mu["mm"] + mb["mm"] + mc["mm"]
        share = (mu["near_mm"] + mb["near_mm"] + mc["near_mm"]) / max(allmm, 1e-12)
        vj, vb = verdicts(mu, mb), verdicts(mc, mb)
        row = {"model": name, "layer_height": lh, "uniform": tu, "band2": tb,
               "band2_blend": [[round(a, 2), round(b, 2)]
                               for a, b in prof_b.blend_intervals()],
               "uniform_J": mu, "band2_measured": mb, "uniform_bottom_angle": mc,
               "near_bed_share": share,
               "vs_uniform_J_pct": vj["pct"], "vs_uniform_J_mm": vj["mm"],
               "vs_uniform_bottom_pct": vb["pct"], "vs_uniform_bottom_mm": vb["mm"],
               "vs_uniform_J": vj, "vs_uniform_bottom": vb}
        if capped:
            th_u, th_b, prof_bc, rejected = capped
            cu = m(AngleProfile.constant(th_u), lh)
            cb = m(prof_bc, lh)
            cc = m(AngleProfile.constant(th_b[0]), lh)
            # 계획기 램프: 상한 없이 고른 프로필을 bed_safe_profile 이 고친 것
            ramp_b, info_b = bed_safe_profile(prof_b, rp, lh)
            ramp_u, info_u = bed_safe_profile(AngleProfile.constant(tu[0]), rp, lh)
            rb, ru = m(ramp_b, lh), m(ramp_u, lh)
            row["cap"] = {
                "cap_deg": cap, "uniform": [th_u], "band2": th_b,
                "band2_rejected_by_bed": rejected,
                "uniform_J": cu, "band2_measured": cb, "uniform_bottom_angle": cc,
                "vs_uniform_J": verdicts(cu, cb),
                "vs_uniform_bottom": verdicts(cc, cb),
                "ramp": {"theta_bed": info_b["theta_bed"],
                         "band2_changed": bool(info_b["changed"]),
                         "uniform_changed": bool(info_u["changed"]),
                         "band2_profile": breakpoints(ramp_b),
                         "uniform_profile": breakpoints(ramp_u),
                         "band2_measured": rb, "uniform_request_measured": ru,
                         "vs_uniform_strict": verdicts(cu, rb),
                         "vs_uniform_request": verdicts(ru, rb)}}
        out.append(row)
    return out


def cell(m, pes=False):
    s = "_pes" if pes else ""
    return f"{m['pct' + s]:6.3f} {m['mm' + s]:6.1f}mm"


def fmt(thetas):
    return "[" + ",".join(f"{t:g}" for t in thetas) + "]"


def print_rows(rows, lh):
    print(f"\n━━ 층고 {lh:g}mm ━━ 진짜 오버행(낙관) — %p 는 페리미터 총 길이 대비, "
          "mm 는 미지지 페리미터의 절대 길이")
    print(f"{'모델':<14}{'균일(J)':>8}{'밴드2':>10} |{'균일(J)':>16}{'밴드2':>16}"
          f"{'균일(아랫각)':>16} |{'바닥2mm':>7}{'대 균일(J) %p/mm':>16}"
          f"{'대 균일(아랫각) %p/mm':>20}{'평균|θ| 균일→밴드2':>18}")
    for r in rows:
        mu, mb, mc = r["uniform_J"], r["band2_measured"], r["uniform_bottom_angle"]
        print(f"{r['model']:<14}{fmt(r['uniform']):>8}{fmt(r['band2']):>10} |"
              f"{cell(mu):>16}{cell(mb):>16}{cell(mc):>16} |"
              f"{r['near_bed_share'] * 100:>6.0f}%"
              f"{r['vs_uniform_J']['pct'] + '/' + r['vs_uniform_J']['mm']:>16}"
              f"{r['vs_uniform_bottom']['pct'] + '/' + r['vs_uniform_bottom']['mm']:>20}"
              f"{mu['angle']:>10.1f}→{mb['angle']:.1f}")
    if "cap" not in rows[0]:
        return
    c0 = rows[0]["cap"]
    print(f"\n  베드 상한 {c0['cap_deg']:g}° 를 두 팔에 다 건 것 (낙관)")
    print(f"{'모델':<14}{'균일(상한)':>8}{'밴드2(상한)':>12} |{'균일(상한)':>16}"
          f"{'밴드2(상한)':>16}{'균일(아랫각)':>16} |{'대 균일(상한)':>14}"
          f"{'대 균일(아랫각)':>16}{'평균|θ|':>12} |{'램프: 밴드2':>16}{'균일 요청':>16}"
          f"{'대 균일(상한)':>13}")
    for r in rows:
        c = r["cap"]
        cu, cb, cc = c["uniform_J"], c["band2_measured"], c["uniform_bottom_angle"]
        rp_ = c["ramp"]
        print(f"{r['model']:<14}{fmt(c['uniform']):>8}{fmt(c['band2']):>12} |"
              f"{cell(cu):>16}{cell(cb):>16}{cell(cc):>16} |"
              f"{c['vs_uniform_J']['pct'] + '/' + c['vs_uniform_J']['mm']:>14}"
              f"{c['vs_uniform_bottom']['pct'] + '/' + c['vs_uniform_bottom']['mm']:>16}"
              f"{cu['angle']:>6.1f}→{cb['angle']:.1f} |"
              f"{cell(rp_['band2_measured']):>16}"
              f"{cell(rp_['uniform_request_measured']):>16}"
              f"{rp_['vs_uniform_strict']['pct'] + '/' + rp_['vs_uniform_strict']['mm']:>13}")


def count(rows, getter):
    vs = [getter(r) for r in rows]
    return " · ".join(f"{k} {vs.count(k)}" for k in ("밴드2", "균일", "무승부"))


def print_tally(rows, lh):
    print(f"\n판정 집계 — 층고 {lh:g}mm (작은 쪽이 승; mm 판정은 0.5mm 안이면 무승부)")
    print(f"  {'비교':<34}{'낙관 %p':>22}{'낙관 mm':>22}{'비관 %p':>22}{'비관 mm':>22}")

    def line(label, getter):
        print(f"  {label:<34}" + "".join(
            f"{count(rows, lambda r, k=k: getter(r)[k]):>22}"
            for k in ("pct", "mm", "pct_pes", "mm_pes")))

    line("밴드2 대 균일(J 최선)", lambda r: r["vs_uniform_J"])
    line("밴드2 대 균일(밴드2 아랫각)", lambda r: r["vs_uniform_bottom"])
    if "cap" in rows[0]:
        line("[상한] 밴드2 대 균일(J 최선)", lambda r: r["cap"]["vs_uniform_J"])
        line("[상한] 밴드2 대 균일(아랫각)", lambda r: r["cap"]["vs_uniform_bottom"])
        line("[램프] 밴드2 대 균일(상한, 진짜 균일)",
             lambda r: r["cap"]["ramp"]["vs_uniform_strict"])
        line("[램프] 밴드2 대 균일 요청+램프",
             lambda r: r["cap"]["ramp"]["vs_uniform_request"])
    near = sum(r["uniform_J"]["near_mm"] + r["band2_measured"]["near_mm"]
               + r["uniform_bottom_angle"]["near_mm"] for r in rows)
    tot = sum(r["uniform_J"]["mm"] + r["band2_measured"]["mm"]
              + r["uniform_bottom_angle"]["mm"] for r in rows)
    print(f"  전체 미지지 길이(낙관) 중 바닥 {NEAR_BED:g}mm 안의 몫: {near / tot * 100:.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer-height", type=float, nargs="+", default=[LAYER_H],
                    help=f"층고 mm, 여러 개 가능 (기본 {LAYER_H})")
    ap.add_argument("--bed-cap", type=float, nargs="?", const=BED_CAP, default=None,
                    help=f"REP5X 베드 상한(도)을 두 팔에 건 표를 더한다 (값 생략 시 {BED_CAP})")
    ap.add_argument("--jobs", type=int, default=1, help="모델을 나눠 돌릴 프로세스 수")
    ap.add_argument("--skip-zero-cost", action="store_true",
                    help="해석식 표 [F] 를 건너뛴다")
    ap.add_argument("--json", default="gap_sample_results.json")
    args = ap.parse_args()

    specs = build_specs(asym=True)
    zero = [] if args.skip_zero_cost else zero_cost_table(specs)
    tasks = [(i, tuple(args.layer_height), args.bed_cap) for i in range(len(specs))]
    by_lh = {lh: [] for lh in args.layer_height}
    if args.jobs > 1:
        with Pool(args.jobs) as pool:
            results = pool.imap(run_model, tasks)
            for res in results:
                for row in res:
                    by_lh[row["layer_height"]].append(row)
                print(f"  측정 끝: {res[0]['model']}", flush=True)
    else:
        for t in tasks:
            res = run_model(t)
            for row in res:
                by_lh[row["layer_height"]].append(row)
            print(f"  측정 끝: {res[0]['model']}", flush=True)

    for lh in args.layer_height:
        print_rows(by_lh[lh], lh)
    for lh in args.layer_height:
        print_tally(by_lh[lh], lh)

    first = args.layer_height[0]
    with open(args.json, "w") as fh:
        json.dump({"zero_cost": zero, "toolpath": by_lh[first],
                   "by_layer_height": {f"{lh:g}": rows for lh, rows in by_lh.items()},
                   "meta": {"layer_heights": list(args.layer_height),
                            "bed_cap_deg": args.bed_cap, "near_bed_mm": NEAR_BED,
                            "selection": "매 실행마다 다시 고름 (select_banded_j N=1, 2)",
                            "bed_cap_layer_height": BED_CAP_LAYER_H,
                            "mm_tie_tolerance": 0.5,
                            "angle_grid_deg": ANGLE_STEP,
                            "b_safe_note": "floor(b_safe(0.15mm, 0.25mm)) = "
                                           f"{math.floor(BED_CAP * 100) / 100}"}},
                  fh, ensure_ascii=False, indent=1)
    print(f"\n저장: {args.json}")


if __name__ == "__main__":
    sys.exit(main())
