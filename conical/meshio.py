"""
meshio.py — STL 파일을 읽거나, 없으면 데모용 구(sphere)를 만든다.

세 CLI 스크립트가 똑같이 반복하던 "인자로 STL 주면 로드, 아니면 데모 구" 부분을
한 곳으로 모은 것. 구(sphere)는 아랫면이 곡면 오버행이라 원뿔 슬라이싱 효과를
보기에 좋은 기본 테스트 모델이다.
"""

import math

import numpy as np
import trimesh


class RadiusProfile:
    """높이 구간별 최대 반경 r_max(z). 블렌드 폭·전이 높이 결정에 쓴다.

    왜 필요한가: 블렌드(각도가 변하는 구간)에서 층간격 배율은 1 − c·r·s 라
    '그 높이의 반경'에 비례해 커진다. 지금까지는 전 모델 최대 반경(r_max)만 써서
    ⓐ 가는 부분에서 필요 이상으로 넓은 블렌드를 잡고 ⓑ '어느 높이에 경계를 두면
    유리한가'를 아예 못 봤다. 높이별 반경을 알면 둘 다 해결된다.

    ⚠ 정직: 정점 기준 구간별 최댓값이다(면 내부는 보간하지 않음). 정점이 없는
      구간은 양 이웃의 큰 값으로 채워 보수적으로 잡는다.

    ⚠⚠ 블렌드 반경은 `max_between` 이 아니라 `max_in_slab` 으로 조회할 것
      (2026-11-10, docs/gap_audit.md G1). 블렌드는 **변환높이 Z′** 구간이고 그 구간의
      층은 원뿔이라 반경이 클수록 실공간에서 아래(outward)로 내려간다. 실공간 z 구간
      [lo, hi] 로 조회하면 그 층들이 실제로 닿는 뚱뚱한 부분을 놓친다 — 램프 밴드2 는
      목(r=2mm)만 보고 폭을 잡았는데 층은 구의 어깨(r=6.6mm)까지 내려가 명목
      m=1.50 이 실제 2.6 이었다.
    """

    SLAB_BIN = 0.05          # max_in_slab 용 포락선의 칸 높이 목표 (mm)
    SLAB_BINS_MAX = 4000     # 그 칸 수의 상한 (아주 높은 모델에서 칸이 굵어진다)

    def __init__(self, mesh, n_bins=120):
        v = np.asarray(mesh.vertices, dtype=float)
        r = np.hypot(v[:, 0], v[:, 1])
        z = v[:, 2]
        self.z0, self.z1 = float(z.min()), float(z.max())
        self.global_max = float(r.max())
        n = max(1, int(n_bins))
        self.n = n
        self.h = max((self.z1 - self.z0) / n, 1e-9)
        idx = np.clip(((z - self.z0) / self.h).astype(int), 0, n - 1)
        rmax = np.full(n, -1.0)
        np.maximum.at(rmax, idx, r)
        # 빈 칸(정점 없는 높이) 채우기: 양쪽 최근접 유효값 중 큰 쪽 (보수적)
        left = rmax.copy()
        for i in range(1, n):
            if left[i] < 0:
                left[i] = left[i - 1]
        right = rmax.copy()
        for i in range(n - 2, -1, -1):
            if right[i] < 0:
                right[i] = right[i + 1]
        filled = np.maximum(left, right)
        filled[filled < 0] = self.global_max
        self.rmax = filled

        # ── max_in_slab 용 촘촘한 포락선: 칸마다 '표면의' 최대 반경 (정확) ──
        # 정점만 보면 긴 변이 지나가는 높이가 비고(원기둥은 위아래 테두리뿐이다),
        # 칸이 0.05mm 로 가늘면 거의 다 빈다. 그래서 변(edge)을 칸 경계에서 자른다:
        # 같은 높이에서 삼각형의 단면은 선분이고 r 은 선분 위에서 볼록이므로 최대는
        # 그 끝점, 곧 변 위에 있다. 변 위에서도 r 이 볼록이라 칸 안의 최대는 변이
        # 칸 경계와 만나는 점 아니면 정점이다 → 그 점들만 보면 칸별 최댓값이 정확하다.
        nf = int(np.clip(math.ceil((self.z1 - self.z0) / self.SLAB_BIN), n,
                         self.SLAB_BINS_MAX))
        hf = max((self.z1 - self.z0) / nf, 1e-9)
        env = np.zeros(nf)                      # 표면이 없는 칸은 0 (재료 없음)
        np.maximum.at(env, np.clip(((z - self.z0) / hf).astype(int), 0, nf - 1), r)
        edges = np.asarray(mesh.edges_unique, dtype=int).reshape(-1, 2)
        flip = z[edges[:, 1]] < z[edges[:, 0]]
        ea = np.where(flip, edges[:, 1], edges[:, 0])                # z[ea] ≤ z[eb]
        eb = np.where(flip, edges[:, 0], edges[:, 1])
        j0 = np.floor((z[ea] - self.z0) / hf).astype(int) + 1        # 첫 경계 (> z_a)
        j1 = np.ceil((z[eb] - self.z0) / hf).astype(int) - 1         # 끝 경계 (< z_b)
        cnt = np.maximum(j1 - j0 + 1, 0)
        cum = np.cumsum(cnt)
        s0 = 0
        while s0 < len(cnt):                    # 교차점 약 200만 개씩 (메모리 상한)
            s1 = max(s0 + 1, int(np.searchsorted(cum, (cum[s0 - 1] if s0 else 0)
                                                 + 2_000_000, side="right")))
            c = cnt[s0:s1]
            if c.sum():
                e = s0 + np.repeat(np.arange(len(c)), c)
                j = j0[e] + np.arange(len(e)) - np.repeat(np.cumsum(c) - c, c)
                a, b = v[ea[e]], v[eb[e]]
                t = (self.z0 + j * hf - a[:, 2]) / (b[:, 2] - a[:, 2])
                rc = np.hypot(a[:, 0] + t * (b[:, 0] - a[:, 0]),
                              a[:, 1] + t * (b[:, 1] - a[:, 1]))
                np.maximum.at(env, np.clip(j - 1, 0, nf - 1), rc)    # 경계는 양쪽 칸에
                np.maximum.at(env, np.clip(j, 0, nf - 1), rc)
            s0 = s1
        self._slab_n, self._slab_h, self._slab_r = nf, hf, env
        self._slab_zlo = self.z0 + hf * np.arange(nf)                # 칸의 아래 끝

    def max_between(self, lo, hi):
        """높이 구간 [lo, hi] 에서의 최대 반경 (구간 밖은 가장 가까운 끝값)."""
        if hi < lo:
            lo, hi = hi, lo
        i0 = int(np.clip(np.floor((lo - self.z0) / self.h), 0, self.n - 1))
        i1 = int(np.clip(np.floor((hi - self.z0) / self.h), 0, self.n - 1))
        return float(self.rmax[i0:i1 + 1].max())

    def max_in_slab(self, lo, hi, tan_lo, tan_hi):
        """변환높이 Z′ ∈ [lo, hi] 의 층들이 **실제로 닿는** 재료의 최대 반경.

        블렌드 반경 r_b 는 이걸로 조회한다. tan_lo·tan_hi 는 그 구간 양 끝의
        tanθ (부호 있는 각도 규약 c=+1: 음수 = inward. `direction="inward"` 로
        부호 없는 각도를 쓰는 호출부는 −tanθ 를 넘긴다).

        닫힌 식 (반복 불필요): 점 (r, z) 의 변환높이는 F(Z′) = Z′ − r·T(Z′) = z 의
        해이고 F 는 순증가(가역성)다. 그래서
            Z′ ∈ [lo, hi]   ⟺   lo − r·tan_lo  ≤  z  ≤  hi − r·tan_hi
        tan_lo = tan_hi = 0 이면 실공간 z 구간 [lo, hi] 그대로다.

        모델은 '높이별 포락선 r_env(z) 까지 찬 회전체' 로 본다 — 그 높이의 반경
        0~r_env 에 재료(페리미터·인필)가 있다. 칸마다 위 부등식을 만족하는 가장 큰
        r ≤ r_env 를 구해 최댓값을 돌려준다. 재료가 안 걸리면 0.

        ⚠ 정직: 칸 높이(≈0.05mm)만큼 보수적이다 — 칸 안의 z 를 부등식마다 유리한
          끝으로 잡는다. 속이 빈 형상은 빈 반경도 재료로 센다(과대 = 안전 쪽).
          축비대칭 모델에서는 '그 높이의 최대 반경' 이 단면 전체를 대표한다.
        """
        if hi < lo:
            lo, hi, tan_lo, tan_hi = hi, lo, tan_hi, tan_lo
        # 슬랩이 걸칠 수 있는 높이 범위로 칸을 먼저 줄인다
        z_min = lo - self.global_max * max(tan_lo, 0.0)
        z_max = hi + self.global_max * max(-tan_hi, 0.0)
        i0 = int(np.clip(np.floor((z_min - self.z0) / self._slab_h) - 1, 0,
                         self._slab_n))
        i1 = int(np.clip(np.ceil((z_max - self.z0) / self._slab_h) + 1, 0,
                         self._slab_n))
        if i1 <= i0:
            return 0.0
        zl = self._slab_zlo[i0:i1]
        zu = zl + self._slab_h
        r_hi = self._slab_r[i0:i1].copy()
        r_lo = np.zeros(len(zl))
        # 아래 경계  z ≥ lo − r·tan_lo   (칸의 위 끝으로 판정)
        if tan_lo > 0.0:
            r_lo = np.maximum(r_lo, (lo - zu) / tan_lo)
        elif tan_lo < 0.0:
            r_hi = np.minimum(r_hi, (lo - zu) / tan_lo)
        else:
            r_hi = np.where(zu >= lo, r_hi, -1.0)
        # 위 경계    z ≤ hi − r·tan_hi   (칸의 아래 끝으로 판정)
        if tan_hi > 0.0:
            r_hi = np.minimum(r_hi, (hi - zl) / tan_hi)
        elif tan_hi < 0.0:
            r_lo = np.maximum(r_lo, (hi - zl) / tan_hi)
        else:
            r_hi = np.where(zl <= hi, r_hi, -1.0)
        ok = r_hi >= r_lo
        return float(r_hi[ok].max()) if ok.any() else 0.0

    def at(self, z):
        """높이 z 의 최대 반경."""
        return self.max_between(z, z)


def center_on_axis(mesh):
    """모델을 원뿔 회전축(Z축, x=y=0)에 맞춘다: XY를 바운딩박스 중심으로, 바닥을 z=0으로.

    ⚠ 꼭 필요한 이유: 원뿔 변환은 '원점 기준 반경 r=√(x²+y²)'로 기울인다
    (z' = z + c·r·tanθ). 모델이 축에서 멀리 떨어져 있으면 모델 전체의 r이 거의
    같아서, 변환이 '모든 점을 똑같이 올리는 균일 이동'에 가까워진다 → 오버행이 거의
    안 변하고 서포트가 상수처럼 나온다. 데모 구는 원점 중심이라 이 문제를 안 만나지만,
    실제 STL은 보통 축에서 벗어난 좌표에 있으므로 분석 전에 반드시 센터링해야 한다.
    (원뿔 슬라이싱은 회전축 중심으로 출력하므로 축에 맞추는 것이 물리적으로도 맞다.)
    """
    lo, hi = mesh.bounds
    cx = 0.5 * (lo[0] + hi[0])
    cy = 0.5 * (lo[1] + hi[1])
    mesh.apply_translation([-cx, -cy, -lo[2]])
    return mesh


def waist_prominence(mesh, n_samples=80, radius_profile=None):
    """'허리'의 두드러짐 (0 = 없음, 1 에 가까울수록 깊은 목).

    ⚠⚠ **이것은 '밴드가 이기는 조건' 의 판정 기준이 아니다** (2026-09-21 반증).
      이 값은 반경의 **비율**이라 반경 스케일에 눈이 먼다. 허리 깊이를 그대로 둔 채
      모델을 XY 로만 λ 배 하면 값은 0.571 로 고정인데 블렌드 폭은 `r_b ∝ λ` 로
      비싸지고, 실측하면 **같은 0.571 에서 승패가 갈린다**(승 3건·패 3건).
      판정 기준은 `analyze_blend_ratio.py` 의 **ρ = 블렌드비용/잠재이득** 을 쓸 것.
      이 함수는 '형상을 재는' 용도로는 그대로 유효하다 — 기준으로 쓰는 것이 틀렸다.

    왜 있었나: 각도 변경에 필요한 블렌드 폭이 `r_b·|Δtanθ|/(limit−1)` 로 '그 높이의
    반경'에 비례하므로, 가는 높이에서만 각도를 싸게 바꿀 수 있다. 그 직관을 구·램프
    두 모델의 일화에서 표본으로 넓히려고 '이 모델에 허리가 있나'를 재현 가능한 수로
    만든 것이다. 직관은 맞았지만 **비율만으로는 비용의 절대 크기를 못 본다.**

    정의: 내부 높이 z* 에 대해 아래쪽 최대 반경과 위쪽 최대 반경 중 **작은 쪽**을
    기준으로 얼마나 잘록한지를 재고, 그 최댓값을 취한다.

        prominence = max over interior z*  of  1 − r(z*) / min(max r below, max r above)

    위쪽 최대를 함께 보는 것이 핵심이다. 그냥 min(r)/max(r) 로 재면 위로 갈수록
    가늘어지기만 하는 형상(구·원뿔·깔때기)의 **꼭대기 테이퍼**가 허리로 잡힌다 —
    거기는 위에 아무것도 없어서 각도를 바꿔봐야 얻을 게 없는데도 그렇다.
    위쪽 최대를 기준에 넣으면 그런 단조 형상은 자동으로 0 이 된다.

    ⚠ 정직: 축대칭을 가정한 반경 프로필(`RadiusProfile`, 정점 기준 구간 최댓값)
      위에서 잰다. 축비대칭 모델(L 브래킷, 아치)에서는 '그 높이의 최대 반경'이
      단면의 실제 모양을 대표하지 못하므로 이 수치도 대표성이 떨어진다.
      블렌드 폭 공식이 같은 근사를 쓰므로 **계획기와 같은 기준**이라는 점은 맞다.

    Returns: (prominence, z_waist, r_waist). 허리가 없으면 (0.0, nan, nan).
    """
    rp = radius_profile if radius_profile is not None else RadiusProfile(mesh)
    z0, z1 = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    h = z1 - z0
    if h <= 0 or n_samples < 3:
        return 0.0, float("nan"), float("nan")
    # 양 끝 2% 는 뺀다 — 바닥/꼭대기의 한 점짜리 반경은 허리가 아니다.
    zs = np.linspace(z0 + 0.02 * h, z1 - 0.02 * h, int(n_samples))
    rs = np.array([float(rp.at(z)) for z in zs])

    # 누적 최대(아래쪽)/역누적 최대(위쪽) 로 O(n) 에 끝낸다.
    max_below = np.maximum.accumulate(rs)
    max_above = np.maximum.accumulate(rs[::-1])[::-1]

    best = (0.0, float("nan"), float("nan"))
    for i in range(1, len(zs) - 1):
        ref = min(max_below[i - 1], max_above[i + 1])
        if ref <= 1e-9:
            continue
        p = 1.0 - rs[i] / ref
        if p > best[0]:
            best = (float(p), float(zs[i]), float(rs[i]))
    return best


def load_mesh_or_demo(argv, subdivisions=4, radius=10.0):
    """명령줄 인자에 STL 경로가 있으면 로드, 없으면 데모 구를 반환한다.

    로드/생성한 메시는 항상 회전축(Z)에 센터링해서 돌려준다(center_on_axis).

    반환: (mesh, path)
      - path: 실제 STL 경로(문자열) 또는 None(데모 구를 만든 경우)
    """
    if len(argv) > 1:
        mesh = trimesh.load(argv[1], force="mesh")
        return center_on_axis(mesh), argv[1]
    mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return center_on_axis(mesh), None
