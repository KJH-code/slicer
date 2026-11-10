"""역변환의 현 분할: 정확 곡선과 출력 폴리라인의 편차가 ε 이하인가.

docs/gap_audit.md G11. 예전 분할은 허용 현 길이 L = 2√(2·r_mid·ε) 로 균등하게
쪼갰는데 r_mid 가 **끝점 반경의 평균**이었다. 축 근처를 지나는 인필·트래블은
곡률이 '축까지의 최근접 거리' 로 정해지므로 ε=0.05 인데 0.33~0.48mm 어긋났다
(노즐이 앞 층을 파는 방향). 지금은 조각마다 실제 편차를 구해 재귀 이등분한다.

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


def _forward(p, prof):
    """실공간 점들 → 변환공간 (outward, 부호 각도 규약)."""
    r = np.hypot(p[:, 0], p[:, 1])
    zw = prof.solve_forward(p[:, 2], r, "outward")
    th = np.radians(prof.theta_at(zw))
    return np.column_stack([p[:, 0] / np.cos(th), p[:, 1] / np.cos(th), zw])


def _split(A, B, prof, eps=EPS, **kw):
    """이동 A→B 하나를 역변환한 출력 꼭짓점 (시작점 포함)과 통계."""
    items = [("move", Move(g=0, x=A[0], y=A[1], z=A[2])),
             ("move", Move(g=1, x=B[0], y=B[1], z=B[2]))]
    out, st = backtransform(items, prof, "outward", chord_tol=eps, **kw)
    return np.array([[p.x, p.y, p.z] for _k, p in out]), st


def _max_dev(A, B, prof, poly, dense=40):
    """정확 곡선에서 출력 폴리라인까지의 최대 거리."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    t = np.clip(((_forward(poly, prof) - A) @ (B - A)) / float((B - A) @ (B - A)),
                0.0, 1.0)
    t[0], t[-1] = 0.0, 1.0
    worst = 0.0
    for j in range(len(poly) - 1):
        tt = np.linspace(t[j], t[j + 1], dense + 1)
        ex = _inv_many(A + (B - A) * tt[:, None], prof)
        a, ab = poly[j], poly[j + 1] - poly[j]
        u = np.clip(((ex - a) @ ab) / max(float(ab @ ab), 1e-18), 0.0, 1.0)
        worst = max(worst, float(np.linalg.norm(ex - (a + ab * u[:, None]),
                                                axis=1).max()))
    return worst


def _old_uniform_dev(A, B, prof, eps=EPS):
    """예전 분할(끝점 반경 평균으로 균등)을 그대로 재현해 편차를 잰다 — 대조용."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    ends = _inv_many(np.array([A, B]), prof)
    r_mid = 0.5 * (math.hypot(*ends[0, :2]) + math.hypot(*ends[1, :2]))
    allowed = 2.0 * math.sqrt(max(2.0 * r_mid * eps, 1e-12))
    n = max(1, math.ceil(float(np.linalg.norm(ends[1] - ends[0])) / allowed))
    poly = _inv_many(A + (B - A) * np.linspace(0, 1, n + 1)[:, None], prof)
    return _max_dev(A, B, prof, poly), n


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
            assert len(poly) - 1 <= 40, f"θ={theta} d={d}: {len(poly) - 1}조각"
    # 대조: 같은 선을 예전 방식으로 쪼개면 ε 의 약 4배다 (이 선 0.19mm. 실제 슬라이스의
    # 더 긴 인필에서는 0.33~0.48mm — docs/gap_audit.md §5)
    old, n_old = _old_uniform_dev((-6.0, 0.3, 5.1), (7.0, 0.3, 5.1),
                                  AngleProfile.constant(24.0))
    assert old > 3 * EPS, f"결함 재현 실패: 예전 분할 편차 {old:.3f} ({n_old}조각)"


def test_line_through_the_axis_is_cut_at_the_axis():
    """축을 정확히 지나는 선은 V 자다 — 꼭짓점(축)에서 한 번만 자르면 끝이다."""
    prof = AngleProfile.constant(30.0)
    A, B = (-6.0, 0.0, 5.1), (7.0, 0.0, 5.1)
    poly, _ = _split(A, B, prof)
    assert len(poly) == 3, f"{len(poly) - 1}조각"
    assert np.allclose(poly[1], (0.0, 0.0, 5.1), atol=1e-12)     # 축 위 점: z = Z′
    assert _max_dev(A, B, prof, poly) < 1e-9


def test_no_needless_splitting():
    """쪼갤 필요가 없는 이동은 한 조각이다."""
    # 평면(θ=0): 역변환이 항등이라 어떤 이동도 직선 그대로
    poly, _ = _split((-6.0, 0.3, 5.1), (7.0, 0.3, 5.1), AngleProfile.constant(0.0))
    assert len(poly) == 2
    # 반경 방향 선(축을 안 지남): 원뿔의 모선이라 실공간에서도 직선
    poly, _ = _split((2.0, 0.0, 5.1), (12.0, 0.0, 5.1), AngleProfile.constant(30.0))
    assert len(poly) == 2
    # 짧은 페리미터 현 (r=8 에서 1mm): 편차 ≈ sinθ·L²/(8r) = 0.008mm
    a = 1.0 / 8.0
    poly, _ = _split((8.0, 0.0, 5.1), (8.0 * math.cos(a), 8.0 * math.sin(a), 5.1),
                     AngleProfile.constant(30.0))
    assert len(poly) == 2


def test_random_moves_within_tolerance_including_blends():
    """무작위 이동 400개 — 블렌드 안의 층, 층을 건너는(Z′ 가 변하는) 이동 포함."""
    rng = np.random.default_rng(1)
    worst_level, worst_ramp, pieces = 0.0, 0.0, 0
    for i in range(400):
        A = np.array([*rng.uniform(-10, 10, 2), rng.uniform(1.0, 25.0)])
        B = np.array([*rng.uniform(-10, 10, 2), A[2]])
        if i % 4 == 0:                                   # 층 전환·램프: Z′ 가 변한다
            B[2] = A[2] + rng.uniform(-3.0, 3.0)
        poly, st = _split(A, B, BLEND)
        dev = _max_dev(A, B, BLEND, poly)
        pieces += len(poly) - 1
        assert st["over_tol"] == 0
        if A[2] == B[2]:
            worst_level = max(worst_level, dev)
        else:
            worst_ramp = max(worst_ramp, dev)
    assert worst_level <= EPS + 1e-9, f"레이어 안 이동 최대 편차 {worst_level:.4f}"
    # Z′ 가 변하는 이동은 닫힌 식이 없어 표본 추정이다 (보수적으로 잡지만 보장은 아님)
    assert worst_ramp <= EPS + 1e-9, f"Z′ 변하는 이동 최대 편차 {worst_ramp:.4f}"
    assert pieces < 400 * 12, f"과분할: 평균 {pieces / 400:.1f}조각"


def test_tighter_tolerance_is_honoured_and_costs_more():
    A, B = (-6.0, 0.3, 5.1), (7.0, 0.3, 5.1)
    prof = AngleProfile.constant(24.0)
    n = {}
    for eps in (0.1, 0.05, 0.01):
        poly, _ = _split(A, B, prof, eps=eps)
        assert _max_dev(A, B, prof, poly) <= eps + 1e-9
        n[eps] = len(poly) - 1
    assert n[0.1] <= n[0.05] < n[0.01], n


def test_piece_limit_is_reported_not_hidden():
    """조각 상한(max_sub)에 걸려 ε 를 못 지키면 통계에 남는다."""
    A, B = (-6.0, 0.3, 5.1), (7.0, 0.3, 5.1)
    poly, st = _split(A, B, AngleProfile.constant(24.0), max_sub=2)
    assert len(poly) - 1 <= 2 and st["over_tol"] > 0


def test_e_is_distributed_along_the_pieces():
    """쪼갠 조각들의 E 가 단조 증가하고 합이 (입력 ΔE × cos²θ) 다."""
    items = [("move", Move(g=0, x=-6.0, y=0.3, z=5.1, e=0.0)),
             ("move", Move(g=1, x=7.0, y=0.3, z=5.1, e=2.0))]
    out, _ = backtransform(items, 24.0, "outward")
    es = [p.e for _k, p in out]
    assert len(es) > 4 and np.all(np.diff(es) > 0)
    assert abs(es[-1] - 2.0 * math.cos(math.radians(24.0)) ** 2) < 1e-9


if __name__ == "__main__":
    test_near_axis_lines_stay_within_tolerance()
    test_line_through_the_axis_is_cut_at_the_axis()
    test_no_needless_splitting()
    test_random_moves_within_tolerance_including_blends()
    test_tighter_tolerance_is_honoured_and_costs_more()
    test_piece_limit_is_reported_not_hidden()
    test_e_is_distributed_along_the_pieces()
    print("PASS: 현 편차 ≤ ε (축 근처·블렌드·층 전환) / 과분할 없음 / 상한 보고")
