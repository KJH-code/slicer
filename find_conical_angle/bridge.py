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
            max_shift=None):
    """팀메 탐색을 메시에 돌리고 우리 프로필로 바꾼다. 모듈 docstring 참조."""
    if kappa_rule not in KAPPA_RULES:
        raise ValueError(f"kappa_rule 은 {KAPPA_RULES} 중 하나")
    cfg = _config(angle_min, angle_max, overrides)
    prepared = prepare_mesh(mesh, cfg)
    comps = find_overhang_components(prepared, cfg)
    if kappa_rule == "fixed":
        k = -math.sin(math.radians(threshold_deg))
        for c in comps:
            if c.valid:
                c.kappa = k
    evaluations, direction_results, selected = evaluate_model(
        comps, cfg["angle_min"], cfg["angle_max"])
    plan = plan_slice_bands(prepared, comps, cfg["angle_min"], cfg["angle_max"],
                            cfg["height_overlap_tolerance"])

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
    profile = AngleProfile.from_bands(band_list, r_max, radius_profile=rp,
                                      spacing_limit=spacing_limit, max_shift=max_shift)
    profile_raw = AngleProfile.from_bands(band_list, r_max)

    return {"uniform": uniform, "direction_results": direction_results,
            "bands": plan["bands"], "transitions": plan["transitions"],
            "band_intervals": band_list, "profile": profile, "profile_raw": profile_raw,
            "components": comp_rows, "kappa_rule": kappa_rule, "config": cfg,
            "prepared": prepared, "raw": {"components": comps, "plan": plan,
                                           "evaluations": evaluations}}


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
    lines.append("  프로필(층간격 제약):")
    lines.append(res["profile"].describe())
    for n in getattr(res["profile"], "notes", []):
        lines.append(f"    ⚠ {n}")
    return "\n".join(lines)
