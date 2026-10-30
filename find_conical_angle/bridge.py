"""
bridge.py — 팀메 탐색 알고리즘(conical_slicing) ↔ 우리 검증 도구(conical/) 다리.

하는 일 셋:
  1. 파일이 아니라 **메시**에서 바로 돌린다 (`center_on_axis` 한 trimesh. 축 = (0,0),
     바닥 = z=0 이라 팀메 config 의 axis_x/y=0, bed_z=0 과 맞는다).
  2. κ 규칙을 고를 수 있다 — `adaptive`(팀메: 성분별 q 에서) / `fixed`(우리:
     −sin(임계각)). 팀메 코드는 안 고치고 성분의 `kappa` 를 바꿔 넣는다.
  3. 팀메 밴드 계획 → 우리 `AngleProfile` 로 바꾼다. 전이는 팀메가 적은 중점 h 에
     두고, 블렌드 폭·층간격 제약은 우리 `profile.py` 가 건다 (= 검증 도구 동일).
     밴드가 없는 높이(오버행 성분이 없는 곳)는 이웃 밴드 각도를 그대로 잇는다.

반환되는 dict 의 키:
  uniform      {"direction","angle","signed","loss"}   팀메 모델 전체 각도
  bands        팀메 밴드 그대로 (h 구간·부호 각·성분)
  transitions  팀메 전이 그대로
  profile      AngleProfile — 층간격 제약 **적용** (우리 파이프라인에 그대로 넣는다)
  profile_raw  AngleProfile — 제약 없음(블렌드 최소 폭만). 팀메 계획 '그대로'의 근사
  components   성분 요약 (면 수·면적·q·κ·방향별 위반 면적)
  prepared / raw  팀메 객체 (디버그용)
"""

import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from conical_slicing.bands import plan_slice_bands  # 팀메
from conical_slicing.config import load_config
from conical_slicing.evaluation import evaluate_model
from conical_slicing.mesh import find_overhang_components, prepare_mesh

from conical.config import (
    BLEND_SHIFT_RATIO,
    MAX_ANGLE_DEG,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.meshio import RadiusProfile
from conical.profile import AngleProfile

KAPPA_RULES = ("adaptive", "fixed")


def _config(angle_min, angle_max, overrides):
    ov = {"angle_min": float(angle_min), "angle_max": float(angle_max),
          "axis_x": 0.0, "axis_y": 0.0, "bed_z": 0.0}
    if overrides:
        ov.update(overrides)
    return load_config(path=os.path.join(_HERE, "config.json"), overrides=ov)


def analyze(mesh, kappa_rule="adaptive", angle_min=0.0, angle_max=MAX_ANGLE_DEG,
            threshold_deg=THRESHOLD_DEG, overrides=None, spacing_limit=MAX_SPACING_FACTOR,
            max_shift=None, quantile=None, bed_tolerance=None, method="mean",
            angle_step=2.0, outward_only=False, reselect=None, tol_pct=0.0):
    """팀메 탐색을 메시에 돌리고 우리 프로필로 바꾼다. 모듈 docstring 참조.

    quantile: None 이면 원본(면적 가중 평균). 0~1 이면 면적 가중 분위수 —
              1.0 = 모든 면의 최소각을 만족하는 각(전부 통과). [수정 ① 2026-10-30]
    method: "mean"(원본) / "sweep"(손실 최소 전수, 수정 ②). quantile 은 mean 에만 적용.
    outward_only: inward 평가를 건너뛴다 (수정 ②).
    reselect: None(팀메 각도 그대로) / "all"(수정 ③: 팀메 **경계**는 두고 밴드 각도를
              그 높이의 **모든 면**(바닥 제외)으로 우리 자에서 격자 전수해 다시 고른다.
              팀메 손실은 성분 면만 세어 부수피해를 모른다 — NOTES.md 수정 ② 결과).
    tol_pct:  reselect="all" 에서 밴드 서포트 최소값 + tol 안에 드는 가장 작은 각을 고른다
              (기울기 허용폭, ε-제약의 밴드판). 0 이면 순수 최소.
    bed_tolerance: 팀메 바닥 판정 높이(세 꼭짓점이 전부 bed_z±tol). 원본 1e-6 은
              구의 극점·거친 바닥면을 오버행으로 센다(램프 p=1 이 43.6° 로 가는 이유,
              AnkleBase 20° inward). 우리 바닥 마스크(0.3mm)와 맞추려면 0.3.
    """
    if kappa_rule not in KAPPA_RULES:
        raise ValueError(f"kappa_rule 은 {KAPPA_RULES} 중 하나")
    ov = dict(overrides or {})
    if bed_tolerance is not None:
        ov["bed_tolerance"] = float(bed_tolerance)
    cfg = _config(angle_min, angle_max, ov)
    prepared = prepare_mesh(mesh, cfg)
    comps = find_overhang_components(prepared, cfg)
    if kappa_rule == "fixed":
        k = -math.sin(math.radians(threshold_deg))
        for c in comps:
            if c.valid:
                c.kappa = k
    evaluations, direction_results, selected = evaluate_model(
        comps, cfg["angle_min"], cfg["angle_max"], quantile, method, angle_step, outward_only)
    plan = plan_slice_bands(prepared, comps, cfg["angle_min"], cfg["angle_max"],
                            cfg["height_overlap_tolerance"], quantile, method, angle_step,
                            outward_only)

    sign = 1.0 if selected["direction"] == "outward" else -1.0
    uniform = {"direction": selected["direction"], "angle": float(selected["angle"]),
               "signed": sign * float(selected["angle"]),
               "loss": float(selected["model_loss"]), "status": selected["status"]}

    comp_rows = []
    for c in comps:
        ev = evaluations[c.component_id]
        row = {"id": c.component_id, "faces": len(c.face_indices), "area": float(c.area),
               "q": c.q, "kappa": c.kappa, "bed_supported": bool(c.bed_supported)}
        for d in ("outward", "inward"):
            e = ev.get(d, {})
            row[d] = {"angle": e.get("selected_angle"),
                      "allows_all": e.get("selected_angle_allows_all"),
                      "violating_area": e.get("violating_area"),
                      "infeasible_area": e.get("infeasible_area")}
        comp_rows.append(row)

    z0, z1 = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    rp = RadiusProfile(mesh)
    if max_shift is None:
        max_shift = BLEND_SHIFT_RATIO * (z1 - z0)
    band_list = bands_to_intervals(plan, z0, z1)
    reselect_info = None
    if reselect == "all":
        band_list, reselect_info = reselect_all_faces(mesh, band_list, angle_max, angle_step,
                                                      threshold_deg, tol_pct)
    profile, profile_err = _try_profile(band_list, r_max, radius_profile=rp,
                                        spacing_limit=spacing_limit, max_shift=max_shift)
    profile_raw, _ = _try_profile(band_list, r_max)

    return {"uniform": uniform, "direction_results": direction_results,
            "bands": plan["bands"], "transitions": plan["transitions"],
            "band_intervals": band_list, "profile": profile, "profile_raw": profile_raw,
            "profile_error": profile_err,
            "components": comp_rows, "kappa_rule": kappa_rule, "quantile": quantile,
            "method": method, "outward_only": outward_only, "reselect": reselect,
            "tol_pct": tol_pct, "reselect_info": reselect_info, "config": cfg,
            "prepared": prepared, "raw": {"components": comps, "plan": plan,
                                           "evaluations": evaluations}}


def reselect_all_faces(mesh, band_list, angle_max, angle_step, threshold_deg, tol_pct=0.0):
    """[수정 ③] 밴드 경계는 그대로, 각도는 그 z 구간의 **모든 면**으로 다시 고른다.

    각 밴드 [z_lo, z_hi) 에 중심이 있는 면(바닥 접촉 면 제외)에 대해 outward 0~angle_max
    를 angle_step 격자로 훑어 남은 서포트 면적을 세고, 최소값 + tol_pct(그 밴드 면적
    기준 %p) 안에 드는 가장 작은 각을 고른다. 각도가 같은 이웃 밴드는 합친다.
    자는 `conical.s3io.support_fraction_dirs` 와 같다 (g = n̂·b̂ < −sin(threshold)).
    """
    from conical.s3io import bed_contact_mask, cone_dirs
    cz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    bed = bed_contact_mask(mesh)
    areas = mesh.area_faces
    kappa = -math.sin(math.radians(threshold_deg))
    grid = [i * angle_step for i in range(int(math.floor(angle_max / angle_step + 1e-9)) + 1)]
    if grid[-1] < angle_max - 1e-9:
        grid.append(float(angle_max))
    gs = {a: np.einsum("ij,ij->i", mesh.face_normals, cone_dirs(mesh, a)) for a in grid}
    out, info = [], []
    for i, (lo, hi, old) in enumerate(band_list):
        inb = (cz >= lo) & ((cz < hi) if i < len(band_list) - 1 else (cz <= hi)) & ~bed
        tot = float(areas[inb].sum())
        if tot <= 0:
            th = out[-1][2] if out else 0.0
            info.append({"band": i, "faces": 0, "theta": th, "note": "면 없음 → 이웃 각"})
        else:
            sup = {a: float(areas[inb & (gs[a] < kappa)].sum() / tot * 100.0) for a in grid}
            best = min(sup.values())
            th = min(a for a in grid if sup[a] <= best + tol_pct + 1e-12)
            info.append({"band": i, "faces": int(inb.sum()), "theta_teammate": float(old),
                         "theta": float(th), "support_min": best, "support_at": sup[th],
                         "support_teammate": sup.get(min(grid, key=lambda a: abs(a - abs(old))))})
        if out and abs(out[-1][2] - th) < 1e-12:
            out[-1] = (out[-1][0], hi, th)
        else:
            out.append((lo, hi, float(th)))
    return out, info


def _try_profile(band_list, r_max, **kw):
    """from_bands 는 블렌드가 서로 겹치면 ValueError 를 낸다(밴드가 너무 좁다).
    팀메 계획은 그 제약을 모르므로 실패가 정상이다 — None 과 사유를 돌려준다.
    (armadillo 에서 처음 났다: 경계 5.01 에 폭 29.49mm 블렌드가 필요했다.)"""
    try:
        return AngleProfile.from_bands(band_list, r_max, **kw), None
    except ValueError as exc:
        return None, str(exc)


def bands_to_intervals(plan, z_bottom, z_top):
    """팀메 밴드(h 구간, 부호 각) → 우리 from_bands 입력 [(z_lo, z_hi, θ_signed), ...].

    · 전이는 팀메가 적은 `transition_h`(이웃 밴드 h 구간의 중점).
    · 맨 아래/위에 밴드가 없는 높이는 가장 가까운 밴드 각도를 잇는다
      (오버행 성분이 없는 곳은 각도를 바꿀 이유가 없고, 바꾸면 블렌드 비용만 든다).
    · 밴드가 없으면 [(z_bottom, z_top, 0)].
    · 같은 각도의 이웃 밴드는 합친다.
    ⚠ 팀메 h 는 변환높이(=우리 Z′)이고 from_bands 는 경계를 축상 Z′≈z 로 쓴다.
      같은 근사를 우리 선택기도 쓴다(profile.py from_bands docstring).
    """
    bands = sorted(plan.get("bands", []), key=lambda b: (b["h_min"], b["h_max"]))
    if not bands:
        return [(float(z_bottom), float(z_top), 0.0)]
    cuts = [float(z_bottom)]
    for lo, hi in zip(bands, bands[1:], strict=False):
        t = 0.5 * (float(lo["h_max"]) + float(hi["h_min"]))
        t = min(max(t, cuts[-1] + 1e-6), float(z_top) - 1e-6)
        cuts.append(t)
    cuts.append(float(z_top))
    out = []
    for i, b in enumerate(bands):
        th = float(b["signed_angle"])
        if out and abs(out[-1][2] - th) < 1e-12:
            out[-1] = (out[-1][0], cuts[i + 1], th)
        else:
            out.append((cuts[i], cuts[i + 1], th))
    return out


def describe(res):
    u = res["uniform"]
    lines = [f"  균일(팀메): {u['direction']} {u['angle']:.2f}°  loss={u['loss']:.4f}  "
             f"κ 규칙={res['kappa_rule']}"]
    for c in res["components"]:
        o = c["outward"]
        lines.append(f"  성분 {c['id']}: 면 {c['faces']}, 면적 {c['area']:.1f}, "
                     f"κ={c['kappa']:+.3f}, outward {o['angle']:.1f}° "
                     f"(전부 통과={o['allows_all']}, 위반 면적 {o['violating_area']:.1f})")
    for b in res["bands"]:
        lines.append(f"  밴드 {b['band_id']}: 성분 {b['component_ids']} "
                     f"{b['signed_angle']:+.1f}°  h=[{b['h_min']:.2f}, {b['h_max']:.2f}]")
    if res["profile"] is None:
        lines.append(f"  프로필 실패: {res['profile_error']}")
    else:
        lines.append("  프로필(층간격 제약):")
        lines.append(res["profile"].describe())
        for n in getattr(res["profile"], "notes", []):
            lines.append(f"    ⚠ {n}")
    return "\n".join(lines)
