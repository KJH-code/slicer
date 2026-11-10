"""검사기 A 의 기준 프레임: 연직(기본) / 공구(층 법선) — docs/gap_audit.md G6.

`toolpath.check_support` 는 '아래에 앞 층이 있는가' 를 연직으로 잰다 (수평 ≤ 압출폭,
수직 (0, 1.5h]). 3축 기계의 판정이다. REP5X 는 노즐이 층 법선을 따라 기울어 비드가
눌리는 방향이 노즐 축이므로, 그 파일은 공구 프레임에서 재야 한다. `tool_up` 인자가
그 스위치다.

고정하는 것:
  ① 기본값(tool_up=None, layer=None)은 예전 그대로다. 전부 (0,0,1) 을 줘도 같은 답
  ② 연직 창이 원뿔 층에서 만드는 인공물 둘이 공구 프레임에서 사라진다
       ⓐ 같은 층의 바깥 페리미터(w·sinθ 낮다)를 '아래 지지' 로 세는 것
       ⓑ 층 법선이 기운 만큼 수평 이동을 덤으로 세어 받쳐진 비드를 미지지로 세는 것
  ③ **공구 프레임에는 자기 인공물이 있다** — 원뿔면이 접평면 아래로 휘어 있어 같은
     고리의 앞 점이 µm 단위로 '아래' 가 된다. `layer`(층 번호)를 주면 같은 층을
     지지 후보에서 빼서 없앤다. 감사 문서의 '공구' 행들은 이걸 안 뺀 값이다
  ④ 실제 경로에서 독립 구현(점별 브루트포스)과 점 단위로 일치한다 (낙관·연쇄)
  ⑤ '아랫층 단면 안인가' 의 판정점이 공구 축을 따라 내린 발로 옮겨진다
  ⑥ `layer_frames` 가 원뿔 층의 법선·두께를 낸다 (REP5X 의 공구 방향과 같은 규약)

    python3 -m pytest tests/test_toolpath_tool_frame.py
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.backtransform import backtransform  # noqa: E402
from conical.meshio import center_on_axis  # noqa: E402
from conical.planar_slicer import slice_mesh  # noqa: E402
from conical.profile import AngleProfile  # noqa: E402
from conical.rep5x import tool_direction  # noqa: E402
from conical.toolpath import (  # noqa: E402
    INSIDE,
    OVERHANG,
    check_support,
    classify_unsupported,
    layer_frames,
    sample_extrusions,
    support_breakdown,
)
from conical.transform import transform_cone  # noqa: E402

W, LH, THETA = 0.45, 0.3, 30.0
PROF = AngleProfile.constant(THETA)
TAN, SIN, COS = (f(math.radians(THETA)) for f in (math.tan, math.sin, math.cos))


def _ring(r, zw, step=0.2):
    """outward 원뿔 층 Z′=zw 위의 반경 r 고리 (점 간격 ≈ step)."""
    n = max(8, int(round(2 * math.pi * r / step)))
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    return np.column_stack([r * np.cos(a), r * np.sin(a), np.full(n, zw - r * TAN)])


def _check(pts, **kw):
    n = len(pts)
    return check_support(pts, np.arange(n), np.full(n, 0.2), layer_height=LH,
                         width=W, **kw)[0]


def _layers(*counts):
    """고리별 점 개수 → 점별 층 번호 (첫 고리가 층 0)."""
    return np.repeat(np.arange(len(counts)), counts)


@pytest.fixture(scope="module")
def sphere_path():
    """구(반지름 4.5)를 24° 균일 원뿔로 슬라이싱한 실제 경로의 표본점."""
    mesh = center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=4.5))
    v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=1.5)
    warped = trimesh.Trimesh(vertices=transform_cone(v, 24.0, "outward"), faces=f,
                             process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=0.4), 24.0, "outward")
    pts, mid, w, kinds, lay = sample_extrusions(real, return_types=True,
                                                return_layers=True)
    up, t_n = layer_frames(pts, AngleProfile.constant(24.0), "outward", 0.4)
    return pts, mid, w, kinds, lay, up, t_n


def _brute(pts, up, hwin, vwin, bed_h, chained, lay=None):
    """독립 구현: 점마다 먼저 놓인 점 전부를 본다 (트리·배치 없음)."""
    sup = pts[:, 2] <= bed_h + 1e-9
    for i in range(len(pts)):
        if sup[i]:
            continue
        keep = np.ones(i, dtype=bool)
        if chained:
            keep &= sup[:i]
        if lay is not None and lay[i] >= 0:
            keep &= lay[:i] != lay[i]
        d = pts[i] - pts[:i][keep]
        dz = d @ up[i]
        lat = np.sqrt(np.maximum((d * d).sum(axis=1) - dz * dz, 0.0))
        sup[i] = bool(np.any((dz > 1e-9) & (dz <= vwin + 1e-9) & (lat <= hwin + 1e-9)))
    return sup


def test_default_frame_is_vertical(sphere_path):
    """① tool_up 을 안 주면 연직이고, 전부 (0,0,1) 을 줘도 같은 판정이다."""
    pts, mid, w, *_ = sphere_path
    up_z = np.tile([0.0, 0.0, 1.0], (len(pts), 1))
    for chained in (False, True):
        ref, st_ref = check_support(pts, mid, w, layer_height=0.4,
                                    require_supported_below=chained)
        # 기본 경로 자체가 독립 구현(연직·층 구분 없음)과 점 단위로 같다
        assert np.array_equal(ref, _brute(pts, up_z, W, 1.5 * 0.4, 0.4, chained))
        got, st = check_support(pts, mid, w, layer_height=0.4,
                                require_supported_below=chained, tool_up=up_z)
        assert np.array_equal(ref, got)
        assert st == st_ref
        # 길이가 1 이 아니어도 방향만 본다
        got2, _ = check_support(pts, mid, w, layer_height=0.4,
                                require_supported_below=chained, tool_up=3.0 * up_z)
        assert np.array_equal(ref, got2)
    with pytest.raises(ValueError):
        check_support(pts, mid, w, layer_height=0.4, tool_up=up_z[:-1])


def test_same_layer_neighbour_is_not_support_in_tool_frame():
    """②ⓐ 같은 층의 바깥 페리미터는 '아래' 가 아니다.

    outward 원뿔 층에서 바깥 고리는 안쪽 고리보다 0.40·tanθ 낮다. 연직 창에는
    '수평 0.40 ≤ w, 수직 0.23 ≤ 1.5h' 로 들어와 아래 지지로 세어진다 — 그 밑에는
    아무것도 없는데도. 층 법선 방향으로는 두 고리의 높이 차가 0 이다.
    """
    outer, inner = _ring(8.40, 10.0), _ring(8.0, 10.0)
    pts = np.vstack([outer, inner])                  # 바깥 고리를 먼저 놓는다
    n_out = len(outer)
    lay = np.zeros(len(pts), dtype=int)              # 둘 다 같은 층
    up, _ = layer_frames(pts, PROF, "outward", LH)
    vert = _check(pts)
    assert not vert[:n_out].any()                    # 바깥 고리: 공중
    assert vert[n_out:].all(), "연직 창의 인공물이 재현되지 않았다"
    # 공구 프레임 + 층 번호: 두 고리 다 공중이다
    assert not _check(pts, tool_up=up, layer=lay).any()
    # 연직 프레임이어도 층 번호를 주면 이 인공물은 사라진다
    assert not _check(pts, layer=lay).any()


def test_tool_frame_needs_layer_ids():
    """③ 공구 프레임만 켜면 고리가 **자기 자신**에게 받쳐진다 — `layer` 가 필요하다.

    공중에 뜬 고리 하나. 원뿔면은 각 점의 접평면 아래로 휘어 있어서 같은 고리의
    앞 점이 sinθ·s²/(2r) ≈ 1µm '아래' 다. 층 번호 없이는 그게 지지로 세어진다.
    """
    pts = _ring(8.0, 10.0)
    up, _ = layer_frames(pts, PROF, "outward", LH)
    assert not _check(pts).any()                              # 연직: 공중 (맞다)
    alone = _check(pts, tool_up=up)
    assert alone[1:].all(), "공구 프레임의 같은-고리 인공물이 재현되지 않았다"
    lay = np.zeros(len(pts), dtype=int)
    for chained in (False, True):
        assert not _check(pts, tool_up=up, layer=lay,
                          require_supported_below=chained).any()
    # 층 번호를 모르는 점(−1)은 가리지 않는다 — 예전 동작으로 떨어진다
    assert np.array_equal(_check(pts, tool_up=up, layer=np.full(len(pts), -1)), alone)
    with pytest.raises(ValueError):
        _check(pts, tool_up=up, layer=lay[:-1])


def test_supported_bead_on_a_cone_is_seen_in_tool_frame():
    """②ⓑ 층 면을 따라 0.43mm 밀린 비드: 공구 프레임 지지, 연직 프레임 미지지.

    층 k (Z′=10) 의 r=8.0 고리 위에 층 k+1 (Z′=10.3) 의 r=8.5 고리.
    연직: 수평 0.50 > w.  공구: 법선 방향 h·cosθ = 0.26, 층 면 방향
    Δr/cosθ − h·sinθ = 0.427 ≤ w.
    """
    lower, upper = _ring(8.0, 10.0), _ring(8.5, 10.0 + LH)
    pts = np.vstack([lower, upper])
    n_low = len(lower)
    lay = _layers(n_low, len(upper))
    up, t_n = layer_frames(pts, PROF, "outward", LH)
    assert np.allclose(t_n, LH * COS)
    vert = _check(pts, layer=lay)
    tool = _check(pts, tool_up=up, layer=lay)
    assert not vert.any(), "연직 프레임: 수평 0.5mm 라 창 밖"
    assert not tool[:n_low].any() and tool[n_low:].all(), \
        "공구 프레임: 층 면 방향 0.43mm 라 창 안"
    # 1mm 밀리면 어느 프레임에서도 미지지다
    far_ring = _ring(9.0, 10.0 + LH)
    far = np.vstack([lower, far_ring])
    lay_far = _layers(n_low, len(far_ring))
    up_far, _ = layer_frames(far, PROF, "outward", LH)
    assert not _check(far, tool_up=up_far, layer=lay_far).any()
    # 연쇄 판정(지지된 재료만 지지 후보)도 같은 프레임을 쓴다: 아랫고리가 공중이면 0
    assert not _check(pts, tool_up=up, layer=lay, require_supported_below=True).any()


def test_tool_frame_matches_brute_force_on_a_real_path(sphere_path):
    """④ 실제 원뿔 경로에서 독립 구현과 점 단위로 일치 (낙관·연쇄, 층 번호 유무)."""
    pts, mid, w, _kinds, lay, up, _t_n = sphere_path
    assert len(pts) > 3000 and (lay >= 0).all()
    differs = False
    unsup = {}
    for chained in (False, True):
        for use_layer in (False, True):
            kw = {"layer": lay} if use_layer else {}
            got, _ = check_support(pts, mid, w, layer_height=0.4,
                                   require_supported_below=chained, tool_up=up, **kw)
            want = _brute(pts, up, W, 1.5 * 0.4, 0.4, chained,
                          lay if use_layer else None)
            assert np.array_equal(got, want), \
                f"연쇄={chained} 층={use_layer}: {int((got != want).sum())}점 다름"
            unsup[chained, use_layer] = int((~got).sum())
        vert, _ = check_support(pts, mid, w, layer_height=0.4,
                                require_supported_below=chained)
        differs |= not np.array_equal(got, vert)
    assert differs, "24° 원뿔 경로에서 두 프레임의 판정이 완전히 같을 수는 없다"
    # 같은 층을 빼면 미지지가 늘어난다 — 안 빼면 인공물이 가려 준 만큼이다
    assert unsup[False, True] > unsup[False, False], unsup


def test_classification_drops_the_foot_along_the_tool_axis():
    """⑤ '아랫층 단면 안인가' 는 공구 축을 따라 아랫층에 내린 발로 묻는다.

    아랫층 단면 = 반경 8 고리가 두른 원판(가장자리 8.225). 윗층의 r=8.3 점은 연직
    투영으로는 단면 밖(오버행)이지만, 층 법선을 따라 t_n=0.26 내리면 XY 가 축 쪽으로
    0.13 옮겨져 r=8.17 — 단면 안이다.
    """
    lower = _ring(8.0, 10.0)
    lower = np.vstack([lower, lower[:1]])                    # 닫힌 고리
    p = np.array([[8.3, 0.0, 10.0 + LH - 8.3 * TAN]])
    pts = np.vstack([lower, p])
    n = len(pts)
    mid = np.r_[np.zeros(n - 1, dtype=int), 1]
    kinds = np.zeros(n, dtype=int)
    lay = np.r_[np.zeros(n - 1, dtype=int), 1]
    sup = np.r_[np.ones(n - 1, dtype=bool), False]
    up, t_n = layer_frames(pts, PROF, "outward", LH)

    assert classify_unsupported(pts, mid, kinds, lay, sup, W)[-1] == OVERHANG
    lab = classify_unsupported(pts, mid, kinds, lay, sup, W, tool_up=up,
                               layer_thickness=t_n)
    assert lab[-1] == INSIDE
    # 두께는 스칼라로 줘도 된다
    assert classify_unsupported(pts, mid, kinds, lay, sup, W, tool_up=up,
                                layer_thickness=LH * COS)[-1] == INSIDE
    with pytest.raises(ValueError):
        classify_unsupported(pts, mid, kinds, lay, sup, W, tool_up=up)

    w = np.full(n, 0.2)
    b_vert = support_breakdown(pts, mid, kinds, lay, sup, w, W)
    b_tool = support_breakdown(pts, mid, kinds, lay, sup, w, W, tool_up=up,
                               layer_thickness=t_n)
    assert b_vert["overhang_pct"] > 0.0 and b_vert["inside_pct"] == 0.0
    assert b_tool["overhang_pct"] == 0.0 and b_tool["inside_pct"] > 0.0
    assert b_tool["perimeter_unsupported_pct"] == b_vert["perimeter_unsupported_pct"]


def test_layer_frames_are_the_cone_normals():
    """⑥ 층 법선·두께. REP5X 의 공구 '위' 방향(B=θ, C=방위각)과 같은 벡터다."""
    rng = np.random.default_rng(0)
    xy = rng.uniform(-9.0, 9.0, (200, 2))
    r = np.hypot(xy[:, 0], xy[:, 1])
    for direction, c in (("outward", 1.0), ("inward", -1.0)):
        pts = np.column_stack([xy, 12.0 - c * r * TAN])        # 층 Z′=12 위의 점들
        up, t_n = layer_frames(pts, PROF, direction, LH)
        assert np.allclose(np.linalg.norm(up, axis=1), 1.0)
        rhat = xy / r[:, None]
        # 층 면의 두 접선(둘레 방향, 모선 방향)에 수직
        circ = np.column_stack([-rhat[:, 1], rhat[:, 0], np.zeros(len(r))])
        gen = np.column_stack([rhat, np.full(len(r), -c * TAN)])
        assert np.allclose((up * circ).sum(axis=1), 0.0, atol=1e-12)
        assert np.allclose((up * gen).sum(axis=1), 0.0, atol=1e-12)
        assert np.all(up[:, 2] > 0) and np.allclose(t_n, LH * COS)
        if direction == "outward":
            for k in range(0, 200, 37):
                d = tool_direction(THETA, math.degrees(math.atan2(xy[k, 1], xy[k, 0])))
                assert np.allclose(up[k], [-d[0], -d[1], -d[2]], atol=1e-12)
    # 축 위의 점: 수평 성분이 없다
    up, _ = layer_frames(np.array([[0.0, 0.0, 5.0]]), PROF, "outward", LH)
    assert np.allclose(up, [[0.0, 0.0, 1.0]])
    # 블렌드 안에서는 두께가 h·m·cosθ (m = 층간격 배율) 로 달라진다
    blend = AngleProfile([(0.0, 30.0), (10.0, 30.0), (14.0, 5.0), (30.0, 5.0)])
    p = np.array([[6.0, 0.0, 12.0 - 6.0 * float(blend.tan_at(12.0))]])
    _, t_n = layer_frames(p, blend, "outward", LH)
    th = math.radians(float(blend.theta_at(12.0)))
    m = float(blend.spacing_factor(12.0, 6.0))
    assert m > 1.5 and abs(t_n[0] - LH * m * math.cos(th)) < 1e-9


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
