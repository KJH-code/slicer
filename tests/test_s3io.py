"""
test_s3io.py — S³ 결과물 읽기 모듈의 정답 아는 시험.

사다리 실험(docs/dof_ladder.md)은 우리 칸과 S³ 칸을 **같은 자**로 재는 것이 전부다.
그래서 여기서 고정하는 것은 (1) 면별 방향 자가 해석식과 비트 단위로 같다,
(2) 사면체 경계 추출이 바깥 법선·닫힌 메시를 준다, (3) 좌표 회전과 법선 부호
맞추기가 생각대로 된다, 이 셋이다.
"""


import numpy as np
import pytest
import trimesh

from conical import analytic
from conical.profile import AngleProfile
from conical.s3io import (
    bed_contact_mask,
    boundary_mesh,
    cone_dirs,
    face_build_dirs,
    load_tet,
    load_waypoints,
    profile_dirs,
    support_fraction_dirs,
    y_up_to_z_up,
    y_up_to_z_up_points,
)


@pytest.fixture
def sphere():
    m = trimesh.creation.icosphere(subdivisions=3, radius=10.0)
    m.apply_translation([0, 0, 10.0])
    return m


# ── (1) 자 동일성 ───────────────────────────────────────────
@pytest.mark.parametrize("theta", [0.0, 12.0, 28.0, 44.0])
def test_cone_dirs_matches_analytic(sphere, theta):
    ours = support_fraction_dirs(sphere, cone_dirs(sphere, theta))
    ref = analytic.support_fraction(sphere, theta, "outward")
    assert abs(ours - ref) < 1e-9


def test_profile_dirs_matches_analytic_profile(sphere):
    prof = AngleProfile([(0.0, 30.0), (8.0, 30.0), (12.0, 0.0), (20.0, 0.0)])
    ours = support_fraction_dirs(sphere, profile_dirs(sphere, prof))
    ref = analytic.support_fraction_profile(sphere, prof)
    assert abs(ours - ref) < 1e-9


def test_planar_dirs_are_up(sphere):
    d = cone_dirs(sphere, 0.0)
    assert np.allclose(d, [0, 0, 1])


def test_exclude_removes_from_both_numerator_and_denominator(sphere):
    d = cone_dirs(sphere, 0.0)
    bed = bed_contact_mask(sphere, height=1.0)
    assert bed.sum() > 0
    full = support_fraction_dirs(sphere, d)
    ex = support_fraction_dirs(sphere, d, exclude=bed)
    # 바닥 면은 전부 서포트 면이므로 빼면 비율이 내려간다
    assert ex < full
    areas = sphere.area_faces
    need = sphere.face_normals[:, 2] < -np.sin(np.radians(45))
    expect = areas[~bed & need].sum() / areas[~bed].sum() * 100
    assert abs(ex - expect) < 1e-9


# ── (2) 사면체 경계 ─────────────────────────────────────────
def _tet_cube():
    """단위 정육면체를 사면체 5개로 (표준 분할). 경계는 삼각형 12개."""
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=float)
    t = np.array([[0, 1, 3, 4], [1, 2, 3, 6], [1, 4, 5, 6],
                  [3, 4, 6, 7], [1, 3, 4, 6]])
    return v, t


def test_boundary_mesh_is_closed_and_outward():
    v, t = _tet_cube()
    m = boundary_mesh(v, t)
    assert len(m.faces) == 12
    assert m.is_watertight
    assert m.volume > 0                       # 바깥 법선이면 부피가 양수
    assert abs(m.volume - 1.0) < 1e-12
    # 모든 면 법선이 그 면 중심에서 바깥(중심 0.5,0.5,0.5 반대쪽)을 본다
    c = m.vertices[m.faces].mean(axis=1) - 0.5
    assert np.all(np.einsum("ij,ij->i", m.face_normals, c) > 0)


def test_boundary_mesh_face_order_independent():
    v, t = _tet_cube()
    m1 = boundary_mesh(v, t)
    m2 = boundary_mesh(v, t[::-1, ::-1])      # 사면체 순서·정점 순서 섞어도
    assert abs(m1.volume - m2.volume) < 1e-12
    assert abs(m1.area - m2.area) < 1e-12


def test_load_tet_roundtrip(tmp_path):
    v, t = _tet_cube()
    p = tmp_path / "cube.tet"
    with open(p, "w") as f:
        f.write(f"{len(v)} vertices\n{len(t)} tets\n")
        for row in v:
            f.write(" ".join(f"{x:.6f}" for x in row) + "\n")
        for row in t:
            f.write("4 " + " ".join(str(i) for i in row) + "\n")
    v2, t2 = load_tet(p)
    assert np.allclose(v2, v)
    assert np.array_equal(t2, t)


# ── (3) 좌표·부호 ───────────────────────────────────────────
def test_y_up_to_z_up_is_proper_rotation():
    p = y_up_to_z_up_points([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    assert np.allclose(p[0], [1, 0, 0])
    assert np.allclose(p[1], [0, 0, 1])       # Y(위) → Z(위)
    assert np.allclose(p[2], [0, -1, 0])
    assert abs(np.linalg.det(p) - 1.0) < 1e-12


def test_y_up_to_z_up_keeps_mesh_volume_sign():
    v, t = _tet_cube()
    m = y_up_to_z_up(boundary_mesh(v, t))
    assert m.is_watertight and abs(m.volume - 1.0) < 1e-12


def test_load_waypoints_flips_sign_to_up(tmp_path):
    # S³ 형식: 저장된 법선이 노즐 방향(아래, Y-위 좌표에서 −Y)
    for i, y in enumerate([0.2, 0.5]):
        np.savetxt(tmp_path / f"{i}.txt",
                   [[x, y, 0.0, 0.0, -1.0, 0.0] for x in range(5)])
    (tmp_path / "9.txt").write_text("")       # 빈 파일은 건너뛴다
    w = load_waypoints(tmp_path)
    assert w["n_layers"] == 2
    assert w["sign_evidence"] < -0.99          # 뒤집기 전 증거는 그대로 보고
    assert np.allclose(w["dirs"][:, 2], 1.0)   # 뒤집은 뒤 위를 본다
    assert np.allclose(w["points"][:, 2], np.repeat([0.2, 0.5], 5))


def test_face_build_dirs_nearest(sphere):
    # 웨이포인트를 전부 +Z 로 두면 평면과 같아야 한다 (정답 아는 시험)
    pts = sphere.vertices[sphere.faces].mean(axis=1)
    w = {"points": pts, "dirs": np.tile([0.0, 0.0, 1.0], (len(pts), 1))}
    d, dist = face_build_dirs(sphere, w)
    assert np.allclose(d, [0, 0, 1]) and np.all(dist < 1e-9)
    assert abs(support_fraction_dirs(sphere, d)
               - analytic.support_fraction(sphere, 0.0, "outward")) < 1e-9
