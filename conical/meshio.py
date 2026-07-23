"""
meshio.py — STL 파일을 읽거나, 없으면 데모용 구(sphere)를 만든다.

세 CLI 스크립트가 똑같이 반복하던 "인자로 STL 주면 로드, 아니면 데모 구" 부분을
한 곳으로 모은 것. 구(sphere)는 아랫면이 곡면 오버행이라 원뿔 슬라이싱 효과를
보기에 좋은 기본 테스트 모델이다.
"""

import trimesh


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
