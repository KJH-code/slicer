from __future__ import annotations

import math

import numpy as np
import pytest

from conical_slicing.mesh import (
    EdgeRecord,
    FaceClass,
    PreparedMesh,
    WarningCollector,
    _downward_boundary_face_indices,
    _face_distances_from_bed,
    find_overhang_components,
    prepare_mesh,
)
from conftest import triangle_mesh


def _prepared_face_graph(
    face_classes: list[FaceClass],
    adjacency: list[tuple[int, int]],
) -> PreparedMesh:
    """Build the minimum PreparedMesh needed for dual-graph BFS tests."""

    face_count = len(face_classes)
    edge_keys_by_face: list[list[tuple]] = [[] for _ in range(face_count)]
    edges: dict[tuple, EdgeRecord] = {}

    def make_vertex_key(seed: int, endpoint: int) -> tuple[int, int, int]:
        return (seed, endpoint, 0)

    edge_seed = 0
    for first, second in adjacency:
        start = make_vertex_key(edge_seed, 0)
        end = make_vertex_key(edge_seed, 1)
        key = (start, end)
        edges[key] = EdgeRecord(
            key=key,
            endpoints=np.asarray([[edge_seed, 0.0, 0.0], [edge_seed, 1.0, 0.0]]),
            faces=[first, second],
            directions=[(start, end), (end, start)],
        )
        edge_keys_by_face[first].append(key)
        edge_keys_by_face[second].append(key)
        edge_seed += 1

    for face_index in range(face_count):
        while len(edge_keys_by_face[face_index]) < 3:
            start = make_vertex_key(edge_seed, 0)
            end = make_vertex_key(edge_seed, 1)
            key = (start, end)
            edges[key] = EdgeRecord(
                key=key,
                endpoints=np.asarray(
                    [[edge_seed, 0.0, 0.0], [edge_seed, 1.0, 0.0]]
                ),
                faces=[face_index],
                directions=[(start, end)],
            )
            edge_keys_by_face[face_index].append(key)
            edge_seed += 1

    return PreparedMesh(
        vertices=np.zeros((face_count * 3, 3), dtype=np.float64),
        faces=np.arange(face_count * 3, dtype=np.int64).reshape((face_count, 3)),
        triangles=np.zeros((face_count, 3, 3), dtype=np.float64),
        face_classes=np.asarray([int(item) for item in face_classes], dtype=np.int8),
        face_edge_keys=[tuple(keys[:3]) for keys in edge_keys_by_face],
        edges=edges,
        axis_x=0.0,
        axis_y=0.0,
        axis_source="test",
        warnings=WarningCollector(),
        open_boundary_edge_count=0,
        non_manifold_edge_count=0,
        inconsistent_winding_edge_count=0,
    )


def test_bed_face_is_classified_before_normal_direction(base_config):
    mesh = triangle_mesh([[0, 0, 0], [0, 1, 0], [1, 0, 0]])
    prepared = prepare_mesh(mesh, base_config)
    assert prepared.face_classes.tolist() == [int(FaceClass.BED)]
    assert find_overhang_components(prepared, base_config) == []


def test_edge_connected_downward_faces_form_one_component(base_config):
    mesh = triangle_mesh(
        [[0, 0, 1], [0, 1, 1], [1, 0, 1], [1, 1, 1]],
        [[0, 1, 2], [1, 3, 2]],
    )
    prepared = prepare_mesh(mesh, base_config)
    components = find_overhang_components(prepared, base_config)
    assert len(components) == 1
    assert components[0].face_indices == [0, 1]
    assert components[0].support_boundary == 0.0
    assert components[0].downward_boundary_face_indices == []
    assert components[0].downward_boundary_area == 0.0
    assert components[0].q == 0.0


def test_disconnected_downward_regions_form_separate_components(base_config):
    mesh = triangle_mesh(
        [
            [0, 0, 1], [0, 1, 1], [1, 0, 1],
            [10, 0, 1], [10, 1, 1], [11, 0, 1],
        ]
    )
    components = find_overhang_components(prepare_mesh(mesh, base_config), base_config)
    assert len(components) == 2


def test_bed_boundary_is_counted_once_and_sets_support(base_config):
    vertices = [
        [0, 0, 0], [0, 1, 0], [1, 0, 1],
        [1, 0, 0],
    ]
    mesh = triangle_mesh(vertices, [[0, 1, 2], [1, 0, 3]])
    components = find_overhang_components(prepare_mesh(mesh, base_config), base_config)
    component = components[0]
    assert component.bed_boundary == pytest.approx(1.0)
    assert component.surface_boundary == 0.0
    assert component.bed_supported is True
    assert component.downward_boundary_face_indices == [0]
    assert component.downward_boundary_area == pytest.approx(component.area)
    assert component.downward_boundary_ratio == pytest.approx(1.0)


def test_surface_boundary_is_counted_once(base_config):
    vertices = [
        [0, 0, 1], [0, 1, 1], [1, 0, 2], [-1, 0, 2],
    ]
    mesh = triangle_mesh(vertices, [[0, 1, 2], [0, 1, 3]])
    components = find_overhang_components(prepare_mesh(mesh, base_config), base_config)
    component = components[0]
    assert component.bed_boundary == 0.0
    assert component.surface_boundary == pytest.approx(1.0)


def test_open_edges_are_warned_but_not_support_boundary(base_config):
    mesh = triangle_mesh([[0, 0, 1], [0, 1, 1], [1, 0, 1]])
    prepared = prepare_mesh(mesh, base_config)
    component = find_overhang_components(prepared, base_config)[0]
    assert component.support_boundary == 0.0
    assert prepared.open_boundary_edge_count == 3
    warning = next(item for item in prepared.warnings.as_list() if item["code"] == "open_boundary_edges")
    assert warning["count"] == 3


def test_default_and_user_axis(base_config):
    mesh = triangle_mesh([[0, 2, 1], [0, 6, 1], [10, 2, 1]])
    default = prepare_mesh(mesh, base_config)
    assert (default.axis_x, default.axis_y, default.axis_source) == (5.0, 4.0, "bounding_box_center")

    custom_config = dict(base_config, axis_x=2.5, axis_y=-3.0)
    custom = prepare_mesh(mesh, custom_config)
    assert (custom.axis_x, custom.axis_y, custom.axis_source) == (2.5, -3.0, "user")


def test_radial_component_is_zero_at_axis(base_config):
    mesh = triangle_mesh([[0, 0, 1], [0, 1, 1], [1, 0, 1]])
    config = dict(base_config, axis_x=1.0 / 3.0, axis_y=1.0 / 3.0)
    prepared = prepare_mesh(mesh, config)
    component = find_overhang_components(prepared, config)[0]
    assert component.faces[0].radial_normal == 0.0
    assert component.radial_undefined_count == 1


def test_q_and_kappa_use_downward_boundary_area_ratio(base_config):
    vertices = [[0, 0, 0], [0, 1, 0], [1, 0, 1], [1, 0, 0]]
    mesh = triangle_mesh(vertices, [[0, 1, 2], [1, 0, 3]])
    component = find_overhang_components(prepare_mesh(mesh, base_config), base_config)[0]
    expected_q = component.downward_boundary_area / component.area
    expected_kappa = -base_config["kappa_max"] * expected_q / (expected_q + base_config["q0"])
    assert component.q == pytest.approx(expected_q)
    assert component.downward_boundary_ratio == pytest.approx(expected_q)
    assert component.kappa == pytest.approx(expected_kappa)


def test_downward_boundary_rejects_longer_safe_detour():
    # 0=BED, 1/4=NON_OVERHANG, 2/3=one OVERHANG component.
    # Face 2 reaches BED in 2 steps through overhang face 3, but its safe route
    # 2->1->4->0 takes 3 steps.  Therefore only face 3 is in B_c^down.
    prepared = _prepared_face_graph(
        [
            FaceClass.BED,
            FaceClass.NON_OVERHANG,
            FaceClass.OVERHANG,
            FaceClass.OVERHANG,
            FaceClass.NON_OVERHANG,
        ],
        [(2, 3), (3, 0), (2, 1), (1, 4), (4, 0)],
    )
    distance_all = _face_distances_from_bed(prepared, allow_overhang=True)
    distance_safe = _face_distances_from_bed(prepared, allow_overhang=False)

    assert distance_all.tolist() == [0, 2, 2, 1, 1]
    assert _downward_boundary_face_indices(
        prepared, [2, 3], distance_all, distance_safe
    ) == [3]


def test_downward_boundary_accepts_safe_path_tied_for_shortest():
    # Face 2 has two shortest paths of length 2: 2->3->0 through an overhang,
    # and 2->1->0 without another overhang.  Existence of the safe shortest path
    # is sufficient, so both component faces belong to B_c^down.
    prepared = _prepared_face_graph(
        [
            FaceClass.BED,
            FaceClass.NON_OVERHANG,
            FaceClass.OVERHANG,
            FaceClass.OVERHANG,
        ],
        [(2, 3), (3, 0), (2, 1), (1, 0)],
    )
    distance_all = _face_distances_from_bed(prepared, allow_overhang=True)
    distance_safe = _face_distances_from_bed(prepared, allow_overhang=False)

    assert _downward_boundary_face_indices(
        prepared, [2, 3], distance_all, distance_safe
    ) == [2, 3]


def test_duplicate_vertex_indices_still_share_normalized_edge(base_config):
    vertices = [
        [0, 0, 1], [0, 1, 1], [1, 0, 1],
        [0, 1, 1], [1, 1, 1], [1, 0, 1],
    ]
    mesh = triangle_mesh(vertices, [[0, 1, 2], [3, 4, 5]])
    prepared = prepare_mesh(mesh, base_config)
    components = find_overhang_components(prepared, base_config)
    assert len(components) == 1
    assert len(components[0].face_indices) == 2


def test_non_manifold_bed_has_priority_and_edge_counted_once(base_config):
    vertices = [
        [0, 0, 0], [0, 1, 0], [1, 0, 1],
        [1, 0, 0], [-1, 0, 1],
    ]
    # One downward face, one bed face, and one non-overhang face share edge (0, 1).
    mesh = triangle_mesh(vertices, [[0, 1, 2], [1, 0, 3], [0, 1, 4]])
    prepared = prepare_mesh(mesh, base_config)
    component = find_overhang_components(prepared, base_config)[0]
    assert prepared.non_manifold_edge_count == 1
    assert component.bed_boundary == pytest.approx(1.0)
    assert component.surface_boundary == 0.0
