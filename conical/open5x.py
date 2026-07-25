"""
open5x.py — 원뿔 G-code → Open5x(베드 틸트+회전) 5축 기계좌표 변환. [실험적]

조사로 확인된 사실 (docs 참고, 출처: FreddieHong19/Open5x 저장소·CHI'22 논문):
  · Prusa i3 판: 축 U=베드 틸트(Y평행선 중심), V=베드 회전. Duet RRF3.
  · 펌웨어는 회전 기구학을 하지 않는다(M669 K0 항등) → **슬라이서가 기계좌표를
    직접 계산해야 한다** (논문의 Grasshopper도 역기구학을 슬라이서에서 수행).
  · XY 원점 = 회전 베드 중심 (M208 주석). 틸트축-베드면 거리(피벗 깊이)는
    스탠드오프(30/50/70mm)에 따라 다름 → 반드시 기계에서 보정할 파라미터.
  · 회전축은 모듈로 감지 말고 절대값을 계속 누적할 것(RRF 당시 랩 기능 없음).
  · Open5x에서 원뿔 모드 출력 사례는 문서화된 것이 없음 → 이 모듈이 첫 시도.
    부호(틸트 방향·회전 방향)는 문서에 없어 기계에서 실측 보정해야 한다.

원뿔 모드 원리 (노즐 수직 고정, 베드가 움직임):
  outward 원뿔 레이어의 국소 법선은 n̂ = sinθ·r̂(φ) + cosθ·ẑ (φ=점의 방위각).
  베드를 틸트 U=θ 로 고정하고, 회전 V가 현재 압출점의 방위각을 따라가면
  압출점에서 레이어면이 수평이 되어 수직 노즐로 원뿔 레이어를 쌓을 수 있다.

수학 (부품좌표 p → 기계좌표):
  1) 베드 회전: 압출점이 항상 틸트 '올라간 쪽'(방위각 φ0=0, +X)에 오도록
       V = −φ(p)   (연속 누적, 랩 없음)
       p1 = Rz(V)·p
  2) 베드 틸트: Y축 평행선(베드 중심, 베드면 아래 pivot_depth d) 중심 회전
       p2 = Ry(s·θ)·(p1 + [0,0,d]) − [0,0,d]     (s=틸트 부호, 기계 보정)
  3) G1 X..Y..Z..U..V.. 로 출력 (U는 상수 θ)

피드레이트 (조사 확인: RRF에서 U/V는 '선형' 취급 → 도(deg)가 norm에 mm처럼
  들어감): 논문 방식대로 세그먼트별 재조정 F' = F × (기계경로길이/표면경로길이).
"""

import math

from .gcode import Move


class MachineProfile:
    """기계별 파라미터. 전부 실기 보정 대상."""
    def __init__(self, tilt_axis="U", rot_axis="V", tilt_sign=-1.0, rot_sign=1.0,
                 pivot_depth=50.0, max_tilt_deg=90.0, uv_linear_feed=True):
        # tilt_sign 기본 -1: 이 부호에서 outward 원뿔 레이어 법선이 기계좌표에서
        # 정확히 수직이 됨을 수치 검증함 (2000점 오차 0). 실기에서 축 방향이
        # 반대로 조립됐으면 +1로 바꿀 것.
        self.tilt_axis = tilt_axis
        self.rot_axis = rot_axis
        self.tilt_sign = tilt_sign          # 틸트 방향 부호 (실측 보정)
        self.rot_sign = rot_sign            # 회전 방향 부호 (실측 보정)
        self.pivot_depth = pivot_depth      # 베드면→틸트축 거리 mm (스탠드오프별)
        self.max_tilt_deg = max_tilt_deg    # Voron 펌웨어 한계 ±110°, 시연 90°
        self.uv_linear_feed = uv_linear_feed  # RRF: U/V가 F norm에 선형으로 포함


PRUSA_UV = MachineProfile("U", "V")          # Open5x Prusa i3 판
VORON_BC = MachineProfile("B", "C", uv_linear_feed=False)  # B/C판(회전은 norm 제외)


def _map_point(x, y, z, theta_deg, prof, v_prev):
    """부품좌표 → (기계 x,y,z, V각도[연속누적]). v_prev: 직전 V (unwrap 기준)."""
    r = math.hypot(x, y)
    if r < 1e-6:
        v = v_prev                          # 축 위: 방위각 정의 불가 → V 유지
    else:
        phi = math.degrees(math.atan2(y, x))
        v_raw = -phi * prof.rot_sign
        # 연속 누적(unwrap): 직전 값과 ±180° 이내가 되도록 360° 단위 이동
        k = round((v_prev - v_raw) / 360.0)
        v = v_raw + 360.0 * k
    # 1) 베드 회전 Rz(v_bed): 부품이 베드에 붙어 돌므로 점은 Rz(v_bed)·p
    a = math.radians(v * (1.0 if prof.rot_sign >= 0 else -1.0))
    ca, sa = math.cos(a), math.sin(a)
    x1 = ca * x - sa * y
    y1 = sa * x + ca * y
    z1 = z
    # 2) 틸트 Ry(s·θ), 피벗 (0,0,-d)
    t = math.radians(prof.tilt_sign * theta_deg)
    ct, st = math.cos(t), math.sin(t)
    zd = z1 + prof.pivot_depth
    x2 = ct * x1 + st * zd
    z2 = -st * x1 + ct * zd - prof.pivot_depth
    return x2, y1, z2, v


def to_open5x(items, cone_angle_deg, cone_type, profile=PRUSA_UV):
    """실공간 원뿔 G-code 아이템 → Open5x 기계좌표 G-code 아이템.

    inward 원뿔은 틸트 부호가 반대(레이어가 안쪽으로 기움).
    반환: (아이템 리스트, 통계 dict)
    """
    if cone_angle_deg > profile.max_tilt_deg:
        raise ValueError(f"cone angle {cone_angle_deg} > machine tilt limit "
                         f"{profile.max_tilt_deg}")
    theta = cone_angle_deg * (1.0 if cone_type == "outward" else -1.0)

    out = [("raw", f"; Open5x conical mode [EXPERIMENTAL] "
                   f"tilt {profile.tilt_axis}={theta:.1f}deg fixed, "
                   f"{profile.rot_axis} tracks azimuth"),
           ("raw", f"; pivot_depth={profile.pivot_depth}mm  "
                   f"(calibrate on machine; signs too)"),
           ("raw", f"G1 {profile.tilt_axis}{theta:.3f} F600  ; tilt bed")]
    x = y = z = None
    v_prev = 0.0
    px = py = pz = None                     # 직전 부품좌표 (F 재조정용)
    mx = my = mz = None                     # 직전 기계좌표
    v_range = [0.0, 0.0]
    for kind, payload in items:
        if kind != "move":
            out.append((kind, payload))
            continue
        mv = payload
        x = mv.x if mv.x is not None else x
        y = mv.y if mv.y is not None else y
        z = mv.z if mv.z is not None else z
        if x is None or y is None or z is None:
            out.append((kind, payload))
            continue
        X, Y, Z, v = _map_point(x, y, z, abs(theta), profile, v_prev)
        # 논문 방식 피드 재조정: F' = F × 기계길이/부품길이
        f_out = mv.f
        if mv.f is not None and px is not None:
            part_len = math.dist((px, py, pz), (x, y, z))
            if profile.uv_linear_feed:
                mach_len = math.sqrt((X - mx) ** 2 + (Y - my) ** 2 +
                                     (Z - mz) ** 2 + (v - v_prev) ** 2)
            else:
                mach_len = math.dist((mx, my, mz), (X, Y, Z))
            if part_len > 1e-9:
                f_out = mv.f * max(mach_len / part_len, 1e-3)
        extra = f"{profile.rot_axis}{v:.3f}"
        out.append(("move", Move(g=mv.g, x=X, y=Y, z=Z, e=mv.e, f=f_out,
                                 extra=extra)))
        v_prev = v
        v_range[0] = min(v_range[0], v)
        v_range[1] = max(v_range[1], v)
        px, py, pz = x, y, z
        mx, my, mz = X, Y, Z

    stats = {"v_min": v_range[0], "v_max": v_range[1],
             "v_turns": (v_range[1] - v_range[0]) / 360.0}
    return out, stats
