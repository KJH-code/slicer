"""make_ladder_models.py — REP5X 시험 출력 사다리용 작은 축대칭 STL 을 만든다.

    python3 tools/make_ladder_models.py      # → examples/rep5x_ladder/*.stl

모두 10~20분 출력을 노린 크기다 (지름 ≤ 34mm, 높이 ≤ 15mm).

- L1 cylinder.stl : 원기둥 r=10, h=8. B=0 으로 뽑아 RTCP 켠 평면 출력이 3축과 같은지
- L2 flare.stl    : 위로 벌어지는 원뿔대. 아래 r=5, 높이 7, 벽이 수직에서 50° 기운다
                    (수평에서 40°) → 평면이면 45° 규칙에 걸리는 오버행, 원뿔 15° 면 걸리지 않는다
- L3 lamp_small.stl : examples/lamp.stl 을 0.6배 (지름 9.6, 높이 18). 실험 A 축소판 —
                    원본은 회전 상한을 지키면 1시간이 넘는다
"""

import os

import numpy as np
import trimesh

OUT = os.path.join(os.path.dirname(__file__), "..", "examples", "rep5x_ladder")


def revolve(profile_rz, sections=96):
    """(r, z) 폴리라인(아래→위, 양 끝은 축 위 r=0) 을 Z축 둘레로 돌린 닫힌 메시."""
    pts = np.asarray(profile_rz, dtype=float)
    return trimesh.creation.revolve(pts, sections=sections)


def main():
    os.makedirs(OUT, exist_ok=True)
    cyl = revolve([(0, 0), (10, 0), (10, 8), (0, 8)])
    h, r0 = 7.0, 5.0
    r1 = r0 + h * np.tan(np.radians(50.0))
    flare = revolve([(0, 0), (r0, 0), (r1, h), (0, h)])
    lamp = trimesh.load(os.path.join(os.path.dirname(__file__), "..", "examples", "lamp.stl"))
    lamp.apply_scale(0.6)
    lamp.apply_translation([0.0, 0.0, -lamp.bounds[0][2]])
    for name, m in (("cylinder", cyl), ("flare", flare), ("lamp_small", lamp)):
        assert m.is_watertight, name
        if m.volume < 0:
            m.invert()
        path = os.path.join(OUT, f"{name}.stl")
        m.export(path)
        print(f"{path}  bounds={m.bounds.round(2).tolist()}  vol={m.volume:.0f}mm³")


if __name__ == "__main__":
    main()
