"""analyze_gap_sample.py — 17 모델의 '밴드 우세' 는 어디서, 무엇과 비교해서 나오나.

## 왜

`analyze_gap_frame.py` 가 실험 A 파일에서 본 것: 대표 지표(진짜 오버행 %p, 낙관)가
**전부 구의 바닥 극점 바로 위**(층 2~5, 베드 위 0.4~1.0mm)에서 나온다. 그리고
밴드2 `[30°, 0°]` 는 그 자리에서 균일 24° 보다 각이 크다 — 밴드라서가 아니라
**아랫밴드가 30° 라서** 이긴 것일 수 있다.

표본 17 개는 전부 '구(또는 구 + 목 + 나팔)' 계열이라 **바닥이 모두 같은 모양**이다.
그렇다면 같은 일이 17 개 전체에서 일어나고 있을 것이다. 이 스크립트가 그걸 잰다.

## 재는 것 (모델마다, 층고 0.4 — docs/verification.md 의 17 모델 표와 같은 경로)

* 균일(J 최선) · 밴드2(J 최선) · **균일(밴드2 의 아랫각)** 의 진짜 오버행 —
  %p(페리미터 총 길이 대비)와 **미지지 길이 mm** 를 둘 다. 원뿔각이 크면 층이 촘촘해져
  페리미터 총 길이(분모)가 늘어나므로, 같은 미지지 길이가 다른 %p 로 보고된다
* 그 오버행 중 **바닥에서 2mm 안**에 있는 몫
* 판정 두 가지: 밴드2 대 균일(J 최선) / 밴드2 대 균일(아랫각)

각도는 `gap_kappa_results.json` 에 저장된 선택을 그대로 쓴다(없으면 다시 고른다).
판정식·검사기는 저장소 것 그대로다. 새 기준은 없다 — **비교 상대만 하나 더 둔다.**

그 앞에 해석식만으로 나오는 표 하나: **각도 비용을 0 으로 두면**(k=0) 균일 원뿔과
이상적 밴드(블렌드 무시, `select_banded`)가 도달하는 예측 서포트 최소값. 둘이 같다면
이 표본에서 밴드가 균일을 **서포트 축에서** 이길 여지는 원래 없고, '우세' 는 전부
J 의 각도 비용 항이 만든 것이다.

    python3 analyze_gap_kappa.py && python3 analyze_gap_sample.py     # 약 15 분
"""

import json
import os
import sys

import numpy as np
import trimesh

import conical.varangle as varangle
from analyze_blend_ratio import build_specs
from conical.analytic import needs_support, support_fraction
from conical.backtransform import backtransform
from conical.config import (
    BLEND_SHIFT_RATIO,
    DEFAULT_K,
    MAX_SPACING_FACTOR,
)
from conical.meshio import RadiusProfile
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile
from conical.toolpath import check_support, classify_unsupported, sample_extrusions
from conical.transform import transform_cone_profile

LAYER_H = 0.4
NEAR_BED = 2.0


def profile_from(mesh, thetas, rp, r_max):
    """저장된 밴드 각도 → 선택기가 만든 것과 같은 프로필."""
    if len(set(thetas)) == 1:
        return AngleProfile.constant(thetas[0])
    _labels, edges = varangle.assign_height_bands(mesh, len(thetas))
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    return AngleProfile.from_bands(varangle._merge_bands(edges, thetas), r_max,
                                   radius_profile=rp,
                                   spacing_limit=MAX_SPACING_FACTOR, max_shift=shift)


def measure(mesh, prof):
    v = transform_cone_profile(mesh.vertices, prof, "outward")
    warped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=LAYER_H), prof, "outward")
    pts, mid, w, kinds, lay = sample_extrusions(real, return_types=True,
                                               return_layers=True)
    sup, _st = check_support(pts, mid, w, layer_height=LAYER_H)
    over = classify_unsupported(pts, mid, kinds, lay, sup) == 0
    tot = float(w[kinds == 0].sum())
    z0 = float(mesh.bounds[0][2])
    near = over & (pts[:, 2] < z0 + NEAR_BED)
    return {"pct": float(w[over].sum() / tot * 100.0), "mm": float(w[over].sum()),
            "near_mm": float(w[near].sum()), "perimeter_mm": tot}


def verdict(a, b, tol=1e-9):
    return "밴드2" if b < a - tol else ("균일" if a < b - tol else "무승부")


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


def main():
    specs = build_specs(asym=True)
    zero = zero_cost_table(specs)
    saved = {}
    if os.path.exists("gap_kappa_results.json"):
        with open("gap_kappa_results.json") as fh:
            data = json.load(fh)
        saved = {r["model"]: r for r in data["models"]}
    rows = []
    print("진짜 오버행 — %p 는 페리미터 총 길이 대비, mm 는 미지지 페리미터의 절대 길이")
    print(f"{'모델':<14}{'균일(J)':>8}{'밴드2':>13} |{'균일(J)':>14}{'밴드2':>14}"
          f"{'균일(아랫각)':>14} |{'바닥2mm':>7}{'대 균일(J)':>9}{'대 균일(아랫각) %p / mm':>22}")
    for name, build in specs:
        mesh = build()
        rp = RadiusProfile(mesh)
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        if name in saved:
            tu, tb = saved[name]["uniform"], saved[name]["band2"]
        else:
            tu = varangle.select_banded_j(mesh, DEFAULT_K, 1, r_max, rp,
                                          MAX_SPACING_FACTOR)["thetas"]
            tb = varangle.select_banded_j(mesh, DEFAULT_K, 2, r_max, rp,
                                          MAX_SPACING_FACTOR)["thetas"]
        mu = measure(mesh, AngleProfile.constant(tu[0]))
        mb = measure(mesh, profile_from(mesh, tb, rp, r_max))
        mc = measure(mesh, AngleProfile.constant(tb[0]))
        allmm = mu["mm"] + mb["mm"] + mc["mm"]
        share = (mu["near_mm"] + mb["near_mm"] + mc["near_mm"]) / max(allmm, 1e-12)
        row = {"model": name, "uniform": tu, "band2": tb, "uniform_J": mu,
               "band2_measured": mb, "uniform_bottom_angle": mc,
               "near_bed_share": share,
               "vs_uniform_J_pct": verdict(mu["pct"], mb["pct"]),
               "vs_uniform_J_mm": verdict(mu["mm"], mb["mm"], 0.5),
               "vs_uniform_bottom_pct": verdict(mc["pct"], mb["pct"]),
               "vs_uniform_bottom_mm": verdict(mc["mm"], mb["mm"], 0.5)}
        rows.append(row)

        def cell(m):
            return f"{m['pct']:6.3f} {m['mm']:5.1f}mm"
        print(f"{name:<14}{str(tu):>8}{str(tb):>13} |{cell(mu):>14}{cell(mb):>14}"
              f"{cell(mc):>14} |{share * 100:>6.0f}%{row['vs_uniform_J_pct']:>9}"
              f"{row['vs_uniform_bottom_pct'] + ' / ' + row['vs_uniform_bottom_mm']:>22}",
              flush=True)

    def count(key):
        vs = [r[key] for r in rows]
        return {k: vs.count(k) for k in ("밴드2", "균일", "무승부")}

    print("\n판정 집계 (작은 쪽이 승, 낙관 지지, 층고 0.4; mm 판정은 0.5mm 안이면 무승부)")
    print(f"  밴드2 대 균일(J 최선)       %p: {count('vs_uniform_J_pct')}   "
          f"mm: {count('vs_uniform_J_mm')}")
    print(f"  밴드2 대 균일(밴드2 아랫각) %p: {count('vs_uniform_bottom_pct')}   "
          f"mm: {count('vs_uniform_bottom_mm')}")
    near = sum(r["uniform_J"]["near_mm"] + r["band2_measured"]["near_mm"]
               + r["uniform_bottom_angle"]["near_mm"] for r in rows)
    tot = sum(r["uniform_J"]["mm"] + r["band2_measured"]["mm"]
              + r["uniform_bottom_angle"]["mm"] for r in rows)
    print(f"  전체 미지지 길이 중 바닥 {NEAR_BED:g}mm 안의 몫: {near / tot * 100:.1f}%")
    with open("gap_sample_results.json", "w") as fh:
        json.dump({"zero_cost": zero, "toolpath": rows}, fh, ensure_ascii=False,
                  indent=1)
    print("\n저장: gap_sample_results.json")


if __name__ == "__main__":
    sys.exit(main())
