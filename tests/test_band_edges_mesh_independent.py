"""밴드 경계의 메시 독립 옵션 (`band_edges="bounds"`) — 회귀 테스트.

T4 (docs/test_t1_t4.md §3.3): 중점 분할(세분화 ×4)은 형상을 바꾸지 않는데 자동 밴드2 의
각도가 바뀌었다. 한 원인은 밴드 등분점을 **면 중심 z** 의 범위로 잡는 것이다 — 면을 쪼개면
면 중심 범위가 실제 높이 쪽으로 넓어져 경계가 움직인다 (docs/test_band_boundary.md).

    (a) 기본값("centroid")은 예전 식 그대로다 (기존 결과 보존)
    (b) "bounds" 경계는 세분화 ×4 에서 1e-9 안에서 같다 — 구 · 허리 · funnel · torus
    (c) 기본값 경계는 실제로 세분화에 따라 움직인다 (결함이 재현되는지 — 고친 줄 착각 방지)
    (d) select_banded_j 가 옵션을 받아 그 경계를 쓴다
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.config import MAX_SPACING_FACTOR  # noqa: E402
from conical.meshio import RadiusProfile, center_on_axis  # noqa: E402
from conical.varangle import assign_height_bands, select_banded_j  # noqa: E402


def _waist(r_neck=3.0):
    # 구 두 개 사이 가는 목 — 허리 모델의 단순판 (회전체)
    zs = np.linspace(0.0, 20.0, 41)
    r = 4.0 + (r_neck - 4.0) * np.exp(-((zs - 10.0) / 3.0) ** 2)
    prof = np.column_stack([np.r_[0, r, 0], np.r_[0, zs, 20.0]])
    m = trimesh.creation.revolve(prof, sections=32)
    m.merge_vertices()
    m.fix_normals()
    return center_on_axis(m)


def _models():
    funnel = trimesh.creation.cone(radius=14, height=5)
    funnel.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    return {
        "sphere": center_on_axis(trimesh.creation.icosphere(subdivisions=2, radius=10.0)),
        "waist": _waist(),
        "funnel": center_on_axis(funnel),
        "torus": center_on_axis(trimesh.creation.torus(major_radius=10, minor_radius=4)),
    }


MODELS = _models()


@pytest.mark.parametrize("name", sorted(MODELS))
def test_default_is_centroid_formula(name):
    m = MODELS[name]
    fz = m.vertices[m.faces].mean(axis=1)[:, 2]
    labels, edges = assign_height_bands(m, 2)
    assert np.allclose(edges, np.linspace(fz.min(), fz.max(), 3), atol=0, rtol=0)
    assert np.array_equal(labels, np.clip(np.digitize(fz, edges[1:-1]), 0, 1))


@pytest.mark.parametrize("name", sorted(MODELS))
@pytest.mark.parametrize("n_bands", [2, 3])
def test_bounds_edges_invariant_under_subdivision(name, n_bands):
    m = MODELS[name]
    _, e0 = assign_height_bands(m, n_bands, "bounds")
    _, e1 = assign_height_bands(m.subdivide(), n_bands, "bounds")
    assert np.max(np.abs(e0 - e1)) <= 1e-9
    rp = RadiusProfile(m)
    assert abs(e0[0] - rp.z0) <= 1e-12 and abs(e0[-1] - rp.z1) <= 1e-12


def test_centroid_edges_do_move_under_subdivision():
    m = MODELS["funnel"]
    _, e0 = assign_height_bands(m, 2)
    _, e1 = assign_height_bands(m.subdivide(), 2)
    assert np.max(np.abs(e0 - e1)) > 1e-3


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        assign_height_bands(MODELS["sphere"], 2, "faces")


def test_select_banded_j_uses_bounds_edges():
    m = MODELS["funnel"]
    r_max = float(np.hypot(m.vertices[:, 0], m.vertices[:, 1]).max())
    out = []
    for mesh in (m, m.subdivide()):
        s = select_banded_j(mesh, 0.2, 2, r_max, RadiusProfile(mesh), MAX_SPACING_FACTOR,
                            band_edges="bounds")
        assert s["band_edges"] == "bounds"
        out.append(np.asarray(s["edges"]))
    assert np.max(np.abs(out[0] - out[1])) <= 1e-9
