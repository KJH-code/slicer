"""역변환의 현 분할: 정확 곡선과 출력 폴리라인의 편차가 ε 이하인가.

docs/gap_audit.md G11. 분할은 허용 현 길이 L = 2√(2·r_mid·ε) 로 균등하게 쪼개는데
r_mid 가 **끝점 반경의 평균**이다. 축 근처를 지나는 인필·트래블은 곡률이 '축까지의
최근접 거리' 로 정해지므로 ε=0.05 인데 0.33~0.48mm 어긋났다(노즐이 앞 층을 파는
방향). 지금은 균등 분할한 조각마다 실제 편차를 구해 ε 를 넘는 조각만 더 쪼갠다.

고정하는 것:
  ① 편차 ≤ ε — 축 근처, 블렌드 안, 층을 건너는 이동 전부
  ② 균등 분할의 꼭짓점은 전부 남는다. ε 를 지키던 이동은 좌표가 예전 그대로다
     (5축 출력이 조각 안에서 B/C 를 선형 보간하므로 조각을 길게 만들지 않는다)
  ③ 축 최근접점 바로 위가 아니라 그 양옆 ±a 에서 자른다
  ④ 조각 상한에 걸리면 숨기지 않고 통계에 남긴다

편차는 여기서 **분할 코드와 무관하게** 잰다: 출력 꼭짓점 사이를 변환공간에서
촘촘히 보간해 역변환한 정확 곡선과, 출력 선분 사이의 거리.

    python3 -m pytest tests/test_backtransform_chord.py
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.backtransform import backtransform  # noqa: E402
from conical.gcode import Move  # noqa: E402
from conical.profile import AngleProfile  # noqa: E402

EPS = 0.05
BLEND = AngleProfile([(0.0, 30.0), (10.0, 30.0), (14.0, 5.0), (30.0, 5.0)])


def _inv_many(P, prof, c=1.0):
    th = np.radians(prof.theta_at(P[:, 2]))
    return np.column_stack([P[:, 0] * np.cos(th), P[:, 1] * np.cos(th),
                            P[:, 2] - c * np.hypot(P[:, 0], P[:, 1]) * np.sin(th)])


def _params(A, B, prof, poly):
    """출력 꼭짓점들의 매개변수 t (정변환해 직선 A→B 에 투영)."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    r = np.hypot(poly[:, 0], poly[:, 1])
    zw = prof.solve_forward(poly[:, 2], r, "outward")
    th = np.radians(prof.theta_at(zw))
    W = np.column_stack([poly[:, 0] / np.cos(th), poly[:, 1] / np.cos(th), zw])
    t = np.clip(((W - A) @ (B - A)) / float((B - A) @ (B - A)), 0.0, 1.0)
    t[0], t[-1] = 0.0, 1.0
    return t


def _split(A, B, prof, eps=EPS, **kw):
    """이동 A→B 하나를 역변환한 출력 꼭짓점 (시작점 포함)과 통계."""
    items = [("move", Move(g=0, x=A[0], y=A[1], z=A[2])),
             ("move", Move(g=1, x=B[0], y=B[1], z=B[2]))]
    out, st = backtransform(items, prof, "outward", chord_tol=eps, **kw)
    return np.array([[p.x, p.y, p.z] for _k, p in out]), st


def _max_dev(A, B, prof, poly, dense=40):
    """정확 곡선에서 출력 폴리라인까지의 최대 거리."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    t = _params(A, B, prof, poly)
    worst = 0.0
    for j in range(len(poly) - 1):
        tt = np.linspace(t[j], t[j + 1], dense + 1)
        ex = _inv_many(A + (B - A) * tt[:, None], prof)
        a, ab = poly[j], poly[j + 1] - poly[j]
        u = np.clip(((ex - a) @ ab) / max(float(ab @ ab), 1e-18), 0.0, 1.0)
        worst = max(worst, float(np.linalg.norm(ex - (a + ab * u[:, None]),
                                                axis=1).max()))
    return worst


def _legacy(A, B, prof, eps=EPS):
    """균등 분할만 한 폴리라인 (2026-11-10 이전 동작의 재현) — 대조용."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    ends = _inv_many(np.array([A, B]), prof)
    r_mid = 0.5 * (math.hypot(*ends[0, :2]) + math.hypot(*ends[1, :2]))
    allowed = 2.0 * math.sqrt(max(2.0 * r_mid * eps, 1e-12))
    if any(a < max(A[2], B[2]) and b > min(A[2], B[2])
           for a, b in prof.blend_intervals()):
        allowed *= 0.5
    n = max(1, math.ceil(float(np.linalg.norm(ends[1] - ends[0])) / allowed))
    return _inv_many(A + (B - A) * (np.arange(n + 1) / n)[:, None], prof)


def test_near_axis_lines_stay_within_tolerance():
    """축 근처를 지나는 13mm 선(인필·트래블)이 ε 를 지킨다. 예전에는 못 지켰다."""
    for theta in (24.0, 30.0):
        prof = AngleProfile.constant(theta)
        for d in (0.0, 0.02, 0.1, 0.3, 1.0, 3.0):         # 축까지 최근접 거리
            A, B = (-6.0, d, 5.1), (7.0, d, 5.1)
            poly, st = _split(A, B, prof)
            dev = _max_dev(A, B, prof, poly)
            assert dev <= EPS + 1e-9, f"θ={theta} d={d}: 편차 {dev:.4f} > ε"
            assert st["over_tol"] == 0
            n_legacy = len(_legacy(A, B, prof)) - 1
            assert len(poly) - 1 <= n_legacy + 6, \
                f"θ={theta} d={d}: {n_legacy} → {len(poly) - 1}조각 (과분할)"
    # 대조: 같은 선을 균등 분할만 하면 ε 의 약 4배다 (이 선 0.19mm. 실제 슬라이스의
    # 더 긴 인필에서는 0.33~0.48mm — docs/gap_audit.md §5)
    A, B, prof = (-6.0, 0.3, 5.1), (7.0, 0.3, 5.1), AngleProfile.constant(24.0)
    old = _max_dev(A, B, prof, _legacy(A, B, prof))
    assert old > 3 * EPS, f"결함 재현 실패: 균등 분할 편차 {old:.3f}"


def test_moves_already_within_tolerance_are_unchanged():
    """ε 를 지키던 이동은 균등 분할 그대로다 — 좌표가 비트 단위로 같다."""
    a = 3.0 / 8.0
    cases = [
        # 평면(θ=0): 역변환이 항등
        ((-6.0, 0.3, 5.1), (7.0, 0.3, 5.1), AngleProfile.constant(0.0)),
        # 반경 방향 선(축을 안 지남): 원뿔의 모선이라 실공간에서도 직선
        ((2.0, 0.0, 5.1), (12.0, 0.0, 5.1), AngleProfile.constant(30.0)),
        # 페리미터 현 (r=8 에서 3mm)
        ((8.0, 0.0, 5.1), (8.0 * math.cos(a), 8.0 * math.sin(a), 5.1),
         AngleProfile.constant(30.0)),
        # 블렌드 안의 층, 축에서 먼 선
        ((6.0, -5.0, 12.0), (6.0, 5.0, 12.0), BLEND),
        # 층을 건너는 트래블 (Z′ 가 변한다), 축에서 먼 곳
        ((7.0, 1.0, 5.1), (9.0, 4.0, 5.4), BLEND),
    ]
    for A, B, prof in cases:
        poly, st = _split(A, B, prof)
        want = _legacy(A, B, prof)
        assert poly.shape == want.shape, f"{A}→{B}: {len(want)} → {len(poly)} 점"
        assert np.allclose(poly, want, rtol=0.0, atol=1e-12)
        assert _max_dev(A, B, prof, poly) <= EPS + 1e-9 and st["over_tol"] == 0


def test_uniform_grid_vertices_survive_refinement():
    """ε 를 넘던 이동도 균등 분할의 꼭짓점은 전부 남고, 그 사이에만 점이 더 든다."""
    for A, B, prof in (((-6.0, 0.3, 5.1), (7.0, 0.3, 5.1), AngleProfile.constant(24.0)),
                       ((-6.0, 0.0, 5.1), (7.0, 0.0, 5.1), AngleProfile.constant(30.0)),
                       ((-5.0, 0.1, 12.0), (8.0, -0.4, 12.0), BLEND),
                       ((-5.0, 0.2, 5.1), (6.0, -0.1, 5.4), BLEND)):
        poly, _ = _split(A, B, prof)
        legacy = _legacy(A, B, prof)
        assert len(poly) > len(legacy), "이 이동은 더 쪼개져야 한다 (표본 선택 오류)"
        for q in legacy:
            assert np.abs(poly - q).sum(axis=1).min() < 1e-12, f"꼭짓점 {q} 가 사라졌다"


def test_axis_passage_is_flanked_not_cut_on_the_closest_point():
    """축 최근접점 양옆 ±a 에서 자른다 (a = √(τ²+2dτ), τ = ε/sinθ).

    조각 [−a, +a] 의 편차가 정확히 ε 다 — 꺾임을 품는 조각을 허용 한도까지 넓게
    잡는 것. 최근접점 바로 위에 꼭짓점을 두면 그 점의 방위각이 경로와 직각이라
    5축 변환이 축 통과를 B 부호 반전 대신 C 90°+90° 로 풀게 된다.
    """
    theta = 30.0
    prof = AngleProfile.constant(theta)
    tau = EPS / math.sin(math.radians(theta))
    for d in (0.0, 0.05, 0.3):
        A, B = (-6.0, d, 5.1), (7.0, d, 5.1)          # 최근접점은 X=0 (t = 6/13)
        poly, _ = _split(A, B, prof)
        u = (_params(A, B, prof, poly) - 6.0 / 13.0) * 13.0   # 최근접점 기준 거리(mm)
        a = math.sqrt(tau * tau + 2.0 * d * tau)
        inner = np.sort(u[np.abs(u) < a + 1e-3])
        assert len(inner) == 2 and np.allclose(inner, [-a, a], atol=1e-4), \
            f"d={d}: 최근접점 근처 꼭짓점 {inner} (기대 ±{a:.4f})"
        dev = _max_dev(A, B, prof, poly)
        assert EPS * 0.98 <= dev <= EPS + 1e-9, f"d={d}: 편차 {dev:.4f}"


def test_random_moves_within_tolerance_including_blends():
    """무작위 이동 400개 — 블렌드 안의 층, 층을 건너는(Z′ 가 변하는) 이동 포함."""
    rng = np.random.default_rng(1)
    worst_level, worst_ramp, pieces, legacy = 0.0, 0.0, 0, 0
    for i in range(400):
        A = np.array([*rng.uniform(-10, 10, 2), rng.uniform(1.0, 25.0)])
        B = np.array([*rng.uniform(-10, 10, 2), A[2]])
        if i % 4 == 0:                                   # 층 전환·램프: Z′ 가 변한다
            B[2] = A[2] + rng.uniform(-3.0, 3.0)
        poly, st = _split(A, B, BLEND)
        dev = _max_dev(A, B, BLEND, poly)
        pieces += len(poly) - 1
        legacy += len(_legacy(A, B, BLEND)) - 1
        assert st["over_tol"] == 0
        if A[2] == B[2]:
            worst_level = max(worst_level, dev)
        else:
            worst_ramp = max(worst_ramp, dev)
    assert worst_level <= EPS + 1e-9, f"레이어 안 이동 최대 편차 {worst_level:.4f}"
    # Z′ 가 변하는 이동은 닫힌 식이 없어 표본 추정이다 (보수적으로 잡지만 보장은 아님)
    assert worst_ramp <= EPS + 1e-9, f"Z′ 변하는 이동 최대 편차 {worst_ramp:.4f}"
    assert pieces < 1.5 * legacy, f"과분할: {legacy} → {pieces}조각"


def test_tighter_tolerance_is_honoured_and_costs_more():
    A, B = (-6.0, 0.3, 5.1), (7.0, 0.3, 5.1)
    prof = AngleProfile.constant(24.0)
    n = {}
    for eps in (0.1, 0.05, 0.01):
        poly, _ = _split(A, B, prof, eps=eps)
        assert _max_dev(A, B, prof, poly) <= eps + 1e-9
        n[eps] = len(poly) - 1
    assert n[0.1] < n[0.05] < n[0.01], n


def test_piece_limit_is_reported_not_hidden():
    """조각 상한(max_sub)에 걸려 ε 를 못 지키면 통계에 남는다."""
    A, B = (-10.0, 3.0, 5.1), (10.0, 3.0, 5.1)   # 축에서 3mm 를 스치는 20mm 선
    prof = AngleProfile.constant(24.0)
    poly, st = _split(A, B, prof, max_sub=2)
    assert len(poly) - 1 <= 4                  # 균등 2 + 더 넣은 분할점 2
    assert st["over_tol"] > 0 and _max_dev(A, B, prof, poly) > EPS
    poly, st = _split(A, B, prof)
    assert st["over_tol"] == 0 and _max_dev(A, B, prof, poly) <= EPS + 1e-9


def test_e_is_distributed_along_the_pieces():
    """쪼갠 조각들의 E 가 단조 증가하고 합이 (입력 ΔE × cos²θ) 다."""
    items = [("move", Move(g=0, x=-6.0, y=0.3, z=5.1, e=0.0)),
             ("move", Move(g=1, x=7.0, y=0.3, z=5.1, e=2.0))]
    out, _ = backtransform(items, 24.0, "outward")
    es = [p.e for _k, p in out]
    assert len(es) > 4 and np.all(np.diff(es) > 0)
    assert abs(es[-1] - 2.0 * math.cos(math.radians(24.0)) ** 2) < 1e-9
    # 조각의 E 몫은 변환공간 길이(매개변수)에 비례한다 — 상수각이면 배율이 같으므로
    poly = np.array([[p.x, p.y, p.z] for _k, p in out])
    t = _params((-6.0, 0.3, 5.1), (7.0, 0.3, 5.1), AngleProfile.constant(24.0), poly)
    assert np.allclose(np.array(es) / es[-1], t, atol=1e-9)


if __name__ == "__main__":
    test_near_axis_lines_stay_within_tolerance()
    test_moves_already_within_tolerance_are_unchanged()
    test_uniform_grid_vertices_survive_refinement()
    test_axis_passage_is_flanked_not_cut_on_the_closest_point()
    test_random_moves_within_tolerance_including_blends()
    test_tighter_tolerance_is_honoured_and_costs_more()
    test_piece_limit_is_reported_not_hidden()
    test_e_is_distributed_along_the_pieces()
    print("PASS: 현 편차 ≤ ε (축 근처·블렌드·층 전환) / 균등 분할 보존 / 상한 보고")
