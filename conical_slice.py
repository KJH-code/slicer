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
import dataclasses
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh

from conical import analytic
from conical import gcode as gc
from conical.backtransform import backtransform
from conical.config import (
    BLEND_COST_K,
    BLEND_SHIFT_RATIO,
    DEFAULT_K,
    MAX_SPACING_FACTOR,
    THRESHOLD_DEG,
)
from conical.machine import MachineProfile, check_start_extrusion
from conical.meshio import RadiusProfile, center_on_axis
from conical.planar_slicer import BRIM_TYPE, FAN_AFTER_LAYERS, layer_times, slice_mesh
from conical.profile import AngleProfile
from conical.selector import select_cone
from conical.transform import transform_cone, transform_cone_profile
from conical.varangle import select_banded, select_banded_j


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


# 브림 팁이 층고의 이 배수보다 높으면 '베드에서 떴다' 로 본다. 판단값이다 — 폭 0.45
# 비드가 베드에 눌려 붙으려면 팁이 노즐 지름(0.4) 안팎보다 높으면 안 된다는 어림.
BRIM_MAX_LIFT = 1.5


def brim_problem(items, cone_angle_deg, cone_type, layer_height, chord_tol=0.05,
                 ring_k=None, mach=None):
    """내장 슬라이서가 낸 브림을 **역변환해서** 실공간 높이를 본다 → (사유 또는 None, 정보).

    왜 필요한가 — 브림은 변환공간의 층 0(평면)에 놓이지만 그 평면은 실공간에서

        z = Z′₀ − c·r·tanθ          (transform.py 의 역, r = 실공간 반경)

    인 **원뿔면**이다. outward(c=+1)는 축에서 멀수록 내려간다: 층 0 이 베드 위에 있는
    곳은 r < Z′₀/tanθ 뿐이고(층고 0.3, 22° 에서 0.74mm), 첫 층 윤곽은 팁 높이가 층고/2
    이상인 안쪽을 이미 쓰고 있다. 그래서 윤곽 **바깥**의 브림은 한 바퀴째부터 팁이
    층고/2 아래이고, 두세 바퀴면 베드 밑이다. inward(c=−1)는 반대로 바깥으로 갈수록
    떠오른다 — 공중에 찍는 고리는 브림이 아니다. θ=0(평면 바닥)에서만 온전히 성립한다.

    보는 것 (브림 구간의 **모든 이동 끝점**, 트래블 포함):
      · 베드 아래: 파일에 적히는 값(소수 3자리)으로 z < 0
      · 뜸: z > BRIM_MAX_LIFT × 층고
      · [rep5x, mach 를 주면] 그 높이에서 기운 핫엔드 몸체가 베드 여유를 침범 —
        `to_rep5x` 의 이동별 베드 방어선과 **같은 식**이다. 통과시키면 방어선이 브림
        이동의 B 를 깎고 "프로필 계획이 못 잡았다" 고 경고하게 된다. 브림 탓인 것을
        거기서는 알 수 없으므로 여기서 거른다. (계획 `bed_safe_profile` 은 '팁은 층고의
        절반보다 낮아지지 않는다' 를 전제하는데 브림이 그 전제를 깬다.)

    층 안에서 z 는 선분을 따라 오목(z = Z′ − sinθ·ρ, ρ 볼록)이므로 outward 의 최저점은
    꼭짓점에 있다 — 끝점만 보면 된다.

    브림은 파일의 첫 압출이라 **그 앞부분만** 역변환한 결과가 전체를 역변환한 것의
    앞부분과 같다 (역변환의 상태는 직전 위치와 누적 E 뿐이다). 전체를 두 번 돌리지 않는다.

    ring_k: `slice_mesh` 의 stats["brim_ring_k"]. 주면 '안쪽 몇 바퀴까지 되는지' 를
    정보에 넣는다 (fit). 반환 정보: rings, z_min, z_max, fit, reason.
    """
    i0 = next((i for i, (k, p) in enumerate(items)
               if k == "raw" and p == BRIM_TYPE), None)
    if i0 is None:
        return None, {"rings": 0, "z_min": None, "z_max": None, "fit": 0, "reason": None}
    i1 = next((i for i in range(i0 + 1, len(items)) if items[i][0] == "raw"
               and str(items[i][1]).upper().startswith(";TYPE:")), len(items))
    zw = next(mv.z for k, mv in items[i0:i1] if k == "move" and mv.z is not None)
    real, _ = backtransform(items[:i1], cone_angle_deg, cone_type, chord_tol=chord_tol)
    j0 = next(i for i, (k, p) in enumerate(real) if k == "raw" and p == BRIM_TYPE)

    rings = []                       # 고리마다 끝점 높이들 (고리 = 트래블 + 닫힌 압출)
    prev_g = None
    for k, mv in real[j0 + 1:]:
        if k != "move":
            continue
        if mv.g == 0 and prev_g != 0:
            rings.append([])
        rings[-1].append(round(float(mv.z), 3))      # 파일에 적히는 값
        prev_g = mv.g

    theta0 = abs(float(cone_angle_deg.theta_at(zw))
                 if hasattr(cone_angle_deg, "theta_at") else float(cone_angle_deg))
    z_all = [z for r in rings for z in r]
    z_lo, z_hi = min(z_all), max(z_all)
    z_top = BRIM_MAX_LIFT * layer_height

    def tilt_limit(z):
        # `to_rep5x` 의 방어선과 글자 그대로 같은 식 (소수 3자리로 내린 B_safe)
        from conical.rep5x import BED_GUARD_MARGIN, b_safe
        return math.floor(b_safe(z, mach.hotend, mach.bed_clearance + BED_GUARD_MARGIN)
                          * 1000.0) / 1000.0

    def bad(r):
        if min(r) < 0.0:
            return "below"
        if max(r) > z_top + 1e-9:
            return "lifted"
        if mach is not None and theta0 > tilt_limit(min(r)):
            return "bed_gap"
        return None

    verdicts = [bad(r) for r in rings]
    fit = None
    if ring_k is not None and len(ring_k) == len(rings):
        failing = [k for k, v in zip(ring_k, verdicts, strict=True) if v]
        fit = min(failing) if failing else max(ring_k) + 1
    info = {"rings": len(rings), "z_min": z_lo, "z_max": z_hi, "fit": fit,
            "reason": next((v for v in ("below", "lifted", "bed_gap") if v in verdicts),
                           None)}
    if info["reason"] is None:
        return None, info
    n_bad = sum(1 for v in verdicts if v)
    why = {
        "below": f"역변환하면 고리 {n_bad}/{len(rings)}개가 **베드 아래**로 내려간다 "
                 f"(최저 z={z_lo:.3f}mm). 층 0 은 실공간에서 원뿔면 z = Z′ − r·tanθ 라 "
                 f"축에서 멀수록 낮다",
        "lifted": f"역변환하면 고리 {n_bad}/{len(rings)}개가 **베드에서 뜬다** "
                  f"(최고 z={z_hi:.3f}mm > 층고의 {BRIM_MAX_LIFT:g}배). inward 원뿔의 "
                  f"층 0 은 바깥으로 갈수록 올라간다",
        "bed_gap": f"팁이 z={z_lo:.3f}mm 까지 내려가 {theta0:.1f}° 기운 핫엔드가 베드 "
                   f"여유를 침범한다 (그 높이의 B_safe = "
                   f"{tilt_limit(z_lo) if mach is not None else 0.0:.2f}°)",
    }[info["reason"]]
    if fit is not None:
        why += (f" — 안쪽 {fit}바퀴까지는 된다 (--brim {fit})" if fit > 0
                else " — 한 바퀴도 못 놓는다")
    return why, info


def _rep5x_self_check(all_items, mach):
    """방금 쓴 REP5X 파일을 **파일에 적힌 그대로** 다시 읽어 검사한다 → 종료 코드.

    생성기가 스스로 지켰다고 믿는 것(베드 여유, 회전 속도 상한, TCP 전환 자리,
    M668 줄 형식)을 검사기로 한 번 더 본다 — 생성기와 검사기가 서로를 검사하는
    구조다. 치명이 하나라도 있으면 2 를 돌려준다. 파일은 남겨 두지만(무엇이
    틀렸는지 봐야 하므로) **프린터에 넣으면 안 된다.**

    출력물과의 간섭(`check_head_interference`)은 느려서 여기서 안 본다 —
    `rep5x_check.py` 가 본다.
    """
    from conical.rep5x import check_m668_format, check_rep5x

    lines = gc.to_lines(all_items)
    findings, st = check_rep5x(gc.parse(lines), mach)
    findings += check_m668_format(lines)[0]
    gap = st["bed_gap_min"]
    zj = st["joint_z_min"]
    print("  자체 점검   : 베드 여유선까지 최소 "
          + (f"{gap:+.2f}mm" if gap is not None else "-")
          + f", 회전 최대 {st['omega_max_deg_s']:.0f}°/s, joint Z 최저 "
          + (f"{zj:.2f}mm" if zj is not None else "-")
          + (" (부품 원점 = 베드 중앙 가정)" if st["origin_assumed"] else ""))
    for sev in ("치명", "경고"):
        for s, msg in findings:
            if s == sev:
                print(f"    {'✖' if sev == '치명' else '⚠'} [{sev}] {msg}")
    n_fatal = sum(1 for s, _ in findings if s == "치명")
    if n_fatal:
        print(f"  ✖✖ 치명 {n_fatal}건 — **이 파일을 프린터에 넣지 말 것.**")
        return 2
    return 0


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
    ap.add_argument("--k-blend", type=float, default=BLEND_COST_K,
                    help=f"J의 블렌드 비용 가중치 (기본 {BLEND_COST_K}; "
                         f"analyze_blend_k.py 참조). 0=블렌드 비용 무시")
    ap.add_argument("--band-select", choices=["j", "independent"], default="j",
                    help="j=프로필 J로 공동 선택(블렌드 비용 포함) / "
                         "independent=밴드별 독립 선택(옛 방식, 비교용)")
    ap.add_argument("--spacing-limit", type=float, default=MAX_SPACING_FACTOR,
                    help=f"블렌드 층간격 배율 상한 (기본 {MAX_SPACING_FACTOR}; "
                         f"config.MAX_SPACING_FACTOR). 0=제약 끄기(옛 동작)")
    ap.add_argument("--layer-height", type=float, default=0.3)
    ap.add_argument("--perimeters", type=int, default=2)
    ap.add_argument("--infill-spacing", type=float, default=2.5,
                    help="인필 간격 mm (0=인필 없음)")
    ap.add_argument("--min-layer-time", type=float, default=0.0,
                    help="[내장 슬라이서] 최소 층 시간(초). 층의 추정 시간이 이보다 "
                         "짧으면 그 층의 압출 피드를 낮춘다. 0=끔(기본, 예전 출력과 같다). "
                         "변환공간 길이 기준이라 실제는 cosθ 배까지 짧다 "
                         "(conical/planar_slicer.py 머리말)")
    ap.add_argument("--min-print-speed", type=float, default=10.0,
                    help="[내장 슬라이서] --min-layer-time 이 낮출 수 있는 속도 하한 mm/s "
                         "(기본 10). 이 아래로는 안 내리므로 아주 작은 층은 시간을 못 채운다")
    ap.add_argument("--fan", action="store_true",
                    help=f"[내장 슬라이서] 처음 {FAN_AFTER_LAYERS} 층 뒤에 팬을 켠다 "
                         f"(M106 S255, 끝에 M106 S0). 기본 끔")
    ap.add_argument("--brim", type=int, default=0,
                    help="[내장 슬라이서] 층 0 윤곽 바깥에 브림 N 바퀴 (기본 0). "
                         "역변환한 높이가 베드 아래거나 떠 있으면 건너뛰고 알린다 — "
                         "outward 원뿔에서는 거의 성립하지 않는다")
    ap.add_argument("--chord-tol", type=float, default=0.05,
                    help="역변환 허용 현 오차 ε (mm)")
    ap.add_argument("--max-edge", type=float, default=1.5,
                    help="정변환 전 최대 변 길이 (세분화)")
    ap.add_argument("--slicer-cmd", default=None,
                    help='외부 슬라이서 CLI 템플릿. 예 "prusa-slicer -g -o {gcode} {stl}"')
    ap.add_argument("--k", type=float, default=DEFAULT_K,
                    help=f"J의 각도 비용 가중치 (기본 {DEFAULT_K}; analyze_k 참조)")
    ap.add_argument("--mode", choices=["xyz", "open5x", "rep5x"], default="xyz",
                    help="xyz=3축(작은 각도) / open5x=베드 틸트+회전 기계좌표 / "
                         "rep5x=헤드 틸트+요, 부품좌표+B/C (펌웨어가 IK) [실험적]")
    ap.add_argument("--machine", choices=["prusa-uv", "voron-bc"], default="prusa-uv")
    ap.add_argument("--v-rewind", type=float, default=1.0,
                    help="배선 감김을 (이 값+1) 회전 이내로 유지 (트래블 중 되감기). "
                         "0 이면 끔. 진짜 한계는 기계의 배선 여유에서 온다")
    ap.add_argument("--v-rewind-feed", type=float, default=1200.0,
                    help="되감기 회전 속도 (deg/min). 올리면 추가 시간이 비례해 준다 "
                         "— 축 속도 한계 확인 후")
    ap.add_argument("--v-rewind-clearance", type=float, default=2.0,
                    help="되감기 전 들어올릴 여유 mm (퇴적물 최고점 위로)")
    ap.add_argument("--pivot-depth", type=float, default=50.0,
                    help="베드면→틸트축 거리 mm (Open5x 스탠드오프별, 실기 보정)")
    ap.add_argument("--bed-clearance", type=float, default=None,
                    help="[rep5x] 기운 핫엔드 몸체와 베드 사이에 남길 여유 mm "
                         "(기본: Rep5xProfile.bed_clearance = 0.2)")
    ap.add_argument("--omega-max", type=float, default=None,
                    help="[rep5x] 회전축(B/C) 속도 상한 °/s (기본 90). 펌웨어는 F 를 "
                         "팁 XYZ 길이에만 적용하므로 슬라이서가 F 를 깎는다")
    ap.add_argument("--strict", action="store_true",
                    help="[rep5x] 요청 각도가 베드 간섭 때문에 못 쓰는 값이면 "
                         "자동으로 낮추지 않고 멈춘다 (요청 각도 그대로가 실험 "
                         "조건일 때)")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--machine-profile", default=None,
                    help="기계 프로파일 INI (시작/종료 G-code). 없으면 경로만 "
                         "나오고 실물로는 못 뽑는다 — profiles/machine.example.ini 참고")
    args = ap.parse_args()
    if args.min_layer_time < 0 or args.min_print_speed <= 0 or args.brim < 0:
        raise SystemExit("--min-layer-time ≥ 0, --min-print-speed > 0, --brim ≥ 0 이어야 한다")

    mesh = trimesh.load(args.stl, force="mesh")
    mesh = center_on_axis(mesh)
    base = analytic.support_fraction(mesh, 0.0, "outward", THRESHOLD_DEG)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    rprof = RadiusProfile(mesh)
    spacing_limit = args.spacing_limit if args.spacing_limit > 1.0 else None
    fine = refine(mesh, args.max_edge)

    mach = None                     # REP5X 기계 파라미터 (rep5x 모드에서만)
    if args.mode == "rep5x":
        from conical.rep5x import REP5X
        mach = dataclasses.replace(
            REP5X,
            bed_clearance=(REP5X.bed_clearance if args.bed_clearance is None
                           else args.bed_clearance),
            omega_max=(REP5X.omega_max if args.omega_max is None
                       else args.omega_max))

    # [1] 각도 결정 (고정각 / 가변각 프로필)
    profile = None
    banded_info = None
    if args.profile is not None or args.auto_bands is not None:
        if args.angle is not None:
            raise SystemExit("--angle 과 --profile/--auto-bands 는 동시 사용 불가")
        if args.mode == "open5x":
            # REP5X 는 펌웨어가 IK 를 하므로 B 만 레이어별로 바꾸면 된다(2026-10-16).
            # Open5x 는 베드가 기울어 기계좌표 자체가 각도에 묶여 있어 따로 풀어야 한다.
            raise SystemExit("가변각 + Open5x 는 향후 과제 (베드 틸트가 상수라는 "
                             "가정이 깨짐) — xyz·rep5x 모드만 지원")
        if args.profile is not None:
            profile = AngleProfile.parse(args.profile)
            if (args.direction or "outward") == "inward":
                profile = AngleProfile(list(zip(profile.zs, -profile.thetas_deg, strict=True)))
            why = "수동 프로필"
        else:
            # 이동 예산은 모델 높이 기준 — 밴드 수와 무관 (config 주석 참조)
            shift = BLEND_SHIFT_RATIO * (mesh.bounds[1][2] - mesh.bounds[0][2])
            if args.band_select == "j":
                banded_info = select_banded_j(
                    mesh, args.k, args.auto_bands, r_max, rprof,
                    spacing_limit, shift, args.k_blend)
                profile = banded_info["profile_obj"]
                why = (f"--auto-bands {args.auto_bands} "
                       f"(프로필 J, k={args.k}, k_blend={args.k_blend})")
            else:
                banded_info = select_banded(mesh, args.k, args.auto_bands)
                profile = AngleProfile.from_banded_result(
                    banded_info, r_max, radius_profile=rprof,
                    spacing_limit=spacing_limit, max_shift=shift)
                why = f"--auto-bands {args.auto_bands} (밴드 독립 J, k={args.k})"
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

    # [1b] REP5X: 베드에 닿는 레이어의 각도를 B_safe 이하로 (슬라이싱 **전에** 고친다).
    #      헤드가 기운 채 첫 층을 찍으면 노즐 몸통이 베드를 친다 — 요청 프로필을
    #      잘라내고 기존 블렌드 폭 제약으로 올려 붙인다 (`rep5x.bed_safe_profile`).
    bed_info = None
    if mach is not None:
        from conical.rep5x import bed_safe_profile
        req = profile if profile is not None else AngleProfile.constant(
            angle if direction == "outward" else -angle)
        # 반경 포락선은 세분화한 메시로 촘촘히 (칸 약 0.1mm) — 거친 메시의 정점만
        # 보면 정점 사이 면의 반경을 놓쳐 팁 높이를 낙관적으로 잡는다.
        height = float(mesh.bounds[1][2] - mesh.bounds[0][2])
        bed_rp = RadiusProfile(fine, n_bins=int(np.clip(math.ceil(height / 0.1),
                                                        120, 1000)))
        safe, bed_info = bed_safe_profile(req, bed_rp, args.layer_height,
                                          mach.hotend, mach.bed_clearance,
                                          spacing_limit)
        if bed_info["changed"]:
            if args.strict:
                raise SystemExit(
                    "--strict: 요청한 각도는 베드 간섭 때문에 그대로 못 쓴다 "
                    f"(팁 높이 {bed_info['tip_floor']:.2f}mm 에서 B_safe = "
                    f"{bed_info['theta_bed']:.1f}°, 핫엔드 '{mach.hotend.name}', "
                    f"여유 {mach.bed_clearance:g}mm).\n  고치면 이렇게 된다:\n    "
                    + "\n    ".join(bed_info["notes"])
                    + "\n  --strict 를 빼면 위처럼 고쳐서 낸다.")
            profile, angle, direction = safe, None, "outward"
            after = analytic.support_fraction_profile(mesh, profile, THRESHOLD_DEG)
            why += " + 베드 안전"

    print("=" * 62)
    print(f"[conical_slice] {args.stl}")
    if profile is not None:
        print(f"  각도 결정   : 가변각 프로필 ({why}, 가역성 검증 통과)")
        print(profile.describe())
        for note in getattr(profile, "notes", []):
            print(f"    ↳ {note}")
        mf = profile.max_spacing_factor(r_max, "outward", rprof)
        print(f"  층간격 배율 : 최대 {mf:.2f}배 "
              f"(상한 {spacing_limit if spacing_limit else '없음'})")
        if spacing_limit is not None:
            for bad in profile.check_spacing(r_max, "outward", spacing_limit, rprof):
                print(f"  ⚠ 층간격 위반: [{bad['lo']:.2f},{bad['hi']:.2f}] "
                      f"θ {bad['theta1']:.0f}°→{bad['theta2']:.0f}° r={bad['r']:.1f} "
                      f"→ 배율 {bad['factor']:.1f}배 (레이어가 떠서 지지가 사라짐)")
        if banded_info is not None and "thetas" in banded_info:
            uni = banded_info["uniform_best"]
            print(f"  밴드 선택   : 독립선택 {banded_info['start_thetas']} → "
                  f"프로필 J {banded_info['thetas']}  "
                  f"(J={banded_info['J']:.2f}, 블렌드비용 {banded_info['blend_penalty']:.1f})")
            print(f"  균일 대조   : 최선 균일 {uni:.0f}° J={banded_info['uniform_J']:.2f}"
                  + ("  → 균일이 더 나아 균일로 수렴"
                     if banded_info["J"] <= banded_info["uniform_J"] + 1e-9
                     else f"  → 부위별이 {banded_info['J'] - banded_info['uniform_J']:.2f} 만큼 이득"))
        elif banded_info is not None:
            print(f"  밴드 서포트 추정: {banded_info['support_pct']:.1f}% "
                  f"(select_banded, 이상적 추정)")
    else:
        print(f"  각도 결정   : {direction} {angle:.0f}°  ({why})")
    if bed_info is not None:
        print(f"  베드 안전   : 팁 높이 {bed_info['tip_floor']:.2f}mm 에서 B_safe = "
              f"{bed_info['theta_bed']:.1f}°  (핫엔드 '{mach.hotend.name}', "
              f"여유 {mach.bed_clearance:g}+{bed_info['margin']:g}mm)")
        print("                " + ("요청 각도를 낮췄다 — 위 ↳ 줄 참조. 균일 원뿔 "
                                    "대조군이면 더 이상 균일이 아니다"
                                    if bed_info["changed"] else
                                    "요청 각도가 레이어별 상한 안이라 그대로 쓴다"))
    print(f"  서포트 예측 : {base:.1f}% (평면) → {after:.1f}% "
          f"({'프로필' if profile is not None else '선택 각도'}"
          f"{', 축상 근사' if profile is not None else ''})")

    # [2] 세분화 + 정변환
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

    # [3]~[5] 를 한 번에 시도한다. rep5x 는 링을 번갈아 돌려(C 가 쌓이지 않게) 먼저
    # 해 보고, 되감기로 못 고치는 구간이 생기면(축 근처 링 안에서 B 부호 반전으로 C 가
    # 180° 뛰어 한 압출 구간이 360° 를 넘는 경우) 번갈아 없이 처음부터 다시 한다.
    import contextlib
    import io

    cone = profile if profile is not None else angle     # 역변환·5축 변환이 받는 각도
    # 브림은 역변환한 높이를 보고 나서야 넣을지 정해진다. 한 번 건너뛰기로 하면
    # 아래 재시도(번갈아 없이 다시)에서도 그대로 간다.
    brim = {"n": args.brim, "note": None}
    cool = {"times": None}      # 내장 슬라이서가 잰 층 시간 (감속 전) — 권장값 안내용

    def _stages(alt):
        rw = {"fixable": True}
        r5 = {}
        # [3] 평면 슬라이싱 (변환공간)
        if args.slicer_cmd:
            with tempfile.TemporaryDirectory() as td:
                items = run_external_slicer(args.slicer_cmd, warped, td)
            print(f"  슬라이서    : 외부 CLI ({args.slicer_cmd.split()[0]})")
            if args.min_layer_time > 0 or args.fan or args.brim > 0:
                print("  ⚠ --min-layer-time / --fan / --brim 은 내장 슬라이서 전용이라 "
                      "무시한다 — 외부 슬라이서의 냉각·브림 설정을 쓸 것")
        else:
            sl = {}

            def _slice(n_brim):
                # rep5x: 링을 번갈아 돌아 C 가 쌓이지 않게 한다 (되감기 제거, planar_slicer 참고)
                return slice_mesh(warped, layer_height=args.layer_height,
                                  perimeters=args.perimeters,
                                  infill_spacing=args.infill_spacing,
                                  alternate_rings=alt,
                                  min_layer_time=args.min_layer_time,
                                  min_print_speed=args.min_print_speed,
                                  fan=args.fan, brim=n_brim, stats=sl)

            items = _slice(brim["n"])
            binfo = None
            if brim["n"] > 0:
                # 브림이 실공간에서 베드 위에 놓이는가 — **역변환해서** 본다
                why_not, binfo = brim_problem(items, cone, direction, args.layer_height,
                                              args.chord_tol, sl.get("brim_ring_k"), mach)
                if why_not:
                    brim.update(n=0, note=why_not)
                    items = _slice(0)          # 브림 없는 출력과 비트 단위로 같아진다
            print(f"  슬라이서    : 내장 (layer {args.layer_height}mm, "
                  f"perim {args.perimeters}, infill {args.infill_spacing}mm"
                  f"{', 링 방향 번갈아' if alt else ''})")
            if brim["note"]:
                print(f"  ⚠ 브림 건너뜀: 요청 {args.brim}바퀴 — {brim['note']}")
            elif brim["n"] > 0:
                print(f"  브림        : 층 0 에 {brim['n']}바퀴, 고리 {binfo['rings']}개 "
                      f"(역변환한 팁 높이 {binfo['z_min']:.3f}~{binfo['z_max']:.3f}mm, "
                      f"명목 {args.layer_height:g}mm)")
                if binfo["z_min"] < args.layer_height / 2.0 - 1e-9:
                    print(f"    ⚠ 팁이 층고의 절반({args.layer_height / 2.0:g}mm) 아래다 — "
                          f"비드가 그만큼 눌린다(압출량은 층고 기준 그대로). 원뿔면이 "
                          f"윤곽 바깥에서 베드로 내려가기 때문이다")
            if args.fan:
                print(f"  팬          : {FAN_AFTER_LAYERS}층을 낸 뒤 M106 S255, 끝에 M106 S0"
                      if len(sl["layer_times"]) > FAN_AFTER_LAYERS else
                      f"  팬          : 층이 {len(sl['layer_times'])}개뿐이라 켜지 않았다")
            # 층 시간 (변환공간 길이 / 명령 피드 — 슬라이서가 감속을 정할 때 쓴 값)
            lt = np.array([[b, a] for _i, b, a in sl["layer_times"]])
            if len(lt):
                cool["times"] = lt[:, 0]
                txt = (f"  층 시간     : 중앙 {np.median(lt[:, 0]):.1f}s, 최소 "
                       f"{lt[:, 0].min():.1f}s ({len(lt)}층, 변환공간 추정·가속 무시)")
                if args.min_layer_time > 0:
                    txt += (f"\n                → 최소 {args.min_layer_time:g}s: "
                            f"{sl['slowed_layers']}층의 압출 피드를 낮춰 중앙 "
                            f"{np.median(lt[:, 1]):.1f}s, 최소 {lt[:, 1].min():.1f}s"
                            + (f" (가장 낮은 F{gc.format_feed(sl['min_feed'])})"
                               if sl["min_feed"] else ""))
                    if sl["floor_limited"]:
                        txt += (f"\n                ⚠ {sl['floor_limited']}층은 속도 하한 "
                                f"{args.min_print_speed:g}mm/s 에 걸려 "
                                f"{args.min_layer_time:g}s 를 못 채운다")
                print(txt)

        # [4] 역변환 (적응 현 분할; 프로필이면 점별 θ(Zw) + 블렌드 분할 2배)
        real_items, stats = backtransform(items, cone, direction, chord_tol=args.chord_tol)
        print(f"  역변환      : 이동 {stats['moves_in']:,} → {stats['moves_out']:,} "
              f"(확장 {stats['expansion']:.2f}배, ε={args.chord_tol}mm 적응 분할)")

        # [5] 출력 모드
        if args.mode == "open5x":
            from conical.open5x import PRUSA_UV, VORON_BC, add_v_rewinds, to_open5x
            prof = PRUSA_UV if args.machine == "prusa-uv" else VORON_BC
            prof.pivot_depth = args.pivot_depth
            real_items, o5 = to_open5x(real_items, angle, direction, prof)
            print(f"  Open5x      : 틸트 {prof.tilt_axis}={angle:.0f}° 고정 "
                  f"(pivot {args.pivot_depth}mm) [실험적 — 부호·피벗 실기보정 필요]")
            if args.v_rewind > 0:
                real_items, rw = add_v_rewinds(real_items, prof,
                                               max_turns=args.v_rewind,
                                               clearance=args.v_rewind_clearance,
                                               rot_feed=args.v_rewind_feed)
                print(f"  되감기      : 트래블 중 {rw['rewinds']}회, "
                      f"감김 ≤{args.v_rewind + 1:.1f}회전 "
                      f"(들어올림 +{args.v_rewind_clearance}mm, "
                      f"추가 시간 약 {rw['rewind_minutes']:.0f}분)")
            else:
                print("  ⚠ 되감기 꺼짐 — 배선 감김을 직접 확인할 것")
        elif args.mode == "rep5x":
            from conical.rep5x import add_c_rewinds, limit_rotary_speed, to_rep5x
            # TCP 는 B0 C0 에서 **한 번만** 켠다. 기계 프로파일의 시작 G-code 가 켜면
            # (호밍·프라임·원점 선언이 끝난 자리) 경로 헤더는 다시 켜지 않는다.
            start_text = (MachineProfile.from_file(args.machine_profile).start_gcode
                          if args.machine_profile else "")
            rtcp_in_start = any(
                ln.split(";", 1)[0].strip().upper().startswith(mach.rtcp_on.upper())
                for ln in start_text.splitlines())
            real_items, r5 = to_rep5x(real_items,
                                      profile if profile is not None else angle,
                                      direction, mach, emit_rtcp=not rtcp_in_start,
                                      bed_clearance=mach.bed_clearance)
            tilt_txt = (f"B={r5['b']:.0f}° 고정" if not r5["variable"] else
                        f"B 레이어별 θ(Z′) {r5['b_abs_min']:.0f}~{r5['b_abs_max']:.0f}°")
            print(f"  REP5X       : 헤드 틸트 {tilt_txt}, C 가 방위각 추종 "
                  f"(펌웨어가 IK — X/Y/Z 는 노즐 팁) [실험적 — 축 부호 실기보정 필요]")
            print(f"                축 통과 {r5['pole_flips']}회는 C 180° 대신 B 부호 반전, "
                  f"수직(θ=0) 구간 {r5['c_held_vertical']:,}이동은 C 고정")
            print(f"                C 누적 {r5['c_turns']:.1f}회전 "
                  f"(펌웨어 소프트 엔드스톱 창 "
                  f"{mach.c_min:.0f}~{mach.c_max:.0f}°)")
            if args.v_rewind > 0:
                real_items, rw = add_c_rewinds(real_items, mach,
                                               clearance=args.v_rewind_clearance,
                                               rot_feed=args.v_rewind_feed)
                note = "" if rw["fixable"] else \
                    f"  ⚠⚠ 못 고친 구간 {rw['unfixable_segments']}개 (창보다 넓게 감긴다)"
                print(f"  C 되감기    : 트래블 중 {rw['rewinds']}회 "
                      f"(시작 오프셋 {rw['start_offset']:+.0f}°, "
                      f"들어올림 +{args.v_rewind_clearance}mm){note}")
            else:
                print("  ⚠⚠ 되감기 꺼짐 — C 가 소프트 엔드스톱을 넘어 기계가 멈춘다")
            if r5["bed_clamped"]:
                print(f"  ⚠ 베드 방어선: 이동 {r5['bed_clamped']:,}개에서 B 를 최대 "
                      f"{r5['bed_clamp_max_deg']:.2f}° 깎았다 — 프로필 계획이 못 잡은 "
                      f"것이다. 그 이동에서는 공구가 레이어 법선에서 그만큼 벗어난다")
            # 회전축 속도 상한은 **맨 마지막**에 건다 (되감기가 이동을 끼워 넣으므로).
            real_items, fs = limit_rotary_speed(real_items, mach)
            print(f"  회전 속도   : 상한 {mach.omega_max:g}°/s — F 를 깎은 이동 "
                  f"{fs['capped']:,}개 (+{fs['added_seconds']:.0f}초, 최저 "
                  f"F{gc.format_feed(fs['min_feed']) if fs['min_feed'] else '-'}), "
                  f"회전만 하는 이동 {fs['rotation_only']:,}개")
        if args.min_layer_time > 0 and not args.slicer_cmd:
            # 위 추정은 변환공간 길이다. 실제로 적힌 경로·F 로 다시 잰다: 역변환이 둘레
            # 길이를 cosθ 배로 줄이고(짧아진다), rep5x 는 회전 상한·되감기가 더한다(길어진다).
            real_t = np.array([t for t in layer_times(real_items).values() if t > 0])
            n_short = int((real_t < args.min_layer_time - 1e-9).sum())
            print(f"  층 시간(파일): 적힌 경로·F 로 다시 재면 중앙 {np.median(real_t):.1f}s, "
                  f"최소 {real_t.min():.1f}s — {args.min_layer_time:g}s 미만 {n_short}층"
                  + (" (속도 하한에 걸린 층, 그리고 역변환이 둘레 길이를 cosθ 배로 "
                     "줄인 몫)" if n_short else ""))
        return real_items, stats, rw, r5

    alt_first = args.mode == "rep5x" and not args.slicer_cmd
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        real_items, stats, rw, r5 = _stages(alt_first)
    if alt_first and not rw.get("fixable", True):
        print("  ↳ 링 번갈아 돌리기로는 C 창에 못 담는 구간이 생겨 번갈아 없이 다시 슬라이싱한다")
        real_items, stats, rw, r5 = _stages(False)
    else:
        print(buf.getvalue(), end="")
    out_path = args.output or (Path(args.stl).stem +
                               {"open5x": "_open5x.gcode",
                                "rep5x": "_rep5x.gcode"}.get(args.mode,
                                                             "_conical.gcode"))
    # 뷰어/후처리 도구가 읽는 메타데이터 (tools/slicing_simulator.html 등)
    # ;CONICAL_META — 검증 탭이 파일 하나로 자기 계산을 할 수 있게 하는
    # 한 줄 JSON (자기기술 G-code, 사이드카 파일 없음).
    import json as _json
    if profile is not None:
        bps = [[float(z), float(t)] for z, t in zip(profile.zs, profile.thetas_deg, strict=True)]
        meta_dir = "outward"          # 부호 각도 규약 (음수=inward)
        prof_txt = ",".join(f"{z:g}:{t:g}"
                            for z, t in zip(profile.zs, profile.thetas_deg, strict=True))
        legacy = f"; conical: profile={prof_txt} direction=outward " \
                 f"mode={args.mode} chord_tol={args.chord_tol}"
    else:
        bps = [[0.0, float(angle)]]
        meta_dir = direction
        legacy = f"; conical: angle={angle:.1f} direction={direction} " \
                 f"mode={args.mode} chord_tol={args.chord_tol}"
    meta_json = _json.dumps({
        "version": 1, "direction": meta_dir, "profile": bps,
        "layer_height": args.layer_height, "extrusion_width": 0.45,
        "chord_tol": args.chord_tol, "source_stl": str(args.stl),
        "mode": args.mode}, separators=(",", ":"))
    meta = [("raw", f";CONICAL_META {meta_json}"), ("raw", legacy)]

    # 기계 프로파일(예열·호밍·프라임·냉각)은 경로 생성과 분리해 파일로 받는다.
    # 없으면 경로만 나오므로 실물로는 못 뽑는다 — 그 사실을 조용히 넘기지 않는다.
    head, tail = [], []
    if args.machine_profile:
        mp = MachineProfile.from_file(args.machine_profile)
        # ⚠ 여기는 오래 **상수각만 가정**하고 있었다 — 가변각(`--profile`/`--auto-bands`)
        #   이면 `angle` 이 None 이라 f"{angle:.1f}" 에서 죽었다. 즉 **이 연구의 핵심
        #   전략(부위별 각도)을 실물용으로 뽑는 경로가 통째로 막혀 있었다.**
        #   (tests/test_machine_profile_varangle.py 가 고정)
        if profile is not None:
            th = [float(t) for t in profile.thetas_deg]
            a_max = max(th, key=abs)
            angle_ctx = {"angle": f"{a_max:.1f}",      # 대표값 = |θ| 최대 (안전 기준)
                         "angle_max": f"{a_max:.1f}",
                         "angle_min": f"{min(th, key=abs):.1f}",
                         "profile": prof_txt}
        else:
            angle_ctx = {"angle": f"{angle:.1f}", "angle_max": f"{angle:.1f}",
                         "angle_min": f"{angle:.1f}",
                         "profile": f"0:{angle:g}"}
        ctx = {"layer_height": args.layer_height,
               "direction": direction, "mode": args.mode,
               "source_stl": Path(args.stl).name, **angle_ctx}
        head, tail = mp.start_items(ctx), mp.end_items(ctx)
        print(f"  기계        : {mp.name}  ({args.machine_profile})")
        # 프로파일이 권하는 최소 층 시간. **권장일 뿐 자동으로 걸지 않는다** — 걸면 같은
        # 명령으로 다시 뽑은 파일이 달라진다(시험 사다리 재현). 짧은 층이 있을 때만 알린다.
        rec = mp.values.get("recommended_min_layer_time")
        if rec and args.min_layer_time <= 0 and cool["times"] is not None:
            n_fast = int((cool["times"] < float(rec)).sum())
            if n_fast:
                print(f"    ↳ 이 프로파일의 권장 최소 층 시간 {float(rec):g}s 보다 짧은 층이 "
                      f"{n_fast}/{len(cool['times'])}개다 — --min-layer-time {float(rec):g} "
                      f"(지금은 꺼짐)")
        # 시작 G-code 의 프라임 선이 부품 자리(원점 둘레)를 지나가면 첫 층이 그 위에
        # 올라간다. 템플릿이 실제로 그랬다(2026-10-16) — 매번 검사한다.
        part_r = max((math.hypot(mv.x, mv.y) for k, mv in real_items
                      if k == "move" and mv.x is not None and mv.y is not None),
                     default=0.0)
        # 출력 가능 반경은 넘기지 않는다: REP5X 의 한계는 원점 기준 반경이 아니라
        # native XY 범위이고, 그건 아래 자체 점검(`check_rep5x`)이 파일 전체로 본다.
        for sev, msg in check_start_extrusion(head, part_r):
            print(f"  {'✖' if sev == '치명' else '⚠'} [{sev}] {msg}")
    all_items = meta + head + real_items + tail
    gc.write(all_items, out_path)
    print(f"  출력        : {out_path}")
    rc = 0
    if args.mode == "rep5x":
        rc = _rep5x_self_check(all_items, mach)
    if not args.machine_profile:
        print("  ⚠ 기계 프로파일이 없다 — 예열·호밍·프라임·냉각이 빠져 있어 "
              "이 파일로는 실물을 못 뽑는다.")
        print("    --machine-profile profiles/machine.example.ini "
              "(템플릿: 값은 실기 확인 전)")
    if args.mode == "open5x":
        # 검사기 A/B 는 3축 가정이라 5축 출력에는 안 맞는다. 기계좌표 검사로 보낸다.
        print(f"  검증        : python3 open5x_check.py {out_path} --bed-radius <mm>")
        print("                (3축용 toolpath_check 는 5축 출력에 맞지 않는다)")
    elif args.mode == "rep5x":
        print(f"  검증        : python3 rep5x_check.py {out_path}")
        print("                (3축용 toolpath_check 는 5축 출력에 맞지 않는다)")
    else:
        print(f"  검증        : python3 toolpath_check.py {out_path}")
    if args.mode == "xyz":
        print("  ⚠ 3축 프린터는 작은 각도만 안전 (노즐-출력물 간섭). "
              "큰 각도는 틸트 하드웨어 필요.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
