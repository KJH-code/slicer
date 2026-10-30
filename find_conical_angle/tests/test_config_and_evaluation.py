from __future__ import annotations

import math

import numpy as np
import pytest

from conical_slicing.config import ConfigError, candidate_angles, validate_config
from conical_slicing.evaluation import (
    component_loss_at_angle,
    evaluate_component_direction,
    evaluate_model,
    minimum_feasible_angle,
    weighted_mean,
    weighted_median,
)
from conical_slicing.mesh import ComponentGeometry, FaceGeometry


def make_component(
    *,
    component_id: int = 0,
    faces: list[FaceGeometry] | None = None,
    area: float = 1.0,
    nz: float = -1.0,
    radial: float = 0.0,
    kappa: float = -0.5,
) -> ComponentGeometry:
    if faces is None:
        faces = [FaceGeometry(0, area, nz, radial, [0.0, 0.0, 1.0])]
    total_area = math.fsum(face.area for face in faces)
    return ComponentGeometry(
        component_id=component_id,
        face_indices=[face.face_index for face in faces],
        faces=faces,
        area=total_area,
        bed_boundary=0.0,
        surface_boundary=0.0,
        support_boundary=0.0,
        bed_supported=False,
        q=0.0,
        kappa=kappa,
        radial_undefined_count=0,
        valid=True,
    )


def test_candidate_angles_remain_available_for_config_compatibility(base_config):
    config = dict(base_config, angle_min=0.0, angle_max=1.0, angle_step=0.3)
    values = candidate_angles(config)
    assert values.tolist() == pytest.approx([0.0, 0.3, 0.6, 0.9, 1.0])


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("angle_step", 0.0, "angle_step"),
        ("angle_min", -1.0, "angle_min"),
        ("kappa_max", -0.1, "kappa_max"),
        ("q0", 0.0, "q0"),
        ("bed_tolerance", -1.0, "bed_tolerance"),
    ],
)
def test_invalid_config_is_rejected_clearly(base_config, key, value, message):
    invalid = dict(base_config)
    invalid[key] = value
    with pytest.raises(ConfigError, match=message):
        validate_config(invalid)


def test_partial_axis_is_rejected(base_config):
    with pytest.raises(ConfigError, match="axis_x와 axis_y"):
        validate_config(dict(base_config, axis_x=1.0, axis_y=None))


def test_analytic_minimum_for_minus_cosine_is_sixty_degrees():
    face = FaceGeometry(0, 1.0, -1.0, 0.0, [0.0, 0.0, 1.0])
    result = minimum_feasible_angle(face, -0.5, "inward", 0.0, 60.0)
    assert result["feasible"] is True
    assert result["angle"] == pytest.approx(60.0)


def test_analytic_minimum_uses_correct_sine_quadrant():
    face = FaceGeometry(0, 1.0, -0.5, 0.5, [0.0, 0.0, 1.0])
    result = minimum_feasible_angle(face, 0.0, "outward", 0.0, 60.0)
    assert result["feasible"] is True
    assert result["angle"] == pytest.approx(45.0)


def test_angle_min_is_returned_when_already_feasible():
    face = FaceGeometry(0, 1.0, -0.2, 1.0, [0.0, 0.0, 1.0])
    result = minimum_feasible_angle(face, -0.5, "outward", 10.0, 60.0)
    assert result["feasible"] is True
    assert result["angle"] == pytest.approx(10.0)


def test_no_feasible_angle_uses_bounded_maximum_score():
    face = FaceGeometry(0, 1.0, -1.0, 0.0, [0.0, 0.0, 1.0])
    result = minimum_feasible_angle(face, 0.0, "outward", 0.0, 60.0)
    assert result["feasible"] is False
    assert result["angle"] == pytest.approx(60.0)
    assert result["score"] == pytest.approx(-0.5)


def test_component_angle_is_area_weighted_mean_of_face_minima():
    faces = [
        FaceGeometry(0, 3.0, -1.0, 0.0, [0.0, 0.0, 1.0]),
        FaceGeometry(1, 1.0, -0.5, 0.5, [0.0, 0.0, 1.0]),
    ]
    component = make_component(faces=faces, kappa=-0.5)
    result = evaluate_component_direction(component, 0.0, 60.0, "outward")
    # Face 0 requires 60 deg; face 1 already passes at 0 deg.
    assert result["selected_angle"] == pytest.approx(45.0)
    assert len(result["face_minimum_angles"]) == 2


def test_inward_and_outward_score_formula():
    component = make_component(nz=-0.5, radial=0.5, kappa=0.0)
    angle = 30.0
    inward = component_loss_at_angle(component, angle, "inward")
    outward = component_loss_at_angle(component, angle, "outward")
    expected_inward_g = -0.5 * math.cos(math.radians(angle)) - 0.5 * math.sin(
        math.radians(angle)
    )
    expected_outward_g = -0.5 * math.cos(math.radians(angle)) + 0.5 * math.sin(
        math.radians(angle)
    )
    assert inward == pytest.approx(max(0.0, -expected_inward_g))
    assert outward == pytest.approx(max(0.0, -expected_outward_g))


def test_weighted_mean():
    assert weighted_mean([10.0, 20.0], [3.0, 1.0]) == pytest.approx(12.5)


def test_weighted_median_is_retained_for_compatibility():
    assert weighted_median([10.0, 20.0, 20.0, 40.0], [2.0, 1.0, 3.0, 2.0]) == 20.0


def test_model_selects_direction_with_lower_loss():
    component = make_component(nz=-0.5, radial=1.0, kappa=0.0)
    _, directions, selected = evaluate_model([component], 0.0, 60.0)
    assert directions["outward"]["model_loss"] < directions["inward"]["model_loss"]
    assert selected["direction"] == "outward"


def test_equal_loss_and_angle_tie_selects_inward():
    component = make_component(nz=-0.5, radial=0.0, kappa=-0.5)
    _, directions, selected = evaluate_model([component], 0.0, 30.0)
    assert directions["inward"] == directions["outward"]
    assert selected["direction"] == "inward"
    assert selected["selection_reason"] == "tie_inward"


def test_no_components_returns_angle_min_status():
    _, directions, selected = evaluate_model([], 7.0, 8.0)
    assert directions["inward"]["status"] == "no_overhang_components"
    assert directions["outward"]["final_angle"] == 7.0
    assert selected["direction"] == "inward"
