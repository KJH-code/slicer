"""
rep5x_check.py — REP5X G-code 사전 점검 (검사기 C 의 REP5X 판).

    python3 rep5x_check.py out_rep5x.gcode
    python3 rep5x_check.py out.gcode --bed-clearance 0.2 --omega-max 90

`open5x_check.py` 와 **보는 것이 다르다.** Open5x 는 슬라이서가 기계좌표를 내므로
기계 Z 음수·베드 이탈을 봤다. REP5X 는 펌웨어가 역기구학을 해서 슬라이서가
**팁 좌표 + 공구 방향(B/C)** 을 내므로, **펌웨어가 그 파일을 어떻게 받아들이는가**가
핵심이다. 파일 전체(시작/종료 G-code 포함)를 한 줄씩 따라가며 본다:

  [치명] 베드 간섭 — 기운 핫엔드 모델의 최저점이 베드 여유 아래로 내려간다
  [치명] native XY 범위 밖 — 라이브 TCP 에서 범위 밖 회전 이동은 조용히 버려진다
  [치명] 상태 — G28 뒤 B0 C0 복귀 없이 압출, B/C≠0 에서 G43.4/G49 전환, T1/T2
  [치명] 회전축 속도 상한 초과 — 펌웨어는 F 를 팁 XYZ 길이에만 적용한다
  [치명] C 가 ±360° 창 밖 (원뿔 G-code 는 C 가 누적되므로 되감기 없이는 넘는다)
  [치명] M668(SD 전처리) 줄 형식 — 이동 줄은 0열 G, 127자 이하, 주석 없음
  [치명] 노즐이 출력물을 친다 / 되감기 도중 쓸린다
  [경고] joint Z < 0, joint XY 범위 밖 — 팁 좌표 리밋으로는 안 잡힌다

근거는 docs/rep5x_machine_facts.md 다.

⚠ 이 검사를 통과해도 **첫 출력은 사람이 지켜봐야 한다.**
  · 핫엔드 모델은 공식 뷰어의 것이고 **실측 전 추정**이다. B_arm·캐리지·팬 덕트·
    Bowden 은 모델에 없다 (`--arm-radius` 로 B_arm 원기둥만 넣을 수 있다)
  · 축 부호(`INVERT_I_DIR`/`INVERT_J_DIR`, 조립 방향)를 보지 못한다.
    첫 출력 전에 `G0 B10` 을 눈으로 확인할 것
  · LB/LC, 베드 중앙 native 좌표, 소프트 엔드스톱은 `M665` `M503` `M211` 로 대조
"""

import argparse
import dataclasses

from conical import gcode as gc
from conical.rep5x import (
    REP5X,
    b_safe,
    check_head_interference,
    check_m668_format,
    check_rep5x,
    check_rewind_sweep,
    print_body,
)
from conical.toolpath import HotendProfile

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
    ap.add_argument("--lb", type=float, default=REP5X.lb,
                    help="틸트축→팁 거리 mm (M665 로 읽은 값). joint Z 판정에 쓴다")
    ap.add_argument("--bed-clearance", type=float, default=REP5X.bed_clearance,
                    help="핫엔드 몸체와 베드 사이에 요구할 여유 mm")
    ap.add_argument("--omega-max", type=float, default=REP5X.omega_max,
                    help="회전축 속도 상한 °/s")
    ap.add_argument("--bed-center", type=float, nargs=2, metavar=("X", "Y"),
                    default=list(REP5X.bed_center),
                    help="베드 중앙의 native 좌표. 시작 G-code 가 없는 파일에서 "
                         "부품 원점으로 가정한다")
    ap.add_argument("--hotend", choices=["rep5x-v3se", "generic"],
                    default="rep5x-v3se",
                    help="핫엔드 모델. rep5x-v3se=공식 뷰어 모델(실측 전 추정), "
                         "generic=예전 기본값(Ender 3 V2 계열 추정)")
    ap.add_argument("--max-step", type=float, default=30.0,
                    help="한 이동에 허용할 C 변화(도). 기본 30")
    ap.add_argument("--max-feed", type=float, default=None,
                    help="기계 최대 피드 (mm/min)")
    ap.add_argument("--no-interference", action="store_true",
                    help="노즐 간섭 검사를 건너뛴다 (O(N²) 라 느리다)")
    ap.add_argument("--stride", type=int, default=4,
                    help="간섭 검사에서 팁을 몇 개에 하나씩 볼지 (장애물은 전부 "
                         "본다). 최종 판정은 1 로 할 것")
    ap.add_argument("--arm-radius", type=float, default=None,
                    help="B_arm 반경 mm (⚠ 저장소에 치수가 없다 — 실측해서 줄 것). "
                         "주면 팁에서 LB 까지 원기둥으로 넣는다")
    args = ap.parse_args()

    prof = dataclasses.replace(
        REP5X, c_min=args.c_min, c_max=args.c_max,
        b_min=args.b_min, b_max=args.b_max, lb=args.lb,
        bed_clearance=args.bed_clearance, omega_max=args.omega_max,
        bed_center=tuple(args.bed_center),
        hotend=REP5X.hotend if args.hotend == "rep5x-v3se" else HotendProfile())
    with open(args.gcode, encoding="utf-8") as fh:
        lines = fh.readlines()
    items = gc.parse(lines)
    findings, st = check_rep5x(items, prof, max_dc_deg=args.max_step,
                               max_feed=args.max_feed)
    fmt_findings, fmt = check_m668_format(lines)
    findings += fmt_findings

    def num(v, spec, unit=""):
        return "-" if v is None else f"{format(v, spec)}{unit}"

    print("=" * 66)
    print(f"[rep5x_check] {args.gcode}")
    if st["tilt"] is None:
        tilt = "없음"
    elif abs(st["b_max"] - st["b_min"]) < 1e-6:
        tilt = f"{st['tilt']:.1f}°"
    else:
        tilt = f"{st['b_min']:.1f} ~ {st['b_max']:.1f}° (한 걸음 최대 {st['b_max_step_deg']:.1f}°)"
    print(f"  이동          : {st['moves']:,}   틸트 {prof.tilt_axis}={tilt}")
    print(f"  RTCP({prof.rtcp_on})  : "
          + ("**없음**" if not st["rtcp"] else f"켜짐 ({st['rtcp_on_count']}번)")
          + f"   상태 위반 {st['state_fatal']}건, TCP 없이 기운 채 압출 "
            f"{st['cold_extrusions']}개")
    print(f"  C 범위        : {st['c_min']:.1f} ~ {st['c_max']:.1f}°  "
          f"(창 {prof.c_min:.0f}~{prof.c_max:.0f}, "
          f"{st['c_span_turns']:.2f}회전)")
    print(f"  C 최대 한 걸음: {st['c_max_step_deg']:.1f}°")
    print(f"  회전 속도     : 최대 {st['omega_max_deg_s']:,.0f}°/s  "
          f"(상한 {prof.omega_max:g}, 초과 {st['omega_violations']:,}개)")
    box = st["native_box"]
    print(f"  native XY     : X {num(box[0], '.1f')}~{num(box[1], '.1f')}  "
          f"Y {num(box[2], '.1f')}~{num(box[3], '.1f')}  "
          f"(범위 X {prof.native_x[0]:g}~{prof.native_x[1]:g}, "
          f"Y {prof.native_y[0]:g}~{prof.native_y[1]:g}; 밖 {st['native_xy_out']:,}개"
          + (", 부품 원점 = 베드 중앙 **가정**" if st["origin_assumed"] else "")
          + ")")
    print(f"  베드 간섭     : {st['bed_hits']:,}개  "
          f"(여유선까지 최소 {num(st['bed_gap_min'], '+.2f', 'mm')}; "
          f"핫엔드 '{prof.hotend.name}', 여유 {prof.bed_clearance:g}mm, "
          f"팁 높이 0 의 B_safe {b_safe(0.0, prof.hotend, prof.bed_clearance):.1f}°)")
    print(f"  joint Z 최저  : {num(st['joint_z_min'], '.2f', 'mm')}  "
          f"(LB {prof.lb:g}; joint XY 범위 밖 {st['joint_xy_out']:,}개)")
    print(f"  M668 줄 형식  : 이동 줄 {fmt['move_lines']:,}개 중 주석 {fmt['commented']}, "
          f"들여쓰기 {fmt['indented']}, 127자 초과 {fmt['too_long']}, "
          f"G2/G3 {fmt['arcs']}")
    print(f"  되감기        : {st['rewinds']}회")

    if not args.no_interference:
        # 간섭 검사는 좌표를 부품좌표로 읽는다 → TCP 가 켜진 구간(출력 본문)만 넘긴다.
        # 시작 G-code 의 프라임 선은 native 좌표라 그대로 넣으면 엉뚱한 장애물이 된다.
        body = print_body(items, prof)
        _col, ci = check_head_interference(body, prof, prof.hotend,
                                           arm_radius=args.arm_radius,
                                           stride=args.stride)
        print(f"  노즐 간섭     : {ci['collision_pct']:.2f}%  "
              f"(팁 {ci['evaluated']:,}/{ci['samples']:,} 표본, "
              f"B_arm {'포함' if ci['arm_modeled'] else '**제외**'})")
        if ci["collision_pct"] > 0.0:
            findings.append(("치명", f"노즐이 출력물을 친다 "
                                     f"{ci['collision_pct']:.2f}% "
                                     f"(처음 z={ci['first_collision_z']})"))
        sw, ss = check_rewind_sweep(body, prof, prof.hotend,
                                    arm_radius=args.arm_radius)
        if ss["checked"]:
            print(f"  되감기 쓸림   : {ss['swept_hits']}/{ss['checked']} 자세")
        findings.extend(sw)

    if not findings:
        print("  ✓ 걸린 것 없음 (그래도 첫 출력은 지켜볼 것)")
    else:
        print(f"  걸린 것 {len(findings)}건:")
        for sev, msg in sorted(findings, key=lambda f: SEVERITY_ORDER[f[0]]):
            mark = {"치명": "✖", "경고": "⚠", "정보": "·"}[sev]
            print(f"    {mark} [{sev}] {msg}")

    print("  ⚠ 핫엔드 모델은 실측 전 추정이고 B_arm·캐리지·축 부호는 보지 못한다. "
          "첫 출력 전 `G0 B10` 을 눈으로 확인할 것.")
    return 1 if any(s == "치명" for s, _ in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
