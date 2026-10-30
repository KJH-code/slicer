"""Mesh loading, tolerance-aware topology, classification, and BFS components."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Hashable, Iterator

import numpy as np
import trimesh


class MeshAnalysisError(ValueError):
    """Raised for an unreadable or unusable STL mesh."""


class FaceClass(IntEnum):
    BED = 0
    NON_OVERHANG = 1
    OVERHANG = 2
    DEGENERATE = 3


VertexKey = tuple[Hashable, Hashable, Hashable]
EdgeKey = tuple[VertexKey, VertexKey]


@dataclass
class EdgeRecord:
    key: EdgeKey
    endpoints: np.ndarray
    faces: list[int] = field(default_factory=list)
    directions: list[tuple[VertexKey, VertexKey]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.endpoints[1] - self.endpoints[0]))


@dataclass
class PreparedMesh:
    vertices: np.ndarray
    faces: np.ndarray
    triangles: np.ndarray
    face_classes: np.ndarray
    face_edge_keys: list[tuple[EdgeKey, EdgeKey, EdgeKey]]
    edges: dict[EdgeKey, EdgeRecord]
    axis_x: float
    axis_y: float
    axis_source: str
    warnings: "WarningCollector"
    open_boundary_edge_count: int
    non_manifold_edge_count: int
    inconsistent_winding_edge_count: int


@dataclass
class FaceGeometry:
    face_index: int
    area: float
    nz: float
    radial_normal: float
    centroid: list[float]


@dataclass
class ComponentGeometry:
    component_id: int
    face_indices: list[int]
    faces: list[FaceGeometry]
    area: float
    bed_boundary: float
    surface_boundary: float
    support_boundary: float
    downward_boundary_face_indices: list[int]
    downward_boundary_area: float
    downward_boundary_ratio: float | None
    bed_supported: bool
    q: float | None
    kappa: float | None
    radial_undefined_count: int
    valid: bool


class WarningCollector:
    """Aggregate warning occurrences without flooding JSON output."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def add(self, code: str, message: str, count: int = 1) -> None:
        if count <= 0:
            return
        if code in self._items:
            self._items[code]["count"] += int(count)
        else:
            self._items[code] = {
                "code": code,
                "count": int(count),
                "message": message,
            }

    def as_list(self) -> list[dict[str, Any]]:
        return [dict(value) for value in self._items.values()]

    @property
    def occurrence_count(self) -> int:
        return sum(int(item["count"]) for item in self._items.values())


def load_stl_mesh(path: str | Path) -> trimesh.Trimesh:
    """Load one STL as a triangle mesh without repairing or reorienting it."""

    source = Path(path)
    if not source.exists():
        raise MeshAnalysisError(f"STL 파일이 존재하지 않습니다: {source}")
    if not source.is_file():
        raise MeshAnalysisError(f"STL 경로가 파일이 아닙니다: {source}")
    try:
        loaded = trimesh.load_mesh(str(source), process=False)
    except Exception as exc:  # trimesh raises several format/backend exception types
        raise MeshAnalysisError(f"STL 파일을 불러오지 못했습니다: {source} ({exc})") from exc
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise MeshAnalysisError(f"STL 메시가 비어 있습니다: {source}")
        try:
            loaded = loaded.to_mesh()
        except AttributeError:
            loaded = trimesh.util.concatenate(tuple(loaded.geometry.values()))
    if not isinstance(loaded, trimesh.Trimesh):
        raise MeshAnalysisError(f"삼각형 메시로 해석할 수 없는 STL입니다: {source}")
    if len(loaded.faces) == 0 or len(loaded.vertices) == 0:
        raise MeshAnalysisError(f"STL 메시가 비어 있습니다: {source}")
    return loaded


def _vertex_key(vertex: np.ndarray, tolerance: float) -> VertexKey:
    if tolerance == 0.0:
        return (float(vertex[0]), float(vertex[1]), float(vertex[2]))
    return tuple(int(round(float(coordinate) / tolerance)) for coordinate in vertex)  # type: ignore[return-value]


def _edge_key(start: VertexKey, end: VertexKey) -> EdgeKey:
    return (start, end) if start <= end else (end, start)


def prepare_mesh(mesh: trimesh.Trimesh, config: dict[str, Any]) -> PreparedMesh:
    """Classify faces and build shared-edge topology in one O(N)-style pass."""

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
        raise MeshAnalysisError("입력은 삼각형으로 구성된 3차원 메시여야 합니다.")
    if len(vertices) == 0 or len(faces) == 0:
        raise MeshAnalysisError("STL 메시가 비어 있습니다.")
    if not np.all(np.isfinite(vertices)):
        raise MeshAnalysisError("STL 꼭짓점 좌표에 NaN 또는 Infinity가 있습니다.")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise MeshAnalysisError("STL 면 인덱스가 꼭짓점 범위를 벗어납니다.")

    triangles = vertices[faces]
    bed_mask = np.max(
        np.abs(triangles[:, :, 2] - float(config["bed_z"])), axis=1
    ) <= float(config["bed_tolerance"])

    side_a = triangles[:, 1] - triangles[:, 0]
    side_b = triangles[:, 2] - triangles[:, 0]
    cross_z = side_a[:, 0] * side_b[:, 1] - side_a[:, 1] * side_b[:, 0]
    cross_epsilon = float(config["cross_z_epsilon"])
    # A face with |c_z| > epsilon cannot have a full cross-product norm <=
    # epsilon. Compute x/y cross terms only for the ambiguous subset so the
    # global fast path remains the requested c_z-only classification.
    ambiguous_mask = (~bed_mask) & (np.abs(cross_z) <= cross_epsilon)
    degenerate_mask = np.zeros(len(faces), dtype=bool)
    if np.any(ambiguous_mask):
        ambiguous_cross = np.cross(side_a[ambiguous_mask], side_b[ambiguous_mask])
        degenerate_mask[ambiguous_mask] = (
            np.linalg.norm(ambiguous_cross, axis=1) <= cross_epsilon
        )
    overhang_mask = (
        (~bed_mask)
        & (~degenerate_mask)
        & (cross_z < -cross_epsilon)
    )

    classes = np.full(len(faces), int(FaceClass.NON_OVERHANG), dtype=np.int8)
    classes[bed_mask] = int(FaceClass.BED)
    classes[degenerate_mask] = int(FaceClass.DEGENERATE)
    classes[overhang_mask] = int(FaceClass.OVERHANG)

    vertex_tolerance = float(config["vertex_tolerance"])
    normalized_vertices = [_vertex_key(vertex, vertex_tolerance) for vertex in vertices]
    edges: dict[EdgeKey, EdgeRecord] = {}
    face_edge_keys: list[tuple[EdgeKey, EdgeKey, EdgeKey]] = []
    local_edges = ((0, 1), (1, 2), (2, 0))
    for face_index, face in enumerate(faces):
        keys: list[EdgeKey] = []
        for local_start, local_end in local_edges:
            start_index = int(face[local_start])
            end_index = int(face[local_end])
            start_key = normalized_vertices[start_index]
            end_key = normalized_vertices[end_index]
            key = _edge_key(start_key, end_key)
            keys.append(key)
            record = edges.get(key)
            if record is None:
                record = EdgeRecord(
                    key=key,
                    endpoints=np.asarray(
                        [vertices[start_index], vertices[end_index]], dtype=np.float64
                    ),
                )
                edges[key] = record
            if face_index not in record.faces:
                record.faces.append(face_index)
                record.directions.append((start_key, end_key))
        face_edge_keys.append((keys[0], keys[1], keys[2]))

    open_count = sum(len(record.faces) == 1 for record in edges.values())
    non_manifold_count = sum(len(record.faces) >= 3 for record in edges.values())
    inconsistent_count = 0
    for record in edges.values():
        if len(record.faces) == 2:
            first, second = record.directions
            if first == second:
                inconsistent_count += 1

    warnings = WarningCollector()
    warnings.add(
        "open_boundary_edges",
        "이웃 면이 없는 열린 메시 변이 있습니다. 이 변은 지지 경계에 포함하지 않았습니다.",
        open_count,
    )
    warnings.add(
        "non_manifold_edges",
        "세 개 이상의 면이 연결된 non-manifold 변이 있습니다.",
        non_manifold_count,
    )
    warnings.add(
        "inconsistent_winding_edges",
        "공유 변 양쪽 면의 winding 방향이 일관되지 않습니다. 메시를 자동 수정하지 않았습니다.",
        inconsistent_count,
    )
    warnings.add(
        "degenerate_faces",
        "퇴화 삼각형을 오버행 분석에서 제외했습니다.",
        int(np.count_nonzero(degenerate_mask)),
    )

    if config["axis_x"] is None:
        bounds_min = np.min(vertices, axis=0)
        bounds_max = np.max(vertices, axis=0)
        axis_x = float((bounds_min[0] + bounds_max[0]) / 2.0)
        axis_y = float((bounds_min[1] + bounds_max[1]) / 2.0)
        axis_source = "bounding_box_center"
    else:
        axis_x = float(config["axis_x"])
        axis_y = float(config["axis_y"])
        axis_source = "user"

    return PreparedMesh(
        vertices=vertices,
        faces=faces,
        triangles=triangles,
        face_classes=classes,
        face_edge_keys=face_edge_keys,
        edges=edges,
        axis_x=axis_x,
        axis_y=axis_y,
        axis_source=axis_source,
        warnings=warnings,
        open_boundary_edge_count=open_count,
        non_manifold_edge_count=non_manifold_count,
        inconsistent_winding_edge_count=inconsistent_count,
    )


def _iter_face_neighbors(
    prepared: PreparedMesh,
    face_index: int,
) -> Iterator[int]:
    """Yield unique faces sharing at least one edge with ``face_index``."""

    emitted: set[int] = set()
    for edge_key in prepared.face_edge_keys[face_index]:
        for neighbor in prepared.edges[edge_key].faces:
            if neighbor == face_index or neighbor in emitted:
                continue
            emitted.add(neighbor)
            yield neighbor


def _face_distances_from_bed(
    prepared: PreparedMesh,
    *,
    allow_overhang: bool,
) -> np.ndarray:
    """Return unweighted dual-graph distances from every reachable face to BED.

    When ``allow_overhang`` is false, OVERHANG and DEGENERATE faces are blocked.
    When it is true, only DEGENERATE faces are blocked.  A value of ``-1`` means
    that no permitted path reaches a bed face.
    """

    distances = np.full(len(prepared.faces), -1, dtype=np.int64)
    queue: deque[int] = deque()

    for value in np.flatnonzero(prepared.face_classes == int(FaceClass.BED)):
        face_index = int(value)
        distances[face_index] = 0
        queue.append(face_index)

    while queue:
        current = queue.popleft()
        next_distance = int(distances[current]) + 1

        for neighbor in _iter_face_neighbors(prepared, current):
            if distances[neighbor] >= 0:
                continue

            neighbor_class = FaceClass(int(prepared.face_classes[neighbor]))
            if neighbor_class == FaceClass.DEGENERATE:
                continue
            if not allow_overhang and neighbor_class == FaceClass.OVERHANG:
                continue

            distances[neighbor] = next_distance
            queue.append(neighbor)

    return distances


def _downward_boundary_face_indices(
    prepared: PreparedMesh,
    component_indices: list[int],
    distance_all: np.ndarray,
    distance_safe: np.ndarray,
) -> list[int]:
    """Return B_c^down for one overhang component.

    A component boundary face belongs to B_c^down when at least one globally
    shortest path from that face to BED exits the component immediately and then
    reaches BED without passing through any OVERHANG face.  The starting face is
    itself overhang and is therefore excluded from the no-overhang condition.
    """

    component_set = set(component_indices)
    selected: list[int] = []

    for face_index in component_indices:
        shortest_distance = int(distance_all[face_index])
        if shortest_distance <= 0:
            continue

        for neighbor in _iter_face_neighbors(prepared, face_index):
            if neighbor in component_set:
                continue

            neighbor_class = FaceClass(int(prepared.face_classes[neighbor]))
            if neighbor_class not in (FaceClass.BED, FaceClass.NON_OVERHANG):
                continue

            safe_distance = int(distance_safe[neighbor])
            if safe_distance < 0:
                continue

            if 1 + safe_distance == shortest_distance:
                selected.append(face_index)
                break

    selected.sort()
    return selected


def _face_geometry(
    prepared: PreparedMesh,
    face_index: int,
    radial_epsilon: float,
) -> tuple[FaceGeometry, bool]:
    triangle = prepared.triangles[face_index]
    cross = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    cross_length = float(np.linalg.norm(cross))
    normal = cross / cross_length
    centroid = np.mean(triangle, axis=0)
    radial_xy = np.asarray(
        [centroid[0] - prepared.axis_x, centroid[1] - prepared.axis_y],
        dtype=np.float64,
    )
    radial_length = float(np.linalg.norm(radial_xy))
    radial_undefined = radial_length <= radial_epsilon
    if radial_undefined:
        radial_normal = 0.0
    else:
        radial_normal = float(np.dot(normal[:2], radial_xy / radial_length))
    return (
        FaceGeometry(
            face_index=face_index,
            area=cross_length / 2.0,
            nz=float(normal[2]),
            radial_normal=radial_normal,
            centroid=[float(value) for value in centroid],
        ),
        radial_undefined,
    )


def find_overhang_components(
    prepared: PreparedMesh,
    config: dict[str, Any],
) -> list[ComponentGeometry]:
    """Find overhang components and evaluate downward bed-connected boundaries."""

    overhang_indices = np.flatnonzero(
        prepared.face_classes == int(FaceClass.OVERHANG)
    )
    if overhang_indices.size == 0:
        return []

    # These two dual-graph BFS passes are shared by every overhang component.
    # distance_all permits overhang faces; distance_safe blocks them.
    distance_all = _face_distances_from_bed(prepared, allow_overhang=True)
    distance_safe = _face_distances_from_bed(prepared, allow_overhang=False)

    scheduled: set[int] = set()
    components: list[ComponentGeometry] = []

    for start_value in overhang_indices:
        start = int(start_value)
        if start in scheduled:
            continue
        queue: deque[int] = deque([start])
        scheduled.add(start)
        component_indices: list[int] = []
        component_faces: list[FaceGeometry] = []
        counted_boundary_edges: set[EdgeKey] = set()
        bed_boundary = 0.0
        surface_boundary = 0.0
        bed_supported = False
        radial_undefined_count = 0

        while queue:
            face_index = queue.popleft()
            component_indices.append(face_index)
            geometry, radial_undefined = _face_geometry(
                prepared,
                face_index,
                float(config["radial_epsilon"]),
            )
            component_faces.append(geometry)
            radial_undefined_count += int(radial_undefined)

            for key in prepared.face_edge_keys[face_index]:
                record = prepared.edges[key]
                neighbors = [index for index in record.faces if index != face_index]
                if not neighbors:
                    continue

                neighbor_classes = {
                    FaceClass(int(prepared.face_classes[index])) for index in neighbors
                }
                for neighbor in neighbors:
                    if (
                        prepared.face_classes[neighbor] == int(FaceClass.OVERHANG)
                        and neighbor not in scheduled
                    ):
                        scheduled.add(neighbor)
                        queue.append(neighbor)

                boundary_kind: str | None = None
                if FaceClass.BED in neighbor_classes:
                    boundary_kind = "bed"
                elif (
                    FaceClass.NON_OVERHANG in neighbor_classes
                    or FaceClass.DEGENERATE in neighbor_classes
                ):
                    boundary_kind = "surface"

                if boundary_kind is not None and key not in counted_boundary_edges:
                    counted_boundary_edges.add(key)
                    if boundary_kind == "bed":
                        bed_boundary += record.length
                        bed_supported = True
                    else:
                        surface_boundary += record.length

        component_faces.sort(key=lambda item: item.face_index)
        component_indices.sort()
        area = float(math.fsum(face.area for face in component_faces))
        support_boundary = float(bed_boundary + surface_boundary)
        valid = math.isfinite(area) and area > 0.0

        downward_indices = _downward_boundary_face_indices(
            prepared,
            component_indices,
            distance_all,
            distance_safe,
        )

        area_by_face = {
            face.face_index: face.area
            for face in component_faces
        }

        downward_area = float(
            math.fsum(area_by_face[index] for index in downward_indices)
        )

        downward_ratio = (
            downward_area / area
            if valid
            else None
        )

        if not valid:
            q = None
            kappa = None
            prepared.warnings.add(
                "invalid_components",
                "면적이 0이거나 유효하지 않은 오버행 성분을 각도 평가에서 제외했습니다.",
            )

        elif support_boundary == 0.0:
            q = 0.0
            kappa = 0.0

        elif downward_area > 0.0:
            q = support_boundary / math.sqrt(downward_area)
            kappa = (
                -float(config["kappa_max"])
                * q
                / (q + float(config["q0"]))
            )

        else:
            # downward_area → 0일 때 q → ∞이므로
            # kappa의 극한은 -kappa_max
            q = None
            kappa = -float(config["kappa_max"])

            prepared.warnings.add(
                "zero_downward_boundary_area",
                "아랫방향 경계 면적이 0이어서 kappa를 극한값 -kappa_max로 처리했습니다.",
            )  
        components.append(
            ComponentGeometry(
                component_id=len(components),
                face_indices=component_indices,
                faces=component_faces,
                area=area,
                bed_boundary=float(bed_boundary),
                surface_boundary=float(surface_boundary),
                support_boundary=support_boundary,
                downward_boundary_face_indices=downward_indices,
                downward_boundary_area=downward_area,
                downward_boundary_ratio=(
                    float(downward_ratio) if downward_ratio is not None else None
                ),
                bed_supported=bed_supported,
                q=float(q) if q is not None else None,
                kappa=float(kappa) if kappa is not None else None,
                radial_undefined_count=radial_undefined_count,
                valid=valid,
            )
        )

    total_radial_undefined = sum(item.radial_undefined_count for item in components)
    prepared.warnings.add(
        "radial_direction_undefined",
        "중심점이 원뿔축 위에 있어 방사 법선 성분을 0으로 처리한 면이 있습니다.",
        total_radial_undefined,
    )
    return components
