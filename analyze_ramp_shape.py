"""analyze_ramp_shape.py — 베드 상한 아래에서 '바닥 램프의 모양' 을 훑는다 (데이터만).

## 왜

`docs/gap_audit.md` §9.6: 블렌드 반경(G1)·압출(G2)을 고친 뒤, 밴드2 는 같은 아랫각의 균일
원뿔을 한 번도 못 이긴다(0/17). REP5X 는 베드에 닿는 층의 각도가 B_safe(약 22.8°)를 넘을 수
없는데, 그 상한 아래에서 **진짜 균일 원뿔(`--strict`)** 을 이기는 것은 "바닥 ~1mm 만 깎고 위로
올리는" 프로필이었다. J13 은 연구 물음을 그 **램프의 모양**으로 옮길지 묻는다.
이 스크립트는 그 판단에 쓸 **수치만** 만든다. 권고는 없다.

## 훑는 프로필 족 (전부 outward, tanθ 선형 블렌드)

    θ(Z′) = θ_bed            (Z′ ≤ z0)
          = 블렌드 → θ_top    (z0 ≤ Z′ ≤ z0 + w)
          = θ_top            (그 위)

    θ_bed = 22°  ·  θ_top ∈ {0, 10, 20, 24, 28, 32, 36, 40}  ·  z0 ∈ {0.3, 0.6, 1.0, 2.0} mm

폭 w 는 **계획기가 허용하는 최소 폭**이다 — `profile._required_width` 와 같은 규칙
(바닥값 0.5mm, 가역성 여유 1.5·r_max·Δtan, 층간격 배율 m ∈ [1/1.5, 1.5], 반경은 블렌드의 층이
실제로 닿는 `RadiusProfile.max_in_slab`)이고, 다른 점은 블렌드의 **중심이 아니라 시작점(z0)을
고정**한다는 것뿐이다. 0.01mm 로 올림하고 `check_spacing` 이 빌 때까지 넓힌다.
θ_top < θ_bed 는 팽창 블렌드(m > 1, '아래가 높고 위가 낮은' 밴드와 같은 방향),
θ_top > θ_bed 는 압축 블렌드(m < 1, 올라가는 램프)다.

**베드 상한**: 만든 프로필이 `rep5x.bed_safe_profile` 을 **그대로 통과**해야 이 기계에서 쓸 수
있다(통과 못 하면 계획기가 프로필을 바꾼다 = 요청한 모양이 아니다). 통과 못 한 칸은
'베드 불가' 로 적고 **재지 않는다** — 못 뽑는 프로필이다.

## 항상 같이 재는 팔

* **균일 22° (진짜 균일, `--strict`)** — 기준선. 모든 표에 이 행이 있다
* 균일 θ_bed* (진짜 균일, 계획기가 쓰는 상한각 그대로 — 층고 0.3 에서 22.79°, 0.4 에서 23.38°).
  자동 램프는 22° 가 아니라 이 각에서 출발하므로, 그 0.8~1.4° 를 따로 떼어 보려는 대조군이다
* 균일 요청 + 자동 램프 — 요청각 = J 최선 균일각(§9.3 의 '균일 요청+램프'), 그리고
  요청각 ∈ {24, 28, 32, 36, 40}. `bed_safe_profile` 이 실제로 내는 프로필이다
* 밴드2(상한) — 아랫밴드 ≤ B_safe 에서 J 최선인 밴드2 (`analyze_gap_sample.select_capped`)

## 재는 것 (팔마다, 층고 0.3·0.4)

* 검사기 A 의 **진짜 오버행** — 미지지 길이 mm 와 %p(페리미터 총 길이 대비). 프레임 둘:
  연직(기본, §9 의 수치와 같은 경로)과 공구(`layer_frames` → `check_support(tool_up=, layer=)`
  → `classify_unsupported(tool_up=, layer_thickness=)`. %p 는 `support_breakdown` 의
  `overhang_pct` 와 같은 수다 — `--selfcheck` 가 확인한다)
* 평균|θ| (면적가중) · 실제 층간격 배율 m 의 최대·최소(압출 표본점의 정확 Z′ 로) · 층 법선 방향
  두께 t_n · 블렌드의 Z′ 구간과 그 층이 차지하는 실공간 z 구간
* 미지지 길이가 **어디에** 있나: 바닥 기준 높이 범위, 2mm 안의 몫, 구간별(블렌드 아래 /
  블렌드 / 블렌드 위), 층간격별(m < 1 / m = 1 / m > 1)

## 압축 효과를 떼어 내기 (gap_audit §1 (b))

검사기 A 의 창은 고정이다(수평 ≤ 압출폭 w, 수직 (0, 1.5h]). 압축 블렌드에서는 층이 m 배로
얇아져 같은 벽 기울기가 한 층에 **m 배만큼만** 옆으로 밀린다 — 각도가 좋아져서가 아니라
층이 얇아서 창을 통과하는 몫이 섞인다. 그래서 **창을 그 점의 m 으로 줄인(늘린) 판정**을 같이 낸다:

    수평 ≤ w·m̄,  수직 (0, 1.5h·m̄]         ('m 보정 창')
    m̄ = (그 점의 층과 바로 아랫층 사이의 실제 수직 간격) ÷ 층고 = 1 − r·(T(Z′) − T(Z′−h))/h

미분 배율 m = 1 − r·s 가 아니라 **층 사이** 배율 m̄ 을 쓴다. 블렌드의 첫 층은 아랫층이 블렌드
밖이라 미분 m 보다 덜 얇고, 블렌드 바로 위의 첫 층은 미분 m = 1 인데 실제로는 얇다 — 폭 0.5mm
짜리 블렌드는 층 두 개가 전부라 이 차이가 결과를 바꾼다(처음에 미분 m 으로 쟀다가 고쳤다).
보고하는 'm 최소·최대' 는 gap_audit 과 같은 미분 m 이고, m̄ 의 범위는 JSON 에 따로 있다.

이 판정은 "그 점의 층이 **같은 각도의 균일 원뿔 두께**(m = 1)였어도 통과했겠는가" 와 같다
(연직·공구 프레임 모두 통과 조건이 m 에 비례한다 — §1 의 식). 균일 팔은 m ≡ 1 이라 두 판정이
같다. ⚠ 이것은 **민감도 측정**이지 새 판정 기준이 아니다 — 얇은 층이 실제로 오버행을 더 잘
받는지(= 기본 창이 맞는지)는 실물(사다리 L5)로만 갈린다.
구현: `toolpath.py` 는 건드리지 않았다. `check_support` 의 판정 규칙(G-code 순서상 먼저 퇴적된
점, 공구 프레임이면 같은 층 제외)을 m ≠ 1 인 페리미터 점에만 다시 적용한다
(`support_scaled`). m = 1 로 두면 `check_support` 와 같은 답이 나오는지 `--selfcheck` 가 본다.

층 두께는 **세는 쪽**에도 들어 있다: 미지지 '길이' 는 고리를 세므로, 같은 높이 구간이라도 층이
얇으면(m < 1) 고리가 많아 길이가 늘고 두꺼우면(m > 1) 준다. 그래서 m 보정 창에는
**층고 환산 길이** Σ(길이·m) 도 같이 적는다(JSON 의 `mm_eq`) — 창 효과와 세는 효과를 둘 다
뺀 수다. 균일 팔은 세 눈금(기본 창 mm / m 창 mm / m 창 환산)이 전부 같다.

## 격자와 시간 — 뺀 것

기본(`--grid full`)은 격자 전부다: θ_top 8 × z0 4 + 자동 램프 요청각 5 + 고정 팔 4, 모델·층고당
41 팔. **베드 불가 칸만 재지 않는다**(못 뽑는 프로필이다 — 1,394 팔 중 311). 4 프로세스로
29분(2026-11-10, 표본 격자 17.4분 + 나머지 11.7분으로 나눠 쟀다. 측정 1,067회).

`--grid sub` 는 급할 때 쓰는 표본 격자(17분)다: θ_top = 28°·36° 를 빼고(올라가는 족·자동 램프
모두), 내려가는 쪽의 10°·20° 는 z0 = 1.0 만 잰다. ⚠ 층고 0.4 의 '최선' 은 17 모델 중 12 개가
θ_top = 28° 라, 표본 격자만으로는 최선 모양이 다르게 나온다. 표는 잰 칸만으로 만들고
표본 수(n)를 적는다.

## 실행

    python3 analyze_ramp_shape.py --selfcheck          # 검산만 (약 1분)
    python3 analyze_ramp_shape.py --jobs 4             # 전체 격자 (4코어 약 29분)
    python3 analyze_ramp_shape.py --grid sub --jobs 4  # 표본 격자 (약 17분)
    python3 analyze_ramp_shape.py --resume --jobs 4    # 끊긴 실행을 이어서 / 빠진 칸만 더
    python3 analyze_ramp_shape.py --replay             # 저장된 JSON 으로 표·그림만 다시

판정은 `analytic.py` 의 해석식 하나이고(J 선택), 툴패스 수치는 검사기 A 다. 새 기준은 없다.
실물 출력은 0건이다 — 전부 계산이다.
"""

import argparse
import contextlib
import json
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import trimesh
from scipy.spatial import cKDTree

import conical.toolpath as toolpath
import conical.varangle as varangle
from analyze_blend_ratio import build_specs
from analyze_gap_sample import BED_CAP, select_capped
from compare_waist import mean_abs_angle
from conical.backtransform import backtransform
from conical.config import DEFAULT_K, MAX_SPACING_FACTOR
from conical.meshio import RadiusProfile
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile, blend_width_for_spacing
from conical.rep5x import bed_safe_profile
from conical.toolpath import (
    OVERHANG,
    check_support,
    classify_unsupported,
    layer_frames,
    sample_extrusions,
    support_breakdown,
)
from conical.transform import transform_cone_profile

THETA_BED = 22.0                       # 족의 바닥각 = 진짜 균일 기준선의 각 (2° 격자, 사다리 L3)
THETA_TOPS = (0.0, 10.0, 20.0, 24.0, 28.0, 32.0, 36.0, 40.0)
Z0S = (0.3, 0.6, 1.0, 2.0)
LAYER_HS = (0.3, 0.4)
AUTO_REQUESTS = tuple(t for t in THETA_TOPS if t > THETA_BED)
TIE_MM = 0.5                           # mm 판정의 무승부 폭 (§9 와 같다)
NEAR_BED = 2.0
WIDTH = 0.45                           # 압출폭 (검사기 기본값)
VWIN_FACTOR = 1.5                      # 검사기 수직 창 (기본값)
BATCH = 500                            # check_support 의 배치 — 결과는 배치와 무관(자체 점검)
M_EPS = 1e-6
FRAMES = (("v", "연직"), ("t", "공구"))
# 급할 때 쓰는 표본 격자(`--grid sub`) — 모듈 docstring 「격자와 시간」. 기본은 전부(full).
SUB_THETA_UP = (24.0, 32.0, 40.0)      # 올라가는 램프·자동 램프 요청각 (28·36 을 뺐다)
SUB_DOWN = {0.0: Z0S, 10.0: (1.0,), 20.0: (1.0,)}   # 내려가는 쪽: 0° 는 z0 전부, 10·20° 는 z0=1
DEFAULT_JSON = "ramp_shape_results.json"
DEFAULT_PNG = "ramp_shape_results.png"


# ─────────────────────────────────────────────────────────────
# 프로필 족
# ─────────────────────────────────────────────────────────────
def min_ramp_width(rp, z0, tan1, tan2, limit=MAX_SPACING_FACTOR, min_blend=0.5,
                   safety=1.5):
    """Z′ = z0 에서 **시작**하는 블렌드(tanθ: tan1 → tan2)의 최소 합법 폭 (mm).

    `profile._required_width` 와 같은 규칙이다 — 바닥값, 가역성 여유(전 모델 반경),
    층간격 폭(`blend_width_for_spacing`, 반경은 그 블렌드의 층이 실제로 닿는
    `max_in_slab`), (폭 → 슬랩 → 반경 → 폭) 고정점 반복. 다른 점은 블렌드의 중심이
    아니라 시작점을 고정한다는 것뿐이다.
    """
    dtan = tan2 - tan1
    w = max(min_blend, safety * rp.global_max * dtan if dtan > 0 else min_blend)
    for _ in range(80):
        r_b = rp.max_in_slab(z0, z0 + w, tan1, tan2)
        w_new = max(w, blend_width_for_spacing(r_b, dtan, "outward", limit))
        if w_new <= w * (1.0 + 1e-4):
            return w_new
        w = w_new
    return w


def family_profile(rp, r_max, z0, theta_top, theta_bed=THETA_BED):
    """족의 프로필 하나 → (AngleProfile, 폭 mm). 폭은 0.01mm 로 올림,
    `check_spacing` 이 빌 때까지 0.01mm 씩 더 넓힌다(올림·고정점 허용오차 몫)."""
    t1 = math.tan(math.radians(theta_bed))
    t2 = math.tan(math.radians(theta_top))
    w = math.ceil(min_ramp_width(rp, z0, t1, t2) * 100.0 - 1e-9) / 100.0
    for _ in range(400):
        prof = AngleProfile([(float(z0), float(theta_bed)),
                             (float(z0 + w), float(theta_top))])
        prof.validate(r_max, "outward")
        if not prof.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp):
            return prof, w
        w = round(w + 0.01, 2)
    raise RuntimeError(f"층간격 제약을 지키는 폭을 못 찾음: z0={z0}, θ_top={theta_top}")


def breakpoints(prof):
    return [[round(float(z), 6), round(float(t), 6)]
            for z, t in zip(prof.zs, prof.thetas_deg, strict=True)]


def prof_from(bps):
    return AngleProfile([(float(z), float(t)) for z, t in bps])


# ─────────────────────────────────────────────────────────────
# 모델 (프로세스마다 한 번씩 만든다)
# ─────────────────────────────────────────────────────────────
_MODELS = {}


def _model(idx):
    if idx not in _MODELS:
        name, build = build_specs(asym=True)[idx]
        mesh = build()
        rp = RadiusProfile(mesh)
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        _MODELS[idx] = (name, mesh, rp, r_max)
    return _MODELS[idx]


def in_grid(grid, theta_top, z0=None):
    """그 (θ_top, z0) 가 이번 격자에 드는가. z0=None 이면 자동 램프 요청각."""
    if grid == "full":
        return True
    if theta_top > THETA_BED:
        return theta_top in SUB_THETA_UP
    return z0 in SUB_DOWN.get(theta_top, ())


def prepare(task):
    """모델 하나의 팔 목록 (층고별). 선택(J)은 여기서 매번 다시 한다."""
    idx, grid = task
    name, mesh, rp, r_max = _model(idx)
    theta_j = float(varangle.select_banded_j(mesh, DEFAULT_K, 1, r_max, rp,
                                             MAX_SPACING_FACTOR)["thetas"][0])
    _th_u, th_b, prof_b, rejected = select_capped(mesh, rp, r_max, BED_CAP)
    fam = {}
    for tt in THETA_TOPS:
        for z0 in Z0S:
            fam[(tt, z0)] = family_profile(rp, r_max, z0, tt)

    def arm(key, kind, label, prof, lh, grid_ok=True, **extra):
        legal = not bed_safe_profile(prof, rp, lh)[1]["changed"]
        return {"key": key, "kind": kind, "label": label, "breakpoints": breakpoints(prof),
                "bed_legal": bool(legal), "in_grid": bool(grid_ok),
                "blend": [[round(a, 4), round(b, 4)] for a, b in prof.blend_intervals()],
                "nominal_m": prof.max_spacing_factor(r_max, "outward", rp),
                "spacing_violation": bool(prof.check_spacing(
                    r_max, "outward", MAX_SPACING_FACTOR, rp)),
                "mean_abs_theta": mean_abs_angle(mesh, prof), **extra}

    by_lh = {}
    for lh in LAYER_HS:
        probe, info = bed_safe_profile(AngleProfile.constant(40.0), rp, lh)
        th_bed = float(info["theta_bed"])
        arms = [arm("U22", "uniform", f"균일 {THETA_BED:g}° (진짜 균일)",
                    AngleProfile.constant(THETA_BED), lh),
                arm("Ubed", "uniform", f"균일 {th_bed:.2f}° (진짜 균일, 계획기 상한각)",
                    AngleProfile.constant(th_bed), lh)]
        ramp_j, info_j = bed_safe_profile(AngleProfile.constant(theta_j), rp, lh)
        arms.append(arm("UJ+ramp", "auto", f"균일 요청 {theta_j:g}°(J 최선) + 자동 램프",
                        ramp_j, lh, request=theta_j, changed=bool(info_j["changed"]),
                        ramp=info_j["ramps"].get("outward")))
        for req in AUTO_REQUESTS:
            ramp, inf = bed_safe_profile(AngleProfile.constant(req), rp, lh)
            arms.append(arm(f"auto{req:g}", "auto", f"균일 요청 {req:g}° + 자동 램프",
                            ramp, lh, grid_ok=in_grid(grid, req), request=req,
                            changed=bool(inf["changed"]),
                            ramp=inf["ramps"].get("outward")))
        arms.append(arm("B2cap", "band2", f"밴드2(상한) [{th_b[0]:g},{th_b[1]:g}]", prof_b,
                        lh, thetas=[float(t) for t in th_b], rejected_by_bed=rejected))
        for (tt, z0), (prof, w) in fam.items():
            arms.append(arm(f"F{tt:g}@{z0:g}", "family",
                            f"{THETA_BED:g}°→{tt:g}°, z0={z0:g}, 폭 {w:.2f}", prof, lh,
                            grid_ok=in_grid(grid, tt, z0), theta_top=tt, z0=z0, width=w,
                            beyond_top=bool(z0 + w > rp.z1)))
        by_lh[f"{lh:g}"] = {"theta_bed_planner": th_bed, "arms": arms}
    return {"idx": idx, "model": name, "r_max": r_max,
            "height": float(mesh.bounds[1][2] - mesh.bounds[0][2]),
            "theta_J": theta_j, "band2_cap": [float(t) for t in th_b],
            "by_layer_height": by_lh}


# ─────────────────────────────────────────────────────────────
# 측정
# ─────────────────────────────────────────────────────────────
class _LazySections(dict):
    """층 번호 → 단면 폴리곤. **요청받은 층만** 복원한다.

    `layer_cross_sections` 는 층마다 독립이므로(그 층의 페리미터 점만 쓴다) 한 층의 점만
    넘겨 불러도 그 층의 결과가 같다. 전 층을 한꺼번에 넘기면 이동마다 전체 배열을 훑어
    (이동 수 × 점 수) 큰 모델에서 한 번에 5~10초가 든다.
    """

    def __init__(self, orig, pts, move_id, kinds, layer, width):
        super().__init__()
        self._args = (orig, pts, move_id, kinds, layer, width)
        self._seen = set()

    def get(self, key, default=None):
        if key not in self._seen:
            self._seen.add(key)
            orig, pts, move_id, kinds, layer, width = self._args
            s = np.where(layer == key)[0]
            if len(s):
                self.update(orig(pts[s], move_id[s], kinds[s], layer[s], width))
        return super().get(key, default)


@contextlib.contextmanager
def shared_sections():
    """`classify_unsupported` 가 쓰는 층별 단면 복원을 한 측정 안에서 층마다 한 번만 하게 한다.

    단면은 (점, 층 번호)만의 함수라 프레임·창과 무관하다. 그런데 `classify_unsupported`
    는 부를 때마다 전 층을 다시 복원하고, 한 팔에서 그 함수를 네댓 번 부른다. 그래서 같은
    배열로 부른 호출은 같은 `_LazySections` 를 돌려준다. 분류 논리는 저장소 함수 그대로다 —
    `--selfcheck` 가 이 캐시 없이 부른 것과 같은 답인지 본다.
    """
    orig = toolpath.layer_cross_sections
    memo = {}

    def cached(pts, move_id, kinds, layer, width=WIDTH):
        key = (id(pts), id(move_id), id(kinds), id(layer), width)
        if key not in memo:
            memo[key] = _LazySections(orig, pts, move_id, kinds, layer, width)
        return memo[key]

    toolpath.layer_cross_sections = cached
    try:
        yield
    finally:
        toolpath.layer_cross_sections = orig


def support_scaled(pts, sup, scale, layer_height, sel, up=None, lay=None,
                   only_changed=True, chunk=4000):
    """`sel` 점들의 지지 판정을 **창을 점마다 scale 배로 바꿔** 다시 한다 → supported 사본.

    판정 규칙은 `toolpath.check_support`(기본 인자) 그대로다: G-code 순서상 먼저 퇴적된 점 q 가
    수직 (0, 1.5h·scale], 수평 ≤ 압출폭·scale 안에 있으면 지지. `up` 을 주면 공구 프레임
    (dz = (p−q)·u, 수평 = 그에 수직), `lay` 를 주면 같은 층의 점은 후보에서 뺀다.
    베드 판정(z ≤ 층고)은 창과 무관하게 그대로 둔다.

    only_changed: 창이 줄면(scale<1) 지지였던 점만, 늘면(scale>1) 미지지였던 점만 답이 바뀔 수
    있으므로 그 점들만 다시 본다. False 면 sel 전부(검산용).
    """
    out = sup.copy()
    vwin = layer_height * VWIN_FACTOR
    bed = pts[:, 2] <= layer_height + 1e-9
    todo = sel & ~bed
    if only_changed:
        todo &= ((scale < 1.0 - M_EPS) & sup) | ((scale > 1.0 + M_EPS) & ~sup)
    todo = np.where(todo)[0]
    if not len(todo):
        return out
    tree = cKDTree(pts)
    for s0 in range(0, len(todo), chunk):
        idx = todo[s0:s0 + chunk]
        hw = WIDTH * scale[idx]
        vw = vwin * scale[idx]
        pairs = cKDTree(pts[idx]).sparse_distance_matrix(
            tree, float(np.hypot(hw, vw).max()) + 1e-9, output_type="ndarray")
        a, j = pairs["i"], pairs["j"]
        i = idx[a]
        keep = j < i                                   # 먼저 퇴적된 점만
        if lay is not None:
            keep &= ~((lay[j] == lay[i]) & (lay[i] >= 0))      # 같은 층은 '아래' 가 아니다
        a, i, j = a[keep], i[keep], j[keep]
        d = pts[i] - pts[j]
        if up is None:
            dz = d[:, 2]
            horiz = np.hypot(d[:, 0], d[:, 1])
        else:
            dz = np.einsum("ij,ij->i", d, up[i])
            horiz = np.sqrt(np.maximum(np.einsum("ij,ij->i", d, d) - dz * dz, 0.0))
        ok = (dz > 1e-9) & (dz <= vw[a] + 1e-9) & (horiz <= hw[a] + 1e-9)
        hit = np.zeros(len(idx), dtype=bool)
        hit[a[ok]] = True
        out[idx] = hit
    return out


def _summary(over, w, tot, zrel, m, zones):
    """미지지(진짜 오버행) 마스크 → 길이·몫·위치."""
    mm = float(w[over].sum())
    zs, ws = zrel[over], w[over]
    if len(zs):
        order = np.argsort(zs)
        cum = np.cumsum(ws[order])
        z_med = float(zs[order][np.searchsorted(cum, 0.5 * cum[-1])])
        z_rng = [float(zs.min()), float(zs.max())]
    else:
        z_med, z_rng = None, None
    low, blend, high = zones
    return {"mm": mm, "pct": mm / tot * 100.0,
            "mm_eq": float((w[over] * m[over]).sum()),     # 층고 환산 길이 Σ 길이·m
            "near_mm": float(w[over & (zrel < NEAR_BED)].sum()),
            "z": z_rng, "z_median": z_med,
            "mm_below_blend": float(w[over & low].sum()),
            "mm_in_blend": float(w[over & blend].sum()),
            "mm_above_blend": float(w[over & high].sum()),
            "mm_m_lt1": float(w[over & (m < 1.0 - M_EPS)].sum()),
            "mm_m_gt1": float(w[over & (m > 1.0 + M_EPS)].sum())}


def measure(mesh, prof, layer_height, detail=False):
    """파이프라인 1회 → 두 프레임 × 두 창의 진짜 오버행과 층간격·위치 통계."""
    v = transform_cone_profile(mesh.vertices, prof, "outward")
    warped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=layer_height), prof,
                            "outward")
    pts, mid, w, kinds, lay = sample_extrusions(real, return_types=True,
                                               return_layers=True)
    n = len(pts)
    peri = kinds == 0
    tot = float(w[peri].sum())
    r = np.hypot(pts[:, 0], pts[:, 1])
    zw = prof.solve_forward(pts[:, 2], r, "outward")
    # 미분 배율 m = 1 − r·s (그 점의 정확 Z′ 에서. gap_audit 의 '실제 m' 과 같은 양)
    m_inst = np.broadcast_to(np.asarray(prof.spacing_factor(zw, r, "outward"),
                                        dtype=float), (n,)).copy()
    # 층 사이 배율 m̄ = (이 층과 바로 아랫층의 수직 간격) ÷ 층고 — 층은 Z′ 로 층고마다 있으므로
    #   z_k(r) − z_{k−1}(r) = h − r·(T(Z′) − T(Z′ − h))  (정확).
    # 창·환산 길이는 이 m̄ 으로 한다: 블렌드의 첫 층은 아랫층이 블렌드 밖이라 미분 m 보다
    # 덜 얇고, 블렌드 바로 위 첫 층은 미분 m = 1 인데 실제로는 얇다.
    m = 1.0 - r * (prof.tan_at(zw) - prof.tan_at(zw - layer_height)) / layer_height
    up, t_n = layer_frames(pts, prof, "outward", layer_height)
    zrel = pts[:, 2] - float(mesh.bounds[0][2])

    ivs = prof.blend_intervals()
    blend = np.zeros(n, dtype=bool)
    for a, b in ivs:
        blend |= (zw >= a) & (zw <= b)
    low = (zw < ivs[0][0]) if ivs else np.ones(n, dtype=bool)
    zones = (low & ~blend, blend, ~low & ~blend)

    out = {"points": int(n), "perimeter_mm": tot,
           "m_max": float(m_inst.max()), "m_min": float(m_inst.min()),
           "mbar_max": float(m.max()), "mbar_min": float(m.min()),
           "t_n_max": float(t_n.max()), "t_n_min": float(t_n.min()),
           "blend_real_z": ([float(zrel[blend].min()), float(zrel[blend].max())]
                            if blend.any() else None),
           "blend_perimeter_mm": float(w[peri & blend].sum()),
           "compressed_perimeter_mm": float(w[peri & (m < 1.0 - M_EPS)].sum())}
    keep = {}
    with shared_sections():
        for frame, _ko in FRAMES:
            tool = frame == "t"
            kw = ({"tool_up": up, "layer_thickness": t_n} if tool else {})
            if tool:
                sup, _ = check_support(pts, mid, w, layer_height=layer_height,
                                       batch_samples=BATCH, tool_up=up, layer=lay)
            else:
                sup, _ = check_support(pts, mid, w, layer_height=layer_height,
                                       batch_samples=BATCH)
            lab = classify_unsupported(pts, mid, kinds, lay, sup, **kw)
            res = _summary(lab == OVERHANG, w, tot, zrel, m, zones)
            res["peri_unsupported_pct"] = float(w[peri & ~sup].sum() / tot * 100.0)
            out[frame] = res

            # m 보정 창: 수평·수직 창을 그 점의 m 배로 (m ≠ 1 인 페리미터 점만 바뀐다)
            sup_s = support_scaled(pts, sup, m, layer_height, peri,
                                   up=up if tool else None, lay=lay if tool else None)
            lab_s = lab.copy()
            flipped = peri & (sup_s != sup)
            lab_s[flipped & sup_s] = -1
            newly = flipped & ~sup_s
            if newly.any():
                only = np.ones(n, dtype=bool)
                only[newly] = False
                lab_s[newly] = classify_unsupported(pts, mid, kinds, lay, only,
                                                    **kw)[newly]
            out[frame + "_ms"] = _summary(lab_s == OVERHANG, w, tot, zrel, m, zones)
            if detail:
                keep[frame] = (sup, lab, sup_s, lab_s)
    if detail:
        return out, dict(pts=pts, mid=mid, w=w, kinds=kinds, lay=lay, up=up, t_n=t_n,
                         m=m, peri=peri, tot=tot, frames=keep)
    return out


def measure_task(task):
    idx, lh, key, bps = task
    _name, mesh, _rp, _r_max = _model(idx)
    t0 = time.time()
    res = measure(mesh, prof_from(bps), lh)
    res["seconds"] = time.time() - t0
    return idx, lh, key, res


# ─────────────────────────────────────────────────────────────
# 검산
# ─────────────────────────────────────────────────────────────
def selfcheck():
    """① 배치 크기 ② 단면 캐시 ③ m 보정 창의 재구현 ④ support_breakdown 과의 일치."""
    ok = True
    for idx, lh, bps in ((6, 0.3, [[1.0, 22.0], [2.54, 28.0]]),
                         (0, 0.4, [[0.6, 22.0], [3.59, 10.0]]),
                         (5, 0.4, [[0.0, 22.0]])):
        name, mesh, rp, r_max = _model(idx)
        prof = prof_from(bps)
        res, d = measure(mesh, prof, lh, detail=True)
        pts, mid, w, kinds, lay = d["pts"], d["mid"], d["w"], d["kinds"], d["lay"]
        up, t_n, m, peri = d["up"], d["t_n"], d["m"], d["peri"]
        print(f"\n[{name}, 층고 {lh:g}, {bps}]  점 {len(pts)}, m {m.min():.3f}~{m.max():.3f}")
        for frame, ko in FRAMES:
            tool = frame == "t"
            sup, lab, _sup_s, _lab_s = d["frames"][frame]
            kw = ({"tool_up": up, "layer_thickness": t_n} if tool else {})
            ckw = ({"tool_up": up, "layer": lay} if tool else {})
            # ① 배치 크기 2000(기본)과 같은 판정인가
            ref, _ = check_support(pts, mid, w, layer_height=lh, **ckw)
            same_batch = bool((ref == sup).all())
            # ② 캐시 없이 부른 분류와 같은가
            same_cls = bool((classify_unsupported(pts, mid, kinds, lay, ref, **kw)
                             == lab).all())
            # ③ 창 배율 1 로 전 페리미터를 다시 판정하면 check_support 와 같은가
            again = support_scaled(pts, sup, np.ones(len(pts)), lh, peri,
                                   up=up if tool else None, lay=lay if tool else None,
                                   only_changed=False)
            diff = int((again[peri] != sup[peri]).sum())
            # ④ support_breakdown 의 overhang_pct 와 같은 수인가
            bd = support_breakdown(pts, mid, kinds, lay, ref, w, **kw)
            same_bd = abs(bd["overhang_pct"] - res[frame]["pct"]) < 1e-9
            # only_changed 지름길이 전수 재판정과 같은가
            full = support_scaled(pts, sup, m, lh, peri, up=up if tool else None,
                                  lay=lay if tool else None, only_changed=False)
            short = support_scaled(pts, sup, m, lh, peri, up=up if tool else None,
                                   lay=lay if tool else None)
            same_short = bool((full[peri] == short[peri]).all())
            good = same_batch and same_cls and diff == 0 and same_bd and same_short
            ok &= good
            print(f"  {ko}: 배치 무관 {same_batch} · 캐시 무관 {same_cls} · "
                  f"배율1 재판정 불일치 {diff}/{int(peri.sum())} · "
                  f"support_breakdown 일치 {same_bd} ({bd['overhang_pct']:.6f}%p) · "
                  f"지름길 일치 {same_short} · "
                  f"진짜 오버행 {res[frame]['mm']:.1f}mm → m 보정 "
                  f"{res[frame + '_ms']['mm']:.1f}mm")
    print("\n검산:", "통과" if ok else "실패")
    return 0 if ok else 1


# ─────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────
def _rounded(obj, nd=4):
    """측정값을 소수 nd 자리로 (파일 크기 — 판정은 0.5mm 단위라 영향 없다)."""
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _rounded(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rounded(v, nd) for v in obj]
    return obj


def dump(path, data):
    """JSON 저장. 팔이 1,400 개쯤이라 들여쓰기 없이, 모델마다 한 줄로 쓴다.
    브레이크포인트는 그대로 둔다(`--resume` 이 그 값으로 같은 프로필을 찾는다)."""
    for mdl in data["models"]:
        for blk in mdl["by_layer_height"].values():
            for a in blk["arms"]:
                if "measured" in a:
                    a["measured"] = _rounded(a["measured"])
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write('{"meta": ' + json.dumps(data["meta"], ensure_ascii=False, indent=1)
                 + ',\n"models": [\n')
        fh.write(",\n".join(json.dumps(mdl, ensure_ascii=False, separators=(",", ":"))
                            for mdl in data["models"]))
        fh.write("\n]}\n")
    os.replace(tmp, path)


def run(args):
    t_start = time.time()
    n_models = len(build_specs(asym=True))
    only = set(args.models) if args.models else set(range(n_models))
    done = {}
    prior = 0.0                                     # 앞선 실행들의 벽시계 (이어서 돌릴 때 더한다)
    if args.resume and os.path.exists(args.json):
        with open(args.json) as fh:
            old = json.load(fh)
        prior = float(old.get("meta", {}).get("wall_seconds", 0.0))
        for mdl in old.get("models", []):
            for lh, blk in mdl["by_layer_height"].items():
                for a in blk["arms"]:
                    if "measured" in a:
                        done[(mdl["idx"], lh, json.dumps(a["breakpoints"]))] = a["measured"]
        print(f"이어서: 이미 잰 팔 {len(done)}개")

    with Pool(args.jobs) as pool:
        models = pool.map(prepare, [(i, args.grid) for i in sorted(only)], chunksize=1)
        print(f"팔 준비 끝 ({time.time() - t_start:.0f}s)", flush=True)
        tasks, slots = [], {}
        for mdl in models:
            for lh, blk in mdl["by_layer_height"].items():
                if float(lh) not in args.layer_height:
                    continue
                for a in blk["arms"]:
                    if not a["bed_legal"]:
                        continue                    # 못 뽑는 프로필은 재지 않는다
                    sig = json.dumps(a["breakpoints"])
                    if (mdl["idx"], lh, sig) in done:
                        a["measured"] = done[(mdl["idx"], lh, sig)]
                        continue
                    if not a["in_grid"]:
                        continue                    # 표본 격자에서 뺀 칸
                    slot = (mdl["idx"], lh, sig)
                    if slot not in slots:           # 같은 프로필은 한 번만 잰다
                        slots[slot] = []
                        tasks.append((mdl["idx"], float(lh), sig, a["breakpoints"]))
                    slots[slot].append(a)
        # 큰 모델부터 (끝에 긴 작업 하나가 남지 않게)
        size = {mdl["idx"]: mdl["r_max"] ** 2 * mdl["height"] for mdl in models}
        tasks.sort(key=lambda t: -size[t[0]] / t[1])
        print(f"측정할 프로필 {len(tasks)}개 (프로세스 {args.jobs})", flush=True)
        data = {"meta": meta(args), "models": models}
        last = time.time()
        for k, (idx, lh, sig, res) in enumerate(
                pool.imap_unordered(measure_task, tasks, chunksize=1), 1):
            for a in slots[(idx, f"{lh:g}", sig)]:
                a["measured"] = res
            if time.time() - last > 90 or k == len(tasks):
                data["meta"]["wall_seconds"] = prior + time.time() - t_start
                dump(args.json, data)
                last = time.time()
                print(f"  {k}/{len(tasks)}  {time.time() - t_start:.0f}s", flush=True)
    data["meta"]["wall_seconds"] = prior + time.time() - t_start
    data["meta"]["cpu_seconds"] = float(sum(
        a["measured"].get("seconds", 0.0) for mdl in models
        for blk in mdl["by_layer_height"].values() for a in blk["arms"]
        if "measured" in a))
    dump(args.json, data)
    print(f"저장: {args.json}  (벽시계 {time.time() - t_start:.0f}s, "
          f"앞선 실행까지 합쳐 {data['meta']['wall_seconds']:.0f}s)")
    return data


def meta(args):
    return {"theta_bed_family": THETA_BED, "theta_tops": list(THETA_TOPS),
            "z0s": list(Z0S), "layer_heights": list(args.layer_height),
            "auto_requests": list(AUTO_REQUESTS), "mm_tie_tolerance": TIE_MM,
            "near_bed_mm": NEAR_BED, "width": WIDTH, "vwin_factor": VWIN_FACTOR,
            "bed_cap_select": BED_CAP, "jobs": args.jobs, "grid": args.grid,
            "sub_grid": {"theta_up": list(SUB_THETA_UP),
                         "down": {f"{k:g}": list(v) for k, v in SUB_DOWN.items()}},
            "frames": {"v": "연직 (check_support 기본)",
                       "t": "공구 (layer_frames + check_support(tool_up, layer))",
                       "v_ms": "연직, 창을 그 점의 m 배로", "t_ms": "공구, 창을 그 점의 m 배로"},
            "note": "bed_legal=false 인 팔은 재지 않았다 (bed_safe_profile 이 프로필을 바꾼다)"}


# ─────────────────────────────────────────────────────────────
# 보고 — 표(마크다운)와 그림
# ─────────────────────────────────────────────────────────────
COLS = (("v", "연직"), ("t", "공구"), ("v_ms", "연직·m창"), ("t_ms", "공구·m창"))


def _arms(mdl, lh):
    return {a["key"]: a for a in mdl["by_layer_height"][f"{lh:g}"]["arms"]}


def _mm(a, col, field="mm"):
    return a["measured"][col][field] if a is not None and "measured" in a else None


def verdict(base, x, tol=TIE_MM):
    """기준선 base 대 팔 x — 미지지 길이가 tol 넘게 짧으면 '승', 길면 '패', 아니면 '무'."""
    return "승" if x < base - tol else ("패" if x > base + tol else "무")


def tally(pairs, n_all):
    vs = [verdict(b, x) for b, x in pairs if b is not None and x is not None]
    if not vs:
        return "—"
    out = f"{vs.count('승')}·{vs.count('무')}·{vs.count('패')}"
    return out if len(vs) == n_all else out + f" (n={len(vs)})"


def _fam_keys(data):
    """잰 적이 있는 족 칸 (θ_top, z0) 을 순서대로."""
    seen = set()
    for mdl in data["models"]:
        for blk in mdl["by_layer_height"].values():
            for a in blk["arms"]:
                if a["kind"] == "family" and "measured" in a:
                    seen.add((a["theta_top"], a["z0"]))
    return sorted(seen)


def _auto_keys(data):
    seen = set()
    for mdl in data["models"]:
        for blk in mdl["by_layer_height"].values():
            for a in blk["arms"]:
                if a["key"].startswith("auto") and "measured" in a:
                    seen.add(a["request"])
    return [f"auto{r:g}" for r in sorted(seen)]


def best_arm(arms, keys, col):
    """keys 중 그 지표(col)의 미지지 길이가 가장 짧은 팔. 0.05mm 안 동률이면 평균|θ| 작은 쪽."""
    cand = [arms[k] for k in keys if k in arms and "measured" in arms[k]]
    if not cand:
        return None
    lo = min(_mm(a, col) for a in cand)
    return min((a for a in cand if _mm(a, col) <= lo + 0.05),
               key=lambda a: a["mean_abs_theta"])


def _rng(vals, fmt="{:.2f}"):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "—"
    lo, hi = min(vals), max(vals)
    return fmt.format(lo) if abs(hi - lo) < 5e-3 else f"{fmt.format(lo)}~{fmt.format(hi)}"


def _med(vals):
    vals = [v for v in vals if v is not None]
    return float(np.median(vals)) if vals else float("nan")


def report(data):
    models = data["models"]
    n = len(models)
    lhs = [lh for lh in data["meta"]["layer_heights"]]
    fam = _fam_keys(data)
    autos = _auto_keys(data)
    fam_up = [f"F{tt:g}@{z0:g}" for tt, z0 in fam if tt > THETA_BED]
    fam_dn = [f"F{tt:g}@{z0:g}" for tt, z0 in fam if tt < THETA_BED]
    auto_all = autos + ["UJ+ramp"]
    print(f"\n모델 {n}개 · 층고 {lhs} · 격자 {data['meta'].get('grid')} · "
          f"벽시계 {data['meta'].get('wall_seconds', 0) / 60:.1f}분 "
          f"(CPU {data['meta'].get('cpu_seconds', 0) / 60:.0f}분, 프로세스 "
          f"{data['meta'].get('jobs')})")

    # ── [A] 합법성과 폭 ──
    print("\n### [A] 베드 통과 모델 수 / 최소 폭 mm (모델 범위)\n")
    print("| θ_top | " + " | ".join(
        f"z0={z0:g} (층고 {lh:g})" for lh in lhs for z0 in Z0S) + " |")
    print("|---|" + "---|" * (len(lhs) * len(Z0S)))
    for tt in THETA_TOPS:
        cells = []
        for lh in lhs:
            for z0 in Z0S:
                arms = [_arms(m, lh).get(f"F{tt:g}@{z0:g}") for m in models]
                ok = sum(a["bed_legal"] for a in arms)
                cells.append(f"{ok}/{n} · {_rng([a['width'] for a in arms])}")
        print(f"| {tt:g}° | " + " | ".join(cells) + " |")
    for lh in lhs:
        for k in autos:
            arms = [_arms(m, lh)[k] for m in models]
            ramps = [a["ramp"] for a in arms if a.get("ramp")]
            print(f"- 자동 램프 {k[4:]}° (층고 {lh:g}): 시작 Z′ "
                  f"{_rng([r[0] for r in ramps])}, 폭 "
                  f"{_rng([r[1] - r[0] for r in ramps])}mm, 바닥각 "
                  f"{models[0]['by_layer_height'][f'{lh:g}']['theta_bed_planner']:.2f}°")

    # ── [B] 팔별 승패, 기준선 = 균일 22° ──
    def row_vs(label, key, base_key="U22"):
        cells = []
        for lh in lhs:
            for col, _ko in COLS:
                pairs = []
                for m in models:
                    arms = _arms(m, lh)
                    pairs.append((_mm(arms.get(base_key), col), _mm(arms.get(key), col)))
                cells.append(tally(pairs, n))
        print(f"| {label} | " + " | ".join(cells) + " |")

    def head(first):
        print(f"| {first} | " + " | ".join(
            f"{lh:g} {ko}" for lh in lhs for _c, ko in COLS) + " |")
        print("|---|" + "---|" * (len(lhs) * len(COLS)))

    print("\n### [B] 팔별 승·무·패 — 기준선: **균일 22° (진짜 균일)**. "
          f"미지지 길이 mm, {TIE_MM}mm 안이면 무\n")
    head("팔 \\ 층고·프레임")
    cells = []
    for lh in lhs:
        for col, _ko in COLS:
            v = [_mm(_arms(m, lh)["U22"], col) for m in models]
            cells.append(f"중앙 {_med(v):.1f} ({min(v):.1f}~{max(v):.1f})")
    print("| **균일 22° (기준, mm)** | " + " | ".join(cells) + " |")
    row_vs("균일 θ_bed* (진짜 균일)", "Ubed")
    row_vs("균일 요청(J 최선) + 자동 램프", "UJ+ramp")
    for k in autos:
        row_vs(f"균일 요청 {k[4:]}° + 자동 램프", k)
    row_vs("밴드2(상한, J 최선)", "B2cap")
    for tt, z0 in fam:
        row_vs(f"족 22°→{tt:g}°, z0={z0:g}", f"F{tt:g}@{z0:g}")

    # ── [C] 같은 θ_top 의 자동 램프 / 균일 θ_bed* 와 비교 ──
    print("\n### [C] 올라가는 족 대 **같은 요청각의 자동 램프**, 그리고 자동 램프 대 "
          "**균일 θ_bed\\*** (승 = 앞의 것이 짧다)\n")
    head("비교")
    for tt, z0 in fam:
        if tt > THETA_BED and f"auto{tt:g}" in autos:
            row_vs(f"족 22°→{tt:g}°, z0={z0:g} 대 자동 램프 {tt:g}°",
                   f"F{tt:g}@{z0:g}", f"auto{tt:g}")
    for k in autos:
        row_vs(f"자동 램프 {k[4:]}° 대 균일 θ_bed*", k, "Ubed")
    for tt, z0 in fam:
        if tt > THETA_BED:
            row_vs(f"족 22°→{tt:g}°, z0={z0:g} 대 균일 θ_bed*", f"F{tt:g}@{z0:g}", "Ubed")

    # ── [D] 모델별 ──
    for lh in lhs:
        print(f"\n### [D] 모델별, 층고 {lh:g}mm — 미지지 길이 mm (연직 / 공구). "
              "'최선' 은 그 프레임에서 가장 짧은 팔(동률이면 평균|θ| 작은 쪽)\n")
        print("| 모델 | **균일 22°** | 균일 θ_bed* | 균일 요청(J)+자동 램프 | 자동 램프 최선: 연직 | "
              "자동 램프 최선: 공구 | 올라가는 족 최선: 연직 | 올라가는 족 최선: 공구 | "
              "내려가는 족 최선: 연직 / 공구 | 밴드2(상한) |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for m in models:
            arms = _arms(m, lh)

            def vt(key, arms=arms):
                a = arms.get(key)
                if a is None or "measured" not in a:
                    return "—"
                return f"{_mm(a, 'v'):.1f} / {_mm(a, 't'):.1f}"

            def bst(keys, col, arms=arms):
                a = best_arm(arms, keys, col)
                if a is None:
                    return "— (베드 불가)"
                tag = (f"{a['request']:g}°" if a["kind"] == "auto"
                       else f"→{a['theta_top']:g}° z0={a['z0']:g}")
                return f"{_mm(a, col):.1f} ({tag}, 평균 {a['mean_abs_theta']:.1f}°)"

            dn_v, dn_t = best_arm(arms, fam_dn, "v"), best_arm(arms, fam_dn, "t")
            dn = (f"{_mm(dn_v, 'v'):.1f} (→{dn_v['theta_top']:g}° z0={dn_v['z0']:g}) / "
                  f"{_mm(dn_t, 't'):.1f} (→{dn_t['theta_top']:g}° z0={dn_t['z0']:g})"
                  if dn_v else "—")
            b2 = arms["B2cap"]
            print(f"| {m['model']} | **{vt('U22')}** | {vt('Ubed')} | "
                  f"{vt('UJ+ramp')} ({arms['UJ+ramp']['request']:g}°) | "
                  f"{bst(auto_all, 'v')} | {bst(auto_all, 't')} | "
                  f"{bst(fam_up, 'v')} | {bst(fam_up, 't')} | {dn} | "
                  f"{vt('B2cap')} [{b2['thetas'][0]:g},{b2['thetas'][1]:g}] |")

    # ── [E] 최선 집계 ──
    print("\n### [E] '모델마다 최선' 집계 — 승·무·패 (지표마다 그 지표의 최선을 따로 고른다)\n")
    head("비교 (앞 대 뒤)")
    groups = (("올라가는 족 최선", fam_up), ("내려가는 족 최선", fam_dn),
              ("자동 램프 최선", auto_all))
    for gname, keys in groups:
        for bname, bkeys in (("**균일 22°**", ["U22"]), ("균일 θ_bed*", ["Ubed"]),
                             ("균일 요청(J)+자동 램프", ["UJ+ramp"]),
                             ("자동 램프 최선", auto_all)):
            if keys is bkeys:
                continue
            cells = []
            for lh in lhs:
                for col, _ko in COLS:
                    pairs = []
                    for m in models:
                        arms = _arms(m, lh)
                        a, b = best_arm(arms, keys, col), best_arm(arms, bkeys, col)
                        pairs.append((_mm(b, col), _mm(a, col)))
                    cells.append(tally(pairs, n))
            print(f"| {gname} 대 {bname} | " + " | ".join(cells) + " |")

    # ── [E2] 최선으로 뽑힌 모양의 분포 ──
    print("\n### [E2] '최선' 으로 뽑힌 모양 — 모델 수, 그리고 (그 팔 mm ÷ **균일 22°** mm) 의 중앙 (범위)\n")
    print("| 묶음 | 층고 | 지표 | 뽑힌 모양 (모델 수) | 팔 ÷ 균일 22° | 평균\\|θ\\| 중앙 |")
    print("|---|---|---|---|---|---|")
    for gname, keys in (("올라가는 족", fam_up), ("자동 램프", auto_all)):
        for lh in lhs:
            for col, ko in COLS:
                cnt, ratio, ang = {}, [], []
                for m in models:
                    arms = _arms(m, lh)
                    a = best_arm(arms, keys, col)
                    if a is None:
                        continue
                    tag = (f"요청 {a['request']:g}°" if a["kind"] == "auto"
                           else f"→{a['theta_top']:g}° z0={a['z0']:g}")
                    cnt[tag] = cnt.get(tag, 0) + 1
                    ratio.append(_mm(a, col) / _mm(arms["U22"], col))
                    ang.append(a["mean_abs_theta"])
                shapes = ", ".join(f"{k} ({v})" for k, v in
                                   sorted(cnt.items(), key=lambda kv: -kv[1]))
                print(f"| {gname} | {lh:g} | {ko} | {shapes} | {np.median(ratio):.2f} "
                      f"({min(ratio):.2f}~{max(ratio):.2f}) | {np.median(ang):.1f}° |")

    # ── [F] 압축(m<1)·팽창(m>1) 의 몫 ──
    print("\n### [F] 창을 m 배로 줄이면(늘리면) 얼마나 달라지나 — 기준선 **균일 22°** 대비 이득 "
          "(= 균일 22° mm − 팔 mm), 모델·팔 쌍 단위. 균일 팔은 m ≡ 1 이라 두 창이 같다\n")
    print("| 팔 묶음 | 층고 | 프레임 | 쌍 수 | 기본 창: 승·무·패 | m 창: 승·무·패 | "
          "m 창 + 층고 환산 길이(Σ길이·m): 승·무·패 | "
          "기본 창의 승이 m 창에서 승 / 무 / 패 | Σ이득: 기본 창 → m 창 → m 창·환산 (mm) | "
          "층 두께 덕에 통과한(+)·탓에 막힌(−) 길이 Σ(m 창 − 기본 창) mm | "
          "승인 쌍에서 그 몫 ÷ 이득: 중앙 (범위) | 미지지 중 m≠1 층의 몫: 기본 → m 창 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    sets = (("올라가는 족 (θ_top>22°, m<1)", fam_up, "mm_m_lt1"),
            ("자동 램프 (m<1)", autos, "mm_m_lt1"),
            ("내려가는 족 (θ_top<22°, m>1)", fam_dn, "mm_m_gt1"),
            ("밴드2(상한) (m>1)", ["B2cap"], "mm_m_gt1"))
    for sname, keys, mfield in sets:
        for lh in lhs:
            for col, ko in COLS[:2]:
                base, ms, eq = [], [], []
                tot_b = tot_m = cmp_b = cmp_m = 0.0
                for m in models:
                    arms = _arms(m, lh)
                    u = _mm(arms["U22"], col)
                    for k in keys:
                        a = arms.get(k)
                        if a is None or "measured" not in a:
                            continue
                        x, xs = _mm(a, col), _mm(a, col + "_ms")
                        base.append((u, x))
                        ms.append((u, xs))
                        eq.append((u, _mm(a, col + "_ms", "mm_eq")))
                        tot_b += x
                        tot_m += xs
                        cmp_b += a["measured"][col][mfield]
                        cmp_m += a["measured"][col + "_ms"][mfield]
                if not base:
                    continue
                vb = [verdict(u, x) for u, x in base]
                vm = [verdict(u, x) for u, x in ms]
                ve = [verdict(u, x) for u, x in eq]
                keep = [vm[i] for i in range(len(vb)) if vb[i] == "승"]
                gb = sum(u - x for u, x in base)
                gm = sum(u - x for u, x in ms)
                ge = sum(u - x for u, x in eq)
                shares = [(ms[i][1] - base[i][1]) / (base[i][0] - base[i][1])
                          for i in range(len(vb)) if vb[i] == "승"]
                share_txt = (f"{np.median(shares) * 100:.0f}% "
                             f"({min(shares) * 100:.0f}~{max(shares) * 100:.0f}%)"
                             if shares and mfield == "mm_m_lt1" else "—")
                print(f"| {sname} | {lh:g} | {ko} | {len(base)} | "
                      f"{vb.count('승')}·{vb.count('무')}·{vb.count('패')} | "
                      f"{vm.count('승')}·{vm.count('무')}·{vm.count('패')} | "
                      f"{ve.count('승')}·{ve.count('무')}·{ve.count('패')} | "
                      f"{keep.count('승')} / {keep.count('무')} / {keep.count('패')} | "
                      f"{gb:.0f} → {gm:.0f} → {ge:.0f} | {gb - gm:+.0f} | {share_txt} | "
                      f"{cmp_b / max(tot_b, 1e-12) * 100:.0f}% → "
                      f"{cmp_m / max(tot_m, 1e-12) * 100:.0f}% |")

    # ── [F2] 이득이 얇은 층에서만 나오는 팔 ──
    print("\n### [F2] 표식 — 기본 창에서는 **균일 22°** 를 이기는데 m 창에서는 못 이기는(무·패) 모델 수 "
          "/ 기본 창에서 이긴 모델 수\n")
    print("| 팔 | " + " | ".join(f"{lh:g} {ko}" for lh in lhs for _c, ko in COLS[:2]) + " |")
    print("|---|" + "---|" * (len(lhs) * 2))
    flag_rows = [("균일 요청(J 최선) + 자동 램프", "UJ+ramp")]
    flag_rows += [(f"균일 요청 {k[4:]}° + 자동 램프", k) for k in autos]
    flag_rows += [(f"족 22°→{tt:g}°, z0={z0:g}", f"F{tt:g}@{z0:g}") for tt, z0 in fam
                  if tt > THETA_BED]
    for label, key in flag_rows:
        cells = []
        for lh in lhs:
            for col, _ko in COLS[:2]:
                won = lost = 0
                for m in models:
                    arms = _arms(m, lh)
                    u, x, xs = (_mm(arms["U22"], col), _mm(arms.get(key), col),
                                _mm(arms.get(key), col + "_ms"))
                    if x is None or verdict(u, x) != "승":
                        continue
                    won += 1
                    lost += verdict(u, xs) != "승"
                cells.append(f"{lost}/{won}" if won else "—")
        print(f"| {label} | " + " | ".join(cells) + " |")

    # ── [G] 어디에 있나 / 각도·층간격 ──
    print("\n### [G] 미지지 길이의 위치와 층간격 (모델 범위 또는 합)\n")
    print("| 팔 | 층고 | 평균\\|θ\\| 중앙 (범위) | 실제 m 최소 | 실제 m 최대 | t_n 최대 mm | "
          "블렌드 Z′ 구간 (모델 범위) | 블렌드 층의 실공간 z | 미지지 최고 z: 연직 / 공구 | "
          "바닥 2mm 안의 몫: 연직 / 공구 | 블렌드 아래·블렌드·블렌드 위 (연직 Σmm) | 〃 (공구 Σmm) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows = [("**균일 22°**", "U22"), ("균일 θ_bed*", "Ubed"),
            ("균일 요청(J)+자동 램프", "UJ+ramp")]
    rows += [(f"자동 램프 {k[4:]}°", k) for k in autos]
    rows += [("밴드2(상한)", "B2cap")]
    rows += [(f"족 →{tt:g}°, z0={z0:g}", f"F{tt:g}@{z0:g}") for tt, z0 in fam]
    for label, key in rows:
        for lh in lhs:
            got = [_arms(m, lh).get(key) for m in models]
            got = [a for a in got if a is not None and "measured" in a]
            if not got:
                continue
            ms_ = [a["measured"] for a in got]

            def zmax(col, ms_=ms_):
                tops = [r[col]["z"][1] for r in ms_ if r[col]["z"]]
                return f"{max(tops):.2f}" if tops else "—"

            def near(col, ms_=ms_):
                tot = sum(r[col]["mm"] for r in ms_)
                return (f"{sum(r[col]['near_mm'] for r in ms_) / tot * 100:.0f}%"
                        if tot > 0 else "—")

            def zone(col, ms_=ms_):
                return " · ".join(f"{sum(r[col][f] for r in ms_):.0f}" for f in (
                    "mm_below_blend", "mm_in_blend", "mm_above_blend"))

            blends = [a["blend"][0] for a in got if a["blend"]]
            bz = [r["blend_real_z"] for r in ms_ if r["blend_real_z"]]
            ang = [a["mean_abs_theta"] for a in got]
            print(f"| {label} | {lh:g} | {_med(ang):.1f}° ({min(ang):.1f}~{max(ang):.1f}) | "
                  f"{min(r['m_min'] for r in ms_):.2f} | {max(r['m_max'] for r in ms_):.2f} | "
                  f"{max(r['t_n_max'] for r in ms_):.2f} | "
                  + (f"{_rng([b[0] for b in blends])} → {_rng([b[1] for b in blends])}"
                     if blends else "없음") + " | "
                  + (f"{min(b[0] for b in bz):.2f}~{max(b[1] for b in bz):.2f}"
                     if bz else "—") + " | "
                  f"{zmax('v')} / {zmax('t')} | {near('v')} / {near('t')} | "
                  f"{zone('v')} | {zone('t')} |")

    # ── [H] θ_top·z0 민감도 ──
    print("\n### [H] 올라가는 램프에서 θ_top 을 바꾸면 미지지 길이가 달라지나 — 같은 z0 에서 "
          f"θ_top 간 최대−최소가 {TIE_MM}mm 넘는 모델 수 (기준선 균일 22° 는 [B] 참고)\n")
    print("| 묶음 | " + " | ".join(f"{lh:g} {ko}" for lh in lhs for _c, ko in COLS) + " |")
    print("|---|" + "---|" * (len(lhs) * len(COLS)))
    z0_up = sorted({z0 for tt, z0 in fam if tt > THETA_BED})
    bundles = [(f"족 z0={z0:g}", [f"F{tt:g}@{z0:g}" for tt, zz in fam
                                  if tt > THETA_BED and zz == z0]) for z0 in z0_up]
    bundles.append(("자동 램프", autos))
    for bname, keys in bundles:
        cells = []
        for lh in lhs:
            for col, _ko in COLS:
                cnt = tot = 0
                for m in models:
                    arms = _arms(m, lh)
                    vals = [_mm(arms.get(k), col) for k in keys]
                    vals = [v for v in vals if v is not None]
                    if len(vals) >= 2:
                        tot += 1
                        cnt += (max(vals) - min(vals)) > TIE_MM
                cells.append(f"{cnt}/{tot}" if tot else "—")
        print(f"| {bname} | " + " | ".join(cells) + " |")


    # ── [I] 바닥이 같은 모델들 — 램프가 어디서 시작하느냐만 다르다 ──
    same = [m for m in models if m["model"].startswith("허리 r=")]
    if len(same) >= 2:
        print("\n### [I] 바닥이 같은 모델들(허리 r=…: 아래 구가 같고 목만 다르다) — 미지지 길이 mm "
              "(연직 / 공구), 괄호는 블렌드가 시작하는 Z′. 균일 팔이 여섯 모델에서 같다는 것이 "
              "'바닥이 같다' 의 확인이다\n")
        cols = [("**균일 22°**", "U22"), ("균일 θ_bed*", "Ubed")]
        cols += [(f"자동 램프 {k[4:]}°", k) for k in autos]
        cols += [(f"족 →{tt:g}° z0={z0:g}", f"F{tt:g}@{z0:g}") for tt, z0 in fam
                 if tt > THETA_BED]
        for lh in lhs:
            print(f"층고 {lh:g}mm\n")
            print("| 모델 | " + " | ".join(c for c, _k in cols) + " |")
            print("|---|" + "---|" * len(cols))
            for m in same:
                arms = _arms(m, lh)
                cells = []
                for _c, k in cols:
                    a = arms.get(k)
                    if a is None or "measured" not in a:
                        cells.append("베드 불가" if a is not None and not a["bed_legal"]
                                     else "—")
                        continue
                    start = f" ({a['blend'][0][0]:.2f})" if a["blend"] else ""
                    cells.append(f"{_mm(a, 'v'):.1f} / {_mm(a, 't'):.1f}{start}")
                print(f"| {m['model']} | " + " | ".join(cells) + " |")
            print()


def plot(data, path=DEFAULT_PNG):
    """θ_top 축의 응답 — 모델별 (팔 mm ÷ 균일 22° mm) 의 중앙값. 층고 × 프레임 4칸.

    한 축에 한 가지 양만 둔다(균일 22° 대비 비). 색은 팔의 정체(족 z0=1 / z0=2 / 자동 램프),
    선 모양은 창(실선 = 검사기 기본 창, 점선·빈 표식 = m 보정 창)이다.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from conical.plotstyle import L

    models = data["models"]
    lhs = list(data["meta"]["layer_heights"])
    fam = _fam_keys(data)
    autos = _auto_keys(data)
    ink, ink2, grid, surface = "#0b0b0b", "#52514e", "#dddcd7", "#fcfcfb"
    blue, orange, aqua, gray = "#2a78d6", "#eb6834", "#1baf7a", "#8a8983"

    def ratio(lh, key, col):
        """모델별 (팔 ÷ 균일 22°) — 그 팔을 잰 모델만."""
        out = []
        for m in models:
            arms = _arms(m, lh)
            u, x = _mm(arms["U22"], col), _mm(arms.get(key), col)
            if x is not None and u > 0:
                out.append(x / u)
        return out

    def series(lh, col, keys_x):
        xs, med, lo, hi = [], [], [], []
        for x, key in keys_x:
            r = [1.0] if key is None else ratio(lh, key, col)
            if not r:
                continue
            xs.append(x)
            med.append(np.median(r))
            lo.append(np.percentile(r, 25))
            hi.append(np.percentile(r, 75))
        return np.array(xs), np.array(med), np.array(lo), np.array(hi)

    groups = [(blue, "o", L("family z0=1", "족 z0=1"),
               sorted([(tt, f"F{tt:g}@1") for tt, zz in fam if zz == 1.0]
                      + [(THETA_BED, None)])),
              (aqua, "o", L("family z0=2", "족 z0=2"),
               sorted([(tt, f"F{tt:g}@2") for tt, zz in fam if zz == 2.0]
                      + [(THETA_BED, None)])),
              (orange, "s", L("auto ramp", "자동 램프"),
               [(float(k[4:]), k) for k in autos])]
    grid_x = sorted({x for _c, _m, _n, kx in groups for x, _k in kx})
    ticks = [x for x in grid_x if x != THETA_BED]
    fig, axes = plt.subplots(len(lhs), 2, figsize=(11.5, 4.1 * len(lhs) + 0.9),
                             sharex=True, squeeze=False, facecolor=surface)
    for i, lh in enumerate(lhs):
        tops = []
        for j, (col, ko) in enumerate(COLS[:2]):
            ax = axes[i][j]
            ax.set_facecolor(surface)
            ax.axhline(1.0, color=gray, lw=1.2, zorder=1)
            ends = []
            for color, mk, name, kx in groups:
                xs, med, lo, hi = series(lh, col, kx)
                if len(xs) < 2:
                    continue
                xm, mm_, _lo, _hi = series(lh, col + "_ms", kx)
                # 잰 격자점 사이만 잇는다 — 안 잰 θ_top 을 건너뛰는 선은 긋지 않는다
                for (xa, ya), ls, lw, z in (((xm, mm_), (0, (4, 2)), 1.6, 3),
                                            ((xs, med), "-", 2.0, 4)):
                    for k in range(len(xa) - 1):
                        if not any(xa[k] < t < xa[k + 1] for t in grid_x):
                            ax.plot(xa[k:k + 2], ya[k:k + 2], color=color, lw=lw, ls=ls,
                                    zorder=z)
                ax.plot(xm, mm_, ls="none", marker=mk, ms=6.5, mfc=surface, mec=color,
                        mew=1.4, zorder=5)
                ax.vlines(xs, lo, hi, color=color, lw=1, alpha=0.5, zorder=2)
                ax.plot(xs, med, ls="none", marker=mk, ms=7, mfc=color, mec=surface,
                        mew=1.0, zorder=6)
                ends.append((float(med[-1]), name, color))
                tops += [float(hi.max()), float(mm_.max())]
            rb = ratio(lh, "Ubed", col)
            th_b = models[0]["by_layer_height"][f"{lh:g}"]["theta_bed_planner"]
            ax.plot([th_b], [np.median(rb)], marker="D", ms=8, color=gray, mec=surface,
                    mew=1.5, ls="none", zorder=5)
            ax.set_title(L(f"layer {lh:g} mm · {'vertical' if col == 'v' else 'tool'} frame",
                           f"층고 {lh:g}mm · {ko} 프레임"), fontsize=11, color=ink,
                         loc="left")
            ax.set_xlim(-1.5, 47.5)
            ax.set_xticks(ticks)
            ax.grid(axis="y", color=grid, lw=0.6)
            ax.set_axisbelow(True)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            for sp in ("left", "bottom"):
                ax.spines[sp].set_color(grid)
            ax.tick_params(colors=ink2, labelsize=9)
            ax._ends = ends
            if j == 0:
                ax.set_ylabel(L("unsupported length ÷ strict uniform 22° (median of models)",
                                "미지지 길이 ÷ 균일 22° (모델 중앙값)"),
                              color=ink2, fontsize=9.5)
            if i == len(lhs) - 1:
                ax.set_xlabel(L("θ_top (deg): family 22° → θ_top / auto ramp: requested angle",
                                "θ_top (도): 족은 22° → θ_top, 자동 램프는 요청각"),
                              color=ink2, fontsize=9.5)
        ymax = max(1.25, max(tops)) * 1.08
        for j in range(2):
            ax = axes[i][j]
            ax.set_ylim(0, ymax)
            # 끝점 직접 라벨 — 실선 셋만 (점선은 범례가 설명한다). 겹치면 아래로 민다
            last = None
            for y, name, color in sorted(ax._ends, key=lambda t: -t[0]):
                yy = y if last is None else min(y, last - 0.06 * ymax)
                last = yy
                ax.annotate(name, (40.0, y), xytext=(41.6, yy), textcoords="data",
                            fontsize=9, color=ink, va="center",
                            arrowprops=dict(arrowstyle="-", color=color, lw=0.9))
    handles = [
        plt.Line2D([], [], color=blue, lw=2, marker="o", ms=7,
                   label=L("family 22°→θ_top, start z0 = 1.0 mm", "족 22°→θ_top, 시작 z0 = 1.0mm")),
        plt.Line2D([], [], color=aqua, lw=2, marker="o", ms=7,
                   label=L("family, start z0 = 2.0 mm", "족, 시작 z0 = 2.0mm")),
        plt.Line2D([], [], color=orange, lw=2, marker="s", ms=7,
                   label=L("uniform request + planner's auto bed ramp",
                           "균일 요청 + 계획기 자동 램프")),
        plt.Line2D([], [], color=ink2, lw=1.6, ls=(0, (4, 2)), marker="o", ms=6.5,
                   mfc=surface, mec=ink2,
                   label=L("same arm, checker window scaled by m",
                           "같은 팔, 검사기 창을 m 배로 (m 보정 창)")),
        plt.Line2D([], [], color=gray, lw=1.2,
                   label=L("strict uniform 22° (baseline)", "균일 22° 진짜 균일 (기준선)")),
        plt.Line2D([], [], color=gray, lw=0, marker="D", ms=8,
                   label=L("strict uniform at planner cap angle",
                           "균일 θ_bed* 진짜 균일 (계획기 상한각)")),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=9,
               labelcolor=ink)
    fig.suptitle(L(f"Bed-ramp shape sweep: unsupported perimeter ÷ strict uniform 22° "
                   f"({len(models)} models, bars = quartiles; computed, no prints)",
                   f"베드 램프 모양 스윕 — 미지지 길이 ÷ 균일 22° ({len(models)} 모델, "
                   "세로 막대 = 사분위. 계산값, 실물 0건)"),
                 fontsize=12, color=ink, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.085, 1, 0.955))
    fig.savefig(path, dpi=140, facecolor=surface)
    plt.close(fig)
    print(f"\n그림: {path}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--layer-height", type=float, nargs="+", default=list(LAYER_HS))
    ap.add_argument("--models", type=int, nargs="+", help="모델 번호만 (0~16)")
    ap.add_argument("--grid", choices=("sub", "full"), default="full",
                    help="full = 격자 전부(기본, 4코어 약 29분), sub = 표본 격자(약 17분)")
    ap.add_argument("--json", default=DEFAULT_JSON)
    ap.add_argument("--resume", action="store_true", help="JSON 에 있는 측정은 건너뛴다")
    ap.add_argument("--selfcheck", action="store_true", help="검산만 하고 끝낸다")
    ap.add_argument("--replay", action="store_true",
                    help="측정하지 않고 저장된 JSON 으로 표·그림만 다시 낸다")
    ap.add_argument("--png", default=DEFAULT_PNG)
    args = ap.parse_args()
    if args.selfcheck:
        return selfcheck()
    if not args.replay and args.jobs > 1 and "OPENBLAS_NUM_THREADS" not in os.environ:
        # 프로세스마다 BLAS 가 코어 수만큼 스레드를 띄우면 서로 밀어낸다 (4 프로세스에서
        # 측정 1회 8.6초 → 5.0초). 수치에는 영향이 없다. numpy 를 읽기 전에 정해야 해서
        # 환경변수를 넣고 자신을 다시 실행한다.
        os.environ.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                          MKL_NUM_THREADS="1")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    if args.replay:
        with open(args.json) as fh:
            data = json.load(fh)
    else:
        data = run(args)
    report(data)
    plot(data, args.png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
