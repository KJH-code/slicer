"""Reusable high-level STL analysis API."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .bands import plan_slice_bands
from .config import load_config
from .evaluation import evaluate_model
from .mesh import (
    FaceClass,
    find_overhang_components,
    load_stl_mesh,
    prepare_mesh,
)


SCHEMA_VERSION = "1.3"
ASSUMPTIONS = [
    (
        "Only non-bed faces with the original winding's cross-product z component "
        "below -cross_z_epsilon are evaluated as overhangs; faces with n_z >= 0 "
        "may become risky at a tilted cone angle but are intentionally excluded."
    ),
    (
        "B_c^down contains component-boundary overhang faces for which at least "
        "one globally shortest dual-graph path to a bed face exits the component "
        "immediately and then crosses no other overhang face."
    ),
    (
        "The component support score is q=A_c^down/A_c. Legacy bed, surface, and "
        "total shared-edge boundary lengths remain diagnostic outputs but no longer "
        "determine kappa."
    ),
    (
        "Mesh winding and topology are inspected and reported but never repaired, "
        "merged, reoriented, or otherwise modified automatically."
    ),
    (
        "The cone axis remains fixed throughout one analysis and radial direction "
        "is evaluated at each overhang triangle centroid."
    ),
    (
        "Each face minimum angle is solved analytically with an inverse-sine "
        "boundary and then area-weighted; angle_step is retained only for "
        "configuration compatibility and is not used for angle sweeping."
    ),
    (
        "Piecewise bands use vertex-exact h=z+d*r*tan(alpha) intervals and "
        "BFS overlap grouping. This is a slicing-plan heuristic; toolpath "
        "generation and transition feasibility must be enforced downstream."
    ),
]


def _component_to_dict(
    component: Any,
    direction_evaluations: dict[str, Any],
    component_interval: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "component_id": int(component.component_id),
        "face_indices": [int(index) for index in component.face_indices],
        "face_count": len(component.face_indices),
        "area": float(component.area),
        "bed_boundary": float(component.bed_boundary),
        "surface_boundary": float(component.surface_boundary),
        "support_boundary": float(component.support_boundary),
        "downward_boundary_face_indices": [
            int(index) for index in component.downward_boundary_face_indices
        ],
        "downward_boundary_face_count": len(
            component.downward_boundary_face_indices
        ),
        "downward_boundary_area": float(component.downward_boundary_area),
        "downward_boundary_ratio": (
            None
            if component.downward_boundary_ratio is None
            else float(component.downward_boundary_ratio)
        ),
        "bed_supported": bool(component.bed_supported),
        "q": None if component.q is None else float(component.q),
        "q_source": "downward_boundary_area_ratio",
        "kappa": None if component.kappa is None else float(component.kappa),
        "radial_undefined_count": int(component.radial_undefined_count),
        "faces": [
            {
                "face_index": int(face.face_index),
                "area": float(face.area),
                "nz": float(face.nz),
                "radial_normal": float(face.radial_normal),
                "centroid": [float(value) for value in face.centroid],
            }
            for face in component.faces
        ],
        "direction_evaluations": direction_evaluations,
        "selected_component_result": component_interval,
        "downward_boundary_face_indices": [
            int(index)
            for index in component.downward_boundary_face_indices
        ],
        "downward_boundary_area": float(
            component.downward_boundary_area
        ),
        "downward_boundary_ratio": (
            None
            if component.downward_boundary_ratio is None
            else float(component.downward_boundary_ratio)
        ),
    }


def _assert_json_safe(result: dict[str, Any]) -> None:
    """Fail internally if a non-standard numeric value escaped conversion."""

    json.dumps(result, ensure_ascii=False, allow_nan=False)


def analyze_stl(
    stl_path: str | Path,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze one STL and return a standard-JSON-serializable dictionary.

    ``config`` may be omitted or may contain a partial set of overrides. Defaults
    are loaded from the project ``config.json`` and all values are validated.
    """

    started = time.perf_counter()
    resolved_config = load_config(overrides=config)
    source = Path(stl_path).expanduser()
    mesh = load_stl_mesh(source)
    prepared = prepare_mesh(mesh, resolved_config)
    components = find_overhang_components(prepared, resolved_config)
    angle_min = float(resolved_config["angle_min"])
    angle_max = float(resolved_config["angle_max"])
    evaluations, direction_results, selected_result = evaluate_model(
        components,
        angle_min,
        angle_max,
    )
    slice_plan = plan_slice_bands(
        prepared,
        components,
        angle_min,
        angle_max,
        float(resolved_config["height_overlap_tolerance"]),
    )
    interval_by_component = {
        int(item["component_ids"][0]): item
        for item in slice_plan["component_intervals"]
        if len(item["component_ids"]) == 1
    }

    classes = prepared.face_classes
    warnings = prepared.warnings.as_list()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "input": {
            "stl_path": str(source),
            "absolute_path": str(source.resolve()),
        },
        "config": dict(resolved_config),
        "axis": {
            "x": float(prepared.axis_x),
            "y": float(prepared.axis_y),
            "source": prepared.axis_source,
        },
        "mesh_summary": {
            "face_count": int(len(prepared.faces)),
            "bed_face_count": int(np.count_nonzero(classes == int(FaceClass.BED))),
            "non_overhang_face_count": int(
                np.count_nonzero(classes == int(FaceClass.NON_OVERHANG))
            ),
            "overhang_face_count": int(
                np.count_nonzero(classes == int(FaceClass.OVERHANG))
            ),
            "degenerate_face_count": int(
                np.count_nonzero(classes == int(FaceClass.DEGENERATE))
            ),
            "overhang_component_count": len(components),
            "open_boundary_edge_count": int(prepared.open_boundary_edge_count),
            "non_manifold_edge_count": int(prepared.non_manifold_edge_count),
            "inconsistent_winding_edge_count": int(
                prepared.inconsistent_winding_edge_count
            ),
            "warning_count": int(prepared.warnings.occurrence_count),
            "warning_type_count": len(warnings),
        },
        "assumptions": list(ASSUMPTIONS),
        "warnings": warnings,
        "components": [
            _component_to_dict(
                component,
                evaluations[component.component_id],
                interval_by_component.get(component.component_id),
            )
            for component in components
        ],
        "direction_results": direction_results,
        "selected_result": selected_result,
        "slice_plan": slice_plan,
        "runtime_seconds": float(time.perf_counter() - started),
    }
    _assert_json_safe(result)
    return result


def write_json(result: dict[str, Any], output_path: str | Path) -> Path:
    """Write an analysis result as strict UTF-8 JSON and return its path."""

    destination = Path(output_path)
    try:
        with destination.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                result,
                stream,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            stream.write("\n")
    except OSError as exc:
        raise OSError(f"JSON 결과를 저장할 수 없습니다: {destination} ({exc})") from exc
    return destination
