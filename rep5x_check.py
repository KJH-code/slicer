"""
rep5x_check.py — REP5X G-code 사전 점검 (검사기 C 의 REP5X 판).

    python3 rep5x_check.py out_rep5x.gcode
    python3 rep5x_check.py out.gcode --c-min -360 --c-max 360 --max-feed 12000

`open5x_check.py` 와 **보는 것이 다르다.** Open5x 는 슬라이서가 기계좌표를 내므로
기계 Z 음수·베드 이탈을 봤다. REP5X 는 펌웨어가 역기구학을 해서 슬라이서가
**부품좌표 + 공구 방향(B/C)** 을 내므로, 대신 **펌웨어 소프트 엔드스톱**이 핵심이다.

가장 중요한 것: **C 가 ±360° 창 안인가.** "Continuous yaw rotation" 은 슬립링이
푸는 기계적 제약이지 소프트웨어 한계가 아니다 — `Configuration.h` 의
`I_MIN_POS/I_MAX_POS` 가 ±360 이고 `MIN/MAX_SOFTWARE_ENDSTOP_I` 가 켜져 있다.
원뿔 G-code 는 C 가 계속 누적되므로(funnel 20° 에서 44.5회전) 되감기 없이 걸면
**소프트 엔드스톱에 걸려 멈춘다.**

⚠ 이 검사를 통과해도 **첫 출력은 사람이 지켜봐야 한다.** 특히 **노즐 몸체·B_arm 과
  출력물의 간섭을 보지 못한다** — 헤드 회전식에서는 베드 틸트식에서 성립하던
  '간섭이 정의상 불가능' 논증이 **성립하지 않는다**(`docs/platform_comparison.md`).
⚠ 축 부호(`INVERT_I_DIR`/`INVERT_J_DIR`, 조립 방향)도 보지 못한다.
  첫 출력 전에 `G0 B10` 을 눈으로 확인할 것.
"""

import argparse

from conical import gcode as gc
from conical.rep5x import REP5X, Rep5xProfile, check_rep5x

SEVERITY_ORDER = {"치명": 0, "경고": 1, "정보": 2}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("gcode")
    ap.add_argument("--c-min", type=float, default=REP5X.c_min,
                    help="C 소프트 엔드스톱 하한 (Configuration.h I_MIN_POS)")
    ap.add_argument("--c-max", type=float, default=REP5X.c_max,
                    help="C 소프트 엔드스톱 상한 (I_MAX_POS)")
    ap.add_argument("--b-min", type=float, default=REP5X.b_min)
    ap.add_argument("--b-max", type=float, default=REP5X.b_max)
    ap.add_argument("--printable-radius", type=float,
                    default=REP5X.printable_radius)
    ap.add_argument("--max-step", type=float, default=30.0,
                    help="한 이동에 허용할 C 변화(도). 기본 30")
    ap.add_argument("--max-feed", type=float, default=None,
                    help="기계 최대 피드 (mm/min)")
    args = ap.parse_args()

    prof = Rep5xProfile(c_min=args.c_min, c_max=args.c_max,
                        b_min=args.b_min, b_max=args.b_max,
                        printable_radius=args.printable_radius)
    items = gc.parse(open(args.gcode).readlines())
    findings, st = check_rep5x(items, prof, max_dc_deg=args.max_step,
                               max_feed=args.max_feed)

    print("=" * 66)
    print(f"[rep5x_check] {args.gcode}")
    tilt = "없음" if st["tilt"] is None else f"{st['tilt']:.1f}°"
    print(f"  이동          : {st['moves']:,}   틸트 {prof.tilt_axis}={tilt}")
    print(f"  RTCP({prof.rtcp_on})  : {'켜짐' if st['rtcp'] else '**없음**'}  "
          f"(꺼져 있으면 X/Y/Z 가 노즐 팁이 아니다)")
    print(f"  C 범위        : {st['c_min']:.1f} ~ {st['c_max']:.1f}°  "
          f"(창 {prof.c_min:.0f}~{prof.c_max:.0f}, "
          f"{st['c_span_turns']:.2f}회전)")
    print(f"  C 최대 한 걸음: {st['c_max_step_deg']:.1f}°")
    print(f"  부품 최대 반경: {st['radius_max']:.1f}mm  "
          f"(PRINTABLE_RADIUS {prof.printable_radius:.0f})")
    print(f"  되감기        : {st['rewinds']}회")

    if not findings:
        print("  ✓ 걸린 것 없음 (그래도 첫 출력은 지켜볼 것)")
    else:
        print(f"  걸린 것 {len(findings)}건:")
        for sev, msg in sorted(findings, key=lambda f: SEVERITY_ORDER[f[0]]):
            mark = {"치명": "✖", "경고": "⚠", "정보": "·"}[sev]
            print(f"    {mark} [{sev}] {msg}")

    print("  ⚠ 노즐 몸체·B_arm 간섭과 축 부호는 보지 못한다. "
          "첫 출력 전 `G0 B10` 을 눈으로 확인할 것.")
    return 1 if any(s == "치명" for s, _ in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
