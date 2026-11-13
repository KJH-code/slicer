"""fibr3d_crosscheck.py — 우리 REP5X G-code 를 **팀 가상 프린터(FIBR3DEmul-Rep5x)의
역기구학·축 한계**로 따로 검증한다 (독립 구현 대조).

    python3 tools/fibr3d_crosscheck.py out.gcode --emu ../FIBR3DEmul-Rep5x [--lb 54.67]

가상 프린터의 CLI(`rep5x_runtime.cli`)는 G28·M 코드를 못 읽고 원점 이동(G92)도 모른다.
그래서 여기서 **파일 전체를 모달로 따라가며**(G28 홈 자세, G92 오프셋, G43.4/G49)
native 좌표를 만들고, IK 와 축 한계 판정만 가상 프린터의 코드(`Rep5xKinematics`,
`MachineProfile`)에 맡긴다. 묻는 것은 한 가지다 — "펌웨어 규약대로 실행하면 축이
한계 안에 있나".

판정:
  · 팁 XY 가 native 범위 밖 (TCP 켜짐)  → 치명 (펌웨어가 회전 이동을 조용히 버린다)
  · joint X/Y/B 한계 밖                → 치명
  · C 가 ±360° 밖                      → 치명 (펌웨어 소프트 엔드스톱)
  · joint Z < 0                        → 경고 (라이브 TCP 는 리밋을 팁에 건다.
                                          갠트리가 실제로 내려가는지는 실기 확인)
  · TCP 전환 시 B·C ≠ 0                → 치명
G28 뒤 홈 자세는 Rep5x-Marlin 예제 설정값이다: X200 Y−40 Z174.6 C0 B−135.
"""

import argparse
import math
import re
import sys

WORD = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))")
HOME = {"X": 200.0, "Y": -40.0, "Z": 174.6, "C": 0.0, "B": -135.0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("gcode")
    ap.add_argument("--emu", default="../FIBR3DEmul-Rep5x", help="FIBR3DEmul-Rep5x 체크아웃 경로")
    ap.add_argument("--lb", type=float, default=54.67)
    ap.add_argument("--lc", type=float, default=1.6)
    a = ap.parse_args(argv)
    sys.path.insert(0, a.emu)
    from rep5x_runtime.kinematics import Rep5xKinematics
    from rep5x_runtime.model import ToolPose
    from rep5x_runtime.profile import MachineProfile, ProfileError

    prof = MachineProfile.load(f"{a.emu}/config/rep5x_ender3_v3_se.json")
    kin = Rep5xKinematics(a.lc, a.lb)
    ax = prof.axes

    native = dict(HOME)            # 펌웨어 native 위치 (TCP 켜지면 팁, 꺼지면 joint)
    off = {k: 0.0 for k in "XYZCB"}  # 논리 = native − off
    tcp = False
    homed = False
    fatal, warn = [], []
    zmin = math.inf
    n = 0
    for ln, raw in enumerate(open(a.gcode, encoding="utf-8"), 1):
        code = raw.split(";", 1)[0].strip()
        if not code:
            continue
        w = {k.upper(): float(v) for k, v in WORD.findall(code)}
        head = code.split()[0].upper()
        if head == "G28":
            native = dict(HOME)
            off = {k: 0.0 for k in "XYZCB"}
            homed = True
            continue
        if head == "G43.4" or head == "G49":
            b, c = native["B"], native["C"]
            # 호밍 전 자세는 모른다 — 부팅 직후의 G49 는 '끄기 선언'일 뿐이라 판정하지 않는다
            if homed and abs(b) > 1e-6 or abs(c % 360.0) > 1e-6 and abs(c % 360.0 - 360) > 1e-6:
                fatal.append(f"{ln}: {head} at B={b:g} C={c:g} (B0 C0 에서만 전환)")
            tcp = head == "G43.4"
            continue
        if head == "G92":
            for k in "XYZCB":
                if k in w:
                    off[k] = native[k] - w[k]
            continue
        if head not in ("G0", "G1"):
            continue
        if not homed:
            fatal.append(f"{ln}: 호밍 전 이동")
            continue
        for k in "XYZCB":
            if k in w:
                native[k] = w[k] + off[k]
        n += 1
        if tcp:
            if not (ax["X"].soft_min <= native["X"] <= ax["X"].soft_max
                    and ax["Y"].soft_min <= native["Y"] <= ax["Y"].soft_max):
                fatal.append(f"{ln}: 팁 XY native ({native['X']:.2f},{native['Y']:.2f}) 범위 밖")
            j = kin.inverse(ToolPose(native["X"], native["Y"], native["Z"],
                                     native["C"], native["B"]))
            jx, jy, jz, jb, jc = j.x_mm, j.y_mm, j.z_mm, j.b_deg, j.c_deg
        else:
            jx, jy, jz, jb, jc = (native[k] for k in "XYZBC")
        for name, v in (("X", jx), ("Y", jy), ("B", jb)):
            try:
                ax[name].check(v, line=ln)
            except ProfileError as e:
                fatal.append(str(e))
        if not -360.0 - 1e-9 <= jc <= 360.0 + 1e-9:
            fatal.append(f"{ln}: C={jc:g} 이 ±360° 밖")
        zmin = min(zmin, jz)
        if jz < 0:
            warn.append(ln)
    print(f"moves={n}  fatal={len(fatal)}  jointZ<0={len(warn)} (min {zmin:.2f}mm)")
    for f in fatal[:15]:
        print("  FATAL", f)
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
