"""verify_proofs.py — 「증명·유도 모음」 §10 의 독립 수치 검산.

저장소 코드(conical/)를 하나도 불러오지 않고 numpy 만으로, 닫힌 식을 다른 계산 방법
(유한차분·전수 탐색)과 맞춘다. 실행 1초 미만.

    python3 tools/verify_proofs.py

보증하는 것은 '식과 유도의 일치' 다. 물리적으로 맞는지(45° 문턱, 비드 모형, 핫엔드 치수,
축 부호)는 실물 사다리 L0·L4·L5 가 가른다.
"""

import numpy as np

RNG = np.random.default_rng(0)
KAPPA = -np.sin(np.radians(45.0))


def tan_profile(zp):
    """임의의 매끈한 tanθ(Z′): θ = 20° + 10°·tanh(Z′ − 5)."""
    return np.tan(np.radians(20.0 + 10.0 * np.tanh(zp - 5.0)))


def inverse_map(big_r, zp, c):
    """왜곡공간 (R, Z′) → 실공간 (r, z):  r = R·cosθ,  z = Z′ − c·R·sinθ."""
    th = np.arctan(tan_profile(zp))
    return big_r * np.cos(th), zp - c * big_r * np.sin(th)


def check_jacobian(n=2000, e=1e-6):
    """(a) dV/dV′ = cos²θ·m  vs  유한차분 행렬식 × r/R."""
    worst = 0.0
    for _ in range(n):
        big_r, zp = RNG.uniform(0.5, 15.0), RNG.uniform(0.0, 10.0)
        c = RNG.choice([1.0, -1.0])
        r0, _z0 = inverse_map(big_r, zp, c)
        rp, zrp = inverse_map(big_r + e, zp, c)
        rm, zrm = inverse_map(big_r - e, zp, c)
        rzp, zzp = inverse_map(big_r, zp + e, c)
        rzm, zzm = inverse_map(big_r, zp - e, c)
        dr_dr, dz_dr = (rp - rm) / (2 * e), (zrp - zrm) / (2 * e)
        dr_dz, dz_dz = (rzp - rzm) / (2 * e), (zzp - zzm) / (2 * e)
        jac_fd = (r0 / big_r) * (dr_dr * dz_dz - dr_dz * dz_dr)
        th = np.arctan(tan_profile(zp))
        s = (tan_profile(zp + e) - tan_profile(zp - e)) / (2 * e)
        m = 1.0 - c * r0 * s
        worst = max(worst, abs(jac_fd - np.cos(th) ** 2 * m) / abs(jac_fd))
    print(f"(a) 야코비안 cos²θ·m vs 유한차분: {n}점 최대 상대오차 {worst:.1e}")


def check_theta_star(n=3000):
    """(b) θ* = asin(κ/R) − atan2(n_z, c·n_r)  vs  0~90° 전수 탐색."""
    ts = np.radians(np.linspace(0.0, 89.99, 200001))
    used = bad = 0
    for _ in range(n):
        v = RNG.normal(size=3)
        v /= np.linalg.norm(v)
        nr, _nt, nz = v
        c = RNG.choice([1.0, -1.0])
        rn = np.hypot(nz, nr)
        if rn <= abs(KAPPA) or nz >= KAPPA:
            continue                                   # 늘 지지되거나 이미 지지됨
        ok = nz * np.cos(ts) + c * nr * np.sin(ts) >= KAPPA
        if not ok.any():
            continue                                   # 어떤 원뿔 각으로도 못 구함
        brute = np.degrees(ts[ok.argmax()])
        closed = np.degrees(np.arcsin(KAPPA / rn) - np.arctan2(nz, c * nr)) % 360.0
        used += 1
        bad += abs(brute - closed) > 1e-3
    print(f"(b) θ* 닫힌 식 vs 0~90° 전수 탐색: {used}면 중 불일치 {bad}")


def check_b_safe(a=2.0, rho=4.5, clearance=0.25, tip=0.15):
    """(c) B_safe = acos(d/R) − φ  vs  자세 전수 탐색 (공식 뷰어 노즐 원통 r4.5, 높이 2)."""
    d = clearance - tip
    closed = np.degrees(np.arccos(d / np.hypot(a, rho)) - np.arctan2(rho, a))
    bs = np.radians(np.linspace(0.0, 89.0, 890001))
    lowest = tip + a * np.cos(bs) - rho * np.sin(bs)   # 테두리 최저점 높이
    brute = np.degrees(bs[lowest >= clearance].max())
    print(f"(c) B_safe 닫힌 식 {closed:.4f}° vs 전수 {brute:.4f}°  "
          f"(팁 {tip}mm, 여유 {clearance}mm)")


def check_tool_direction(n=2000):
    """(d) (B, C) = (cθ, φ) 와 극점 반전 (−cθ, φ+180°) 가 둘 다 공구 방향 = −b."""
    err = 0.0
    for _ in range(n):
        th, ph = np.radians(RNG.uniform(1.0, 60.0)), np.radians(RNG.uniform(-180.0, 180.0))
        c = RNG.choice([1.0, -1.0])
        b = np.array([c * np.sin(th) * np.cos(ph), c * np.sin(th) * np.sin(ph), np.cos(th)])
        for bb, cc in ((c * th, ph), (-c * th, ph + np.pi)):
            d = np.array([-np.sin(bb) * np.cos(cc), -np.sin(bb) * np.sin(cc), -np.cos(bb)])
            err = max(err, float(np.abs(d + b).max()))
    print(f"(d) 공구 방향 = −b (두 분기): 최대 오차 {err:.1e}")


def check_concavity(c, n=500, k=200):
    """(e) 원뿔 층 z = Z′ − c·r·tanθ 의 점이 접평면 위로 나오는 개수."""
    above = 0
    for _ in range(n):
        th = np.radians(RNG.uniform(5.0, 40.0))
        p = RNG.uniform(-10.0, 10.0, 2)
        q = RNG.uniform(-15.0, 15.0, (k, 2))
        fq = -c * np.linalg.norm(q, axis=1) * np.tan(th)
        fp = -c * np.linalg.norm(p) * np.tan(th)
        grad = -c * np.tan(th) * p / np.linalg.norm(p)
        above += int((fq > fp + (q - p) @ grad + 1e-12).sum())
    return above, n * k


def main():
    check_jacobian()
    check_theta_star()
    check_b_safe()
    check_tool_direction()
    out_up, tot = check_concavity(+1.0)
    in_up, _ = check_concavity(-1.0)
    print(f"(e) 원뿔 층이 접평면 위로 나오는 점: outward {out_up} / {tot}, inward {in_up} / {tot}")
    print(f"(f) cos22° = {np.cos(np.radians(22.0)):.4f}  "
          f"(사다리 L4b/L4a 실측 E/mm 비 0.05204/0.05613 = {0.05204 / 0.05613:.4f})")


if __name__ == "__main__":
    main()
