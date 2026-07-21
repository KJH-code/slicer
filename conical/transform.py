"""
transform.py — 원뿔(conical) 좌표 변환식. 이 연구의 기하학적 핵심 한 줄.

RotBot 실제 코드(Transformation_STL_var_angle.py)의 변환식을 그대로 사용한다.
    f(x, y, z) = ( x/cosθ,  y/cosθ,  z + c·√(x²+y²)·tanθ )
    c = +1 (outward 원뿔) / -1 (inward 원뿔)

즉 평평한 레이어를 원뿔 모양으로 '기울여' 쌓는 효과를, 모델 좌표를 미리
왜곡시키는 방식으로 흉내 낸다. (선행연구: RotBot/ZHAW, slicer4rtn)
"""

import numpy as np


def transform_cone(vertices, cone_angle_deg, cone_type):
    """정점 배열(N,3)에 원뿔 변환을 적용해 '새 정점 배열(N,3)'을 돌려준다.

    입력 vertices 는 건드리지 않는다(원본 보존).
    """
    th = np.radians(cone_angle_deg)
    c = 1 if cone_type == "outward" else -1
    x, y, z = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    r = np.sqrt(x**2 + y**2)
    xt = x / np.cos(th)
    yt = y / np.cos(th)
    zt = z + c * r * np.tan(th)
    return np.column_stack([xt, yt, zt])
