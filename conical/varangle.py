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

from .config import THRESHOLD_DEG, MAX_ANGLE_DEG, ANGLE_STEP
# 판정 기준 통일(2026-07 리뷰): metrics(변환공간 근사) → analytic(해석식).
# α=0 에서 두 정의는 일치, α>0 에서 해석식이 물리 기준이다.
from .analytic import face_support_and_staircase


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
