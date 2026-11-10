"""
rep5x.py — 원뿔 G-code → REP5X(헤드 틸트+요) 5축 출력. [실험적]

Open5x 와 **출력 계약이 다르다.** Open5x 는 펌웨어가 회전 기구학을 하지 않아
슬라이서가 기계좌표를 직접 계산했다(`open5x.py`). REP5X 는 **펌웨어가 역기구학을
한다** — 그래서 슬라이서는 **노즐 팁 위치(부품좌표 그대로) + 공구 방향**만 내면
되고, 좌표 변환이 아예 **빠진다.** `to_open5x` 보다 하는 일이 적다.

## 저장소·펌웨어 원문으로 확인한 것 (2026-09-19)

축이 **헤드에 붙는다** (`build-guide/assembly-instructions-universal.md`):
  · Step 10 "Attach **carriage mount** to **X-carriage**"
  · Step 11 "Mount **C-axis (yaw) stepper motor** to carriage mount"
  · Step 12 "Route all wires and Bowden tube through **B_arm** center"
  · 슬립링이 나르는 것: hotend fan / heater / thermistor / B-axis endstop
  → **베드는 안 움직인다.** 부품이 고정이고 노즐이 기울고 돈다.

펌웨어 규약 (`Rep5x-Marlin`, 브랜치 `Marlin2ForPipetBot`, `Marlin/Configuration.h`):
  · `AXIS4_NAME 'C'` + `AXIS4_ROTATES` — 요(yaw), Z축 둘레. 내부 축은 I
  · `AXIS5_NAME 'B'` + `AXIS5_ROTATES` — 틸트, **0 에서 Y 에 평행**. 내부 축은 J
  · `PENTA_AXIS_HH` (head-head 기구학, Marlin2ForPipetBot 파생)
  · `DEFAULT_TOOL_CENTERPOINT_CONTROL true` — **RTCP 기본 ON.**
    즉 **G-code 의 X/Y/Z 는 노즐 팁 위치**이고 펌웨어가 캐리지 위치를 역산한다.
    런타임 전환: `G43.4` 켜기 / `G49` 끄기 → 시작 G-code 에 `G43.4` 를 박는다
  · `DEFAULT_ROTATIONAL_JOINT_OFFSET_Z 54.67` (LB: 틸트축→노즐 팁)
  · `DEFAULT_ROTATIONAL_JOINT_OFFSET_Y 1.6`   (LC: 요축 중심→툴)
  · `I_MIN_POS -360` / `I_MAX_POS 360`  ← **C 는 ±360° 다**
  · `J_MIN_POS -135` / `J_MAX_POS 135`
  · `MIN_SOFTWARE_ENDSTOP_I` / `MAX_SOFTWARE_ENDSTOP_I` 둘 다 켜져 있다
  · `PRINTABLE_RADIUS 100.0`

## ⚠⚠ C 가 ±360° 라 **되감기가 여전히 필요하다**

"Continuous yaw rotation" 은 **슬립링이 푸는 기계적 제약**이지 소프트웨어 한계가
아니다. 펌웨어 소프트 엔드스톱이 C 를 ±360° 로 묶고 랩 기능이 없다. 우리 원뿔
G-code 는 C 가 방위각을 따라 **계속 누적**되므로(funnel 20° 에서 44.5회전)
그대로 걸면 **소프트 엔드스톱에 걸려 멈춘다.**

되감기는 `open5x.add_v_rewinds` 를 그대로 쓴다 — 그 함수는 `profile.rot_axis` 만
보므로 축 문자만 'C' 로 주면 된다. 되는 이유도 같다: C 를 360° 배수만큼 돌리면
**공구 방향이 정확히 같은 값으로 돌아온다**(Rz 주기). RTCP 가 켜져 있으면 팁도
제자리다.

⚠ 다만 **도는 도중에 B_arm 이 팁 둘레를 쓸고 지나간다** (반각 θ, 팁에서 LB 만큼
  위, 수평 반경 LB·sinθ ≈ 18.7mm @ θ=20°). 베드 회전식과 달리 부품은 안 움직이지만
  팔이 움직인다. 그래서 들어올림을 그대로 유지한다.

## 수학 (부품좌표 p → B/C)

원뿔 레이어의 국소 법선 (outward, 레이어 `z = z₀ − r·tanθ`):

    n̂ = sinθ·r̂(φ) + cosθ·ẑ           (φ = 점의 방위각)

노즐은 그 반대를 향해야 한다. 펌웨어 규약에서 공구 방향은

    d̂ = Rz(C)·Ry(B)·(0,0,−1) = (−sinB·cosC, −sinB·sinC, −cosB)

둘을 맞추면 **B = c·θ (상수), C = φ(p)** 가 나온다 (c = +1 outward / −1 inward).
`tests/test_rep5x.py` 가 이 일치를 수치로 강제한다 — 부호 하나가 틀리면 노즐이
반대로 기울므로 말로 두면 안 되는 부분이다.

⚠⚠ **부호는 실기 보정 대상이다.** 위 유도는 펌웨어 **설정 파일의 규약**을 따른
  것이고, 실제 조립에서 모터 방향이 반대로 붙었으면 `INVERT_I_DIR`/`INVERT_J_DIR`
  로 펌웨어 쪽에서 뒤집힌다. `tilt_sign` / `rot_sign` 으로 여기서도 뒤집을 수
  있게 두었다. **첫 출력 전에 `G0 B10` 을 눈으로 확인할 것.**

## ⚠⚠ 피드레이트 — `to_rep5x` 는 그대로 통과시키고, **마지막에 깎는다**

X/Y/Z 가 노즐 팁의 실제 경로이므로 F 의 **단위**는 이미 맞다 (Open5x 에서 필요했던
`F × 기계길이/부품길이` 재조정이 없다). 그런데 예전에 여기 적어 둔 "회전축이 못
따라가면 Marlin 플래너가 알아서 전체를 늦춘다" 는 **틀렸다** (2026-11-10,
docs/rep5x_machine_facts.md §7): 펌웨어는 F 를 **팁 XYZ 경로 길이에만** 적용하고
회전량은 넣지 않는다. 그래서 XYZ 가 짧고 회전이 큰 이동(축 근처에서 한 걸음에
C 45~179°)은 회전축이 **축 한계(3600°/s, 1000°/s²)까지 가속**한다. 회전만 하는
이동은 F 를 °/min 으로 읽는다.

→ `limit_rotary_speed` 가 이동마다 F 를 깎는다. 되감기(`add_c_rewinds`)가 이동을
  끼워 넣으므로 **파이프라인의 맨 마지막**에 돌린다 (`conical_slice.py`).

## ⚠⚠ 베드 간섭 — 헤드가 기운 채 첫 층을 찍으면 **노즐 몸통이 베드를 친다**

`check_head_interference` 는 **출력물**만 본다. 그런데 첫 층들은 팁이 Z≈층고에
있고 B 가 24~30° 다. 공식 뷰어 모델(`toolpath.REP5X_V3SE_HOTEND`)로는 팁이 베드에
있을 때 노즐 몸통(반경 4.5, 팁 위 2mm)이 **약 24° 에서 베드면에 닿는다.**

  · `bed_gap` / `b_safe` — 핫엔드 모델과 베드 사이 여유, 팁 높이별 최대 |B| (닫힌 식)
  · `bed_safe_profile` — 베드에 닿는 레이어의 각도를 B_safe 이하로 낮추고 기존
    블렌드 폭 제약으로 올려 붙인다 (슬라이싱 **전에** 프로필을 고친다)
  · `to_rep5x(bed_clearance=…)` — 그래도 넘는 이동은 B 를 깎는다 (마지막 방어선)
  · `check_rep5x` — 파일 전체(시작/종료 G-code 포함)를 모달 상태 기계로 따라가며
    베드 간섭·native XY 범위·TCP 전환 상태·회전 속도·joint Z 를 본다
"""

import json
import math
import re
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from .config import MAX_SPACING_FACTOR
from .gcode import Move
from .gcode import parse as _parse_gcode
from .profile import AngleProfile, blend_width_for_spacing
from .toolpath import REP5X_V3SE_HOTEND, HotendProfile, hotend_hit, hotend_reach


def _rep5x_hotend():
    # dataclass 기본값으로 인스턴스를 직접 못 넣어서(가변 기본값 금지) 공장 함수로 돌린다.
    return REP5X_V3SE_HOTEND


C_OVERSHOOT_TOL = 0.5   # 이보다 작게 C 창을 넘는 것은 경고 (°) — check_rep5x 참고


@dataclass
class Rep5xProfile:
    """REP5X 기계 파라미터. 기본값은 저장소 `Configuration.h` 에서 가져왔다.

    2026-11-10 에 붙인 것들의 출처는 docs/rep5x_machine_facts.md 다 — 거기 [S] 는
    소스에서 확인, **[실기 확인]** 은 기계 앞에서 대조해야 하는 값이다.
    """

    tilt_axis: str = "B"
    rot_axis: str = "C"
    tilt_sign: float = 1.0          # 실기 보정: 조립이 반대면 -1
    rot_sign: float = 1.0
    b_min: float = -135.0           # J_MIN_POS
    b_max: float = 135.0            # J_MAX_POS
    c_min: float = -360.0           # I_MIN_POS ← 되감기가 필요한 이유
    c_max: float = 360.0            # I_MAX_POS
    # ⚠ 더는 검사에 쓰지 않는다 (2026-11-10). delta 용 상수이고, 이 기계의 한계는
    #   아래 native XY 범위다. 예전 기본값 대조 테스트 때문에 필드는 남긴다.
    printable_radius: float = 100.0  # PRINTABLE_RADIUS
    lb: float = 54.67               # DEFAULT_ROTATIONAL_JOINT_OFFSET_Z  [실기 확인: M665]
    lc: float = 1.6                 # DEFAULT_ROTATIONAL_JOINT_OFFSET_Y  [실기 확인: M665]
    rtcp_on: str = "G43.4"          # RTCP 켜기
    rtcp_off: str = "G49"           # RTCP 끄기
    name: str = "REP5X (Configuration.h 기본값)"
    # ── native 좌표·리밋 (facts §4) ──
    # native X0 Y0 은 **베드 모서리**다. 라이브 TCP 에서 회전이 섞인 이동의 팁 XY 가
    # 이 범위 밖이면 펌웨어가 그 이동을 **조용히 버린다** (M211 과 무관).
    native_x: tuple = (0.0, 200.0)      # X_MIN_POS, X_MAX_POS  [S]
    native_y: tuple = (-40.0, 200.0)    # Y_MIN_POS, Y_MAX_POS  [S]
    bed_center: tuple = (100.0, 100.0)  # 베드 중앙 native 좌표  [실기 확인]
    # G28 직후의 native 위치: X→MAX, Y→MIN, Z→MAX, C 0°, **B −135°**  [S]
    home_xyz: tuple = (200.0, -40.0, 174.6)
    home_b: float = -135.0
    home_c: float = 0.0
    # ── 회전축 속도 상한 (°/s) ──
    # 펌웨어 한계는 3600°/s 지만 그건 '모터가 낼 수 있는 값' 이지 '헤드를 그렇게
    # 돌려도 되는 값' 이 아니다 (Bowden·배선이 딸려 돈다). 90°/s 는 보수적으로 잡은
    # 값이고 근거가 실측이 아니다 — 첫 출력을 보고 조정할 것.
    omega_max: float = 90.0
    # ── 베드 간섭 ──
    hotend: HotendProfile = field(default_factory=_rep5x_hotend)
    bed_clearance: float = 0.2      # 핫엔드 몸체와 베드 사이에 남길 여유 (mm)


REP5X = Rep5xProfile()

# 프로필을 계획할 때 `bed_clearance` 에 더 얹는 여유 (mm). 계획은 반경 포락선으로
# 어림한 팁 높이를 쓰므로, 검사기(같은 식·실제 경로)가 넘지 않게 조금 남긴다.
BED_PLAN_MARGIN = 0.05
# `to_rep5x` 의 이동별 방어선이 쓰는 여유 (mm). 좌표·각도를 소수 3자리로 적으면서
# 생기는 반올림과 이동 안의 보간 오차만 덮으면 되므로 작다.
BED_GUARD_MARGIN = 0.005


def _q(v):
    """G-code 에 적히는 좌표 (소수 3자리). 펌웨어는 **적힌 값**으로 길이를 잰다.

    길이가 0.0004mm 인 이동은 파일에서 길이 0 이 되고, 그러면 펌웨어가 그 줄의 F 를
    mm/min 이 아니라 °/min 으로 읽는다. 생성기와 검사기가 같은 값을 봐야 한다.
    """
    # ⚠ float() 가 필요하다: 좌표가 numpy 스칼라로 올 때 `round(np.float64, 3)` 은
    #   numpy 의 반올림(1000 을 곱해 반올림)이라 `f"{v:.3f}"` 와 끝자리가 어긋나는
    #   값이 있다. 그러면 생성기가 잰 길이와 파일의 길이가 달라 F 상한을 0.02% 넘는다
    #   (원기둥 30° 에서 60개 이동이 90.02°/s — 자체 점검이 잡았다).
    return None if v is None else round(float(v), 3)


# ─────────────────────────────────────────────────────────────
# 베드 간섭 기하: 기운 핫엔드 모델의 최저점
# ─────────────────────────────────────────────────────────────
def _rim_terms(hotend, clearance):
    """테두리별 (높이 a, 뻗음 ρ, 그 테두리에 요구할 여유).

    ρ 는 **양쪽 중 큰 값**을 쓴다. 모델은 틸트 방향으로 비대칭이지만(블록 편심·
    케이블), ① 축 통과 때 B 부호가 뒤집혀 양쪽이 다 나오고 ② 조립 부호가 실기
    확인 전이라 어느 쪽이 내려가는지 믿을 수 없다.

    a=0 인 테두리(팁 평면)에는 여유를 요구하지 않는다 — 팁은 원래 층에 닿는
    부분이다. 베드 **아래로** 내려가는 것만 막는다.
    """
    return [(a, max(rp, rm), clearance if a > 1e-9 else 0.0)
            for a, rp, rm in hotend.bed_rims()]


def bed_gap(tip_z, b_deg, hotend=None, clearance=0.2):
    """팁이 높이 `tip_z` 에 있고 `b_deg` 만큼 기울었을 때 **베드 여유선까지 남은 거리** (mm).

    음수면 핫엔드 모델이 베드 위 `clearance` 안으로 들어온 것이다(= 간섭).

        테두리 최저점 = tip_z + a·cos|B| − ρ·sin|B|

    C 는 안 들어간다: 베드가 수평이라 최저점은 틸트 크기에만 달려 있다.
    |B| > 90° (공구가 위를 본다)이면 a 대신 모델 꼭대기를 쓴다 — 보수적 근사다.
    """
    h = hotend or REP5X_V3SE_HOTEND
    b = abs(math.radians(b_deg))
    cb, sb = math.cos(b), math.sin(b)
    top = h.top()
    return min(tip_z + (a if cb >= 0.0 else top) * cb - rho * sb - clr
               for a, rho, clr in _rim_terms(h, clearance))


def b_safe(tip_z, hotend=None, clearance=0.2, b_cap=89.0):
    """팁 높이 `tip_z` 에서 베드 여유를 지키는 **최대 |B|** (도). 닫힌 식이다.

    테두리 하나의 조건 `a·cosB − ρ·sinB ≥ d` (d = 여유 − tip_z) 는
    R = √(a²+ρ²), φ = atan2(ρ, a) 로 `R·cos(B+φ) ≥ d` 이고, 좌변이 [0°, 90°] 에서
    단조 감소라

        B ≤ acos(d/R) − φ

    전 테두리의 최솟값이 답이다. B=0 에서도 못 지키면(팁이 너무 낮다) 0 을 돌려준다.
    팁이 베드 아래(tip_z < 0)면 어떤 자세도 안 된다 → 0.
    """
    h = hotend or REP5X_V3SE_HOTEND
    if tip_z < -1e-9:
        return 0.0
    lim = float(b_cap)
    for a, rho, clr in _rim_terms(h, clearance):
        d = clr - tip_z
        if d > a + 1e-12:
            return 0.0
        r = math.hypot(a, rho)
        if r < 1e-12 or d <= -r:
            continue
        lim = min(lim, math.degrees(math.acos(min(1.0, d / r))
                                    - math.atan2(rho, a)))
    return max(0.0, lim)


def tip_height_needed(b_deg, hotend=None, clearance=0.2):
    """|B| 로 기운 채 베드 여유를 지키려면 팁이 얼마나 높아야 하나 (mm, `b_safe` 의 역)."""
    return -bed_gap(0.0, b_deg, hotend, clearance)


# ─────────────────────────────────────────────────────────────
# 베드 안전 프로필: 베드에 닿는 레이어의 각도를 B_safe 이하로
# ─────────────────────────────────────────────────────────────
def _layer_tip_floor(zw, tan_th, rp, layer_height):
    """outward 레이어 Z′ 에서 팁이 내려갈 수 있는 **가장 낮은 높이** (배열).

    슬라이서는 변환공간에서 Z′−h/2 를 잘라 Z′ 높이에 낸다. 그래서 낸 점의 실제
    높이는 '자른 면 위 메시 점의 높이 + h/2' 다. 메시 점은 반경 포락선 r_env(z)
    안에 있으므로, 원뿔 `z = Zc − r·tanθ` 가 포락선 안으로 들어오는 가장 낮은 z 가
    하한이다 (그런 z 가 없으면 그 레이어에는 재료가 없다 → +inf).

    ⚠ 포락선은 `RadiusProfile` 의 칸별 최대 반경(정점 기준)이다. 반경이 클수록
      레이어가 더 낮게 내려오므로 최댓값을 쓰는 것이 보수적이다.
    """
    zk = rp.z0 + rp.h * np.arange(rp.n)             # 칸의 아래 끝
    zc = np.asarray(zw, dtype=float) - layer_height / 2.0
    cand = np.maximum(zk[None, :], zc[:, None] - rp.rmax[None, :] * tan_th[:, None])
    ok = (cand <= zk[None, :] + rp.h + 1e-9) & (cand <= zc[:, None] + 1e-9)
    return np.where(ok, cand, np.inf).min(axis=1) + layer_height / 2.0


def bed_tilt_cap(zw, radius_profile, layer_height, hotend=None, clearance=0.2,
                 inward=False, hi=80.0):
    """레이어 Z′(배열)마다 베드와 안 닿고 쓸 수 있는 **최대 |θ|** (도).

    레이어의 팁 최저 높이 h_low(Z′, θ) 와 그 각도가 요구하는 팁 높이
    `tip_height_needed(θ)` 를 맞춘다. θ 가 커지면 레이어는 더 낮게 내려오고
    (outward) 필요한 높이는 더 커지므로 가능 영역이 구간 [0, θ*] 이다 → 이분법.

      · outward: h_low = `_layer_tip_floor` (반경 포락선이 필요하다)
      · inward : 레이어 `z = Z′ + r·tan|θ|` 의 최저점은 축(r=0) 쪽이라
                 h_low = h/2 + max(0, Z′ − h/2). 닫힌 식 `b_safe` 로 끝난다

    어느 레이어든 팁은 층고의 절반보다 낮아지지 않으므로 답은 항상
    `b_safe(h/2)` 이상이다.
    """
    h = hotend or REP5X_V3SE_HOTEND
    zw = np.asarray(zw, dtype=float)
    half = layer_height / 2.0
    if inward:
        return np.array([b_safe(half + max(0.0, z - half), h, clearance, hi)
                         for z in zw])
    lo = np.full(len(zw), min(hi, b_safe(half, h, clearance, hi)))
    up = np.full(len(zw), float(hi))
    for _ in range(32):
        mid = 0.5 * (lo + up)
        tip = _layer_tip_floor(zw, np.tan(np.radians(mid)), radius_profile,
                               layer_height)
        need = np.array([tip_height_needed(m, h, clearance) for m in mid])
        ok = tip >= need
        lo, up = np.where(ok, mid, lo), np.where(ok, up, mid)
    return lo


def _ramp_width(z_a, dtan, sign, rp, limit, min_blend, t_top):
    """θ_bed → θ_top 을 올려 붙이는 블렌드의 최소 폭 (기존 층간격 제약 그대로).

    반경은 **그 블렌드의 레이어가 지나가는 높이 전체**의 최댓값을 쓴다: outward
    레이어는 바닥까지 내려오고, inward 레이어는 위로 r·tanθ 만큼 올라간다.
    `AngleProfile.validate` 가 전 모델 반경으로 가역성을 보므로 그 폭(여유 1.5배,
    `from_bands` 와 같다)도 함께 지킨다.
    """
    w = max(min_blend, 1.5 * rp.global_max * dtan if sign > 0 else min_blend)
    for _ in range(40):
        if sign > 0:
            r_b = rp.max_between(rp.z0, z_a + w)
        else:
            r_b = rp.max_between(z_a, z_a + w + rp.global_max * t_top)
        w_new = max(w, blend_width_for_spacing(r_b, sign * dtan, "outward", limit))
        if w_new <= w * (1.0 + 1e-4):
            return w_new
        w = w_new
    return w


def _fit_ramp(zw, cap, t_bed, t_top, sign, rp, limit, min_blend):
    """cap 곡선 아래에 들어가는 (시작 Z′, 끝 Z′) 를 찾는다. 없으면 None.

    가장 좁은 폭만 쓰면 cap 이 완만하게 오르는 형상(구의 아랫면)에서 늦게 시작해야
    한다. 더 넓고 일찍 시작하는 쪽이 각도를 덜 잃을 수 있어 폭 배수 몇 개를 같이
    보고, **블렌드 중심이 가장 낮은** 것을 고른다(잃는 각도의 넓이가 그에 비례).
    """
    d = t_top - t_bed
    low_top = np.where(cap < t_top - 1e-9)[0]       # 꼭대기 각도를 못 쓰는 레이어
    if len(low_top) and low_top[-1] + 1 >= len(zw):
        return None
    z_free = zw[low_top[-1] + 1] if len(low_top) else zw[0]
    best = None
    for mult in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
        for z_a in zw:
            # 폭은 0.01mm 로 올림 — 넓은 쪽이 안전하고 프로필 숫자가 깔끔해진다
            w = math.ceil(_ramp_width(z_a, d, sign, rp, limit, min_blend, t_top)
                          * mult * 100.0 - 1e-9) / 100.0
            z_b = z_a + w
            if z_b < z_free - 1e-9:
                continue
            seg = (zw >= z_a) & (zw <= z_b)
            if np.all(t_bed + d * (zw[seg] - z_a) / w <= cap[seg] + 1e-9):
                if best is None or z_a + w / 2.0 < best[0] - 1e-9:
                    best = (z_a + w / 2.0, round(float(z_a), 6),
                            round(float(z_b), 6))
                break                               # 이 배수에서는 가장 낮은 시작이 최선
    return None if best is None else best[1:]


def bed_safe_profile(requested, radius_profile, layer_height, hotend=None,
                     clearance=0.2, spacing_limit=MAX_SPACING_FACTOR,
                     margin=BED_PLAN_MARGIN, min_blend=0.5, grid=0.05):
    """요청한 각도 프로필을 **핫엔드가 베드에 안 닿게** 고친다 → (프로필, 정보 dict).

    ## 문제

    헤드 회전식은 노즐이 레이어 법선을 따라 기운다. 첫 층들은 팁이 Z≈층고에 있는데
    B 가 24~30° 면 노즐 몸통이 베드를 친다 (`bed_gap`). 팁 높이 h 에서 쓸 수 있는
    최대 틸트가 `b_safe(h)` 다.

    ## 하는 것

      ① θ_bed = b_safe(층고/2) — 팁은 층고의 절반보다 낮아지지 않으므로, 이 각도
         이하인 레이어는 **어디를 지나가든** 안전하다
      ② 레이어별 상한 cap(Z′) (`bed_tilt_cap`) — 그 레이어가 실제로 내려가는
         높이에서 허용되는 각도. 베드에서 멀어질수록 커진다
      ③ θ_bed 로 시작해 cap 아래로 올라가는 직선(tanθ 선형) 램프를 **기존 블렌드 폭
         제약**(`blend_width_for_spacing`, 층간격 배율 [1/limit, limit])으로 놓는다
      ④ 새 프로필 = 요청 프로필을 그 램프로 **잘라낸** 것 (부호별: outward 는 위에서,
         inward 는 아래에서). 요청이 이미 램프 아래면 그대로 둔다

    램프 자리가 없으면(부품이 낮거나 cap 이 끝까지 안 올라오면) 그 방향 전체를
    θ_bed 로 낮춘다 — 안 닿는 것이 각도보다 먼저다.

    ## 왜 '자동으로 낮추기' 가 기본이고 `--strict` 가 선택인가

    요청 각도가 못 쓰는 값이라고 **멈추면** 사용자는 각도를 손으로 낮춰 다시
    돌리게 되는데, 그러면 **모델 전체**의 각도가 내려간다. 필요한 것은 바닥
    몇 mm 만 낮추는 것이고 그 계산(베드 간섭 + 블렌드 폭)을 사람이 손으로 할 수는
    없다. 그래서 기본은 고쳐서 내고, **무엇을 바꿨는지 반드시 출력한다**
    (`info["notes"]`, 프로필의 `.notes`). 조용히 바꾸지 않는다.

    다만 실험에서는 '요청한 각도 그대로' 가 조건일 때가 있다(균일 원뿔 대조군).
    그때는 `--strict` 로 멈추게 한다 — 바뀐 프로필로 비교하면 결론이 틀어진다.

    ⚠ 여기서 쓰는 팁 높이는 **반경 포락선으로 어림한 하한**이다(내장 슬라이서의
      '레이어 가운데를 잘라 위에 낸다' 를 가정). 그래서 `clearance` 에 `margin` 을
      얹어 계획하고, 실제 경로는 `to_rep5x(bed_clearance=…)` 의 이동별 방어선과
      `check_rep5x` 가 다시 본다.

    정보 dict: changed, theta_bed, tip_floor, ramps{부호: (Z′ 시작, 끝) 또는 None},
               notes[사람이 읽는 설명]
    """
    h = hotend or REP5X_V3SE_HOTEND
    rp = radius_profile
    clr = clearance + margin
    limit = spacing_limit if spacing_limit and spacing_limit > 1.0 \
        else MAX_SPACING_FACTOR
    half = layer_height / 2.0
    th_bed = math.floor(b_safe(half, h, clr) * 100.0) / 100.0
    t_bed = math.tan(math.radians(th_bed))
    info = {"changed": False, "theta_bed": th_bed, "tip_floor": half,
            "clearance": clearance, "margin": margin, "ramps": {}, "notes": []}
    if float(np.max(np.abs(requested.thetas_deg))) <= th_bed + 1e-9:
        return requested, info

    t_abs = float(np.max(np.abs(requested.tans)))
    reach = rp.global_max * t_abs + 1.0
    zw = grid * np.arange(math.floor((rp.z0 - reach) / grid),
                          math.ceil((rp.z1 + reach) / grid) + 1)
    t_req = requested.tan_at(zw)
    limits = {}                                     # 부호 → 크기 상한 함수 R(Z′)
    for sign in (1.0, -1.0):
        t_top = float(np.max(sign * requested.tans))
        if t_top <= t_bed + 1e-12:
            continue
        cap = np.tan(np.radians(bed_tilt_cap(zw, rp, layer_height, h, clr,
                                             inward=sign < 0)))
        if np.all(sign * t_req <= cap + 1e-9):
            continue                                # 이 방향은 요청대로 안전하다
        name = "outward" if sign > 0 else "inward"
        th_top = math.degrees(math.atan(t_top))
        fit = _fit_ramp(zw, cap, t_bed, t_top, sign, rp, limit, min_blend)
        info["ramps"][name] = fit
        if fit is None:
            limits[sign] = ((float(zw[0]),), (t_bed,))
            info["notes"].append(
                f"베드 안전({name}): 요청 {th_top:.1f}° 를 올려 붙일 자리가 없어 "
                f"그 방향 전체를 {th_bed:.1f}° 로 낮췄다")
        else:
            limits[sign] = (fit, (t_bed, t_top))
            info["notes"].append(
                f"베드 안전({name}): Z′ ≤ {fit[0]:.2f} 는 {th_bed:.1f}° 로 낮추고 "
                f"Z′ {fit[0]:.2f}~{fit[1]:.2f} (폭 {fit[1] - fit[0]:.2f}mm) 에서 "
                f"{th_top:.1f}° 로 올린다")
    if not limits:
        return requested, info

    def build(lims):
        def bound(sign, z):
            if sign not in lims:
                return np.full(np.shape(z), np.inf)
            return np.interp(z, lims[sign][0], lims[sign][1])

        # 꺾이는 점: 요청의 브레이크포인트 + 램프 양 끝 + 둘이 만나는 점.
        # 이웃한 두 점 사이에서는 요청도 램프도 직선이라 교점이 닫힌 식으로 나온다.
        zs = sorted({float(z) for z in requested.zs}
                    | {float(z) for lim in lims.values() for z in lim[0]})
        cross = []
        for sign in lims:
            g = sign * requested.tan_at(np.array(zs)) - bound(sign, np.array(zs))
            for i in range(len(zs) - 1):
                if g[i] * g[i + 1] < 0.0:
                    cross.append(zs[i] + (zs[i + 1] - zs[i]) * g[i] / (g[i] - g[i + 1]))
        zs = sorted(set(zs) | set(cross))
        zs = [z for i, z in enumerate(zs) if i == 0 or z - zs[i - 1] > 1e-9]
        za = np.array(zs)
        ts = [float(t) for t in np.minimum(
            np.maximum(requested.tan_at(za), -bound(-1.0, za)), bound(1.0, za))]
        keep = [0] + [i for i in range(1, len(zs) - 1)
                      if abs((ts[i] - ts[i - 1]) * (zs[i + 1] - zs[i])
                             - (ts[i + 1] - ts[i]) * (zs[i] - zs[i - 1])) > 1e-12] \
            + ([len(zs) - 1] if len(zs) > 1 else [])
        prof = AngleProfile([(zs[i], round(math.degrees(math.atan(ts[i])), 6))
                             for i in keep])
        prof.validate(rp.global_max, "outward")
        return prof

    try:
        new = build(limits)
    except ValueError as err:
        # 램프를 얹은 프로필이 가역성 검사에 걸렸다(반경 어림이 빗나간 드문 경우).
        # 평평하게 자르면 기울기가 요청보다 커지지 않으므로 요청이 통과했다면 통과한다.
        flat = {sign: ((float(zw[0]),), (t_bed,)) for sign in limits}
        new = build(flat)
        info["ramps"] = dict.fromkeys(info["ramps"])
        info["notes"] = [f"베드 안전: 올려 붙이는 블렌드가 가역성 검사에 걸려 "
                         f"({str(err)[:60]}…) 요청 각도를 전부 {th_bed:.1f}° 로 낮췄다"]
    new.notes = list(getattr(requested, "notes", [])) + info["notes"]
    info["changed"] = True
    return new, info


def tool_direction(b_deg, c_deg):
    """(B, C) → 공구 방향 단위벡터 `d̂ = Rz(C)·Ry(B)·(0,0,−1)`.

    검증용 역함수다. `to_rep5x` 가 낸 각도를 이걸로 되돌려 원뿔 법선과 맞춰본다.
    """
    b, c = math.radians(b_deg), math.radians(c_deg)
    return (-math.sin(b) * math.cos(c),
            -math.sin(b) * math.sin(c),
            -math.cos(b))


def cone_tool_direction(x, y, cone_angle_deg, cone_type):
    """원뿔 레이어 법선의 반대 = 노즐이 향해야 할 방향 (해석식)."""
    th = math.radians(cone_angle_deg) * (1.0 if cone_type == "outward" else -1.0)
    r = math.hypot(x, y)
    if r < 1e-12:
        return (0.0, 0.0, -1.0)
    return (-math.sin(th) * x / r, -math.sin(th) * y / r, -math.cos(th))


def _layer_thetas(items, angle_profile):
    """이동마다 그 점이 놓인 **레이어의 각도** θ(Z′) (부호 있는 도, 모달 좌표 반영).

    가변각에서도 레이어 하나는 각도 하나짜리 원뿔이다(`z = Z′ − r·tanθ(Z′)`, Z′ 고정).
    그래서 점의 (z, r) 로 Z′ 를 정확히 되풀면(`AngleProfile.solve_forward`) 그 점의
    레이어 법선 = sinθ·r̂ + cosθ·ẑ 이고, 공구 틸트는 B = c·θ(Z′) 가 된다.
    좌표가 아직 안 정해진 이동은 None.
    """
    x = y = z = None
    idx, zs, rs = [], [], []
    for i, (kind, mv) in enumerate(items):
        if kind != "move":
            continue
        x = mv.x if mv.x is not None else x
        y = mv.y if mv.y is not None else y
        z = mv.z if mv.z is not None else z
        if None in (x, y, z):
            continue
        idx.append(i)
        zs.append(z)
        rs.append(math.hypot(x, y))
    th = {}
    if idx:
        zarr, rarr = np.asarray(zs), np.asarray(rs)
        try:
            zp = angle_profile.solve_forward(zarr, rarr, "outward")
        except RuntimeError:
            # 해가 없는 점(가역 범위 밖의 트래블 등)은 하나씩 풀고, 못 풀면 직전 값.
            zp = np.full(len(idx), np.nan)
            for k in range(len(idx)):
                try:
                    zp[k] = angle_profile.solve_forward(zarr[k:k + 1], rarr[k:k + 1],
                                                        "outward")[0]
                except RuntimeError:
                    zp[k] = zp[k - 1] if k else zarr[k]
        for i, t in zip(idx, angle_profile.theta_at(zp), strict=True):
            th[i] = float(t)
    return th


def to_rep5x(items, cone_angle_deg, cone_type, profile=REP5X, pole_flip=True,
             emit_rtcp=True, bed_clearance=None):
    """원뿔 G-code(부품좌표) → REP5X G-code. **좌표는 그대로 두고 B/C 만 붙인다.**

    cone_angle_deg: 상수 각도(도) 또는 `AngleProfile`(가변각). 가변각이면 점마다
      자기 레이어의 θ(Z′) 로 B 를 정한다 — cone_type 은 무시(프로필 각도에 부호가 있다).

    pole_flip (2026-10-16): 공구 방향은 (B, C) 와 (−B, C+180°) 가 **같다.** 경로가 축을
      지나가면 방위각이 180° 뒤집히는데, 예전에는 그때마다 C 를 180° 돌렸다(헤드
      급회전, `check_rep5x` 경고). 이동마다 두 해 중 직전 자세에서 덜 움직이는 쪽을
      고르면 축 통과는 **B 를 2θ 넘기는 것**으로 바뀐다 (5축 가공의 '극 통과' 처리).
      그리고 θ=0 레이어는 공구가 수직이라 C 가 의미가 없으므로 **C 를 그대로 둔다.**

      ⚠ 남는 것: 축 근처(r≲3mm)에서는 짧은 이동에도 방위각이 크게 돌아 C 가 한
      걸음에 30~100° 움직인다(램프 24° 에서 441회, 전부 r<3mm). 정확 추종의 본성이다.
      꼭짓점 근처 틸트를 줄이고 C 를 오차 허용 안에서 늦게 따라가게 하는 완화를
      시험했으나(r_p 1~3mm, 허용 1~2°) 30° 초과 걸음이 줄지 않고(430~460회) 축 근처
      공구 방향 오차만 최대 24° 생겨 **넣지 않았다** (docs/verification.md 2026-10-16).
      → 그 걸음들이 헤드를 축 한계까지 돌리지 않게 `limit_rotary_speed` 가 F 를 깎는다.

    emit_rtcp (2026-11-10): 헤더에 `G43.4` 를 넣을지. **기계 프로파일의 시작 G-code 가
      이미 켰으면 False 로 준다** — TCP 는 B0 C0 에서 **한 번만** 켜야 하고, 그 자리는
      호밍·프라임·원점 선언이 끝난 시작 G-code 의 맨 끝이다. 경로만 내는 경우(기계
      프로파일 없음)에는 True 로 두어 파일이 X/Y/Z 를 팁 좌표로 선언하게 한다.

      헤더는 더 이상 `G1 B.. F600 ; tilt head` 를 내지 않는다. 이동 줄에 주석이
      붙으면 M668(SD 전처리)이 못 읽고, 틸트는 TCP 를 켠 **뒤** 첫 자세로 가면서
      하면 된다 — `limit_rotary_speed` 가 첫 이동 앞에 회전만 하는 줄을 넣는다.

    bed_clearance (2026-11-10): 주면 **이동별 베드 방어선**을 건다 — 그 이동의 팁
      높이에서 `b_safe` 를 넘는 틸트는 그만큼 깎는다(`bed_clamped` 로 센다).
      이건 마지막 방어선이다. 틸트를 깎으면 공구가 레이어 법선에서 벗어나므로,
      제대로 된 대책은 슬라이싱 **전에** 프로필을 고치는 것이다(`bed_safe_profile`).
      그쪽이 맞게 됐으면 여기서는 0건이 나온다. None 이면 끈다(예전 동작).

    반환: (아이템 리스트, 통계 dict)
    """
    variable = hasattr(cone_angle_deg, "solve_forward")
    if variable:
        th_of = _layer_thetas(items, cone_angle_deg)
        c_dir = 1.0
        th_all = [float(t) for t in cone_angle_deg.thetas_deg]
        a_max = max(th_all, key=abs)
    else:
        c_dir = 1.0 if cone_type == "outward" else -1.0
        a_max = float(cone_angle_deg)
    if abs(a_max) > max(abs(profile.b_min), abs(profile.b_max)):
        raise ValueError(f"cone angle {a_max} > B 축 한계 "
                         f"[{profile.b_min}, {profile.b_max}]")
    b_const = None if variable else profile.tilt_sign * c_dir * float(cone_angle_deg)
    b0 = b_const if b_const is not None else profile.tilt_sign * th_all[0]

    # ⚠ 명령 줄에는 주석을 붙이지 않는다 (M668 전처리 호환 — facts §10).
    out = [("raw", "; REP5X 5-axis conical mode [EXPERIMENTAL]"),
           ("raw", "; head-head kinematics: firmware does the IK "
                   "(PENTA_AXIS_HH), X/Y/Z = nozzle tip"),
           ("raw", f"; {profile.tilt_axis}="
                   + (f"{b_const:.3f}deg" if b_const is not None
                      else "per-layer theta(Z') (variable angle)")
                   + f", {profile.rot_axis} tracks azimuth (continuous, unwrapped)"
                   + ("; pole crossing by B sign flip" if pole_flip else "")),
           ("raw", f"; LB={profile.lb} LC={profile.lc} "
                   f"(verify on machine; axis signs too)")]
    if emit_rtcp:
        out += [("raw", "; enable tool centerpoint control (RTCP) - only at B0 C0"),
                ("raw", profile.rtcp_on)]
    else:
        out.append(("raw", f"; RTCP ({profile.rtcp_on}) is enabled by the machine "
                           f"start G-code at B0 C0"))

    def unwrap(c_raw, ref):
        return c_raw + 360.0 * round((ref - c_raw) / 360.0)

    guard_clr = None if bed_clearance is None else bed_clearance + BED_GUARD_MARGIN
    x = y = z = None
    c_prev, b_prev = 0.0, b0
    branch = 1.0                    # +1: (B, φ) / −1: (−B, φ+180°)
    c_range = [0.0, 0.0]
    b_range = [b0, b0]
    babs = [abs(b0), abs(b0)]
    n_on_axis = n_flip = n_hold = n_guard = 0
    guard_max = 0.0
    first = True
    for i, (kind, payload) in enumerate(items):
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
        b_nom = b_const if b_const is not None else \
            profile.tilt_sign * th_of.get(i, th_all[0])
        if guard_clr is not None:
            # 소수 3자리로 **내려** 적는다 — 올림이 되면 방어선을 0.0005° 넘는다.
            lim = math.floor(b_safe(_q(z), profile.hotend, guard_clr) * 1000.0) / 1000.0
            if abs(b_nom) > lim:
                n_guard += 1
                guard_max = max(guard_max, abs(b_nom) - lim)
                b_nom = math.copysign(lim, b_nom)
        r = math.hypot(x, y)
        if abs(b_nom) < 1e-9:
            b, c = 0.0, c_prev              # 수직 공구: C 무관 → 돌리지 않는다
            n_hold += 1
        elif r < 1e-6:
            b, c = branch * b_nom, c_prev   # 축 위: 방위각 정의 불가 → 유지
            n_on_axis += 1
        else:
            phi = profile.rot_sign * math.degrees(math.atan2(y, x))
            ca = unwrap(phi, c_prev)
            cand = [(abs(ca - c_prev) + abs(b_nom - b_prev), 1.0, b_nom, ca)]
            if pole_flip and not first:     # 첫 자세는 기준이 없으니 자연해(B, φ)
                cb = unwrap(phi + 180.0, c_prev)
                cand.append((abs(cb - c_prev) + abs(-b_nom - b_prev), -1.0, -b_nom, cb))
            _cost, br, b, c = min(cand, key=lambda t: (t[0], -t[1]))
            if br != branch:
                n_flip += 1
                branch = br
        # 좌표·피드는 **그대로**. 이것이 Open5x 와의 차이다.
        # (피드 상한은 되감기까지 끝난 뒤 `limit_rotary_speed` 가 건다.)
        out.append(("move", Move(g=mv.g, x=mv.x, y=mv.y, z=mv.z, e=mv.e,
                                 f=mv.f,
                                 extra=f"{profile.tilt_axis}{b:.3f} "
                                       f"{profile.rot_axis}{c:.3f}")))
        c_prev, b_prev = c, b
        if r >= 1e-6 and abs(b_nom) >= 1e-9:
            first = False
        c_range[0] = min(c_range[0], c)
        c_range[1] = max(c_range[1], c)
        b_range[0] = min(b_range[0], b)
        b_range[1] = max(b_range[1], b)
        babs[0] = min(babs[0], abs(b))
        babs[1] = max(babs[1], abs(b))

    return out, {"b": b_const if b_const is not None else b0,
                 "b_min": b_range[0], "b_max": b_range[1],
                 "b_abs_min": babs[0], "b_abs_max": babs[1],
                 "variable": variable,
                 "c_min": c_range[0], "c_max": c_range[1],
                 "c_turns": (c_range[1] - c_range[0]) / 360.0,
                 "on_axis_moves": n_on_axis, "pole_flips": n_flip,
                 "c_held_vertical": n_hold,
                 "bed_clamped": n_guard, "bed_clamp_max_deg": guard_max}


# ─────────────────────────────────────────────────────────────
# 회전축 속도 상한 — 파이프라인의 마지막 패스
# ─────────────────────────────────────────────────────────────
def _bc_words(extra, profile):
    """extra 문자열의 (B, C) 워드. 없는 축은 None."""
    b = c = None
    for tok in (extra or "").split():
        t = tok.upper()
        try:
            if t.startswith(profile.tilt_axis.upper()):
                b = float(tok[len(profile.tilt_axis):])
            elif t.startswith(profile.rot_axis.upper()):
                c = float(tok[len(profile.rot_axis):])
        except ValueError:
            pass
    return b, c


def _floor_feed(f):
    """`gcode.format_feed` 가 적는 자릿수로 **내린** F. 올림이 되면 상한을 넘는다."""
    if f >= 100.0:
        return float(math.floor(f))
    return max(0.001, math.floor(f * 1000.0) / 1000.0)


def limit_rotary_speed(items, profile=REP5X, orient_feed=1800.0):
    """회전축이 `profile.omega_max` (°/s) 를 넘지 않게 이동마다 F 를 깎는다.

    ## 왜 (facts §7)

    REP5X Marlin 은 XYZ 가 움직이는 이동의 F 를 **팁 XYZ 경로 길이에만** 적용한다.
    회전량은 F 에 들어가지 않는다. 그래서 길이 L 인 이동의 시간은 `L/F` 뿐이고,
    그 사이에 C 가 45° 돌아야 하면 그냥 그 속도로 돈다 — 축 근처의 0.03mm 짜리
    이동(F1800)이면 **46,000°/s** 를 요구받아 축 한계(3600°/s)까지 가속한다.

    ## 어떻게

        t  = max(L/F, max(|ΔB|, |ΔC|)/ω_max)        ← 이동에 걸려야 하는 시간
        F′ = L/t                                     ← 그 시간이 나오는 피드

    **회전만 하는 이동**(L=0)은 펌웨어가 F 를 °/min 으로 읽는다 → `ω_max·60` 이하로.
    지시서는 "= ω_max·60" 이었는데 **min 을 썼다**: 일부러 느리게 지정한 회전
    (되감기 `--v-rewind-feed`, 종료 G-code)을 상한까지 끌어올릴 이유가 없다.

    ⚠ L 은 **파일에 적히는 값**(소수 3자리)으로 잰다. 0.0004mm 짜리 이동은 파일에서
      길이 0 이 되어 펌웨어가 F 를 °/min 으로 읽는다. 그걸 mm/min 으로 깎아 F0.05 를
      적으면 45° 를 15시간 동안 돈다.
    ⚠ F 는 모달이다. 깎은 줄 다음 줄에 F 가 없으면 깎인 값이 이어지므로, 그런 줄에는
      원래 피드를 **다시 적는다** (외부 슬라이서는 F 를 바뀔 때만 낸다).

    ## 첫 자세

    시작 G-code 는 B0 C0 에서 TCP 를 켜고 끝난다. 첫 경로 이동이 (B, C) 를 바꾸면
    그 이동은 **출발점을 모르는 채**(시작 위치는 기계 프로파일에 있다) 회전하게
    되어 깎을 수가 없다. 그래서 첫 자세가 0 이 아니면 그 앞에 **회전만 하는 줄**
    `G0 F.. B.. C..` 을 넣는다 (`orient_feed` °/min, 상한 이하). 그러면 첫 이동은
    회전 없는 순수 이동이 된다.

    반환: (아이템 리스트, 통계 dict)
    """
    w = float(profile.omega_max)
    rot_cap = w * 60.0
    out = []
    x = y = z = None
    b = c = None
    f_in = f_out = None
    n_cap = n_rot = n_orient = 0
    t_added = 0.0
    f_min = None
    for kind, mv in items:
        if kind != "move":
            out.append((kind, mv))
            continue
        bw, cw = _bc_words(mv.extra, profile)
        nb = bw if bw is not None else b
        nc = cw if cw is not None else c
        nx = _q(mv.x) if mv.x is not None else x
        ny = _q(mv.y) if mv.y is not None else y
        nz = _q(mv.z) if mv.z is not None else z
        if mv.f is not None:
            f_in = mv.f
        if b is None and c is None and (bw is not None or cw is not None):
            # 첫 자세: 시작 G-code 가 남긴 B0 C0 에서 회전만으로 먼저 맞춘다.
            b, c = nb or 0.0, nc or 0.0
            nb, nc = b, c
            if abs(b) > 1e-9 or abs(c) > 1e-9:
                f_out = _floor_feed(min(orient_feed, rot_cap))
                out.append(("move", Move(
                    g=0, f=f_out,
                    extra=f"{profile.tilt_axis}{b:.3f} {profile.rot_axis}{c:.3f}")))
                n_orient += 1
        db = abs(nb - b) if None not in (nb, b) else 0.0
        dc = abs(nc - c) if None not in (nc, c) else 0.0
        dth = max(db, dc)
        f_des = f_in
        if dth > 1e-9:
            known = None not in (x, y, z, nx, ny, nz)
            # 출발점을 모르면(위의 첫 자세 처리 덕에 일어나지 않는다) 회전만으로 본다.
            length = math.dist((x, y, z), (nx, ny, nz)) if known else 0.0
            if length < 5e-4:
                n_rot += 1
                if f_in is None or f_in > rot_cap:
                    f_des = _floor_feed(rot_cap)
            else:
                f_cap = 60.0 * length * w / dth
                if f_in is None or f_in > f_cap:
                    f_des = _floor_feed(f_cap)
                    n_cap += 1
                    if f_in is not None:
                        t_added += 60.0 * length * (1.0 / f_des - 1.0 / f_in)
            f_min = f_des if f_min is None else min(f_min, f_des)
        emit = f_des if (f_des is not None and
                         (mv.f is not None or f_des != f_out)) else None
        if emit is not None:
            f_out = emit
        out.append(("move", Move(g=mv.g, x=mv.x, y=mv.y, z=mv.z, e=mv.e, f=emit,
                                 extra=mv.extra)))
        x, y, z, b, c = nx, ny, nz, nb, nc
    return out, {"capped": n_cap, "rotation_only": n_rot, "oriented": n_orient,
                 "added_seconds": t_added, "min_feed": f_min,
                 "omega_max": w}


_CMD_WORD = re.compile(r"([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
_MOVE_LINE = re.compile(r"^\s*[Gg]0*[01](?![\d.])")


def _normalized(items):
    """raw 문자열로 들어온 G0/G1 줄을 Move 로 다시 읽는다.

    `to_rep5x` 의 헤더와 기계 프로파일의 시작/종료 G-code 는 메모리 안에서는 raw
    문자열이다. 파일로 쓴 뒤 다시 읽으면 Move 가 된다. 검사기가 두 경우에 같은
    답을 내려면 여기서 맞춰야 한다.
    """
    for kind, payload in items:
        if kind == "raw" and isinstance(payload, str) and _MOVE_LINE.match(payload):
            yield _parse_gcode([payload])[0]
        else:
            yield kind, payload


def _modal(cur, val, rel):
    """모달 좌표 갱신: 워드가 없으면 유지, G91 이면 더한다 (모르는 값엔 못 더한다)."""
    if val is None:
        return cur
    if rel:
        return None if cur is None else cur + val
    return val


def check_rep5x(items, profile=REP5X, max_dc_deg=30.0, max_feed=None):
    """REP5X G-code 를 기계에 걸기 **전에** 검사한다 (검사기 C 의 REP5X 판).

    Open5x 판(`check_open5x`)과 **보는 것이 다르다.** 슬라이서가 기계좌표가 아니라
    **팁 좌표 + 공구 방향**을 내므로, 좌표 변환 대신 **펌웨어가 그 파일을 어떻게
    받아들이는가**가 핵심이다.

    ## 파일 전체를 모달 상태 기계로 따라간다 (2026-11-10)

    예전에는 B/C 워드만 모아 범위를 봤다. 그래서 **시작 G-code 가 틀린 것을 못
    봤다** — 실제로 뽑아 둔 예시 파일이 G28(B 를 −135° 로 호밍) 뒤 B 를 0 으로
    되돌리지 않고 프라임 선을 긋고, 그 상태로 `G43.4` 를 켰다. 지금은 시작·종료
    G-code 까지 포함해 한 줄씩 상태를 따라간다:

        G28            → B = −135°(홈), C = 0°, XYZ = 홈 위치, G92 오프셋 해제
        G43.4 / G49    → TCP 켬 / 끔
        G92            → 원점 이동 (native = G-code 좌표 + 오프셋)
        G90/G91, M82/M83, T<n>, M211

    보는 것 (심각도):
      · **베드 간섭** [치명] — 기운 핫엔드 모델(`profile.hotend`)의 최저점이 베드 위
        `bed_clearance` 아래로 내려가는 이동. 이동 안에서 (Z, B) 를 보간해 본다.
        팁 자체가 Z<0 인 이동도 치명이다
      · **native XY 범위** [치명] — 팁 XY 가 native [0,200]×[−40,200] 밖. 라이브
        TCP 에서 범위 밖의 회전 이동은 **조용히 버려진다**
      · **상태** [치명] — TCP 없이 B/C≠0 인 채 압출(G28 뒤 B0 C0 복귀 누락),
        B/C≠0 에서 `G43.4`/`G49` 전환, T1/T2, 기운 채 `G92 B0`
      · **회전 속도** [치명] — 이동이 요구하는 회전축 속도가 `omega_max` 초과
        (`limit_rotary_speed` 를 거친 파일은 0건이어야 한다)
      · **joint 좌표** [경고] — joint Z = Ztip + (cosB−1)·LB 가 음수, joint XY 가
        native 범위 밖. 라이브 TCP 는 리밋을 **팁 좌표**에 걸어서 안 잘린다 —
        갠트리를 지켜 주는 것이 없다
      · C 가 ±360° 창 안인가 [치명], B 가 축 한계 안인가 [치명]
      · 압출 중 틸트 크기가 프로필과 맞는가 [경고], C 급회전 [경고]
      · RTCP(`G43.4`) 가 있는가 [치명]

    ⚠ 보지 **못하는** 것: 줄의 **글자 형식**(주석·길이) → `check_m668_format`,
      출력물과의 간섭 → `check_head_interference`, 축 부호(조립 의존).
    ⚠ 시작 G-code 가 없는 파일(경로만)은 부품 원점을 `profile.bed_center` 로
      **가정**하고 native 범위를 본다 (`origin_assumed`).

    반환: (findings, stats). 심각도 "치명"/"경고"/"정보".
    """
    hot = profile.hotend
    clr = profile.bed_clearance
    lb, lc = profile.lb, profile.lc
    rtcp_on, rtcp_off = profile.rtcp_on.upper(), profile.rtcp_off.upper()
    eps = 1e-6
    cmds = list(_normalized(items))

    def _declares_origin(text):
        code = text.split(";", 1)[0].strip().upper()
        if code.startswith("G28"):
            return True
        return code.startswith("G92") and ("X" in code[3:] or "Y" in code[3:])

    origin_assumed = not any(k == "raw" and isinstance(p, str) and _declares_origin(p)
                             for k, p in cmds)
    ox, oy = profile.bed_center if origin_assumed else (0.0, 0.0)
    oz = 0.0

    findings = []
    b_all, b_print, cs, feeds = [], [], [], []
    in_rewind, n_rewind, rewind_max = False, 0, 0.0
    dc_max, dc_at, db_max = 0.0, None, 0.0
    has_rtcp = False
    meta_thetas = None      # ;CONICAL_META 의 프로필 각도들 (가변각 판정용)

    x = y = z = None        # G-code(논리) 좌표
    b = c = None            # **물리** 각도 (G92 B/C 오프셋 반영). None = 모른다
    ob = oc = 0.0           # 물리 = 논리 + 오프셋
    tcp = None              # None = 파일이 아직 말하지 않았다 (부팅 기본값이 엇갈린다)
    rel = e_rel = False
    e_prev = 0.0
    f_modal = None
    n_tcp_on = 0

    state_fatal, state_warn = [], []
    n_cold = 0              # TCP 없이 기운 채 압출
    cold_first = None
    n_bed, n_bed_extr, bed_min, bed_at = 0, 0, None, None
    n_below, tip_min = 0, None      # 팁 자체가 베드 아래
    n_blind = 0                     # TCP 상태를 모르는 채 움직인 이동
    n_xy, nat = 0, [None, None, None, None]     # native X/Y 최소·최대
    n_omega, omega_top, n_omega_blind = 0, 0.0, 0
    zj_min, zj_at = None, None
    n_jxy, jxy = 0, [None, None, None, None]

    def _span(box, vx, vy):
        box[0] = vx if box[0] is None else min(box[0], vx)
        box[1] = vx if box[1] is None else max(box[1], vx)
        box[2] = vy if box[2] is None else min(box[2], vy)
        box[3] = vy if box[3] is None else max(box[3], vy)

    def _outside(vx, vy):
        return (vx < profile.native_x[0] - eps or vx > profile.native_x[1] + eps or
                vy < profile.native_y[0] - eps or vy > profile.native_y[1] + eps)

    def _tilted():
        return (b is not None and abs(b) > eps) or (c is not None and abs(c) > eps)

    for kind, payload in cmds:
        # ───────── 이동이 아닌 줄: 모달 상태 갱신 ─────────
        if kind != "move":
            if not isinstance(payload, str):
                continue
            up = payload.upper()
            if payload.startswith(";CONICAL_META"):
                try:
                    meta = json.loads(payload.split(";CONICAL_META", 1)[1])
                    meta_thetas = [float(t) for _z, t in meta.get("profile", [])]
                except (ValueError, TypeError):
                    pass
            if "V_REWIND BEGIN" in up:
                in_rewind, n_rewind = True, n_rewind + 1
            elif "V_REWIND END" in up:
                in_rewind = False
            code = up.split(";", 1)[0].strip()
            if not code:
                continue
            word0 = code.split()[0]
            words = _CMD_WORD.findall(code)
            args = {k: float(v) for k, v in words[1:]}
            if word0 == rtcp_on or word0 == rtcp_off:
                turning_on = word0 == rtcp_on
                if turning_on:
                    has_rtcp = True
                    n_tcp_on += 1
                if _tilted():
                    state_fatal.append(
                        f"`{word0}` 를 B={b or 0.0:.1f}° C={c or 0.0:.1f}° 에서 전환한다 — "
                        f"이 명령은 움직이지 않고 플래너 위치만 다시 쓰므로 팁이 "
                        f"그만큼 어긋난다 (B=20° 면 X 18.7mm). **B0 C0 에서만** 전환할 것")
                tcp = turning_on
            elif word0.startswith("G28"):
                axes = set(re.findall(r"[A-Z]", code[3:]))
                every = not axes
                if tcp is True:
                    state_warn.append("TCP 가 켜진 채 `G28` 을 한다 — 호밍은 "
                                      f"`{profile.rtcp_off}` 상태에서 할 것")
                if every or "X" in axes:
                    x, ox = profile.home_xyz[0], 0.0
                if every or "Y" in axes:
                    y, oy = profile.home_xyz[1], 0.0
                if every or "Z" in axes:
                    z, oz = profile.home_xyz[2], 0.0
                if every or profile.tilt_axis.upper() in axes:
                    b, ob = profile.home_b, 0.0
                if every or profile.rot_axis.upper() in axes:
                    c, oc = profile.home_c, 0.0
            elif word0 == "G90":
                rel = False
            elif word0 == "G91":
                rel = True
            elif word0 == "M82":
                e_rel = False
            elif word0 == "M83":
                e_rel = True
            elif word0 == "M211" and args.get("S") == 0.0:
                state_warn.append("`M211 S0` 으로 소프트 엔드스톱을 끈다 — 라이브 TCP "
                                  "에서 팁 좌표에 걸리는 리밋이 유일한 보호다")
            elif word0 == "G92":
                # 원점 이동: 지금 자리를 새 값으로 부른다 (native 는 그대로).
                if "X" in args:
                    ox, x = (ox + x - args["X"], args["X"]) if x is not None \
                        else (ox, args["X"])
                if "Y" in args:
                    oy, y = (oy + y - args["Y"], args["Y"]) if y is not None \
                        else (oy, args["Y"])
                if "Z" in args:
                    oz, z = (oz + z - args["Z"], args["Z"]) if z is not None \
                        else (oz, args["Z"])
                if "E" in args:
                    e_prev = args["E"]
                for ax, cur in ((profile.tilt_axis.upper(), b),
                                (profile.rot_axis.upper(), c)):
                    if ax not in args:
                        continue
                    if cur is None:
                        cur = args[ax]          # 모르는 자세를 그 값이라고 선언한 것
                    elif abs(cur) > eps and abs(args[ax]) < eps:
                        state_fatal.append(
                            f"`{code}`: {ax}={cur:.1f}° 인 채로 {ax}0 을 선언한다 — "
                            f"이후의 {ax}0 은 수직/정면이 아니다")
                    if ax == profile.tilt_axis.upper():
                        b, ob = cur, cur - args[ax]
                    else:
                        c, oc = cur, cur - args[ax]
            elif word0[0] == "T" and words and words[0][0] == "T":
                if int(float(words[0][1])) != 0:
                    state_fatal.append(
                        f"`{word0}`: T0 만 써야 한다 — T1/T2 는 Z 오프셋이 "
                        f"−10/−2.2mm 라 팁이 그만큼 내려간다")
            continue

        # ───────── 이동 ─────────
        mv = payload
        x0, y0, z0, b0, c0 = x, y, z, b, c

        x, y, z = (_modal(x, mv.x, rel), _modal(y, mv.y, rel),
                   _modal(z, mv.z, rel))
        bw, cw = _bc_words(mv.extra, profile)
        has_xyz = not (mv.x is None and mv.y is None and mv.z is None)
        for tok in (mv.extra or "").upper().split():
            for ax in (profile.tilt_axis.upper(), profile.rot_axis.upper()):
                if tok.startswith(ax):
                    try:
                        float(tok[len(ax):])
                    except ValueError:
                        findings.append(("치명", f"회전축 값을 못 읽었다: {tok}"))
        if bw is not None:
            b = (b + bw if b is not None else None) if rel else bw + ob
            if b is not None:
                b_all.append(b)
                if has_xyz:
                    b_print.append(b)
                if b0 is not None and has_xyz:
                    db_max = max(db_max, abs(b - b0))
        if cw is not None:
            c = (c + cw if c is not None else None) if rel else cw + oc
            if c is not None:
                cs.append(c)
                if c0 is not None:
                    dc = abs(c - c0)
                    if in_rewind:
                        rewind_max = max(rewind_max, dc)
                    elif has_xyz and dc > dc_max:
                        # 회전만 하는 줄(자세 맞춤·종료 복귀)은 급회전이 아니라
                        # 느린 피드로 일부러 도는 것이라 세지 않는다.
                        dc_max, dc_at = dc, (mv.x, mv.y, mv.z)
        if mv.f is not None:
            f_modal = mv.f
            feeds.append(mv.f)
        extruding = False
        if mv.e is not None:
            extruding = mv.e > 1e-9 if e_rel else mv.e > e_prev + 1e-9
            if not e_rel:
                e_prev = mv.e

        # (iii) TCP 없이 기운 채 압출 — G28 뒤 B0 C0 복귀를 빼먹은 시작 G-code
        if extruding and tcp is not True and _tilted():
            n_cold += 1
            if cold_first is None:
                cold_first = (mv.to_line(), b or 0.0, c or 0.0)

        if tcp is None and not origin_assumed:
            n_blind += 1

        # (ii) native XY
        if x is not None and y is not None:
            _span(nat, x + ox, y + oy)
            if _outside(x + ox, y + oy):
                n_xy += 1

        # (i) 베드 간섭 + (v) joint 좌표. 이동 안에서 (Z, B) 를 선형 보간한다.
        bb0 = b0 if b0 is not None else 0.0
        bb1 = b if b is not None else 0.0
        if z is not None:
            zs0 = z0 if z0 is not None else z
            n_s = 1 if abs(bb1 - bb0) <= 0.5 else min(180, math.ceil(abs(bb1 - bb0) / 0.5))
            hit = False
            for k in range(1, n_s + 1):
                t = k / n_s
                bt = bb0 + (bb1 - bb0) * t
                zt = zs0 + (z - zs0) * t + oz
                cosb = math.cos(math.radians(bt))
                # TCP 가 꺼져 있으면 G-code 의 Z 는 joint Z 다 → 팁은 그만큼 위.
                tip = zt if tcp is True else zt + (1.0 - cosb) * lb
                gap = bed_gap(tip, bt, hot, clr)
                if bed_min is None or gap < bed_min:
                    bed_min, bed_at = gap, (x, y, z, bt)
                hit = hit or gap < -1e-9
                tip_min = tip if tip_min is None else min(tip_min, tip)
            n_below += tip < -1e-9
            n_bed += hit
            n_bed_extr += hit and extruding
            zj = z + oz if tcp is not True else \
                z + oz + (math.cos(math.radians(bb1)) - 1.0) * lb
            if zj_min is None or zj < zj_min:
                zj_min, zj_at = zj, (x, y, z, bb1)
        if tcp is True and x is not None and y is not None:
            cr, br = math.radians(c or 0.0), math.radians(bb1)
            xj = x + ox - math.sin(cr) * lc + math.cos(cr) * math.sin(br) * lb
            yj = y + oy + (math.cos(cr) - 1.0) * lc + math.sin(cr) * math.sin(br) * lb
            _span(jxy, xj, yj)
            n_jxy += _outside(xj, yj)

        # (iv) 회전축 속도. 펌웨어는 F 를 팁 XYZ 길이에만 적용한다.
        if b0 is not None or c0 is not None:
            db = abs(b - b0) if None not in (b, b0) else 0.0
            dcc = abs(c - c0) if None not in (c, c0) else 0.0
            dth = max(db, dcc)
            if dth > 1e-9 and f_modal is not None:
                if not has_xyz:
                    length = 0.0
                elif None in (x0, y0, z0, x, y, z):
                    length = None
                else:
                    length = math.dist((_q(x0), _q(y0), _q(z0)), (_q(x), _q(y), _q(z)))
                if length is None:
                    n_omega_blind += 1
                else:
                    if length < 5e-4:           # 회전만: F 는 °/min (√(ΔB²+ΔC²) 기준)
                        omega = f_modal / 60.0 * dth / math.hypot(db, dcc)
                    else:
                        omega = dth * f_modal / (60.0 * length)
                    omega_top = max(omega_top, omega)
                    n_omega += omega > profile.omega_max * (1.0 + 1e-6) + 1e-9

    # ───────── 판정 ─────────
    if not has_rtcp:
        findings.append(("치명", f"RTCP({profile.rtcp_on})가 없다 — 없으면 X/Y/Z 가 "
                                f"노즐 팁이 아니라 캐리지로 해석된다"))
    findings += [("치명", m) for m in dict.fromkeys(state_fatal)]
    findings += [("경고", m) for m in dict.fromkeys(state_warn)]
    if n_tcp_on > 1:
        findings.append(("경고", f"`{profile.rtcp_on}` 가 {n_tcp_on}번 나온다 — "
                                f"TCP 는 시작 G-code 끝(B0 C0)에서 한 번만 켤 것"))
    if n_cold:
        line, bv, cv = cold_first
        findings.append(("치명", f"TCP({profile.rtcp_on}) 없이 B={bv:.1f}° C={cv:.1f}° 인 채 "
                                f"압출하는 이동 {n_cold}개 (처음 `{line}`) — G28 은 B 를 "
                                f"{profile.home_b:.0f}° 로 호밍한다. 압출 전에 "
                                f"`G0 C0 B0` 으로 되돌릴 것"))
    if n_bed:
        bx, by, bz, bt = bed_at
        findings.append(("치명", f"핫엔드({hot.name})가 베드 여유 {clr:g}mm 를 침범하는 "
                                f"이동 {n_bed}개 (그중 압출 {n_bed_extr}개) — "
                                f"가장 깊은 곳 {bed_min:+.2f}mm "
                                f"(X{bx:.2f} Y{by:.2f} Z{bz:.2f}, B={bt:.1f}°). "
                                f"그 높이의 B_safe 는 "
                                f"{b_safe(bz, hot, clr):.1f}° 다"))
    if n_below:
        findings.append(("치명", f"팁이 베드 아래(Z<0)로 내려가는 이동 {n_below}개 "
                                f"(최저 {tip_min:.2f}mm) — 소프트 엔드스톱이 팁 Z 를 "
                                f"0 에서 자르므로 경로가 뭉개진다"))
    if n_blind:
        findings.append(("경고", f"TCP 상태를 밝히지 않은 채 움직이는 이동 {n_blind}개 — "
                                f"부팅 기본값이 config 마다 엇갈린다. 파일 맨 앞에서 "
                                f"`{profile.rtcp_off}` 로 밝힐 것"))
    if n_xy:
        findings.append(("치명", f"팁 XY 가 native 범위 X[{profile.native_x[0]:g},"
                                f"{profile.native_x[1]:g}] Y[{profile.native_y[0]:g},"
                                f"{profile.native_y[1]:g}] 밖인 이동 {n_xy}개 "
                                f"(native X {nat[0]:.1f}~{nat[1]:.1f}, "
                                f"Y {nat[2]:.1f}~{nat[3]:.1f}"
                                + (", 부품 원점을 베드 중앙으로 가정"
                                   if origin_assumed else "")
                                + ") — 라이브 TCP 에서 범위 밖의 회전 이동은 "
                                  "조용히 버려진다"))
    if n_omega:
        findings.append(("치명", f"회전축 속도가 상한 {profile.omega_max:g}°/s 를 넘는 "
                                f"이동 {n_omega}개 (최대 {omega_top:,.0f}°/s) — 펌웨어는 "
                                f"F 를 팁 XYZ 길이에만 적용한다. "
                                f"`limit_rotary_speed` 로 F 를 깎을 것"))
    if n_omega_blind:
        findings.append(("경고", f"출발 위치를 모르는 채 회전하는 이동 {n_omega_blind}개 — "
                                f"회전 속도를 판정할 수 없다"))
    if zj_min is not None and zj_min < -eps:
        jx, jy, jz, jb = zj_at
        findings.append(("경고", f"joint Z 가 {zj_min:.2f}mm 까지 내려간다 "
                                f"(Z{jz:.2f}, B={jb:.1f}°: Ztip + (cosB−1)·{lb:g}). "
                                f"라이브 TCP 는 리밋을 팁 좌표에 걸어서 잘리지 않는다 — "
                                f"갠트리가 Z<0 까지 실제로 내려가는지 [실기 확인]"))
    if n_jxy:
        findings.append(("경고", f"joint XY 가 native 범위 밖인 이동 {n_jxy}개 "
                                f"(X {jxy[0]:.1f}~{jxy[1]:.1f}, Y {jxy[2]:.1f}~{jxy[3]:.1f}) "
                                f"— 리밋은 팁 좌표에 걸리므로 펌웨어가 막지 않는다"))

    if not b_all:
        findings.append(("치명", "틸트 축 값이 하나도 없다"))
    else:
        # (B, C) 와 (−B, C+180°) 는 같은 공구 방향이다(축 통과 시 B 부호 반전,
        # `to_rep5x` pole_flip). 그래서 틸트의 **크기** |B| 로 본다. 회전만 하는
        # 줄(시작의 `G0 C0 B0`, 자세 맞춤, 종료 복귀)은 출력 자세가 아니라 뺀다.
        mags = [abs(v) for v in (b_print or b_all)]
        variable = meta_thetas is not None and \
            max(meta_thetas) - min(meta_thetas) > 1e-9
        if variable:
            lo = min(abs(t) for t in meta_thetas)
            hi = max(abs(t) for t in meta_thetas)
            if min(mags) < lo - 0.01 or max(mags) > hi + 0.01:
                findings.append(("경고", f"틸트 크기 {min(mags):.2f}~{max(mags):.2f}° 가 "
                                         f"프로필 각도 범위 {lo:.2f}~{hi:.2f}° 밖이다"))
        elif max(mags) - min(mags) > 1e-6:
            findings.append(("경고", f"틸트 크기가 여러 값이다 "
                                     f"({min(mags):.2f}~{max(mags):.2f}) — "
                                     f"고정 틸트 원뿔 모드가 아니다"))
        if min(b_all) < profile.b_min - 1e-9 or max(b_all) > profile.b_max + 1e-9:
            findings.append(("치명", f"틸트 {min(b_all):.1f}~{max(b_all):.1f}° 가 "
                                     f"기계 한계 [{profile.b_min}, "
                                     f"{profile.b_max}] 밖이다"))

    c_lo, c_hi = (min(cs), max(cs)) if cs else (0.0, 0.0)
    over = max(profile.c_min - c_lo, c_hi - profile.c_max, 0.0) if cs else 0.0
    if 1e-9 < over <= C_OVERSHOOT_TOL:
        # 360° 폭 링을 ±360° 창에 놓으면 위상에 따라 경계에 딱 붙는다. 펌웨어가
        # 넘친 만큼 자르면 공구 방향이 그 각도만큼 틀어진다 — 0.5° 이하는 무의미하다
        findings.append(("경고", f"C 가 창 경계를 {over:.3f}° 넘는다 ({c_lo:.3f}~"
                                 f"{c_hi:.3f}°) — 펌웨어가 잘라도 공구 방향 오차 "
                                 f"{over:.3f}° (허용 {C_OVERSHOOT_TOL}°)"))
    elif over > C_OVERSHOOT_TOL:
        findings.append(("치명", f"C 가 {c_lo:.0f}~{c_hi:.0f}° 로 펌웨어 소프트 "
                                 f"엔드스톱 [{profile.c_min:.0f}, "
                                 f"{profile.c_max:.0f}] 을 넘는다 "
                                 f"({(c_hi - c_lo) / 360.0:.1f}회전). "
                                 f"되감기(`add_c_rewinds`)가 필요하다"))
    if dc_max > max_dc_deg:
        findings.append(("경고", f"C 가 한 이동에 {dc_max:.0f}° 뛴다"
                                 + (f" (부품좌표 {dc_at})" if dc_at else "")
                                 + " — 축 근처 방위각 반전. 회전 속도 상한 때문에 "
                                   "그 이동은 느려진다"))
    if max_feed is not None and feeds and max(feeds) > max_feed + 1e-9:
        findings.append(("경고", f"피드 최대 {max(feeds):.0f} > {max_feed:.0f}"))

    bp = b_print or b_all
    stats = {"tilt": bp[0] if bp else None,
             "c_min": c_lo, "c_max": c_hi,
             "c_wind_turns": (max(abs(v - cs[0]) for v in cs) / 360.0) if cs else 0.0,
             "c_span_turns": (c_hi - c_lo) / 360.0,
             "c_max_step_deg": dc_max, "b_max_step_deg": db_max,
             "b_min": min(bp) if bp else None,
             "b_max": max(bp) if bp else None,
             "moves": len(cs), "rewinds": n_rewind,
             "rewind_max_deg": rewind_max, "rtcp": has_rtcp,
             "rtcp_on_count": n_tcp_on,
             "bed_hits": n_bed, "bed_hits_extruding": n_bed_extr,
             "bed_gap_min": bed_min,            # 여유선까지 남은 거리 (음수 = 침범)
             "tip_below_bed": n_below, "tip_z_min": tip_min,
             "native_xy_out": n_xy, "native_box": tuple(nat),
             "origin_assumed": origin_assumed,
             "state_fatal": len(set(state_fatal)) + (1 if n_cold else 0),
             "cold_extrusions": n_cold,
             "omega_violations": n_omega, "omega_max_deg_s": omega_top,
             "joint_z_min": zj_min, "joint_xy_out": n_jxy}
    return findings, stats


def check_m668_format(lines):
    """M668(SD 전처리)이 읽을 수 있는 **줄 형식**인가. 파일의 글자 그대로를 본다.

    REP5X 에는 실행 경로가 둘이다 (facts §10): 라이브 TCP(`G43.4`)와 SD 전처리
    (`M668` — 펌웨어가 SD 파일을 joint 좌표로 미리 바꾼다). 전처리기는 이동 줄을
    손으로 읽어서 제약이 있다:

      · 이동 줄은 **0열의 `G`** 로 시작해야 한다 (들여쓰기·소문자 불가)
      · **127자 이하**
      · **주석이 붙으면 안 된다** — 주석 속의 `z0.6` 도 Z 로 읽힌다
      · G2/G3 미지원

    우리는 두 경로 모두에 걸 수 있는 파일을 낸다. 이동 줄(G0/G1)의 위반은 치명,
    127자를 넘는 **주석 줄**은 정보로만 알린다(전처리기가 긴 주석을 어떻게 다루는지
    확인하지 못했다 — `;CONICAL_META` 줄이 여기 해당한다).

    반환: (findings, stats)
    """
    n_move = n_indent = n_comment = n_long = n_arc = n_long_other = 0
    first = {}
    for no, raw in enumerate(lines, 1):
        line = raw.rstrip("\r\n")
        code = line.split(";", 1)[0]
        if re.match(r"^\s*[Gg]0*[23](?![\d.])", code):
            n_arc += 1
            first.setdefault("arc", no)
        if not _MOVE_LINE.match(line):
            if len(line) > 127:
                n_long_other += 1
            continue
        n_move += 1
        if not line.startswith("G"):
            n_indent += 1
            first.setdefault("indent", no)
        if ";" in line or "(" in line:
            n_comment += 1
            first.setdefault("comment", no)
        if len(line) > 127:
            n_long += 1
            first.setdefault("long", no)
    findings = []
    if n_indent:
        findings.append(("치명", f"0열의 `G` 로 시작하지 않는 이동 줄 {n_indent}개 "
                                f"(처음 {first['indent']}번 줄) — M668 전처리가 못 읽는다"))
    if n_comment:
        findings.append(("치명", f"주석이 붙은 이동 줄 {n_comment}개 "
                                f"(처음 {first['comment']}번 줄) — M668 전처리는 주석 속 "
                                f"글자도 좌표로 읽는다. 주석은 따로 줄을 낼 것"))
    if n_long:
        findings.append(("치명", f"127자를 넘는 이동 줄 {n_long}개 "
                                f"(처음 {first['long']}번 줄)"))
    if n_arc:
        findings.append(("치명", f"G2/G3 줄 {n_arc}개 (처음 {first['arc']}번 줄) — "
                                f"M668 전처리가 지원하지 않고 역변환도 못 한다"))
    if n_long_other:
        findings.append(("정보", f"이동이 아닌 줄 중 127자를 넘는 것 {n_long_other}개 "
                                f"(주석·메타) — M668 전처리가 긴 줄을 어떻게 다루는지 "
                                f"[실기 확인]"))
    return findings, {"move_lines": n_move, "indented": n_indent,
                      "commented": n_comment, "too_long": n_long, "arcs": n_arc,
                      "long_other_lines": n_long_other}


def print_body(items, profile=REP5X):
    """TCP 가 켜져 있는 구간의 아이템만 (= 출력 본문).

    출력물 간섭 검사(`check_head_interference`, `check_rewind_sweep`)는 좌표를
    부품좌표로 읽는다. 시작 G-code 의 프라임 선은 `G92 X0 Y0` **이전**의 native
    좌표라 그대로 넣으면 엉뚱한 자리의 장애물이 된다. TCP 를 켜는 줄이 없으면
    (경로만 있는 파일) 전부 돌려준다.
    """
    on, off = profile.rtcp_on.upper(), profile.rtcp_off.upper()

    def word0(payload):
        code = payload.split(";", 1)[0].strip().upper()
        return code.split()[0] if code else ""

    marks = [word0(p) if k == "raw" and isinstance(p, str) else "" for k, p in items]
    if on not in marks:
        return list(items)
    out, live = [], False
    for (kind, payload), w in zip(items, marks, strict=True):
        if w == on:
            live = True
        elif w == off:
            live = False
        elif live:
            out.append((kind, payload))
    return out


# ─────────────────────────────────────────────────────────────
# C 되감기: **절대 창** 제약 — Open5x 의 되감기와 종류가 다르다
# ─────────────────────────────────────────────────────────────
def _with_axis(extra, axis, value):
    """extra 문자열에서 `axis` 워드만 갈아끼운다 (B 등 다른 워드는 보존)."""
    toks = [t for t in (extra or "").split()
            if not t.upper().startswith(axis.upper())]
    toks.append(f"{axis}{value:.3f}")
    return " ".join(toks)


def _c_of(extra, axis):
    for tok in (extra or "").split():
        if tok.upper().startswith(axis.upper()):
            try:
                return float(tok[len(axis):])
            except ValueError:
                return None
    return None


def add_c_rewinds(items, profile=REP5X, clearance=2.0, rot_feed=3600.0,
                  lift_feed=3000.0):
    """C 를 펌웨어 소프트 엔드스톱 **창 안에** 유지한다 (트래블 중 360° 배수 되감기).

    ## 왜 `open5x.add_v_rewinds` 를 그대로 못 쓰나 — 제약의 **종류가 다르다**

      · Open5x: 배선 감김 = **시작점 기준 이탈** `max|V − V₀|`. 기준점에서
        멀어지지만 않으면 되므로 '가까운 쪽으로 되감기' 가 맞다.
      · REP5X: 펌웨어 소프트 엔드스톱 = **절대 창** `c_min ≤ C ≤ c_max`.
        **창 밖으로 나가면 기계가 멈춘다.**

    창 가운데로 되감으면 안 된다. 360° 배수로만 옮길 수 있어 **나머지 각도가
    ±180° 까지 남고**, 거기서 한 바퀴(360°)를 더 감으면 ±540° 로 창을 넘는다.
    실측으로 확인했다: 가운데로 되감으니 funnel 이 −450~275° 로 나갔다.

    ## 하는 것: **다음 압출 구간을 미리 보고** 딱 맞는 k 를 고른다

    되감기는 트래블에서만 할 수 있으므로, 한 번 정하면 **다음 트래블까지** 그
    값으로 버텨야 한다. 그래서 추측하지 않고 앞을 본다:

      ① 이 트래블부터 다음 트래블까지 C 가 훑을 범위 `[lo, hi]` 를 미리 구한다
      ② `[lo + 360k, hi + 360k] ⊆ [c_min, c_max]` 인 정수 k 를 고른다
         (여러 개면 창 가운데에 가장 가까운 것)
      ③ 그런 k 가 없으면 **되감기로 못 고치는 구간**이다 — `fixable=False` 로
         알리고 넘어간다. 창보다 넓게 감기는 압출 구간이 있다는 뜻이고,
         그때는 슬라이싱 쪽에서 경로를 끊어야 한다

    앞을 보기 때문에 방향을 추측할 필요가 없다. 추측하면 요동친다 — 직전 이동의
    부호로 방향을 정했더니 되감기가 214회로 늘고 C 가 여전히 창을 벗어났다.

    ⚠ C 를 360° 배수만큼 돌리면 **공구 방향이 정확히 같은 값으로 돌아온다**
      (`d̂` 는 C 에 대해 360° 주기). RTCP 가 켜져 있으면 노즐 팁도 제자리다.
      그래서 툴패스가 보존된다 — 회귀 테스트가 이걸 강제한다.

    ⚠ 도는 도중 **B_arm 이 팁 둘레를 쓸고 지나간다** (팁에서 LB 만큼 위, 수평
      반경 LB·sinθ ≈ 18.7mm @ θ=20°). 부품은 안 움직이지만 팔이 움직이므로
      들어올림을 유지한다. ⚠ 들어올림은 '여태 퇴적한 것보다 위' 까지만 보장하고
      팔이 **옆으로** 부딪히는 것은 **보지 못한다.**
    """
    axis = profile.rot_axis
    lo_lim, hi_lim = profile.c_min, profile.c_max
    center = (lo_lim + hi_lim) / 2.0

    # ── 1패스: 이동만 뽑아 C 와 압출 여부를 정리한다
    moves = [(i, p) for i, (k, p) in enumerate(items) if k == "move"]
    cs, extr = [], []
    e_prev = 0.0
    for _i, mv in moves:
        cs.append(_c_of(mv.extra, axis))
        extr.append(mv.e is not None and mv.e > e_prev + 1e-9)
        if mv.e is not None:
            e_prev = mv.e

    # 각 이동에서 '다음 트래블까지' C 가 훑는 범위 (되감기 판단용 look-ahead)
    n = len(moves)
    seg_lo, seg_hi = [None] * n, [None] * n
    for start in range(n):
        if extr[start]:
            continue                     # 트래블에서만 되감으므로 거기서만 계산
        # 다음 트래블에서 또 되감을 수 있으므로, 이번 결정이 책임질 구간은
        # [start, 다음 트래블 직전] 이다.
        nxt = start + 1
        while nxt < n and extr[nxt]:
            nxt += 1
        vals = [cs[j] for j in range(start, nxt) if cs[j] is not None]
        if vals:
            seg_lo[start], seg_hi[start] = min(vals), max(vals)

    # ── 첫 트래블 **이전** 구간은 어떤 되감기 결정에도 안 잡힌다.
    # 거기서 이미 창을 넘을 수 있으므로(실측: funnel 이 −450° 로 시작), 시작
    # 오프셋으로 분기를 골라 둔다. G-code 를 더 내지는 않는다 — 헤드는 어차피
    # 시작 전에 그 각도로 가 있어야 하고, C 는 360° 주기라 공구 방향이 같다.
    # 첫 이동에서는 되감기를 낼 수 없다(직전 좌표가 없다). 그래서 **1번부터**
    # 다음 트래블을 찾는다 — 실측: funnel 은 이동 0 이 트래블이고 1~16 이
    # 한 번에 0.94회전 감기는 압출 구간이라, 여기가 통째로 안 덮이면 −450° 로
    # 시작해 버린다.
    t0 = 1
    while t0 < n and extr[t0]:
        t0 += 1
    head_vals = [cs[j] for j in range(0, min(t0, n)) if cs[j] is not None]
    start_offset, start_unfixable = 0.0, 0
    if head_vals:
        h_lo, h_hi = min(head_vals), max(head_vals)
        k_lo = math.ceil((lo_lim - h_lo) / 360.0 - 1e-9)
        k_hi = math.floor((hi_lim - h_hi) / 360.0 + 1e-9)
        if k_lo <= k_hi:
            start_offset = 360.0 * min(range(k_lo, k_hi + 1),
                                       key=lambda kk: abs((h_lo + h_hi) / 2
                                                          + 360.0 * kk - center))
        else:
            # 첫 구간부터 창보다 넓게 감긴다 — 되감기로 못 고친다. 조용히
            # 넘어가면 기계 앞에서 알게 되므로 여기서 센다.
            start_unfixable = 1

    # ── 2패스: 되감기를 끼워 넣는다
    out, mi = [], 0
    offset = start_offset
    c_prev = None
    extra_prev = None               # 직전 이동의 자세 (B 포함) — 되감기가 그대로 쓴다
    px = py = pz = None
    z_dep = None
    e_prev = 0.0
    n_rewinds, rewind_deg, unfixable = 0, 0.0, start_unfixable

    for kind, payload in items:
        if kind != "move":
            out.append((kind, payload))
            continue
        mv = payload
        c_raw = cs[mi]
        extruding = extr[mi]
        lo, hi = seg_lo[mi], seg_hi[mi]
        mi += 1

        if c_raw is not None:
            c = c_raw + offset
            if (not extruding and c_prev is not None and lo is not None
                    and None not in (px, py, pz)):
                lo_o, hi_o = lo + offset, hi + offset
                # 되감기는 **직전 자세 c_prev** 에서 360k 만큼 돈다 — 그 끝 자세도 창 안이어야
                # 한다. 다음 구간만 보면 c_prev+360k 가 창 밖에 떨어질 수 있었다
                # (lamp 15°, 351.7 → −368.3°, 2026-11-10). 그래서 c_prev 를 범위에 넣는다.
                lo_o, hi_o = min(lo_o, c_prev), max(hi_o, c_prev)
                if lo_o < lo_lim - 1e-9 or hi_o > hi_lim + 1e-9:
                    # [lo+360k, hi+360k] ⊆ 창 인 k 들 중 가운데에 가장 가까운 것
                    k_lo = math.ceil((lo_lim - lo_o) / 360.0 - 1e-9)
                    k_hi = math.floor((hi_lim - hi_o) / 360.0 + 1e-9)
                    if k_lo > k_hi:
                        unfixable += 1          # 창보다 넓게 감기는 구간
                    else:
                        k = min(range(k_lo, k_hi + 1),
                                key=lambda kk: abs((lo_o + hi_o) / 2
                                                   + 360.0 * kk - center))
                        if k != 0:
                            safe_z = max(z_dep if z_dep is not None else pz,
                                         pz) + clearance
                            c_new = c_prev + 360.0 * k
                            out.append(("raw",
                                        f"; V_REWIND BEGIN {k:+d} turn(s): "
                                        f"{c_prev:.1f} -> {c_new:.1f} deg "
                                        f"(lift to Z{safe_z:.2f}) [{axis} window "
                                        f"{lo_lim:.0f}..{hi_lim:.0f}]"))
                            # 되감기는 **직전 자세 그대로** C 만 360° 배수 돌린다.
                            # 예전에는 다음 이동의 B 를 썼다 — 그러면 되감기 끝에
                            # '직전 위치(낮을 수 있다)에 다음 레이어의 틸트' 로
                            # 내려오게 되어, 틸트가 커지는 구간에서 베드 여유를
                            # 침범할 수 있다. B 는 다음 이동이 가면서 바꾼다.
                            pose = extra_prev if extra_prev is not None else mv.extra
                            for zz, ff, cc in ((safe_z, lift_feed, c_prev),
                                               (safe_z, rot_feed, c_new),
                                               (pz, lift_feed, c_new)):
                                out.append(("move", Move(
                                    g=0, x=px, y=py, z=zz, f=ff,
                                    extra=_with_axis(pose, axis, cc))))
                            out.append(("raw", "; V_REWIND END"))
                            rewind_deg += abs(360.0 * k)
                            offset += 360.0 * k
                            c = c_raw + offset
                            n_rewinds += 1
            mv = Move(g=mv.g, x=mv.x, y=mv.y, z=mv.z, e=mv.e, f=mv.f,
                      extra=_with_axis(mv.extra, axis, c))
            c_prev = c
            extra_prev = mv.extra

        out.append(("move", mv))
        if mv.x is not None:
            px = mv.x
        if mv.y is not None:
            py = mv.y
        if mv.z is not None:
            pz = mv.z
        if extruding and pz is not None:
            z_dep = pz if z_dep is None else max(z_dep, pz)
        if mv.e is not None:
            e_prev = mv.e

    return out, {"rewinds": n_rewinds, "rewind_deg": rewind_deg,
                 "unfixable_segments": unfixable, "fixable": unfixable == 0,
                 "start_offset": start_offset,
                 "window_turns": (hi_lim - lo_lim) / 360.0}


# ─────────────────────────────────────────────────────────────
# 헤드 회전식 노즐 간섭 — 베드 틸트식의 '정의상 불가능' 이 여기서는 성립 안 한다
# ─────────────────────────────────────────────────────────────
def move_tool_frames(items, profile=REP5X):
    """이동별 (B, C) → 공구 축 '위' 방향 단위벡터 배열.

    `sample_extrusions` 의 `move_id` 가 **이동 인덱스**이므로, 여기서 만든 배열을
    `up[move_id]` 로 색인하면 샘플점마다의 공구 자세가 된다.

    모달이다: B/C 가 안 적힌 이동은 직전 값을 잇는다.
    """
    b = c = 0.0
    ups = []
    for kind, p in items:
        if kind != "move":
            continue
        for tok in (p.extra or "").split():
            t = tok.upper()
            if t.startswith(profile.tilt_axis.upper()):
                try:
                    b = float(tok[len(profile.tilt_axis):])
                except ValueError:
                    pass
            elif t.startswith(profile.rot_axis.upper()):
                try:
                    c = float(tok[len(profile.rot_axis):])
                except ValueError:
                    pass
        d = tool_direction(b, c)
        ups.append((-d[0], -d[1], -d[2]))       # 팁에서 공구 축을 따라 '위'
    return np.asarray(ups, dtype=float)


def sample_tool_frames(items, pts, mid, profile=REP5X):
    """샘플점마다의 공구 '위' 방향 — 이동 **안에서 (B, C) 를 선형 보간**한다.

    펌웨어는 한 이동 동안 회전축을 시작값→끝값으로 선형 보간한다. 예전 검사는
    이동의 **끝** 자세를 그 이동 전체에 붙였는데(`move_tool_frames[mid]`), 축을
    가로지르는 이동에서는 축 앞쪽 절반이 2θ 반대로 기운 자세로 평가돼 간섭을
    **지어냈다**(램프 밴드2 0.3mm, r=0.52mm 에서 '치명' 0.01% — 2026-10-16).
    """
    bc, ends = [], []
    b = c = 0.0
    x = y = z = None
    for kind, p in items:
        if kind != "move":
            continue
        start = (x, y, z)
        for tok in (p.extra or "").split():
            t = tok.upper()
            try:
                if t.startswith(profile.tilt_axis.upper()):
                    b = float(tok[len(profile.tilt_axis):])
                elif t.startswith(profile.rot_axis.upper()):
                    c = float(tok[len(profile.rot_axis):])
            except ValueError:
                pass
        x = p.x if p.x is not None else x
        y = p.y if p.y is not None else y
        z = p.z if p.z is not None else z
        bc.append((b, c))
        ends.append((start, (x, y, z)))
    pts = np.asarray(pts, dtype=float)
    ups = np.empty((len(pts), 3))
    for k, (pt, m) in enumerate(zip(pts, mid, strict=True)):
        b1, c1 = bc[m]
        b0, c0 = bc[m - 1] if m > 0 else bc[m]
        (s0, s1) = ends[m]
        t = 1.0
        if None not in s0 and None not in s1:
            L = math.dist(s0, s1)
            if L > 1e-12:
                t = min(1.0, max(0.0, math.dist(s0, pt) / L))
        d = tool_direction(b0 + (b1 - b0) * t, c0 + (c1 - c0) * t)
        ups[k] = (-d[0], -d[1], -d[2])
    return ups


def check_head_interference(items, profile=REP5X, hotend=None, width=0.45,
                            clearance=0.3, arm_radius=None,
                            batch_samples=2000, stride=1):
    """헤드 회전식에서 **노즐/B_arm 이 출력물을 치는가**.

    ## 왜 이게 따로 필요한가

    베드 틸트식(Open5x)에서는 원뿔 레이어가 기계공간에서 수평면이 되어 **간섭이
    정의상 불가능**했다(`envelope.check_planar_stacking`). **헤드 회전식에서는 그
    논증이 성립하지 않는다** — 부품이 고정이라 레이어가 기울어 있고, 노즐이 기운다.

    그렇다고 3축과 같지도 않다. 3축은 노즐이 **수직 고정**이라 기운 원뿔면 위에서
    핫엔드가 출력물을 파고들었다(funnel 의 3축 MAX_ANGLE 이 24° 였던 이유).
    헤드 회전식은 노즐이 **원뿔면의 법선을 따라간다** — 국소적으로는 평면 출력과
    같은 자세다. 그래서 유리할 것으로 **예상**되는데, 예상은 근거가 아니므로 잰다.

    ## 어떻게

    `toolpath.check_nozzle` 을 **공구 프레임**으로 일반화해 그대로 쓴다. 3축은
    `tool_up=(0,0,1)` 인 특수 경우이고 두 경로의 결과가 **정확히 같다**
    (테스트가 강제). 그래서 3축 판정과 5축 판정을 **같은 기하·같은 코드**로
    비교할 수 있다 — 기하가 다르면 비교가 안 된다.

    ⚠ 보지 못하는 것:
      · **B_arm 의 실제 치수** — 저장소에 3MF 뿐이라 반경을 모른다. `arm_radius`
        를 주면 팁에서 `LB`(54.67mm)까지 원기둥으로 근사해 넣고, 안 주면 **끈다**.
        (`arm_modeled` 로 어느 쪽인지 보고한다)
      · **트래블·되감기 도중**의 자세 → `check_rewind_sweep`
      · 캐리지·팬 덕트·보덴 튜브
    """
    from .toolpath import check_nozzle, sample_extrusions

    pts, mid, _wt = sample_extrusions(items, width=width)
    if len(pts) == 0:
        return np.zeros(0, dtype=bool), {"collision_pct": 0.0,
                                         "first_collision_z": None,
                                         "arm_modeled": False, "samples": 0,
                                         "evaluated": 0}
    ups = sample_tool_frames(items, pts, mid, profile)
    col, st = check_nozzle(pts, mid, hotend or profile.hotend,
                           batch_samples=batch_samples, clearance=clearance,
                           tool_up=ups,
                           arm_length=profile.lb if arm_radius else None,
                           arm_radius=arm_radius, stride=stride)
    return col, st


def check_rewind_sweep(items, profile=REP5X, hotend=None, width=0.45,
                       n_angles=24, clearance=0.3, arm_radius=None):
    """되감기 **도중** 핫엔드가 쓸고 지나가는 부피가 출력물을 치는가.

    되감기는 C 를 360° 배수만큼 돌린다. **끝난 뒤**의 자세는 시작과 같지만
    (Rz 주기), **도는 도중**에는 다르다. RTCP 가 팁을 붙잡아 두므로 핫엔드 몸체가
    팁 둘레를 **반각 B 의 원뿔로 쓸고 지나간다.** 베드 회전식에서는 부품이 돌아
    문제였는데, 여기서는 팔이 돈다 — 어느 쪽이든 도중 자세를 봐야 한다.

    들어올림(`add_c_rewinds` 의 `clearance`)이 그 대책인데, 그 들어올림은
    '여태 퇴적한 것보다 위' 까지만 보장한다. 옆으로 부딪히는 것은 **이 검사가**
    본다.

    방법: 되감기 블록 안의 이동마다 **그 이동이 실제로 훑는 C 구간**을
    `n_angles` 개로 나눠 각 자세에서 간섭을 보고 OR 한다. 되감기는
    들어올림 → 회전 → 하강 세 이동인데 **C 가 도는 것은 가운데 하나뿐**이고
    나머지는 C 가 고정이다. 전부 360° 훑는 것으로 잘못 세면 들어올림을 30mm 로
    키워도 검출 수가 안 변한다 — 실제로 그렇게 만들었다가 잡았다.

    반환: (findings, stats). 되감기가 없으면 빈 목록.
    """
    from .toolpath import sample_extrusions

    h = hotend or profile.hotend
    pts, _mid, _wt = sample_extrusions(items, width=width)
    if len(pts) == 0:
        return [], {"rewinds": 0, "swept_hits": 0, "checked": 0}

    # 되감기 구간의 '들어올린 뒤 회전하는' 이동을 모은다: 그 위치와 B, 그리고
    # 그 시점까지 퇴적된 점만 후보다 (아직 안 찍은 것은 부딪힐 것이 없다).
    tree = cKDTree(pts)
    arm_len = profile.lb if arm_radius else None
    _use_arm, radius = hotend_reach(h, arm_len, arm_radius)

    def hit(dz, horiz):
        return hotend_hit(h, dz, horiz, clearance, arm_len, arm_radius)

    in_rw, n_rw, hits, checked = False, 0, 0, 0
    worst = None
    px = py = pz = None
    b_cur = 0.0
    # 여태 퇴적한 샘플 수. `_mid` 는 이동 인덱스이고 샘플은 G-code 순서이므로,
    # '이동 m 까지의 샘플 수' = searchsorted(_mid, m, "right") 로 정확히 나온다.
    # (직접 포인터를 미는 방식은 이동 하나가 샘플을 0개 내는 경우에 어긋난다)
    n_dep = 0
    move_i = -1
    c_from = c_cur = None
    for kind, payload in items:
        if kind != "move":
            if isinstance(payload, str):
                up = payload.upper()
                if "V_REWIND BEGIN" in up:
                    in_rw, n_rw = True, n_rw + 1
                elif "V_REWIND END" in up:
                    in_rw = False
            continue
        mv = payload
        move_i += 1
        n_dep = int(np.searchsorted(_mid, move_i, side="right"))
        for tok in (mv.extra or "").split():
            if tok.upper().startswith(profile.tilt_axis.upper()):
                try:
                    b_cur = float(tok[len(profile.tilt_axis):])
                except ValueError:
                    pass
        c_new = _c_of(mv.extra, profile.rot_axis)
        if c_new is not None:
            c_from, c_cur = (c_cur if c_cur is not None else c_new), c_new
        px = mv.x if mv.x is not None else px
        py = mv.y if mv.y is not None else py
        pz = mv.z if mv.z is not None else pz
        if not in_rw or None in (px, py, pz) or n_dep == 0:
            continue
        checked += 1
        p = np.array([px, py, pz], dtype=float)
        nb = [j for j in tree.query_ball_point(p, r=radius) if j < n_dep]
        if not nb:
            continue
        q = pts[np.array(nb)] - p
        d2 = np.einsum("ij,ij->i", q, q)
        # 이 이동이 실제로 훑는 C 구간만 본다. C 가 안 변하면 자세 하나다.
        lo, hi = (c_from, c_cur) if c_from <= c_cur else (c_cur, c_from)
        n_a = 1 if abs(hi - lo) < 1e-9 else max(2, n_angles)
        for a in range(n_a):
            cc = lo if n_a == 1 else lo + (hi - lo) * a / (n_a - 1)
            d = tool_direction(b_cur, cc)
            u = np.array([-d[0], -d[1], -d[2]])
            dz = q @ u
            horiz = np.sqrt(np.maximum(d2 - dz * dz, 0.0))
            if np.any(hit(dz, horiz)):
                hits += 1
                if worst is None:
                    worst = (float(px), float(py), float(pz), float(cc))
                break

    findings = []
    if hits:
        findings.append(("치명", f"되감기 도중 핫엔드가 출력물을 친다 "
                                 f"({hits}/{checked} 자세, 처음 {worst}). "
                                 f"들어올림(`--v-rewind-clearance`)을 키우거나 "
                                 f"되감기 위치를 옮겨야 한다"))
    return findings, {"rewinds": n_rw, "swept_hits": hits, "checked": checked,
                      "arm_modeled": bool(arm_radius)}
