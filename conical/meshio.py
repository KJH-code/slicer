"""
meshio.py — STL 파일을 읽거나, 없으면 데모용 구(sphere)를 만든다.

세 CLI 스크립트가 똑같이 반복하던 "인자로 STL 주면 로드, 아니면 데모 구" 부분을
한 곳으로 모은 것. 구(sphere)는 아랫면이 곡면 오버행이라 원뿔 슬라이싱 효과를
보기에 좋은 기본 테스트 모델이다.
"""

import trimesh


def load_mesh_or_demo(argv, subdivisions=4, radius=10.0):
    """명령줄 인자에 STL 경로가 있으면 로드, 없으면 데모 구를 반환한다.

    반환: (mesh, path)
      - path: 실제 STL 경로(문자열) 또는 None(데모 구를 만든 경우)
    """
    if len(argv) > 1:
        mesh = trimesh.load(argv[1], force="mesh")
        return mesh, argv[1]
    mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return mesh, None
