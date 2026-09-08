"""
varangle.py — 높이 구간별 '변수각 원뿔' 전략 (부위별 각도의 실현 가능한 형태).

왜 '높이 구간'인가 (물리적 실현):
    부위마다 각도를 다르게 하려면, 실제로는 각도가 '높이에 따라 변하는 함수' θ(z)여야
    실제로 프린트할 수 있다. 이것이 RotBot의 변수각(var_angle) 방식이다. 그래서 영역을
    '오버행 심한 정도'가 아니라 '높이 구간'으로 나눈다. (높이 구간 = θ(z)로 실현 가능)

평가 방식 (정직):
    각 구간은 '상수각'으로 독립 평가한다(그 구간 면들에 그 각도를 적용했다고 가정).
    이는 이상적 추정이다 — 구간 경계에서 각도가 변하며 생기는 왜곡은 무시한다. 실측용이
    아니라 '균일각 하나 vs 구간별 여러 각도'의 경향 비교용이다. (각도가 급격히 변하면
    실제로는 왜곡이 생기므로, 구간은 적게/각도는 완만하게 두는 것이 전제.)

핵심 논지:
    균일각은 모델 전체에 대한 '타협값' 하나라 손해다. 구간별은 '각도 예산'을 오버행이
    심한 구간에만 몰아써서, 같은(또는 더 적은) 총 왜곡으로 서포트를 더 줄인다.
"""

import numpy as np

from .config import (THRESHOLD_DEG, MAX_ANGLE_DEG, ANGLE_STEP,
                     BLEND_COST_K, MAX_SPACING_FACTOR)
# 판정 기준 통일(2026-07 리뷰): metrics(변환공간 근사) → analytic(해석식).
# α=0 에서 두 정의는 일치, α>0 에서 해석식이 물리 기준이다.
from .analytic import face_support_and_staircase, support_fraction, \
    support_fraction_profile
from .profile import AngleProfile


# ─────────────────────────────────────────────────────────────
# 높이 구간 나누기
# ─────────────────────────────────────────────────────────────
def assign_height_bands(mesh, n_bands):
    """면을 centroid 높이(z)로 n_bands개 구간에 배정한다. (0=맨 아래)"""
    fz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    edges = np.linspace(fz.min(), fz.max(), n_bands + 1)
    # digitize 로 각 면을 구간에 배정 (경계 clip)
    labels = np.clip(np.digitize(fz, edges[1:-1]), 0, n_bands - 1)
    return labels, edges


# ─────────────────────────────────────────────────────────────
# 한 구간(또는 전체)에 대한 최적 각도/방향 — J 기준
# ─────────────────────────────────────────────────────────────
def best_angle_for_mask(mesh, mask, orig_areas, k,
                        max_angle=MAX_ANGLE_DEG, step=ANGLE_STEP,
                        threshold_deg=THRESHOLD_DEG):
    """mask 면들만 놓고 J=(서포트 감소 %) − k×각도 가 최대인 (각도, 방향)."""
    band_area = orig_areas[mask].sum()
    need0, _ = face_support_and_staircase(mesh, 0, "outward", threshold_deg)
    base_pct = orig_areas[mask & need0].sum() / band_area * 100.0

    best = (-1e9, 0, "outward")   # (J, angle, direction)
    for c in ("outward", "inward"):
        for a in range(0, max_angle + 1, step):
            need, _ = face_support_and_staircase(mesh, a, c, threshold_deg)
            pct = orig_areas[mask & need].sum() / band_area * 100.0
            J = (base_pct - pct) - k * a
            if J > best[0]:
                best = (J, a, c)
    return best[1], best[2]


# ─────────────────────────────────────────────────────────────
# 배정(각 구간의 각도)을 받아 전체 3지표를 계산
# ─────────────────────────────────────────────────────────────
def evaluate_assignment(mesh, assignment, threshold_deg=THRESHOLD_DEG):
    """assignment: [(mask, angle, cone_type), ...]  → 지표 dict.

      support_pct : 전체 대비 남은 서포트 넓이(%)   (낮을수록 좋음, 속도와 연결)
      staircase   : 강도 proxy (낮을수록 좋음)
      avg_angle   : 면적가중 평균 각도 (복잡도/왜곡 비용 proxy)
    """
    areas = mesh.area_faces
    total = areas.sum()
    sup_area = 0.0
    stair = 0.0
    ang_area = 0.0
    for mask, ang, c in assignment:
        need, st = face_support_and_staircase(mesh, ang, c, threshold_deg)
        sup_area += areas[mask & need].sum()
        stair += (st[mask] * areas[mask]).sum()
        ang_area += ang * areas[mask].sum()
    return {
        "support_pct": sup_area / total * 100.0,
        "staircase": stair / total,
        "avg_angle": ang_area / total,
    }


# ─────────────────────────────────────────────────────────────
# 전략들: 균일 / 구간별 / 세밀(면마다)
# ─────────────────────────────────────────────────────────────
def select_uniform(mesh, k, max_angle=MAX_ANGLE_DEG, step=ANGLE_STEP,
                   threshold_deg=THRESHOLD_DEG):
    """전역 단일 각도 (RotBot식 균일 원뿔 = 비교 대상)."""
    allmask = np.ones(len(mesh.faces), dtype=bool)
    a, c = best_angle_for_mask(mesh, allmask, mesh.area_faces, k,
                               max_angle, step, threshold_deg)
    m = evaluate_assignment(mesh, [(allmask, a, c)], threshold_deg)
    return {"strategy": "uniform", "n_regions": 1, "profile": [(a, c)], **m}


def select_banded(mesh, k, n_bands, max_angle=MAX_ANGLE_DEG, step=ANGLE_STEP,
                  threshold_deg=THRESHOLD_DEG):
    """높이 n_bands 구간, 각 구간에 최적 각도 (변수각 θ(z)로 실현 가능)."""
    labels, edges = assign_height_bands(mesh, n_bands)
    areas = mesh.area_faces
    assignment = []
    profile = []
    for i in range(n_bands):
        mask = labels == i
        if not mask.any():
            profile.append(None)
            continue
        a, c = best_angle_for_mask(mesh, mask, areas, k, max_angle, step, threshold_deg)
        assignment.append((mask, a, c))
        profile.append((a, c))
    m = evaluate_assignment(mesh, assignment, threshold_deg)
    return {"strategy": f"banded-{n_bands}", "n_regions": n_bands,
            "profile": profile, "edges": edges, **m}


# ─────────────────────────────────────────────────────────────
# 프로필 단위 평가 — J 에 '블렌드 비용'을 넣는다
# ─────────────────────────────────────────────────────────────
def blend_penalty(mesh, profile, radius_profile=None,
                  spacing_limit=MAX_SPACING_FACTOR, direction="outward"):
    """블렌드 비용 = Σ (그 구간에 있는 표면적 %) × (m−1)/(limit−1).

    (m−1)/(limit−1) 은 '허용된 층간격 여유를 얼마나 썼는가'(0~1)다. 각도 변화가
    없으면 블렌드 구간 자체가 없어 0 이 되고, J 는 균일각 J 와 정확히 같아진다.

    ⚠ 왜 필요한가: analytic 의 판정은 면을 '그 높이의 국소 원뿔각'과만 비교하므로
      블렌드에서 레이어가 벌어지는 것을 못 본다. 그 눈먼 부분을 메우는 항이다.
    ⚠ 선형 가중은 유도된 물리가 아닌 휴리스틱 (analyze_blend_k.py 로 창 분석).
    """
    if spacing_limit is None or spacing_limit <= 1.0:
        return 0.0
    c = 1.0 if direction == "outward" else -1.0
    fz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    areas = mesh.area_faces
    total = areas.sum()
    cost = 0.0
    for i in range(len(profile.zs) - 1):
        a, b = float(profile.zs[i]), float(profile.zs[i + 1])
        dt = profile.tans[i + 1] - profile.tans[i]
        if abs(dt) < 1e-12:
            continue
        s = dt / (b - a)
        r = (radius_profile.max_between(a, b) if radius_profile is not None
             else float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max()))
        m = abs(1.0 - c * r * s)
        risk = min(1.0, max(0.0, (m - 1.0) / (spacing_limit - 1.0)))
        area_pct = areas[(fz >= a) & (fz <= b)].sum() / total * 100.0
        cost += area_pct * risk
    return float(cost)


def profile_objective(mesh, profile, base_pct, k, k_blend=BLEND_COST_K,
                      radius_profile=None, spacing_limit=MAX_SPACING_FACTOR,
                      threshold_deg=THRESHOLD_DEG):
    """프로필 하나의 J = (서포트 감소 %p) − k×평균|θ| − k_blend×블렌드 비용.

    상수 프로필이면 블렌드 비용 0, 평균|θ| = 그 각도 → 균일각 J 와 동일하다
    (tests/test_blend_cost_j.py 가 강제).
    """
    sup = support_fraction_profile(mesh, profile, threshold_deg)
    fz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    areas = mesh.area_faces
    mean_ang = float((np.abs(profile.theta_at(fz)) * areas).sum() / areas.sum())
    pen = blend_penalty(mesh, profile, radius_profile, spacing_limit)
    return {"J": (base_pct - sup) - k * mean_ang - k_blend * pen,
            "support_pct": sup, "avg_angle": mean_ang, "blend_penalty": pen}


def _merge_bands(edges, thetas):
    """같은 각도인 이웃 밴드 병합 → 불필요한 블렌드를 안 만든다."""
    bands = [[float(edges[0]), float(edges[1]), float(thetas[0])]]
    for i in range(1, len(thetas)):
        if abs(thetas[i] - bands[-1][2]) < 1e-12:
            bands[-1][1] = float(edges[i + 1])
        else:
            bands.append([float(edges[i]), float(edges[i + 1]), float(thetas[i])])
    return [tuple(b) for b in bands]


def select_banded_j(mesh, k, n_bands, r_max, radius_profile=None,
                    spacing_limit=MAX_SPACING_FACTOR, max_shift=0.0,
                    k_blend=BLEND_COST_K, max_angle=MAX_ANGLE_DEG,
                    step=ANGLE_STEP, threshold_deg=THRESHOLD_DEG,
                    max_sweeps=4):
    """밴드별 각도를 '실제로 만들어질 프로필'의 J 로 고른다 (좌표하강).

    select_banded 와의 차이: 저기는 밴드마다 독립적으로 '그 구간만 놓고' 최적
    각도를 고른다 — 각도를 바꾸는 데 드는 블렌드 비용을 아예 모른다. 여기서는
    후보 각도를 넣어 프로필을 실제로 만들고(층간격 제약 포함) 그 프로필의 J 를
    잰다. 그래서 '블렌드가 비싼 모델(구처럼 어디나 뚱뚱한)'에서는 저절로 균일각
    쪽으로 수렴하고, '허리가 있는 모델'에서만 각도를 나눈다.

    탐색: 밴드 수 N 에 대해 전수 조사는 후보^N 이라 못 한다. '한 밴드씩 돌아가며
    다시 고르기'(좌표하강)를 값이 안 변할 때까지 — 비용은 N × 후보수 × 스윕 번의
    프로필 평가로 선형이다.

    ⚠ 좌표하강만으로는 균일해를 놓친다(실측으로 발견): 구에서 [36°,0°] 로 출발하면
      균일 [36°,36°] 로 가려면 두 밴드를 '동시에' 바꿔야 하는데, 한 칸씩 움직이는
      중간 상태([36°,2°] 등)가 블렌드 비용을 다 물어서 [2°,2°] 같은 국소 최적에
      갇힌다. 그래서 균일 후보(모든 밴드 같은 각도)를 전부 따로 평가해 넣는다.
      부수 효과로 **결과가 균일 원뿔보다 나쁠 수 없다**(J 기준)는 성질이 생긴다.
    """
    labels, edges = assign_height_bands(mesh, n_bands)
    areas = mesh.area_faces
    base_pct = support_fraction(mesh, 0.0, "outward", threshold_deg)

    # 후보 각도(부호 있음: 음수=inward). 0 은 한 번만.
    cands = sorted({float(sgn * a)
                    for a in range(0, max_angle + 1, step)
                    for sgn in (1, -1)})

    def build(thetas):
        return AngleProfile.from_bands(
            _merge_bands(edges, thetas), r_max, radius_profile=radius_profile,
            spacing_limit=spacing_limit, max_shift=max_shift)

    def score(thetas):
        try:
            prof = build(thetas)
        except ValueError:
            return None, {"J": -1e9}
        return prof, profile_objective(mesh, prof, base_pct, k, k_blend,
                                       radius_profile, spacing_limit,
                                       threshold_deg)

    def descend(thetas):
        thetas = list(thetas)
        prof, met = score(thetas)
        for _ in range(max_sweeps):
            changed = False
            for i in range(n_bands):
                best_t, best_m, best_p = thetas[i], met, prof
                for t in cands:
                    if t == thetas[i]:
                        continue
                    trial = list(thetas)
                    trial[i] = t
                    p, m = score(trial)
                    if m["J"] > best_m["J"] + 1e-9:
                        best_t, best_m, best_p = t, m, p
                if best_t != thetas[i]:
                    thetas[i] = best_t
                    met, prof = best_m, best_p
                    changed = True
            if not changed:
                break
        return thetas, prof, met

    # 출발점 ①: 기존 방식(밴드 독립 선택) — 블렌드 비용을 모르는 선택
    start = []
    for i in range(n_bands):
        mask = labels == i
        if not mask.any():
            start.append(start[-1] if start else 0.0)
            continue
        a, c = best_angle_for_mask(mesh, mask, areas, k, max_angle, step,
                                   threshold_deg)
        start.append(float(a) if c == "outward" else -float(a))

    # 출발점 ②: 균일 후보 전수 (좌표하강이 못 가는 곳 — 위 ⚠ 참조)
    best_uni, best_uni_m = None, {"J": -1e9}
    for t in cands:
        _, m = score([t] * n_bands)
        if m["J"] > best_uni_m["J"]:
            best_uni, best_uni_m = [t] * n_bands, m

    results = [descend(start)]
    if best_uni is not None:
        results.append(descend(best_uni))
    thetas, prof, met = max(results, key=lambda r: r[2]["J"])

    return {"strategy": f"banded-{n_bands}-J", "n_regions": n_bands,
            "edges": edges, "thetas": thetas, "start_thetas": start,
            "uniform_best": best_uni[0] if best_uni else None,
            "uniform_J": best_uni_m["J"],
            "profile_obj": prof, "staircase": float("nan"), **met}


def select_fine(mesh, k, max_angle=MAX_ANGLE_DEG, step=ANGLE_STEP,
                threshold_deg=THRESHOLD_DEG):
    """세밀: 면마다 각자 최적 각도 (복잡도 최대 = 성능 하한선/이론적 바닥).

    각 (각도,방향)을 전체에 한 번씩만 적용해 면별 지표를 미리 구하고, 면마다 자기
    J가 가장 큰 각도를 고른다. '이보다 더 줄이긴 어렵다'는 기준선.
    """
    areas = mesh.area_faces
    F = len(mesh.faces)
    need0, _ = face_support_and_staircase(mesh, 0, "outward", threshold_deg)
    # 면별 baseline 서포트(0/1). J는 면 단위로 (감소) - k*각도.
    best_J = np.full(F, -1e9)
    best_ang = np.zeros(F, dtype=int)
    best_need = need0.copy()
    best_stair = np.zeros(F)
    _, stair0 = face_support_and_staircase(mesh, 0, "outward", threshold_deg)
    for c in ("outward", "inward"):
        for a in range(0, max_angle + 1, step):
            need, st = face_support_and_staircase(mesh, a, c, threshold_deg)
            # 면 단위 J: baseline에서 서포트가 사라지면 +1(=100%p*면), 각도비용 -k*a
            gain = (need0.astype(float) - need.astype(float)) * 100.0
            J = gain - k * a
            better = J > best_J
            best_J[better] = J[better]
            best_ang[better] = a
            best_need[better] = need[better]
            best_stair[better] = st[better]
    total = areas.sum()
    return {
        "strategy": "fine", "n_regions": F,
        "support_pct": areas[best_need].sum() / total * 100.0,
        "staircase": (best_stair * areas).sum() / total,
        "avg_angle": (best_ang * areas).sum() / total,
        "profile": None,
    }
