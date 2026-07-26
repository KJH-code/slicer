"""
conical_slice.py — 형상 적응형 원뿔 슬라이싱 파이프라인 (분석 → 실제 G-code).

RotBot 의 검증된 3단계 구조에 우리 '자동 각도 결정'을 앞단으로 붙인 것:

    [1] 분석/결정 : STL 오버행 분석 → 최적 (방향, 각도) 자동 선택  (우리 기여)
    [2] 정변환    : 메시를 원뿔 변환 (+ 사전 세분화)               (RotBot 차용)
    [3] 평면 슬라이싱 :
          · 기본: 내장 미니 슬라이서 (외부 의존 없음, 연구용)
          · 옵션: --slicer-cmd 로 외부 슬라이서 CLI 를 꽂음
                  (예: "prusa-slicer -g -o {gcode} {stl}")
    [4] 역변환    : 적응 현 분할 L=2√(2rε) 로 실공간 G-code 생성   (우리 개선)

사용:
    python3 conical_slice.py model.stl                      # 각도 자동
    python3 conical_slice.py model.stl --angle 30 --direction outward
    python3 conical_slice.py model.stl --layer-height 0.2 --chord-tol 0.05
    python3 conical_slice.py model.stl --slicer-cmd "prusa-slicer -g -o {gcode} {stl}"

출력: <입력이름>_conical.gcode  (+ 요약 리포트 stdout)
⚠ 슬라이서 자동 서포트는 끄고 쓸 것 — 변환공간의 45° 판정은 물리와 다르다
   (docs/warped_threshold_finding.md). 서포트 필요 여부는 [1]의 해석식이 판단.
"""

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh

from conical import analytic
from conical.meshio import center_on_axis
from conical.transform import transform_cone, transform_cone_profile
from conical.planar_slicer import slice_mesh
from conical.backtransform import backtransform
from conical import gcode as gc
from conical.selector import select_cone
from conical.profile import AngleProfile
from conical.varangle import select_banded
from conical.config import THRESHOLD_DEG, MAX_ANGLE_DEG, ANGLE_STEP, DEFAULT_K


def auto_select(mesh, k=DEFAULT_K):
    """평가함수 J = (서포트 감소) − k×각도 로 (방향, 각도) 자동 선택.

    이전에는 k 없이 순수 서포트 최소화였는데, 그건 프로젝트 핵심 통찰인
    '최소화의 함정'(항상 최대각 선택)과 모순이라 selector 의 J 로 교체.
    (selector 는 판정 통일로 해석식을 쓴다.)
    """
    best, _ = select_cone(mesh, k, verbose=False)
    return best["support"], best["angle"], best["direction"], best["J"]


def refine(mesh, max_edge):
    """정변환 전 세분화: 긴 변을 쪼개야 '변환 후 평면 슬라이스'가 원뿔면을 잘 근사."""
    v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces,
                                            max_edge=max_edge)
    return trimesh.Trimesh(vertices=v, faces=f, process=False)


def run_external_slicer(cmd_template, warped_mesh, workdir):
    stl_path = Path(workdir) / "warped.stl"
    gcode_path = Path(workdir) / "warped.gcode"
    warped_mesh.export(stl_path)
    cmd = cmd_template.format(stl=stl_path, gcode=gcode_path)
    subprocess.run(cmd, shell=True, check=True)
    with open(gcode_path) as fh:
        return gc.parse(fh.readlines())


def main():
    ap = argparse.ArgumentParser(description="adaptive conical slicing pipeline")
    ap.add_argument("stl")
    ap.add_argument("--angle", type=float, default=None, help="원뿔 각도(도). 생략=자동")
    ap.add_argument("--direction", choices=["outward", "inward"], default=None)
    ap.add_argument("--profile", default=None,
                    help='가변각 θ(Z′) 수동 지정 "Z1:deg1,Z2:deg2,..." '
                         '(예 "0:15,10:15,14:35,30:35"; 음수=inward)')
    ap.add_argument("--auto-bands", type=int, default=None,
                    help="밴드 N개 자동 탐색(select_banded) → 가변각 프로필")
    ap.add_argument("--layer-height", type=float, default=0.3)
    ap.add_argument("--perimeters", type=int, default=2)
    ap.add_argument("--infill-spacing", type=float, default=2.5,
                    help="인필 간격 mm (0=인필 없음)")
    ap.add_argument("--chord-tol", type=float, default=0.05,
                    help="역변환 허용 현 오차 ε (mm)")
    ap.add_argument("--max-edge", type=float, default=1.5,
                    help="정변환 전 최대 변 길이 (세분화)")
    ap.add_argument("--slicer-cmd", default=None,
                    help='외부 슬라이서 CLI 템플릿. 예 "prusa-slicer -g -o {gcode} {stl}"')
    ap.add_argument("--k", type=float, default=DEFAULT_K,
                    help=f"J의 각도 비용 가중치 (기본 {DEFAULT_K}; analyze_k 참조)")
    ap.add_argument("--mode", choices=["xyz", "open5x"], default="xyz",
                    help="xyz=3축(작은 각도) / open5x=베드 틸트+회전 기계좌표 [실험적]")
    ap.add_argument("--machine", choices=["prusa-uv", "voron-bc"], default="prusa-uv")
    ap.add_argument("--pivot-depth", type=float, default=50.0,
                    help="베드면→틸트축 거리 mm (Open5x 스탠드오프별, 실기 보정)")
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()

    mesh = trimesh.load(args.stl, force="mesh")
    mesh = center_on_axis(mesh)
    base = analytic.support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)

    # [1] 각도 결정 (고정각 / 가변각 프로필)
    profile = None
    banded_info = None
    if args.profile is not None or args.auto_bands is not None:
        if args.angle is not None:
            raise SystemExit("--angle 과 --profile/--auto-bands 는 동시 사용 불가")
        if args.mode == "open5x":
            raise SystemExit("가변각 + open5x 는 향후 과제 (틸트 U가 상수라는 "
                             "가정이 깨짐) — xyz 모드만 지원")
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        if args.profile is not None:
            profile = AngleProfile.parse(args.profile)
            if (args.direction or "outward") == "inward":
                profile = AngleProfile(list(zip(profile.zs, -profile.thetas_deg)))
            why = "수동 프로필"
        else:
            banded_info = select_banded(mesh, args.k, args.auto_bands)
            profile = AngleProfile.from_banded_result(banded_info, r_max)
            why = f"--auto-bands {args.auto_bands} (J, k={args.k})"
        profile.validate(r_max, "outward")
        direction = "outward"          # 부호 있는 각도 규약 (음수=inward)
        angle = None
        after = analytic.support_fraction_profile(mesh, profile, THRESHOLD_DEG)
    elif args.angle is not None:
        direction = args.direction or "outward"
        angle = args.angle
        after = analytic.support_fraction(mesh, angle, direction, THRESHOLD_DEG)
        why = "사용자 지정"
    else:
        after, angle, direction, j_score = auto_select(mesh, args.k)
        why = f"J 기준, k={args.k} (J={j_score:.2f})"

    print("=" * 62)
    print(f"[conical_slice] {args.stl}")
    if profile is not None:
        print(f"  각도 결정   : 가변각 프로필 ({why}, 가역성 검증 통과)")
        print(profile.describe())
        if banded_info is not None:
            print(f"  밴드 서포트 추정: {banded_info['support_pct']:.1f}% "
                  f"(select_banded, 이상적 추정)")
    else:
        print(f"  각도 결정   : {direction} {angle:.0f}°  ({why})")
    print(f"  서포트 예측 : {base:.1f}% (평면) → {after:.1f}% "
          f"({'프로필' if profile is not None else '선택 각도'}"
          f"{', 축상 근사' if profile is not None else ''})")

    # [2] 세분화 + 정변환
    fine = refine(mesh, args.max_edge)
    if profile is not None:
        warped = trimesh.Trimesh(
            vertices=transform_cone_profile(fine.vertices, profile, "outward"),
            faces=fine.faces, process=False)
    elif angle > 0:
        warped = trimesh.Trimesh(
            vertices=transform_cone(fine.vertices, angle, direction),
            faces=fine.faces, process=False)
    else:
        warped = fine
    print(f"  메시        : {len(mesh.faces):,} → 세분화 {len(fine.faces):,} 면")

    # [3] 평면 슬라이싱 (변환공간)
    if args.slicer_cmd:
        with tempfile.TemporaryDirectory() as td:
            items = run_external_slicer(args.slicer_cmd, warped, td)
        print(f"  슬라이서    : 외부 CLI ({args.slicer_cmd.split()[0]})")
    else:
        items = slice_mesh(warped, layer_height=args.layer_height,
                           perimeters=args.perimeters,
                           infill_spacing=args.infill_spacing)
        print(f"  슬라이서    : 내장 (layer {args.layer_height}mm, "
              f"perim {args.perimeters}, infill {args.infill_spacing}mm)")

    n_moves_planar = sum(1 for k, _ in items if k == "move")

    # [4] 역변환 (적응 현 분할; 프로필이면 점별 θ(Zw) + 블렌드 분할 2배)
    real_items, stats = backtransform(items, profile if profile is not None else angle,
                                      direction, chord_tol=args.chord_tol)
    print(f"  역변환      : 이동 {stats['moves_in']:,} → {stats['moves_out']:,} "
          f"(확장 {stats['expansion']:.2f}배, ε={args.chord_tol}mm 적응 분할)")

    # [5] 출력 모드
    if args.mode == "open5x":
        from conical.open5x import to_open5x, PRUSA_UV, VORON_BC
        prof = PRUSA_UV if args.machine == "prusa-uv" else VORON_BC
        prof.pivot_depth = args.pivot_depth
        real_items, o5 = to_open5x(real_items, angle, direction, prof)
        print(f"  Open5x      : 틸트 {prof.tilt_axis}={angle:.0f}° 고정, "
              f"{prof.rot_axis} {o5['v_turns']:.1f}회전 누적 "
              f"(pivot {args.pivot_depth}mm) [실험적 — 부호·피벗 실기보정 필요]")
    out_path = args.output or (Path(args.stl).stem +
                               ("_open5x.gcode" if args.mode == "open5x"
                                else "_conical.gcode"))
    # 뷰어/후처리 도구가 읽는 메타데이터 (tools/slicing_simulator.html 등)
    if profile is not None:
        prof_txt = ",".join(f"{z:g}:{t:g}"
                            for z, t in zip(profile.zs, profile.thetas_deg))
        meta = [("raw", f"; conical: profile={prof_txt} direction=outward "
                        f"mode={args.mode} chord_tol={args.chord_tol}")]
    else:
        meta = [("raw", f"; conical: angle={angle:.1f} direction={direction} "
                        f"mode={args.mode} chord_tol={args.chord_tol}")]
    gc.write(meta + real_items, out_path)
    print(f"  출력        : {out_path}")
    print(f"  검증        : python3 toolpath_check.py {out_path}")
    if args.mode == "xyz":
        print("  ⚠ 3축 프린터는 작은 각도만 안전 (노즐-출력물 간섭). "
              "큰 각도는 틸트 하드웨어 필요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
