"""T7: 층간격 제약 (블렌드 팽창 결함 수정).

가역성 조건은 배율 m = 1 − c·r·s 가 0 이하로 가는 것만 막는다. 각도가 '감소'하는
안정 방향은 가역성엔 안 걸리면서 m 이 커져(레이어가 벌어져) 지지가 사라진다 —
구 밴드2에서 실측 미지지 25.5%로 잡힌 결함(docs/verification.md).

    (a) 폭 공식이 실제로 배율을 상한에 맞추는가
    (b) from_bands 가 구(허리 없음)에서 블렌드를 넓혀 15.5배 → 상한 이내로
    (c) 허리가 있는 모델은 경계를 허리로 옮겨 '좁은' 블렌드로 해결하는가
    (d) spacing_limit=None 이면 예전 동작 그대로인가 (회귀 방지)

2026-11-10 추가 (docs/gap_audit.md G1): 위 (a)~(d) 는 **명목** 배율만 봤다 — 계획기와
검사가 같은 반경 조회를 쓰므로 조회가 틀리면 둘이 같이 틀린다. 실제로 그랬다:
블렌드는 변환높이 Z′ 구간인데 반경을 실공간 z 구간으로 조회해서, 그 층들이 원뿔을
따라 내려가 닿는 뚱뚱한 부분을 못 봤다 (실험 A 램프 밴드2: 명목 1.50, 실제 2.6).

    (e) 반경 조회가 '그 Z′ 구간의 층이 실제로 닿는 범위' 를 보는가 (`max_in_slab`)
    (f) 실험 A 램프 밴드2 — **생성된 층에서 잰** 배율이 상한 안인가  ← 명목이 아니라 실제
    (g) J 의 블렌드 벌점이 실제 블렌드 면적을 세는가

    python3 tests/test_blend_spacing.py
"""

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.backtransform import backtransform  # noqa: E402
from conical.config import BLEND_SHIFT_RATIO, MAX_SPACING_FACTOR  # noqa: E402
from conical.meshio import RadiusProfile, center_on_axis  # noqa: E402
from conical.planar_slicer import slice_mesh  # noqa: E402
from conical.profile import AngleProfile, blend_width_for_spacing  # noqa: E402
from conical.toolpath import sample_extrusions  # noqa: E402
from conical.transform import transform_cone_profile  # noqa: E402
from conical.varangle import (  # noqa: E402
    _merge_bands,
    assign_height_bands,
    blend_penalty,
)

LAMP_STL = Path(__file__).resolve().parent.parent / "examples" / "lamp.stl"
# 실험 A 의 밴드2 파일(examples/lamp_expA_band2_*)에 들어간 프로필 — 고치기 전 계획기의 답
EXP_A_BAND2 = [(0.006392146150271098, 30.0), (16.34849550315555, 30.0),
               (18.657896642994718, 0.0), (30.0, 0.0)]


def _sphere():
    return center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=10.0))


def _waisted():
    """구 + 가는 목 + 위로 벌어지는 형상 (허리 있음). examples/lamp.stl 과 동일 형상."""
    R, ZC = 8.0, 8.0
    t_end = math.pi - math.asin(2.0 / R)
    pts = [(R * math.sin(t), ZC - R * math.cos(t))
           for t in np.linspace(0, t_end, 60)]
    z_neck = pts[-1][1]
    pts += [(2.0, z) for z in np.linspace(z_neck, 20.0, 8)[1:]]
    pts += [(r, z) for r, z in zip(np.linspace(2.0, 7.0, 12)[1:],
                                   np.linspace(20.0, 30.0, 12)[1:], strict=True)]
    pts += [(0.0, 30.0)]
    m = trimesh.creation.revolve(np.array(pts), sections=64)
    m.merge_vertices()
    m.fix_normals()
    return center_on_axis(m)


def test_width_formula_hits_the_limit():
    """(a) 공식이 준 폭에서 배율이 정확히 상한이 된다."""
    r, limit = 9.8, 1.5
    dtan = math.tan(math.radians(0.0)) - math.tan(math.radians(36.0))   # 팽창 방향
    w = blend_width_for_spacing(r, dtan, "outward", limit)
    m = 1.0 - 1.0 * r * (dtan / w)                                      # 1 − c·r·s
    assert abs(m - limit) < 1e-9, f"배율 {m} ≠ 상한 {limit}"
    # 압축 방향은 하한 1/limit 에 맞아야 한다
    w2 = blend_width_for_spacing(r, -dtan, "outward", limit)
    m2 = 1.0 - 1.0 * r * (-dtan / w2)
    assert abs(m2 - 1.0 / limit) < 1e-9, f"압축 배율 {m2} ≠ {1/limit}"


def test_sphere_blend_widened():
    """(b) 허리 없는 모델: 블렌드를 넓혀서 상한을 지킨다 (15.5배 → ≤1.5배)."""
    m = _sphere()
    rp = RadiusProfile(m)
    r_max = float(np.hypot(m.vertices[:, 0], m.vertices[:, 1]).max())
    bands = [(0.0, 10.0, 36.0), (10.0, 20.0, 0.0)]

    old = AngleProfile.from_bands(bands, r_max)
    assert old.max_spacing_factor(r_max, "outward", rp) > 10.0, "결함 재현 실패"

    new = AngleProfile.from_bands(bands, r_max, radius_profile=rp,
                                  spacing_limit=1.5, max_shift=2.5)
    f = new.max_spacing_factor(r_max, "outward", rp)
    assert f <= 1.5 + 1e-6, f"상한 위반: {f}"
    assert not new.check_spacing(r_max, "outward", 1.5, rp)
    (a, b), = new.blend_intervals()
    assert b - a > 10.0, f"구는 블렌드가 넓어져야 함 (폭 {b-a:.2f})"


def test_waist_moves_boundary_and_keeps_blend_narrow():
    """(c) 허리 있는 모델: 경계를 목으로 옮겨 좁은 블렌드로 해결."""
    m = _waisted()
    rp = RadiusProfile(m)
    r_max = float(np.hypot(m.vertices[:, 0], m.vertices[:, 1]).max())
    bands = [(0.0, 15.0, 30.0), (15.0, 30.0, 0.0)]
    prof = AngleProfile.from_bands(bands, r_max, radius_profile=rp,
                                   spacing_limit=1.5,
                                   max_shift=0.25 * 15.0)
    f = prof.max_spacing_factor(r_max, "outward", rp)
    assert f <= 1.5 + 1e-6, f"상한 위반: {f}"
    (a, b), = prof.blend_intervals()
    assert b - a < 4.0, f"허리에서는 블렌드가 좁아야 함 (폭 {b-a:.2f})"
    zc = 0.5 * (a + b)
    assert zc > 16.0, f"경계가 목(z≈15.8~20)으로 이동해야 함 (중심 {zc:.2f})"
    assert prof.notes, "경계를 옮겼으면 그 사실이 notes 에 남아야 함"


def test_default_is_unchanged():
    """(d) spacing_limit 을 안 주면 예전 동작 그대로 (회귀 방지)."""
    r_max = 20.0
    bands = [(0.0, 10.0, 10.0), (10.0, 40.0, 40.0)]
    prof = AngleProfile.from_bands(bands, r_max)
    w_min = r_max * (math.tan(math.radians(40.0)) - math.tan(math.radians(10.0)))
    (a, b), = prof.blend_intervals()
    assert abs((b - a) - 1.5 * w_min) < 1e-9, f"폭이 safety×w_min 이 아님: {b-a}"
    assert prof.notes == []


def _lamp():
    mesh = center_on_axis(trimesh.load(LAMP_STL, force="mesh"))
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    return mesh, RadiusProfile(mesh), r_max


def _lamp_band2(mesh, rp, r_max):
    """`select_banded_j` 가 각도 [30°, 0°] 에 대해 만드는 바로 그 프로필."""
    _, edges = assign_height_bands(mesh, 2)
    shift = BLEND_SHIFT_RATIO * float(mesh.bounds[1][2] - mesh.bounds[0][2])
    return AngleProfile.from_bands(_merge_bands(edges, [30.0, 0.0]), r_max,
                                   radius_profile=rp,
                                   spacing_limit=MAX_SPACING_FACTOR, max_shift=shift)


def _measured_spacing(mesh, prof, layer_height=0.3):
    """실제 파이프라인으로 층을 만들어 압출점마다 층간격 배율을 잰다.

    반환: (그 점의 배율 m = 1 − r·s 의 최대, 바로 아랫층 원뿔면까지의 수직 간격 ÷
    층고 의 최대). 뒤의 것은 식이 아니라 생성된 층 두 장 사이의 실제 거리다.
    """
    v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=1.5)
    warped = trimesh.Trimesh(vertices=transform_cone_profile(v, prof, "outward"),
                             faces=f, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=layer_height), prof,
                            "outward")
    pts, _mid, _w = sample_extrusions(real)
    r = np.hypot(pts[:, 0], pts[:, 1])
    zw = prof.solve_forward(pts[:, 2], r, "outward")       # 그 점이 놓인 층 (정확 해)
    m_point = prof.spacing_factor(zw, r)
    gap = 1.0 - r * (prof.tan_at(zw) - prof.tan_at(zw - layer_height)) / layer_height
    return float(m_point.max()), float(gap.max())


def test_slab_radius_follows_the_cone_layers():
    """(e) `max_in_slab`: 블렌드 Z′ 구간의 층이 실제로 닿는 반경."""
    mesh, rp, _ = _lamp()
    t30 = math.tan(math.radians(30.0))
    # 각도가 0 이면 실공간 z 구간과 같다 (목: r=2)
    assert abs(rp.max_in_slab(16.35, 18.66, 0.0, 0.0) - 2.0) < 1e-3
    # 30° 원뿔 층은 목(z 16.35~18.66)에서 출발해 구의 어깨(r≈6.6)까지 내려간다
    assert rp.max_between(16.35, 18.66) < 2.01            # 옛 조회: 목만 본다
    assert rp.max_in_slab(16.35, 18.66, t30, 0.0) > 6.4   # 새 조회: 어깨를 본다
    # 원뿔이 구에 접하는 높이는 8 + 8/cos30° = 17.24 — 그 위에서 출발하면 구를 비켜 간다
    assert abs(rp.max_in_slab(17.35, 19.66, t30, 0.0) - 2.0) < 1e-3
    # inward(음수 각도)는 층이 위로 올라간다: 나팔(z>20, r>2)에 닿는다
    assert 2.5 < rp.max_in_slab(17.35, 19.66, 0.0, -t30) < 2.7   # 정확값 2.57
    # 재료가 없는 높이는 0
    assert rp.max_in_slab(40.0, 41.0, 0.0, 0.0) == 0.0

    # 정점이 위아래 테두리에만 있는 원기둥: 가운데 높이에도 반경이 있어야 한다
    cyl = center_on_axis(trimesh.creation.cylinder(radius=10.0, height=20.0,
                                                   sections=64))
    assert abs(RadiusProfile(cyl).max_in_slab(8.0, 12.0, 0.3, 0.0) - 10.0) < 1e-6

    # 속이 찬 회전체로 본 전수 대조: 작게 잡는 일이 없다 (보수적), 크게는 칸 높이만큼
    def r_true(z):                                         # examples/lamp.stl 의 윤곽
        neck = 8.0 + math.sqrt(60.0)
        return np.where(z <= neck, np.sqrt(np.maximum(64.0 - (z - 8.0) ** 2, 0.0)),
                        np.where(z <= 20.0, 2.0, 2.0 + 0.5 * (z - 20.0)))
    zg, rg = np.linspace(0.0, 30.0, 1501), np.linspace(0.0, 8.0, 801)
    Z, R = np.meshgrid(zg, rg, indexing="ij")
    solid = R <= r_true(zg)[:, None]
    rng = np.random.default_rng(0)
    for _ in range(200):
        lo = rng.uniform(0.0, 27.0)
        hi = lo + rng.uniform(0.5, 6.0)
        t1, t2 = np.tan(np.radians(rng.uniform(-35.0, 35.0, 2)))
        inside = solid & (Z >= lo - R * t1) & (Z <= hi - R * t2)
        brute = float(R[inside].max()) if inside.any() else 0.0
        got = rp.max_in_slab(lo, hi, t1, t2)
        assert got >= brute - 0.03, f"과소: {got:.3f} < {brute:.3f} ({lo:.2f},{hi:.2f})"
        assert got <= brute + 0.6, f"과대: {got:.3f} ≫ {brute:.3f} ({lo:.2f},{hi:.2f})"


def test_lamp_band2_actual_spacing_within_limit():
    """(f) 실험 A 램프 밴드2: 생성된 층의 **실제** 층간격 배율이 상한 안이다.

    고치기 전: 블렌드 Z′ 16.35~18.66, 명목 m=1.50 인데 층이 구의 어깨까지 내려가
    실제 2.6 (층 사이 수직 간격 0.69~0.78mm, 층고 0.30). 그 프로필을 여기 그대로
    두고 결함이 재현되는 것부터 확인한다.
    """
    mesh, rp, r_max = _lamp()

    # ── 고치기 전의 프로필: 결함 재현 + 이제는 검사가 잡는다 ──
    old = AngleProfile(EXP_A_BAND2)
    m_old, gap_old = _measured_spacing(mesh, old)
    assert m_old > 2.5 and gap_old > 2.2, f"결함 재현 실패: m={m_old:.2f}, 간격={gap_old:.2f}"
    bad = old.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp)
    assert len(bad) == 1 and bad[0]["factor"] > 2.5 and bad[0]["r"] > 6.4, bad
    assert old.max_spacing_factor(r_max, "outward", rp) > 2.5

    # ── 지금 계획기가 같은 각도 [30°, 0°] 로 만드는 프로필 ──
    new = _lamp_band2(mesh, rp, r_max)
    (a, b), = new.blend_intervals()
    assert list(new.thetas_deg[[0, -1]]) == [30.0, 0.0], "각도를 깎으면 안 된다 (자리가 있다)"
    # 30° 원뿔이 구를 비켜 가는 높이(17.24) 위로 올라가야 한다. 폭은 그대로 2.31mm
    assert 17.2 < a < 17.6, f"블렌드 시작 {a:.2f} (고치기 전 16.35, 기대 ≈17.25~17.35)"
    assert abs((b - a) - 2.31) < 0.02, f"블렌드 폭 {b - a:.3f}"
    assert not new.check_spacing(r_max, "outward", MAX_SPACING_FACTOR, rp)
    assert new.max_spacing_factor(r_max, "outward", rp) <= MAX_SPACING_FACTOR + 1e-6

    m_new, gap_new = _measured_spacing(mesh, new)
    assert m_new <= MAX_SPACING_FACTOR + 1e-6, f"실제 배율 {m_new:.3f} > 상한"
    assert gap_new <= MAX_SPACING_FACTOR + 1e-6, f"실제 층 간격 {gap_new:.3f}×층고"
    assert m_new > 1.3, "블렌드가 재료에 안 걸렸다 — 측정이 블렌드를 못 보고 있다"


def test_blend_penalty_counts_the_slab_area():
    """(g) J 의 블렌드 벌점이 세는 면적 = 변환높이가 블렌드 구간에 드는 면의 면적."""
    mesh, rp, r_max = _lamp()
    areas = mesh.area_faces
    fc = mesh.vertices[mesh.faces].mean(axis=1)

    def exact_area_pct(prof):
        (a, b), = prof.blend_intervals()
        zw = prof.solve_forward(fc[:, 2], np.hypot(fc[:, 0], fc[:, 1]), "outward")
        return areas[(zw >= a) & (zw <= b)].sum() / areas.sum() * 100.0

    new = _lamp_band2(mesh, rp, r_max)                # m = 상한 → risk = 1
    assert abs(blend_penalty(mesh, new, rp) - exact_area_pct(new)) < 1e-9
    # 고치기 전 프로필: z 구간으로 세면 2.3% 였다. 실제로는 구의 어깨까지 15%
    old = AngleProfile(EXP_A_BAND2)
    pen = blend_penalty(mesh, old, rp)                # m = 2.65 > 상한 → risk = 1 로 포화
    assert abs(pen - exact_area_pct(old)) < 1e-9
    assert 13.0 < pen < 17.0, f"옛 프로필의 블렌드 면적 {pen:.1f}% (기대 ≈15%)"


if __name__ == "__main__":
    test_width_formula_hits_the_limit()
    test_sphere_blend_widened()
    test_waist_moves_boundary_and_keeps_blend_narrow()
    test_default_is_unchanged()
    test_slab_radius_follows_the_cone_layers()
    test_lamp_band2_actual_spacing_within_limit()
    test_blend_penalty_counts_the_slab_area()
    print("PASS: 폭 공식=상한 / 구는 넓히기 / 허리는 경계 이동 / 기본값 회귀 없음 / "
          "슬랩 반경 / 램프 밴드2 실제 배율 / 벌점 면적")
