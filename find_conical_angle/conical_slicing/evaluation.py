"""Analytical conical-angle evaluation and model-level selection."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .mesh import ComponentGeometry, FaceGeometry


DIRECTION_SIGNS = {"inward": -1.0, "outward": 1.0}
TIE_ABSOLUTE_TOLERANCE = 1e-12
TIE_RELATIVE_TOLERANCE = 1e-12
EVALUATION_TOLERANCE = 1e-12
_TWO_PI = 2.0 * math.pi


def _score(face: FaceGeometry, angle_radians: float, direction_sign: float) -> float:
    return (
        face.nz * math.cos(angle_radians)
        + direction_sign * face.radial_normal * math.sin(angle_radians)
    )


def _best_bounded_angle(
    face: FaceGeometry,
    direction_sign: float,
    angle_min_radians: float,
    angle_max_radians: float,
) -> tuple[float, float]:
    """Return the smallest bounded angle that maximizes g_i(alpha)."""

    a = float(face.nz)
    b = direction_sign * float(face.radial_normal)
    phase = math.atan2(a, b)  # a*cos(alpha)+b*sin(alpha)=R*sin(alpha+phase)
    theta_min = angle_min_radians + phase
    theta_max = angle_max_radians + phase

    candidates = [angle_min_radians, angle_max_radians]
    first_k = math.ceil((theta_min - math.pi / 2.0) / _TWO_PI)
    last_k = math.floor((theta_max - math.pi / 2.0) / _TWO_PI)
    for k in range(first_k, last_k + 1):
        candidates.append(math.pi / 2.0 + _TWO_PI * k - phase)

    best_angle = angle_min_radians
    best_score = -math.inf
    for angle in candidates:
        if angle < angle_min_radians - EVALUATION_TOLERANCE:
            continue
        if angle > angle_max_radians + EVALUATION_TOLERANCE:
            continue
        bounded = min(angle_max_radians, max(angle_min_radians, angle))
        value = _score(face, bounded, direction_sign)
        if value > best_score + EVALUATION_TOLERANCE:
            best_angle = bounded
            best_score = value
        elif math.isclose(
            value,
            best_score,
            rel_tol=TIE_RELATIVE_TOLERANCE,
            abs_tol=TIE_ABSOLUTE_TOLERANCE,
        ) and bounded < best_angle:
            best_angle = bounded
            best_score = value
    return best_angle, best_score


def minimum_feasible_angle(
    face: FaceGeometry,
    kappa: float,
    direction: str,
    angle_min: float,
    angle_max: float,
) -> dict[str, Any]:
    """Solve g_i(alpha) >= kappa analytically inside a degree interval.

    The identity used is

        a*cos(alpha) + b*sin(alpha) = R*sin(alpha + delta),

    where ``a=n_z``, ``b=d*r_i``, ``R=hypot(a,b)``, and
    ``delta=atan2(a,b)``.  ``asin`` gives one boundary, and periodic sine
    intervals are intersected with the configured angle range so the principal
    branch alone cannot select a wrong quadrant.

    If the inequality has no solution in the configured interval, the returned
    fallback angle is the bounded angle that maximizes ``g_i``.
    """

    if direction not in DIRECTION_SIGNS:
        raise ValueError(f"알 수 없는 원뿔 방향: {direction}")
    if not all(math.isfinite(value) for value in (kappa, angle_min, angle_max)):
        raise ValueError("각도 범위와 kappa는 유한해야 합니다.")
    if angle_max < angle_min:
        raise ValueError("angle_max는 angle_min 이상이어야 합니다.")

    direction_sign = DIRECTION_SIGNS[direction]
    lower = math.radians(angle_min)
    upper = math.radians(angle_max)
    a = float(face.nz)
    b = direction_sign * float(face.radial_normal)
    radius = math.hypot(a, b)
    lower_score = _score(face, lower, direction_sign)

    if lower_score >= kappa - EVALUATION_TOLERANCE:
        return {
            "angle": float(angle_min),
            "feasible": True,
            "reason": "angle_min_already_feasible",
            "score": float(lower_score),
            "amplitude": float(radius),
        }

    if radius <= EVALUATION_TOLERANCE:
        best_angle, best_score = _best_bounded_angle(
            face, direction_sign, lower, upper
        )
        return {
            "angle": math.degrees(best_angle),
            "feasible": False,
            "reason": "constant_score_below_kappa",
            "score": float(best_score),
            "amplitude": float(radius),
        }

    if kappa > radius + EVALUATION_TOLERANCE:
        best_angle, best_score = _best_bounded_angle(
            face, direction_sign, lower, upper
        )
        return {
            "angle": math.degrees(best_angle),
            "feasible": False,
            "reason": "kappa_above_maximum_score",
            "score": float(best_score),
            "amplitude": float(radius),
        }

    if kappa <= -radius + EVALUATION_TOLERANCE:
        return {
            "angle": float(angle_min),
            "feasible": True,
            "reason": "entire_range_feasible",
            "score": float(lower_score),
            "amplitude": float(radius),
        }

    phase = math.atan2(a, b)
    threshold = max(-1.0, min(1.0, kappa / radius))
    boundary = math.asin(threshold)
    theta_min = lower + phase
    theta_max = upper + phase

    # sin(theta) >= threshold on
    # [boundary + 2*pi*k, pi - boundary + 2*pi*k].
    first_k = math.floor((theta_min - (math.pi - boundary)) / _TWO_PI) - 1
    last_k = math.ceil((theta_max - boundary) / _TWO_PI) + 1
    for k in range(first_k, last_k + 1):
        interval_start = boundary + _TWO_PI * k
        interval_end = math.pi - boundary + _TWO_PI * k
        candidate_theta = max(theta_min, interval_start)
        if candidate_theta <= min(theta_max, interval_end) + EVALUATION_TOLERANCE:
            candidate = min(upper, max(lower, candidate_theta - phase))
            candidate_score = _score(face, candidate, direction_sign)
            if candidate_score >= kappa - 10.0 * EVALUATION_TOLERANCE:
                return {
                    "angle": math.degrees(candidate),
                    "feasible": True,
                    "reason": "analytic_asin_boundary",
                    "score": float(candidate_score),
                    "amplitude": float(radius),
                }

    best_angle, best_score = _best_bounded_angle(face, direction_sign, lower, upper)
    return {
        "angle": math.degrees(best_angle),
        "feasible": False,
        "reason": "no_feasible_angle_in_range",
        "score": float(best_score),
        "amplitude": float(radius),
    }


def weighted_mean(values: list[float], weights: list[float]) -> float:
    """Return an arithmetic mean weighted by nonnegative finite weights."""

    if len(values) != len(weights) or not values:
        raise ValueError("weighted mean에는 같은 길이의 비어 있지 않은 입력이 필요합니다.")
    if any(
        not math.isfinite(value)
        or not math.isfinite(weight)
        or weight < 0.0
        for value, weight in zip(values, weights, strict=True)
    ):
        raise ValueError("weighted mean 입력은 유한해야 하며 가중치는 0 이상이어야 합니다.")
    total_weight = math.fsum(weights)
    if total_weight <= 0.0:
        raise ValueError("weighted mean의 전체 가중치는 0보다 커야 합니다.")
    return math.fsum(
        value * weight for value, weight in zip(values, weights, strict=True)
    ) / total_weight


def weighted_quantile(values: list[float], weights: list[float], p: float) -> float:
    """[수정 2026-10-30] 면적 가중 분위수 — 누적 가중치가 p·전체 에 처음 닿는 값.

    p=1 이면 최댓값(모든 면의 최소각을 만족 = 전부 통과), p=0.5 면 가중 중앙값.
    원본의 면적 가중 평균(`weighted_mean`)은 평균보다 큰 최소각의 면을 전부
    위반으로 남긴다(우리 모델에서 위반 면적 44~46 %, NOTES.md P1). 그 자리를
    바꿔 끼우는 규칙이고, quantile=None 이면 원본 그대로 평균을 쓴다.
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError("quantile p 는 0~1 이어야 합니다.")
    if len(values) != len(weights) or not values:
        raise ValueError("weighted quantile 에는 같은 길이의 비어 있지 않은 입력이 필요합니다.")
    order = sorted(range(len(values)), key=lambda i: values[i])
    total = math.fsum(weights)
    if total <= 0.0:
        raise ValueError("weighted quantile 의 전체 가중치는 0보다 커야 합니다.")
    target = p * total
    cumulative = 0.0
    for i in order:
        cumulative += weights[i]
        if cumulative >= target - 1e-12 * total:
            return float(values[i])
    return float(values[order[-1]])


def _select_angle(values: list[float], weights: list[float], quantile: float | None) -> float:
    return weighted_mean(values, weights) if quantile is None else weighted_quantile(values, weights, quantile)


def weighted_median(angles: list[float], weights: list[float]) -> float:
    """Legacy helper retained for callers; model selection now uses weighted mean."""

    if len(angles) != len(weights) or not angles:
        raise ValueError("weighted median에는 같은 길이의 비어 있지 않은 입력이 필요합니다.")
    grouped: dict[float, float] = {}
    for angle, weight in zip(angles, weights, strict=True):
        if not math.isfinite(angle) or not math.isfinite(weight) or weight < 0:
            raise ValueError("weighted median 입력은 유한해야 하며 가중치는 0 이상이어야 합니다.")
        grouped[float(angle)] = grouped.get(float(angle), 0.0) + float(weight)
    total = math.fsum(grouped.values())
    if total <= 0.0:
        raise ValueError("weighted median의 전체 가중치는 0보다 커야 합니다.")
    halfway = total / 2.0
    cumulative = 0.0
    for angle in sorted(grouped):
        cumulative += grouped[angle]
        if cumulative >= halfway:
            return angle
    return max(grouped)


def component_loss_at_angle(
    component: ComponentGeometry,
    angle_degrees: float,
    direction: str,
) -> float:
    """Recompute L_c,d at one selected angle."""

    if direction not in DIRECTION_SIGNS:
        raise ValueError(f"알 수 없는 원뿔 방향: {direction}")
    if not component.valid or component.kappa is None:
        raise ValueError("유효하지 않은 성분의 손실은 계산할 수 없습니다.")
    radians = math.radians(angle_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    sign = DIRECTION_SIGNS[direction]
    weighted_violation = math.fsum(
        face.area
        * max(
            0.0,
            float(component.kappa)
            - (face.nz * cosine + sign * face.radial_normal * sine),
        )
        for face in component.faces
    )
    return weighted_violation / component.area


def evaluate_component_direction(
    component: ComponentGeometry,
    angle_min: float,
    angle_max: float,
    direction: str,
    quantile: float | None = None,
) -> dict[str, Any]:
    """Solve each face minimum analytically and area-average the results."""

    if direction not in DIRECTION_SIGNS:
        raise ValueError(f"알 수 없는 원뿔 방향: {direction}")
    if not component.valid or component.kappa is None:
        return {
            "status": "invalid_component",
            "selection_method": "analytic_face_min_area_weighted_mean",
            "selected_angle": None,
            "selected_loss": None,
            "all_face_minima_feasible": False,
            "selected_angle_allows_all": False,
            "feasible_face_count": 0,
            "infeasible_face_count": 0,
            "feasible_area": 0.0,
            "infeasible_area": 0.0,
            "passed_area": 0.0,
            "violating_area": 0.0,
            "face_minimum_angles": [],
        }

    solutions = [
        minimum_feasible_angle(
            face,
            float(component.kappa),
            direction,
            angle_min,
            angle_max,
        )
        for face in component.faces
    ]
    areas = [float(face.area) for face in component.faces]
    minimum_angles = [float(item["angle"]) for item in solutions]
    selected_angle = _select_angle(minimum_angles, areas, quantile)
    selected_loss = component_loss_at_angle(component, selected_angle, direction)

    radians = math.radians(selected_angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    sign = DIRECTION_SIGNS[direction]
    selected_scores = np.asarray(
        [
            face.nz * cosine + sign * face.radial_normal * sine
            for face in component.faces
        ],
        dtype=np.float64,
    )
    area_array = np.asarray(areas, dtype=np.float64)
    passing = selected_scores >= float(component.kappa) - EVALUATION_TOLERANCE
    feasible = np.asarray([bool(item["feasible"]) for item in solutions], dtype=bool)

    return {
        "status": "ok",
        "selection_method": "analytic_face_min_area_weighted_mean",
        "selected_angle": float(selected_angle),
        "selected_loss": float(selected_loss),
        "all_face_minima_feasible": bool(np.all(feasible)),
        "selected_angle_allows_all": bool(np.all(passing)),
        "feasible_face_count": int(np.count_nonzero(feasible)),
        "infeasible_face_count": int(np.count_nonzero(~feasible)),
        "feasible_area": float(np.sum(area_array[feasible])),
        "infeasible_area": float(np.sum(area_array[~feasible])),
        "passed_area": float(np.sum(area_array[passing])),
        "violating_area": float(np.sum(area_array[~passing])),
        "face_minimum_angles": [
            {
                "face_index": int(face.face_index),
                "area": float(face.area),
                "angle": float(solution["angle"]),
                "feasible": bool(solution["feasible"]),
                "reason": str(solution["reason"]),
                "score_at_face_angle": float(solution["score"]),
                "amplitude": float(solution["amplitude"]),
            }
            for face, solution in zip(component.faces, solutions, strict=True)
        ],
    }


def evaluate_model(
    components: list[ComponentGeometry],
    angle_min: float,
    angle_max: float,
    quantile: float | None = None,
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Area-average analytical face minima, then choose the lower-loss direction."""

    if angle_max < angle_min:
        raise ValueError("angle_max는 angle_min 이상이어야 합니다.")
    evaluations: dict[int, dict[str, Any]] = {
        component.component_id: {} for component in components
    }
    valid_components = [component for component in components if component.valid]

    direction_results: dict[str, dict[str, Any]] = {}
    for direction in DIRECTION_SIGNS:
        for component in components:
            evaluations[component.component_id][direction] = evaluate_component_direction(
                component, angle_min, angle_max, direction, quantile
            )

        if not valid_components:
            status = (
                "no_overhang_components"
                if not components
                else "no_valid_overhang_components"
            )
            direction_results[direction] = {
                "status": status,
                "selection_method": "analytic_face_min_area_weighted_mean",
                "final_angle": float(angle_min),
                "model_loss": 0.0,
            }
            continue

        representative_angles = [
            float(evaluations[item.component_id][direction]["selected_angle"])
            for item in valid_components
        ]
        weights = [float(item.area) for item in valid_components]
        final_angle = _select_angle(representative_angles, weights, quantile)
        component_losses = [
            component_loss_at_angle(item, final_angle, direction)
            for item in valid_components
        ]
        total_area = math.fsum(weights)
        model_loss = math.fsum(
            item.area * loss
            for item, loss in zip(valid_components, component_losses, strict=True)
        ) / total_area
        direction_results[direction] = {
            "status": "ok",
            "selection_method": "analytic_face_min_area_weighted_mean",
            "final_angle": float(final_angle),
            "model_loss": float(model_loss),
        }

    inward = direction_results["inward"]
    outward = direction_results["outward"]
    losses_tied = math.isclose(
        float(inward["model_loss"]),
        float(outward["model_loss"]),
        rel_tol=TIE_RELATIVE_TOLERANCE,
        abs_tol=TIE_ABSOLUTE_TOLERANCE,
    )
    if not losses_tied:
        selected_direction = (
            "inward"
            if float(inward["model_loss"]) < float(outward["model_loss"])
            else "outward"
        )
        reason = "lower_model_loss"
    else:
        angles_tied = math.isclose(
            float(inward["final_angle"]),
            float(outward["final_angle"]),
            rel_tol=TIE_RELATIVE_TOLERANCE,
            abs_tol=TIE_ABSOLUTE_TOLERANCE,
        )
        if not angles_tied:
            selected_direction = (
                "inward"
                if float(inward["final_angle"]) < float(outward["final_angle"])
                else "outward"
            )
            reason = "tie_smaller_angle"
        else:
            selected_direction = "inward"
            reason = "tie_inward"

    selected = direction_results[selected_direction]
    selected_result = {
        "status": selected["status"],
        "direction": selected_direction,
        "angle": float(selected["final_angle"]),
        "model_loss": float(selected["model_loss"]),
        "selection_reason": reason,
        "selection_method": "analytic_face_min_area_weighted_mean",
    }
    return evaluations, direction_results, selected_result
