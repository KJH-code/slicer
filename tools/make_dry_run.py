"""make_dry_run.py — REP5X 공중 시운전(L0) G-code. **히터 없음, 압출 없음.**

    python3 tools/make_dry_run.py      # → examples/rep5x_ladder/L0_dry_run.gcode

첫 실물 출력 전에 기계 앞에서 **눈으로** 확인할 것만 담았다. 팁은 베드 위 30mm 에 둔다.
각 단계 앞의 `G4` 멈춤(초) 동안 보고, 결과를 docs/experiment_plan.md 「R. REP5X 사다리」
L0 표에 적는다.

  1. B 부호   — `B+10` 에서 헤드 몸체(히트블록 위쪽)가 +X 쪽으로 기울고 팁은 제자리
                (우리 수식: 공구축(팁→몸체) = (sinB·cosC, sinB·sinC, cosB))
  2. C 부호   — `C+90` 이 위에서 볼 때 반시계 (수학 양의 방향)
  3. RTCP     — B 0→20° 동안 **팁이 제자리**. 팁 아래에 자 끝이나 종이 표시를 두고 본다.
                팁이 옆으로 많이 움직이면 LB 값이 틀렸다 (출처마다 47.9/52.87/54.67)
  4. 회전 속도 — B20 에서 C 를 한 바퀴씩 90 → 180 → 360°/s. 헤드 흔들림·Bowden 꼬임·
                슬립링 소리를 본다. 사다리 L2·L3 은 180°/s 로 뽑았다
  5. 원뿔 레이어 흉내 — B15 로 기운 채 반경 10mm 원을 C 가 방위각을 따라가며 돈다
                (실제 출력의 둘레 경로와 같은 모양, 압출만 없다)
"""

import math
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "examples", "rep5x_ladder",
                   "L0_dry_run.gcode")
Z = 30.0                 # 팁 높이 (부품 원점 기준). 베드에서 넉넉히 띄운다
ORIGIN = (100.0, 100.0)  # 베드 중앙 native 좌표 [실기 확인] — profiles/rep5x_ender3v3se.ini 와 같게


def main():
    g = []
    a = g.append
    a("; REP5X L0 공중 시운전 — 히터 없음, 압출 없음 (tools/make_dry_run.py)")
    a("; ⚠ 첫 실행은 손을 비상정지(전원) 가까이에 둘 것")
    a("G49")
    a("G21")
    a("G90")
    a("M82")
    a("G28 X")
    a("G28")
    a("; B 홈은 -135 도 — 먼저 0 으로")
    a("G0 C0 B0 F3000")
    a("M211 S1")
    a(f"G1 Z{Z + 10:.1f} F3000")
    a(f"G0 X{ORIGIN[0]:.1f} Y{ORIGIN[1]:.1f} F2400")
    a("G92 X0 Y0 C0 B0")
    a("G43.4")
    a(f"G1 X0 Y0 Z{Z:.1f} F1200")
    a("G4 S3")
    a("; --- 1. B 부호: B+10 에서 몸체가 +X 쪽으로, 팁은 제자리")
    a("G1 B10 F600")
    a("G4 S5")
    a("G1 B0 F600")
    a("G4 S2")
    a("; --- 2. C 부호: C+90 이 위에서 볼 때 반시계")
    a("G1 C90 F1800")
    a("G4 S5")
    a("G1 C0 F1800")
    a("G4 S2")
    a("; --- 3. RTCP: B 0 -> 20 동안 팁이 제자리여야 한다")
    a("G1 B20 F300")
    a("G4 S5")
    a("G1 B0 F300")
    a("G4 S2")
    a("G1 B20 F600")
    a("G4 S2")
    a("; --- 4. 회전 속도: B20 에서 C 한 바퀴씩 90 / 180 / 360 deg/s (회전만 하는 이동: F 는 도/분)")
    for w in (90, 180, 360):
        a(f"; C {w} deg/s")
        a(f"G1 C360 F{w * 60}")
        a("G4 S2")
        a(f"G1 C0 F{w * 60}")
        a("G4 S3")
    a("G1 B0 F600")
    a("G4 S2")
    a("; --- 5. 원뿔 레이어 흉내: B15, 반경 10mm 원, C 가 방위각을 따라간다 (F 30mm/s)")
    r, n = 10.0, 72
    a(f"G1 X{-r:.3f} Y0.000 Z{Z:.3f} F1200")
    a("G1 B15 C-180 F600")
    a("G4 S2")
    for i in range(1, n + 1):
        phi = -180.0 + 360.0 * i / n
        x = r * math.cos(math.radians(phi))
        y = r * math.sin(math.radians(phi))
        a(f"G1 X{x:.3f} Y{y:.3f} Z{Z:.3f} B15.000 C{phi:.3f} F1800")
    a("G4 S2")
    a("; 같은 원을 반대로 (실제 출력은 링을 번갈아 돈다)")
    for i in range(n - 1, -1, -1):
        phi = -180.0 + 360.0 * i / n
        x = r * math.cos(math.radians(phi))
        y = r * math.sin(math.radians(phi))
        a(f"G1 X{x:.3f} Y{y:.3f} Z{Z:.3f} B15.000 C{phi:.3f} F1800")
    a("G4 S2")
    a("; --- 끝: B0 C0 에서 TCP 끄고 Z 호밍")
    a(f"G1 X0 Y0 Z{Z:.1f} F1200")
    a("G0 B0 C0 F1800")
    a("G49")
    a("G28 Z")
    a("M84 X Y E C B")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(g) + "\n")
    print(OUT, len(g), "줄")


if __name__ == "__main__":
    main()
