"""make_ladder_models.py — REP5X 시험 출력 사다리용 작은 축대칭 STL 을 만든다.

    python3 tools/make_ladder_models.py      # → examples/rep5x_ladder/*.stl

모두 10~20분 출력을 노린 크기다 (지름 ≤ 34mm, 높이 ≤ 15mm).

- L1 cylinder.stl : 원기둥 r=10, h=8. B=0 으로 뽑아 RTCP 켠 평면 출력이 3축과 같은지
- L2 flare.stl    : 위로 벌어지는 원뿔대. 아래 r=5, 높이 6, 벽이 수직에서 60° 기운다.
                    층고 0.3 에서 층마다 0.52mm 바깥으로 나가 비드 폭(0.45)을 넘는다 → 평면이면
                    받침 없음, 원뿔 15° 면 층 법선 기준 45°(0.30mm)라 받쳐진다.
                    ⚠ 처음 쓴 50° 는 평면에서도 0.36mm 라 툴패스 검사기 기준 오버행이 0 이었다
- L5 overhang_steps.stl : 오버행 각도 사다리. 단 높이 2.5mm × 6단, 단마다 r=5 에서 시작해
                    벽이 수직에서 40·45·50·55·60·65° 로 벌어지고, 윗면(수평)으로 r=5 에 돌아온다.
                    평면(B=0)으로 뽑아 **이 기계의 오버행 한계**(gap_audit J5·J7)를 잰다
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
    h, r0 = 6.0, 5.0
    r1 = r0 + h * np.tan(np.radians(60.0))
    flare = revolve([(0, 0), (r0, 0), (r1, h), (0, h)])
    prof = [(0.0, 0.0), (5.0, 0.0)]
    z = 0.0
    for a in (40, 45, 50, 55, 60, 65):
        prof.append((5.0 + 2.5 * np.tan(np.radians(a)), z + 2.5))
        z += 2.5
        prof.append((5.0, z))
    prof[-1] = (0.0, z)                      # 맨 윗면은 축까지 닫는다
    steps = revolve(prof)
    lamp = trimesh.load(os.path.join(os.path.dirname(__file__), "..", "examples", "lamp.stl"))
    lamp.apply_scale(0.6)
    lamp.apply_translation([0.0, 0.0, -lamp.bounds[0][2]])
    for name, m in (("cylinder", cyl), ("flare", flare), ("lamp_small", lamp),
                    ("overhang_steps", steps)):
        assert m.is_watertight, name
        if m.volume < 0:
            m.invert()
        path = os.path.join(OUT, f"{name}.stl")
        m.export(path)
        print(f"{path}  bounds={m.bounds.round(2).tolist()}  vol={m.volume:.0f}mm³")


if __name__ == "__main__":
    main()
