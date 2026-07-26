"""
profile.py — θ(Z′) 가변각 프로필. 부위별 최적 각도를 '실제 G-code'로 만드는 코어.

설계 (변환공간 높이 Z′의 함수):
    프로필 = 브레이크포인트 [(Z′_1, θ_1), ..., (Z′_n, θ_n)] (Z′ 오름차순).
    내부적으로 T(Z′) = tanθ(Z′) 를 브레이크포인트 사이 '선형 보간', 양 끝 밖은
    상수 외삽. θ가 아니라 tanθ를 보간하는 이유: 변환에 실제로 들어가는 양이
    tanθ이고, 아래 가역성 조건·블렌드 최소 폭이 정확한 닫힌 식으로 나온다.

    각도는 '부호 있는' 값으로 통일한다: θ>0 = outward, θ<0 = inward (c=+1 고정).
    tanθ가 0을 지나며 연속이므로 방향 전환 없는 밴드 조합을 하나의 c로 표현 가능.

역변환 (닫힌 형태 — 반복 불필요):
    G-code 점은 Zw(=Z′)를 이미 아므로  θ = theta_at(Zw),
    x = X·cosθ,  y = Y·cosθ,  z = Zw − c·√(X²+Y²)·sinθ.

정변환 (정점별 1차원 방정식의 '정확 해' — 이분법 금지):
    정점 (x,y,z), r=√(x²+y²) 고정일 때 Z′는  z = Z′ − c·r·T(Z′) 를 만족.
    T가 조각별 선형이므로 구간 [a,b]에서 T(Z′)=t_a+s·(Z′−a) 라면
        Z′ = ( z + c·r·(t_a − s·a) ) / ( 1 − c·r·s )
    가 그 구간의 정확 해다. 구간을 차례로 검사해 [a,b]에 드는 해를 채택한다.

가역성 조건과 블렌드 최소 폭 (이 유도가 우리 분석 기여):
    해가 유일하려면 F(Z′) = Z′ − c·r·T(Z′) 가 순증가해야 한다:
        1 − c·r·(dT/dZ′) > 0   ⟺   c·r·s < 1   (모든 구간, 모든 정점 r)
    각도가 θ₁→θ₂로 바뀌는 블렌드 구간(폭 w)에서 s = (tanθ₂−tanθ₁)/w 이므로,
    c·(tanθ₂−tanθ₁) > 0 (불안정 방향)일 때만 제약이 걸리고
        w_min = c · r_max · (tanθ₂ − tanθ₁)
    ⚠ 정직: r_max는 '전 모델 최대 반경'을 쓰는 보수적 근사다 — 블렌드가 걸리는
      높이 구간의 실제 최대 반경보다 클 수 있다(필요보다 넓은 블렌드 허용).
"""

import math

import numpy as np


class AngleProfile:
    """θ(Z′) 프로필. breakpoints = [(Zw, theta_deg_signed), ...] (Zw 오름차순)."""

    def __init__(self, breakpoints):
        if not breakpoints:
            raise ValueError("빈 프로필")
        zs = np.array([float(b[0]) for b in breakpoints])
        th = np.array([float(b[1]) for b in breakpoints])
        if len(zs) > 1 and not np.all(np.diff(zs) > 1e-12):
            raise ValueError(f"브레이크포인트 Z′는 순증가여야 함: {zs.tolist()}")
        self.zs = zs
        self.thetas_deg = th
        self.tans = np.tan(np.radians(th))

    # ── 조회 ──
    def tan_at(self, zw):
        return np.interp(zw, self.zs, self.tans)      # 양 끝 상수 외삽

    def theta_at(self, zw):
        """도(deg, 부호 있음). 스칼라/배열 모두."""
        return np.degrees(np.arctan(self.tan_at(zw)))

    def is_constant(self):
        return len(self.zs) == 1 or np.allclose(self.tans, self.tans[0])

    def blend_intervals(self):
        """기울기 s≠0 인 내부 구간 [(a,b), ...] — 각도가 변하는 블렌드 구간."""
        out = []
        for i in range(len(self.zs) - 1):
            if abs(self.tans[i + 1] - self.tans[i]) > 1e-12:
                out.append((float(self.zs[i]), float(self.zs[i + 1])))
        return out

    # ── 검증 ──
    def validate(self, r_max, direction="outward"):
        """가역성 검사: 모든 구간에서 c·r_max·s < 1. 위반 시 w_min 포함 에러."""
        c = 1.0 if direction == "outward" else -1.0
        for i in range(len(self.zs) - 1):
            a, b = self.zs[i], self.zs[i + 1]
            dt = self.tans[i + 1] - self.tans[i]
            s = dt / (b - a)
            if c * r_max * s >= 1.0 - 1e-12:
                w_min = c * r_max * dt
                raise ValueError(
                    f"프로필 가역성 위반: 구간 [{a:.2f},{b:.2f}] 에서 "
                    f"c·r_max·s = {c * r_max * s:.3f} ≥ 1. "
                    f"θ {self.thetas_deg[i]:.1f}°→{self.thetas_deg[i+1]:.1f}° 전환에는 "
                    f"최소 폭 w_min = c·r_max·(tanθ₂−tanθ₁) = {w_min:.2f} mm 가 필요 "
                    f"(현재 폭 {b - a:.2f} mm). 블렌드를 넓히거나 각도 차를 줄일 것.")
        return True

    # ── 정변환 (정확 해, 벡터화) ──
    def solve_forward(self, z, r, direction="outward"):
        """z = Z′ − c·r·T(Z′) 의 정확 해 Z′ (배열). validate 통과 프로필 전제."""
        z = np.asarray(z, dtype=float)
        r = np.asarray(r, dtype=float)
        c = 1.0 if direction == "outward" else -1.0
        zs, tans = self.zs, self.tans
        out = np.full(z.shape, np.nan)

        # 왼쪽 바깥 (T = tans[0] 상수)
        cand = z + c * r * tans[0]
        m = np.isnan(out) & (cand <= zs[0] + 1e-9)
        out[m] = cand[m]
        # 내부 구간들
        for i in range(len(zs) - 1):
            a, b = zs[i], zs[i + 1]
            s = (tans[i + 1] - tans[i]) / (b - a)
            denom = 1.0 - c * r * s
            with np.errstate(divide="ignore", invalid="ignore"):
                cand = (z + c * r * (tans[i] - s * a)) / denom
            m = np.isnan(out) & (denom > 1e-12) & \
                (cand >= a - 1e-9) & (cand <= b + 1e-9)
            out[m] = cand[m]
        # 오른쪽 바깥 (T = tans[-1] 상수)
        cand = z + c * r * tans[-1]
        m = np.isnan(out) & (cand >= zs[-1] - 1e-9)
        out[m] = cand[m]

        if np.isnan(out).any():
            raise RuntimeError(
                f"정변환 해를 못 찾은 정점 {int(np.isnan(out).sum())}개 — "
                "프로필 validate() 를 먼저 통과시킬 것")
        return out

    # ── 생성기 ──
    @classmethod
    def constant(cls, theta_deg):
        return cls([(0.0, float(theta_deg))])

    @classmethod
    def from_bands(cls, bands, r_max, safety=1.5, min_blend=0.5):
        """밴드 리스트 → 블렌드 자동 삽입 프로필.

        bands: [(z_lo, z_hi, theta_deg_signed), ...]  실공간 z 구간(오름차순).
        ⚠ 경계 해석(정직): 실공간 z 경계를 '축상(r=0, 그곳에서 Z′=z)' 기준 Z′ 값으로
          근사한다 — 축에서 멀수록 경계가 최대 r·tanθ 만큼 어긋날 수 있다.
          이 오차가 실제로 문제인지는 툴패스 검사기(P2)가 판정한다.
        블렌드 폭 w = max(min_blend, safety × w_min),  w_min = r_max·Δtan (불안정 방향만).
        """
        if not bands:
            raise ValueError("빈 밴드 리스트")
        bps = [(float(bands[0][0]), float(bands[0][2]))]
        for i in range(len(bands) - 1):
            th1 = float(bands[i][2])
            th2 = float(bands[i + 1][2])
            zb = float(bands[i][1])                    # 경계 (축상 Z′≈z 근사)
            dtan = math.tan(math.radians(th2)) - math.tan(math.radians(th1))
            w_min = r_max * dtan                       # c=+1 (부호 있는 각도 규약)
            w = max(min_blend, safety * w_min if w_min > 0 else min_blend)
            lo, hi = zb - w / 2.0, zb + w / 2.0
            if lo <= bps[-1][0] + 1e-9:
                raise ValueError(
                    f"블렌드 구간이 겹침: 경계 {zb:.2f} 의 블렌드 폭 {w:.2f}mm 가 "
                    f"이전 브레이크포인트 {bps[-1][0]:.2f} 와 충돌. 밴드를 넓힐 것.")
            bps.append((lo, th1))
            bps.append((hi, th2))
        bps.append((float(bands[-1][1]), float(bands[-1][2])))
        # 같은 각도 연속 등 중복 제거는 하지 않음(무해) — 단조성만 보장됨
        prof = cls(bps)
        prof.validate(r_max, "outward")
        return prof

    @classmethod
    def from_banded_result(cls, banded_result, r_max, safety=1.5, min_blend=0.5):
        """varangle.select_banded 결과(실공간 z 밴드 + 각도/방향) → 프로필 어댑터.

        ⚠ 경계 해석(정직): select_banded 의 z 경계를 축상(r=0, Z′=z) 기준 Z′ 로
          근사 — 축에서 멀수록 경계가 최대 r·tanθ 만큼 어긋날 수 있다. 이 오차의
          실질 영향은 툴패스 검사기(toolpath_check.py)가 판정한다.
        방향은 부호로 접음: inward 밴드 = 음수 각도 (c=+1 규약).
        빈 밴드(None)는 이전 밴드 각도를 이어받아 불필요한 블렌드를 피한다.
        """
        edges = banded_result["edges"]
        prof_list = banded_result["profile"]
        bands = []
        prev_theta = 0.0
        for i, p in enumerate(prof_list):
            if p is None:
                theta = prev_theta
            else:
                ang, direction = p
                theta = float(ang) if direction == "outward" else -float(ang)
            bands.append((float(edges[i]), float(edges[i + 1]), theta))
            prev_theta = theta
        # 같은 각도 연속 밴드 병합 (블렌드 최소화)
        merged = [list(bands[0])]
        for lo, hi, th in bands[1:]:
            if abs(th - merged[-1][2]) < 1e-12:
                merged[-1][1] = hi
            else:
                merged.append([lo, hi, th])
        return cls.from_bands([tuple(b) for b in merged], r_max, safety, min_blend)

    @classmethod
    def parse(cls, text):
        """CLI 문자열 "Z1:deg1,Z2:deg2,..." → 프로필 (deg 는 부호 허용)."""
        bps = []
        for part in text.split(","):
            zs, ds = part.split(":")
            bps.append((float(zs), float(ds)))
        return cls(bps)

    def describe(self):
        """사람용 표: 구간·각도·블렌드 표시."""
        lines = []
        for i, (z, th) in enumerate(zip(self.zs, self.thetas_deg)):
            lines.append(f"    Z'={z:8.2f}  θ={th:6.1f}°")
        for a, b in self.blend_intervals():
            lines.append(f"    (블렌드 [{a:.2f}, {b:.2f}] 폭 {b - a:.2f} mm)")
        return "\n".join(lines)
