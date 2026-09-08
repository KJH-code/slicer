"""
meshio.py — STL 파일을 읽거나, 없으면 데모용 구(sphere)를 만든다.

세 CLI 스크립트가 똑같이 반복하던 "인자로 STL 주면 로드, 아니면 데모 구" 부분을
한 곳으로 모은 것. 구(sphere)는 아랫면이 곡면 오버행이라 원뿔 슬라이싱 효과를
보기에 좋은 기본 테스트 모델이다.
"""

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
    """

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

    def max_between(self, lo, hi):
        """높이 구간 [lo, hi] 에서의 최대 반경 (구간 밖은 가장 가까운 끝값)."""
        if hi < lo:
            lo, hi = hi, lo
        i0 = int(np.clip(np.floor((lo - self.z0) / self.h), 0, self.n - 1))
        i1 = int(np.clip(np.floor((hi - self.z0) / self.h), 0, self.n - 1))
        return float(self.rmax[i0:i1 + 1].max())

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
