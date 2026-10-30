"""Piecewise conical-angle band planning in transformed-height coordinates."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from .evaluation import DIRECTION_SIGNS, evaluate_model
from .mesh import ComponentGeometry, PreparedMesh


@dataclass(frozen=True)
class HeightInterval:
    """One component/group interval in its selected cone-height coordinate."""

    item_id: int
    h_min: float
    h_max: float


def signed_angle(direction: str, angle_degrees: float) -> float:
    """Return inward as negative and outward as positive degrees."""

    if direction not in DIRECTION_SIGNS:
        raise ValueError(f"알 수 없는 원뿔 방향: {direction}")
    return float(DIRECTION_SIGNS[direction] * angle_degrees)


def transformed_height_values(
    prepared: PreparedMesh,
    face_indices: list[int],
    direction: str,
    angle_degrees: float,
) -> np.ndarray:
    """Return h=z+d*r*tan(alpha) at every triangle vertex.

    This sign convention is consistent with the current face score
    ``g=n_z*cos(alpha)+d*n_r*sin(alpha)`` because the normalized gradient of
    ``h`` is ``d*e_r*sin(alpha)+e_z*cos(alpha)``.
    """

    if direction not in DIRECTION_SIGNS:
        raise ValueError(f"알 수 없는 원뿔 방향: {direction}")
    if not face_indices:
        raise ValueError("변환 높이를 계산할 면이 없습니다.")

    triangles = prepared.triangles[np.asarray(face_indices, dtype=np.int64)]
    vertices = triangles.reshape((-1, 3))
    radial = np.hypot(
        vertices[:, 0] - float(prepared.axis_x),
        vertices[:, 1] - float(prepared.axis_y),
    )
    tangent = math.tan(math.radians(float(angle_degrees)))
    direction_sign = float(DIRECTION_SIGNS[direction])
    heights = vertices[:, 2] + direction_sign * radial * tangent
    if not np.all(np.isfinite(heights)):
        raise ValueError("변환 높이 계산 결과에 NaN 또는 Infinity가 있습니다.")
    return np.asarray(heights, dtype=np.float64)


def transformed_height_interval(
    prepared: PreparedMesh,
    components: list[ComponentGeometry],
    direction: str,
    angle_degrees: float,
) -> tuple[float, float]:
    """Return the vertex-exact transformed-height union for components."""

    if not components:
        raise ValueError("변환 높이구간을 계산할 성분이 없습니다.")
    values = [
        transformed_height_values(
            prepared,
            component.face_indices,
            direction,
            angle_degrees,
        )
        for component in components
    ]
    return (
        float(min(float(np.min(item)) for item in values)),
        float(max(float(np.max(item)) for item in values)),
    )


def overlapping_interval_groups_bfs(
    intervals: list[HeightInterval],
    tolerance: float,
) -> list[list[int]]:
    """Find connected components of the interval-overlap graph with BFS."""

    if tolerance < 0.0 or not math.isfinite(tolerance):
        raise ValueError("height_overlap_tolerance은 유한한 0 이상의 값이어야 합니다.")
    if not intervals:
        return []

    adjacency: dict[int, list[int]] = {item.item_id: [] for item in intervals}
    ordered = sorted(intervals, key=lambda item: (item.h_min, item.h_max, item.item_id))

    # Sorted sweep: stop comparing once later h_min is above the current h_max.
    for position, current in enumerate(ordered):
        for other in ordered[position + 1 :]:
            if other.h_min > current.h_max + tolerance:
                break
            if current.h_min <= other.h_max + tolerance:
                adjacency[current.item_id].append(other.item_id)
                adjacency[other.item_id].append(current.item_id)

    visited: set[int] = set()
    groups: list[list[int]] = []
    order_ids = [item.item_id for item in ordered]
    for start in order_ids:
        if start in visited:
            continue
        queue: deque[int] = deque([start])
        visited.add(start)
        group: list[int] = []
        while queue:
            item_id = queue.popleft()
            group.append(item_id)
            for neighbor in adjacency[item_id]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        groups.append(sorted(group))
    return groups


def _evaluate_group(
    prepared: PreparedMesh,
    component_by_id: dict[int, ComponentGeometry],
    component_ids: list[int],
    angle_min: float,
    angle_max: float,
    quantile: float | None = None,
) -> dict[str, Any]:
    components = [component_by_id[item] for item in component_ids]
    _, _, selected = evaluate_model(components, angle_min, angle_max, quantile)
    direction = str(selected["direction"])
    angle = float(selected["angle"])
    h_min, h_max = transformed_height_interval(
        prepared,
        components,
        direction,
        angle,
    )
    return {
        "component_ids": sorted(component_ids),
        "direction": direction,
        "angle": angle,
        "signed_angle": signed_angle(direction, angle),
        "model_loss": float(selected["model_loss"]),
        "selection_reason": str(selected["selection_reason"]),
        "selection_method": str(selected["selection_method"]),
        "h_min": h_min,
        "h_max": h_max,
    }


def plan_slice_bands(
    prepared: PreparedMesh,
    components: list[ComponentGeometry],
    angle_min: float,
    angle_max: float,
    height_overlap_tolerance: float,
    quantile: float | None = None,
) -> dict[str, Any]:
    """Build non-separable transformed-height bands by repeated BFS merging.

    Start with one component per group. Each group chooses its own best direction
    and angle, obtains ``[h_min, h_max]``, and is connected to every overlapping
    group. BFS merges each connected set. Merging can change the compromise angle
    and therefore the interval, so the process repeats until no groups merge.
    """

    valid_components = [component for component in components if component.valid]
    if not valid_components:
        return {
            "status": "no_valid_overhang_components",
            "height_formula": "h = z + d*r*tan(alpha)",
            "direction_signs": dict(DIRECTION_SIGNS),
            "height_overlap_tolerance": float(height_overlap_tolerance),
            "iterations": 0,
            "component_intervals": [],
            "bands": [],
            "transitions": [],
        }

    component_by_id = {
        component.component_id: component for component in valid_components
    }
    groups = [[component.component_id] for component in valid_components]
    groups.sort(key=lambda item: item[0])
    component_plans = [
        _evaluate_group(
            prepared,
            component_by_id,
            group,
            angle_min,
            angle_max,
            quantile,
        )
        for group in groups
    ]
    component_plans.sort(key=lambda item: item["component_ids"][0])
    iteration = 0

    while True:
        iteration += 1
        plans = [
            _evaluate_group(
                prepared,
                component_by_id,
                group,
                angle_min,
                angle_max,
                quantile,
            )
            for group in groups
        ]
        intervals = [
            HeightInterval(index, plan["h_min"], plan["h_max"])
            for index, plan in enumerate(plans)
        ]
        merged_plan_indices = overlapping_interval_groups_bfs(
            intervals,
            height_overlap_tolerance,
        )
        merged_groups = [
            sorted(
                component_id
                for plan_index in plan_indices
                for component_id in groups[plan_index]
            )
            for plan_indices in merged_plan_indices
        ]
        merged_groups.sort(key=lambda item: item[0])

        if merged_groups == groups:
            final_plans = plans
            break
        groups = merged_groups

        # Every non-stable pass merges at least two groups, so C passes suffice.
        if iteration > len(valid_components):
            raise RuntimeError("변환 높이구간 BFS 병합이 수렴하지 않았습니다.")

    final_plans.sort(key=lambda item: (item["h_min"], item["h_max"]))
    bands: list[dict[str, Any]] = []
    for band_id, plan in enumerate(final_plans):
        bands.append({"band_id": band_id, **plan})

    transitions: list[dict[str, Any]] = []
    for lower, upper in zip(bands, bands[1:], strict=False):
        gap = float(upper["h_min"] - lower["h_max"])
        transitions.append(
            {
                "from_band_id": int(lower["band_id"]),
                "to_band_id": int(upper["band_id"]),
                "h_gap": gap,
                "transition_h": float((lower["h_max"] + upper["h_min"]) / 2.0),
                "angle_change": float(upper["signed_angle"] - lower["signed_angle"]),
            }
        )

    return {
        "status": "ok",
        "height_formula": "h = z + d*r*tan(alpha)",
        "direction_signs": dict(DIRECTION_SIGNS),
        "height_overlap_tolerance": float(height_overlap_tolerance),
        "iterations": iteration,
        "component_intervals": component_plans,
        "bands": bands,
        "transitions": transitions,
    }
