"""역변환이 순수 E 이동(리트랙트/프라임)을 보존하는지 검증.

수정 전 버그: XYZ 변화 없는 `G1 E.. F..`는 warp_len≈0 → scale=0 으로
ΔE가 0이 되어 리트랙션이 전부 사라졌다 (E가 5에서 안 내려감).

⚠ 2026-11-10 기대값 변경 (docs/gap_audit.md G2 — 압출 배율과 E 회계 수정):
  이 테스트의 퇴적 이동 둘은 **반경 방향**(Y=0 에서 X 만 증가)이다. 예전 보정
  '실길이/변환길이' 는 반경 방향에서 정확히 1 이라, 입력 E(5, 3, 5, 10)가 출력에
  그대로 나왔다 — 그래서 `es[-1] == 10.0` 이 '보정이 걸리는지' 와 무관하게 통과했다.
  지금 배율은 체적 야코비안 cos²θ·m 이다 (30°·상수각 → 0.75, 방향 무관).
  **리트랙트·프라임의 ΔE(−2, +2)는 그대로**이고 퇴적 ΔE 만 0.75 배가 된다.
  검증하려는 성질(리트랙션 보존)은 같고, 숫자만 아래처럼 바뀐다.

    python3 tests/test_backtransform_retraction.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.backtransform import backtransform
from conical.gcode import parse


def test_retraction_preserved():
    g = """G1 X10 Y0 Z1 E0
G1 X20 Y0 Z1 E5
G1 E3 F2400
G1 X30 Y0 Z1 F6000
G1 E5 F2400
G1 X40 Y0 Z1 E10
""".splitlines()
    out, _ = backtransform(parse(g), 30, "outward")
    es = [p.e for k, p in out if k == "move" and p.e is not None]
    k = math.cos(math.radians(30.0)) ** 2            # 체적 야코비안 (30° 상수각) = 0.75
    # 예전 기대: E=5 도달 → 3 까지 하강 → 10 으로 종료.
    # 지금    : 첫 퇴적 +5 가 ×k → 3.75 도달  (변경: 5.0 → 5·k)
    #           리트랙트 −2 는 그대로 → 1.75   (변경: 3.0 → 5·k − 2. 하강 폭 2 는 동일)
    #           프라임 +2 는 그대로 → 3.75
    #           둘째 퇴적 +5 가 ×k → 7.5 로 종료 (변경: 10.0 → 10·k)
    peak = next(i for i, e in enumerate(es) if abs(e - 5.0 * k) < 1e-9)
    assert abs(min(es[peak:]) - (5.0 * k - 2.0)) < 1e-9, es
    assert abs(es[-1] - 10.0 * k) < 1e-9, es
    # 리트랙트·프라임 직후 값까지 못 박는다 — 하강·복귀 폭이 정확히 2 (배율 없음)
    assert abs(es[peak + 1] - (es[peak] - 2.0)) < 1e-9, es
    assert abs(es[peak + 2] - es[peak]) < 1e-9, es


if __name__ == "__main__":
    test_retraction_preserved()
    print("PASS: 리트랙션 보존 (퇴적 E 는 ×cos²30°, 리트랙트·프라임 ±2 는 그대로)")
