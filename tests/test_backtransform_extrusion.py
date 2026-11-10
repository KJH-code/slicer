"""역변환의 압출량: 회계(입력 E / 출력 E 분리)와 배율(체적 야코비안 cos²θ·m).

docs/gap_audit.md G2·G14 에서 나온 결함 둘을 고정한다.

  ① **회계** — 예전에는 ΔE 를 `입력 E − 직전 '출력' E` 로 구했다. 앞 이동에서 줄인
     양이 다음 이동에 도로 붙어 O_i = O_{i−1} + s·(E_i − O_{i−1}) 가 되고, 보정이
     누적으로는 상쇄됐다(낸 E = 입력 E × 1.000). `G92 E0` 도 몰랐다.
  ② **배율** — 의도했던 보정은 '실길이/변환길이' 였는데 체적과 다르다. 맞는 값은
     역변환의 체적 야코비안 cos²θ·m 이다 (유도는 `conical/backtransform.py`).
     여기서는 그 유도를 **식을 쓰지 않는 두 가지 방법**으로 확인한다:
       · 점 사상 `_inv_point` 의 유한차분 야코비안 행렬식
       · 변환공간의 작은 칸을 실공간으로 옮겨 그린 정리로 잰 체적

    python3 -m pytest tests/test_backtransform_extrusion.py
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.backtransform import _inv_point, backtransform, volume_scale  # noqa: E402
from conical.gcode import parse  # noqa: E402
from conical.profile import AngleProfile  # noqa: E402

# 블렌드 둘(팽창 30°→5°, 압축 5°→20°)을 가진 프로필 — m ≠ 1 인 구간을 포함한다
BLEND = AngleProfile([(0.0, 30.0), (10.0, 30.0), (14.0, 5.0), (20.0, 5.0),
                      (26.0, 20.0), (40.0, 20.0)])
COS2_30 = math.cos(math.radians(30.0)) ** 2          # 0.75


def _es(items):
    return [p.e for k, p in items if k == "move" and p.e is not None]


def _fd_det(X, Y, Zw, prof, c, eps=1e-5):
    cols = []
    for d in ((eps, 0, 0), (0, eps, 0), (0, 0, eps)):
        a = np.array(_inv_point(X + d[0], Y + d[1], Zw + d[2], prof, c))
        b = np.array(_inv_point(X - d[0], Y - d[1], Zw - d[2], prof, c))
        cols.append((a - b) / (2 * eps))
    return float(np.linalg.det(np.array(cols).T))


def test_jacobian_matches_finite_difference():
    """체적 야코비안 = cos²θ·m — 점 사상의 유한차분 행렬식과 일치 (가변각 포함)."""
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(1500):
        X, Y = rng.uniform(-12, 12, 2)
        Zw = rng.uniform(1.0, 35.0)
        if min(abs(Zw - z) for z in BLEND.zs) < 1e-3:     # 꺾이는 점에서는 미분 불가
            continue
        det = _fd_det(X, Y, Zw, BLEND, 1.0)
        worst = max(worst, abs(det - volume_scale(BLEND, X, Y, Zw, 1.0)) / abs(det))
    assert worst < 1e-7, f"유한차분과 상대오차 {worst:.2e}"

    # 상수각: outward 와 inward(c=−1) 둘 다 정확히 cos²θ (m ≡ 1)
    for theta, c in ((24.0, 1.0), (24.0, -1.0), (40.0, 1.0)):
        prof = AngleProfile.constant(theta)
        det = _fd_det(7.0, -3.0, 5.0, prof, c)
        want = math.cos(math.radians(theta)) ** 2
        assert abs(det - want) < 1e-8
        assert abs(volume_scale(prof, 7.0, -3.0, 5.0, c) - want) < 1e-12


def test_jacobian_matches_volume_of_a_mapped_cell():
    """식을 안 쓰는 두 번째 확인: 변환공간의 작은 칸을 옮겨 **체적을 직접** 잰다.

    칸 = 반경 [R, R+dR] × 방위 dφ × 높이 [Z, Z+dZ]. 축대칭이라 방위는 그대로이고
    실공간 체적 = dφ·∬ r dr dz = dφ·∮ ½ r² dz (그린 정리, 경계를 촘촘히 옮긴다).
    변환공간 체적 = dφ·½((R+dR)² − R²)·dZ. 그 비가 cos²θ·m 이어야 한다.
    """
    def ratio(prof, R, Z, dR=0.02, dZ=0.02, n=400):
        t = np.linspace(0.0, 1.0, n, endpoint=False)
        Rb = np.concatenate([R + dR * t, np.full(n, R + dR), R + dR * (1 - t),
                             np.full(n, R)])
        Zb = np.concatenate([np.full(n, Z), Z + dZ * t, np.full(n, Z + dZ),
                             Z + dZ * (1 - t)])
        th = np.radians(prof.theta_at(Zb))
        r, z = Rb * np.cos(th), Zb - Rb * np.sin(th)          # c = +1
        area_r = 0.5 * np.sum(0.5 * (r ** 2 + np.roll(r, -1) ** 2)
                              * (np.roll(z, -1) - z))          # ∮ ½ r² dz
        return area_r / (0.5 * ((R + dR) ** 2 - R ** 2) * dZ)

    for R, Z in ((6.0, 5.0), (9.0, 12.0), (3.0, 23.0), (11.0, 30.0)):
        got = ratio(BLEND, R, Z)
        want = volume_scale(BLEND, R + 0.01, 0.0, Z + 0.01, 1.0)
        assert abs(got - want) < 2e-4 * want, f"R={R} Z={Z}: {got:.6f} vs {want:.6f}"
    # 블렌드 안의 값은 cos²θ 만으로는 안 나온다 (m 이 실제로 들어간다)
    th = math.radians(float(BLEND.theta_at(12.01)))
    assert abs(ratio(BLEND, 9.0, 12.0) / math.cos(th) ** 2 - 1.0) > 0.5


def _ring(R, Zw, n, e_per_move):
    """변환공간 반경 R 의 정 n 각형을 도는 이동들 (절대 E)."""
    lines = [f"G1 X{R:.6f} Y0 Z{Zw} E0"]
    for i in range(1, n + 1):
        a = 2 * math.pi * i / n
        lines.append(f"G1 X{R * math.cos(a):.6f} Y{R * math.sin(a):.6f} "
                     f"E{i * e_per_move:.6f}")
    return lines


def test_scaling_is_applied_to_every_move_not_cancelled():
    """200 이동을 지나도 출력 E = 입력 E × cos²θ. (예전: 누적으로 상쇄돼 1.000배)"""
    out, _ = backtransform(parse(_ring(10.0, 5.0, 200, 0.05)), 30.0, "outward")
    es = _es(out)
    assert abs(es[-1] - 200 * 0.05 * COS2_30) < 1e-9, es[-1]
    # 이동마다 같은 양씩 는다 — 첫 이동만 줄고 나머지는 입력 그대로가 아니다
    steps = np.diff(es)
    assert np.allclose(steps, 0.05 * COS2_30, atol=1e-9), (steps.min(), steps.max())


def test_blend_moves_use_the_local_spacing_factor():
    """블렌드 안에서는 cos²θ 에 m = 1 − r·s 가 곱해진다 (팽창 >1, 압축 <1)."""
    for Zw in (12.0, 23.0):                    # 팽창 블렌드 / 압축 블렌드
        out, _ = backtransform(parse(_ring(8.0, Zw, 720, 0.01)), BLEND, "outward")
        got = _es(out)[-1] / (720 * 0.01)
        want = volume_scale(BLEND, 8.0, 0.0, Zw, 1.0)
        assert abs(got - want) < 1e-4 * want, f"Z′={Zw}: {got:.6f} vs {want:.6f}"
    th = math.radians(float(BLEND.theta_at(12.0)))
    assert volume_scale(BLEND, 8.0, 0.0, 12.0) > 1.5 * math.cos(th) ** 2      # 팽창
    th = math.radians(float(BLEND.theta_at(23.0)))
    assert volume_scale(BLEND, 8.0, 0.0, 23.0) < 0.8 * math.cos(th) ** 2      # 압축


def test_deposited_volume_per_real_length():
    """실공간 길이당 낸 양 = (층 면 안 폭) × (층 법선 방향 두께) — 방향과 무관.

    슬라이서 기준 e = w·h/A 로 낸 이동이, 실공간에서
      둘레 방향: 폭 w        × 두께 h·cosθ  → 실길이당 e·cosθ
      반경 방향: 폭 w·cosθ   × 두께 h·cosθ  → 실길이당 e·cos²θ   (실길이 = 변환길이)
    가 된다. '실길이/변환길이' 보정이면 둘 다 e 가 나온다.
    """
    theta = 30.0
    ct = math.cos(math.radians(theta))
    e = 0.056                                   # 변환길이 1mm 당 E (임의)

    def per_real_length(lines):
        out, _ = backtransform(parse(lines), theta, "outward")
        mv = [p for k, p in out if k == "move"]
        L = sum(math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
                for a, b in zip(mv[:-1], mv[1:], strict=True))
        return mv[-1].e / L

    n, R = 720, 10.0
    chord = 2 * R * math.sin(math.pi / n)
    ring = per_real_length(_ring(R, 5.0, n, e * chord))
    assert abs(ring / e - ct) < 1e-6, ring / e
    radial = per_real_length(["G1 X4 Y0 Z5 E0", f"G1 X12 Y0 E{8 * e}"])
    assert abs(radial / e - ct * ct) < 1e-9, radial / e


def test_g92_resets_both_counters():
    """`G92 E0` 뒤 E 가 0 에서 이어진다 (예전: 0 → 0.906 으로 튄 뒤 감소 = 리트랙트)."""
    src = ["G1 X10 Y0 Z0.3 F1800", "G1 X10 Y10 E0.5", "G1 X0 Y10 E1.0",
           "G92 E0", "G1 X0 Y0 E0.5", "G1 X10 Y0 E1.0"]
    out, _ = backtransform(parse(src), 24.0, "outward")
    k = math.cos(math.radians(24.0)) ** 2
    i = next(j for j, (kind, p) in enumerate(out) if kind == "raw" and p == "G92 E0")
    before, after = _es(out[:i]), _es(out[i:])
    assert abs(before[-1] - 1.0 * k) < 1e-9
    assert after[0] > 0.0 and np.all(np.diff([0.0, *after]) > 0), after   # 단조 증가
    assert abs(after[-1] - 1.0 * k) < 1e-9, after[-1]
    # 0 이 아닌 값으로의 재설정, 주석·다른 축 워드가 붙은 줄도 읽는다
    out, _ = backtransform(parse(["G1 X5 Y0 Z1 E0", "G1 X6 Y0 E1",
                                  "G92 X6 E2.5 ; reset", "G1 X7 Y0 E3.5"]),
                           30.0, "outward")
    assert abs(_es(out)[-1] - (2.5 + 1.0 * COS2_30)) < 1e-9


def test_retract_prime_and_wipe_are_not_scaled():
    """퇴적이 아닌 ΔE 는 그대로 옮긴다: 순수 E 이동, 그리고 움직이며 빼는 와이프."""
    src = ["G1 X10 Y0 Z1 E0", "G1 X20 Y0 E5",        # 퇴적 +5 → ×0.75
           "G1 E3 F2400",                              # 리트랙트 −2
           "G1 X25 Y0 E2",                             # 와이프: 움직이며 −1
           "G1 X30 Y0 F6000",                          # 트래블
           "G1 E5 F2400",                              # 프라임 +3
           "G1 X40 Y0 E10"]                            # 퇴적 +5 → ×0.75
    out, _ = backtransform(parse(src), 30.0, "outward")
    es = _es(out)
    dep = 5 * COS2_30
    want = [0.0, dep, dep - 2, dep - 3, dep, 2 * dep]
    got = [es[0], es[1], es[2], es[3], es[4], es[-1]]
    assert np.allclose(got, want, atol=1e-9), (got, want)


if __name__ == "__main__":
    test_jacobian_matches_finite_difference()
    test_jacobian_matches_volume_of_a_mapped_cell()
    test_scaling_is_applied_to_every_move_not_cancelled()
    test_blend_moves_use_the_local_spacing_factor()
    test_deposited_volume_per_real_length()
    test_g92_resets_both_counters()
    test_retract_prime_and_wipe_are_not_scaled()
    print("PASS: 야코비안 cos²θ·m (유한차분·칸 체적) / 회계 / G92 / 리트랙트·와이프")
