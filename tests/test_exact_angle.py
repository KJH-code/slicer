"""균일각 정확 탐색 (conical/exact_angle.py, docs/exact_angle.md).

손계산 가능한 작은 메시에서 정확해를 고정하고, 사전 등록 기준 (a)(b)(c) 를
표본 모델에서 강제한다. 기본 경로(격자)가 바뀌지 않았는지도 확인한다.
"""

import math

import numpy as np
import pytest
import trimesh

from compare_waist import waisted_model
from conical.analytic import critical_angle, radial_normal, support_fraction
from conical.config import MAX_ANGLE_DEG, THRESHOLD_DEG
from conical.exact_angle import EPS_DEG, select_uniform_exact, support_step
from conical.meshio import center_on_axis
from conical.selector import select_cone
from conical.varangle import angle_candidates, best_angle_for_mask, select_uniform

KAPPA = -math.sin(math.radians(THRESHOLD_DEG))


def tri(center, normal, size=1.0):
    """center 에 중심, normal 법선을 가진 삼각형 하나 (꼭짓점 3, 면 1)."""
    n = np.asarray(normal, float)
    n /= np.linalg.norm(n)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    ps = [size * (math.cos(t) * u + math.sin(t) * v)
          for t in (0, 2 * math.pi / 3, 4 * math.pi / 3)]
    return np.asarray(center, float) + np.array(ps)


def mesh_of(tris):
    """(center, normal, size) 목록 → 면 법선이 그 normal 인 메시 (처리 없음)."""
    verts = np.concatenate([tri(*t) for t in tris])
    faces = np.arange(len(verts)).reshape(-1, 3)
    m = trimesh.Trimesh(verts, faces, process=False)
    for t, fn in zip(tris, m.face_normals, strict=True):
        n = np.asarray(t[1], float) / np.linalg.norm(t[1])
        assert np.allclose(fn, n, atol=1e-12)
    return m


def fine_best(mesh, k, step=0.001):
    nz = mesh.face_normals[:, 2]
    nr = radial_normal(mesh)
    w = mesh.area_faces / mesh.area_faces.sum() * 100
    angs = np.array(angle_candidates(MAX_ANGLE_DEG, step))
    base = w[nz < KAPPA].sum()
    best = -np.inf
    for d in (1.0, -1.0):
        ar = np.radians(angs)[:, None]
        g = nz * np.cos(ar) + d * nr * np.sin(ar)
        J = base - (g < KAPPA) @ w - k * angs
        best = max(best, J.max())
    return best


# ─── 손계산 ──────────────────────────────────────────────────
def test_single_overhang_face_hand_computed():
    """n=(0.4359, 0, −0.9) 면이 x=10 에 있다 (n_r>0). outward 첫 근:
    θ* = asin(κ) − atan2(n_z, n_r) = −45° + 64.16° ≈ 19.16°. 둘째 근은 범위 밖.
    윗면(넓이 같음)과 섞으면 S(0)=50%, θ* 에서 0% → J = 50 − 0.2·θ*."""
    nr = math.sqrt(1 - 0.81)
    m = mesh_of([((10, 0, 0), (nr, 0, -0.9), 1.0),
                 ((10, 0, 5), (0, 0, 1), 1.0)])
    expected = math.degrees(math.asin(KAPPA) - math.atan2(-0.9, nr))
    assert expected == pytest.approx(19.158, abs=1e-3)
    best, info = select_uniform_exact(m, 0.2)
    assert best["direction"] == "outward"
    assert best["angle"] == pytest.approx(expected, abs=2 * EPS_DEG)
    assert best["angle"] > expected                      # 근 '바로 위' 에서 평가
    assert best["support"] == pytest.approx(0.0, abs=1e-12)
    assert best["J"] == pytest.approx(50 - 0.2 * expected, abs=1e-6)
    # 격자는 20° 에서 J = 50 − 4 = 46 — 정확해가 0.2·(20 − 19.158) 만큼 높다
    g, _ = select_cone(m, 0.2, verbose=False)
    assert g["angle"] == 20
    assert best["J"] - g["J"] == pytest.approx(0.2 * (20 - expected), abs=1e-6)
    # inward 로는 이 면이 고쳐지지 않는다 (g 가 줄기만)
    st = info["steps"]["inward"]
    assert np.allclose(st["eval"]([10.0, 30.0, 44.0]), 50.0, atol=1e-12)


def test_second_root_face_fails_again():
    """n=(−0.98, 0, −0.2) 면 (n_r<0): 0° 에서 통과, outward 로 키우면
    θ = 180° + 45° − atan2(−0.2, −0.98)·… → 33.46° 에서 **다시 실패**(둘째 근)."""
    n = np.array([-0.98, 0, -0.2])
    n /= np.linalg.norm(n)
    m = mesh_of([((10, 0, 0), tuple(n), 1.0), ((10, 0, 5), (0, 0, 1), 1.0)])
    delta = math.atan2(n[2], n[0])
    root = math.degrees(math.pi - math.asin(KAPPA) - delta) % 360.0
    assert root == pytest.approx(33.46, abs=0.05)
    st = support_step(m, "outward")
    assert st["S0"] == 0.0
    assert len(st["roots_deg"]) == 1 and not st["rising"][0]
    assert st["roots_deg"][0] == pytest.approx(root, abs=1e-9)
    assert st["eval"]([root - 1e-6])[0] == 0.0
    assert st["eval"]([root + 1e-6])[0] == pytest.approx(50.0)
    for a in (root - 1e-6, root + 1e-6, 40.0):
        assert st["eval"]([a])[0] == pytest.approx(
            support_fraction(m, a, "outward"), abs=1e-12)
    # 최적은 0° (고칠 것이 없다)
    best, _ = select_uniform_exact(m, 0.2)
    assert best["angle"] == 0.0 and best["J"] == 0.0


def test_zero_radial_downward_face_has_root():
    """n_r = 0, n_z = −0.8: g = n_z·cosθ 가 커져 θ = acos(κ/n_z) ≈ 27.88° 에서 고쳐진다
    (두 방향 모두). analytic.critical_angle 은 이 면을 '못 고침'(nan) 으로 본다 —
    support_fraction 과 어긋나는 점. 정확 탐색은 support_fraction 을 따른다."""
    m = mesh_of([((0, 10, 0), (0.6, 0, -0.8), 3.0),     # 중심 (0,10): n_r = 0 (φ 방향 성분만)
                 ((10, 0, 5), (0, 0, 1), 3.0)])
    assert abs(radial_normal(m)[0]) < 1e-12
    root = math.degrees(math.acos(KAPPA / -0.8))
    assert root == pytest.approx(27.886, abs=1e-3)
    assert support_fraction(m, root + 1e-6, "outward") == 0.0
    assert np.isnan(critical_angle(m, "outward")[0])     # 알려진 어긋남 (고치지 않음)
    best, _ = select_uniform_exact(m, 0.2)
    assert best["direction"] == "outward"                # 동률이면 outward 먼저
    assert best["angle"] == pytest.approx(root, abs=2 * EPS_DEG)


def test_small_R_face_never_fails():
    """R ≤ |κ| 면 (φ 방향 법선, n_z=−0.6): g < κ 불가 → 근 없음, 늘 통과."""
    m = mesh_of([((10, 0, 0), (0, 0.8, -0.6), 1.0), ((10, 0, 5), (0, 0, 1), 1.0)])
    for d in ("outward", "inward"):
        st = support_step(m, d)
        assert st["n_face_roots"] == 0 and st["S0"] == 0.0


def test_exact_ignores_k_when_gain_too_small():
    """이득 50%p 가 k·θ* 보다 작으면 0° (k=3 → 비용 57.5)."""
    nr = math.sqrt(1 - 0.81)
    m = mesh_of([((10, 0, 0), (nr, 0, -0.9), 1.0), ((10, 0, 5), (0, 0, 1), 1.0)])
    best, _ = select_uniform_exact(m, 3.0)
    assert best["angle"] == 0.0 and best["direction"] == "outward"


# ─── 사전 등록 기준 (a)(b)(c) — 표본 모델 ───────────────────────
@pytest.fixture(scope="module")
def models():
    out = {"sphere": center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=10.0)),
           "waist2": waisted_model(2.0)}
    torus = trimesh.creation.torus(major_radius=10, minor_radius=4)
    out["torus"] = center_on_axis(torus)
    return out


@pytest.mark.parametrize("name", ["sphere", "waist2", "torus"])
def test_criteria_abc(models, name):
    m = models[name]
    k = 0.2
    g, _ = select_cone(m, k, verbose=False)
    e, info = select_uniform_exact(m, k)
    # (a)
    assert e["J"] >= g["J"] - 1e-6
    # (b)
    assert support_fraction(m, e["angle"], e["direction"]) == pytest.approx(
        e["support"], abs=1e-9)
    # (b′)
    for d in ("outward", "inward"):
        st = info["steps"][d]
        for a in angle_candidates(MAX_ANGLE_DEG, 2):
            assert st["eval"]([a])[0] == pytest.approx(support_fraction(m, a, d), abs=1e-9)
    # (c)
    jf = fine_best(m, k)
    assert jf <= e["J"] + 1e-6
    assert e["J"] - jf <= k * 0.001 + 1e-6


# ─── 회귀 상수 (2026-11-10, docs/exact_angle.md §4) ────────────
def test_regression_constants(models):
    e, _ = select_uniform_exact(models["sphere"], 0.2)
    assert (e["direction"], round(e["angle"], 3), round(e["J"], 4)) == ("outward", 27.356, 7.5203)
    e, _ = select_uniform_exact(models["waist2"], 0.2)
    assert (e["direction"], round(e["angle"], 3), round(e["J"], 4)) == ("outward", 21.13, 2.3687)
    e, _ = select_uniform_exact(models["torus"], 0.2)
    assert (e["direction"], round(e["angle"], 3), round(e["J"], 4)) == ("outward", 5.492, 2.8139)


def test_default_is_still_grid(models):
    """기본값은 바뀌지 않았다 — 격자 각도(정수)를 낸다."""
    m = models["waist2"]
    g, cands = select_cone(m, 0.2, verbose=False)
    assert g["angle"] == 24 and len(cands) == 46
    u = select_uniform(m, 0.2)
    assert u["profile"] == [(24, "outward")]


def test_mask_exact_matches_fine_grid(models):
    """best_angle_for_mask(method='exact') — mask 정규화 J 의 최댓값이 격자 이상."""
    m = models["waist2"]
    fz = m.vertices[m.faces].mean(axis=1)[:, 2]
    mask = fz < np.median(fz)
    a, c = best_angle_for_mask(m, mask, m.area_faces, 0.2, method="exact")
    areas = m.area_faces

    def J(ang, d):
        base = areas[mask & (m.face_normals[:, 2] < KAPPA)].sum() / areas[mask].sum() * 100
        need = (m.face_normals[:, 2] * math.cos(math.radians(ang))
                + (1 if d == "outward" else -1) * radial_normal(m)
                * math.sin(math.radians(ang))) < KAPPA
        return base - areas[mask & need].sum() / areas[mask].sum() * 100 - 0.2 * ang

    ag, cg = best_angle_for_mask(m, mask, m.area_faces, 0.2)
    assert J(a, c) >= J(ag, cg) - 1e-9
    with pytest.raises(ValueError):
        best_angle_for_mask(m, mask, m.area_faces * 2, 0.2, method="exact")
