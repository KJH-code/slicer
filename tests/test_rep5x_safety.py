"""T27: REP5X 실기 안전 — 베드 간섭, TCP 전환 상태, 회전축 속도, M668 줄 형식.

왜 필요한가 (2026-11-10): 첫 실물 출력을 앞두고 펌웨어 소스를 읽어 보니
(docs/rep5x_machine_facts.md) **뽑아 둔 예시 파일이 그대로는 기계를 친다.**

  · G28 은 B 를 −135° 로 호밍한다. 시작 G-code 가 B0 C0 으로 되돌리지 않고 프라임
    선을 긋고, 그 상태로 `G43.4` 를 켰다 (TCP 전환은 B0 C0 에서만 해야 한다)
  · 첫 층은 팁이 Z≈층고인데 B 가 30° 다. 공식 뷰어 모델로는 노즐 몸통이 약 24° 에서
    베드에 닿는다. 예전 간섭 검사는 **출력물만** 봤다
  · 펌웨어는 F 를 팁 XYZ 길이에만 적용한다. 축 근처의 0.03mm 짜리 이동이 C 를 45°
    돌리면 회전축이 축 한계까지 가속한다
  · native X0 Y0 은 베드 모서리다. 모서리를 원점으로 선언하면 부품 절반이 범위 밖

이 파일은 '예전 파일은 치명으로 잡히고, 새로 뽑은 파일은 치명 0' 을 고정한다.
'0 이 나왔다' 만으로는 검사가 죽은 것과 구별이 안 되므로 **잡아야 할 때 잡는지**를
항목마다 같이 본다.

    python3 -m pytest tests/test_rep5x_safety.py -q
"""

import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
import trimesh

from conical import gcode as gc
from conical.gcode import Move
from conical.machine import MachineProfile
from conical.meshio import RadiusProfile, center_on_axis
from conical.profile import AngleProfile
from conical.rep5x import (
    REP5X,
    b_safe,
    bed_gap,
    bed_safe_profile,
    bed_tilt_cap,
    check_head_interference,
    check_m668_format,
    check_rep5x,
    limit_rotary_speed,
    print_body,
    tip_height_needed,
    to_rep5x,
)
from conical.toolpath import REP5X_V3SE_HOTEND, HotendProfile

ROOT = Path(__file__).resolve().parent.parent
OLD_EXAMPLE = ROOT / "examples" / "lamp_expA_band2_lh03_rep5x.gcode"
NEW_INI = ROOT / "profiles" / "rep5x_ender3v3se.ini"


def _raw(*lines):
    return [("raw", ln) for ln in lines]


def _fatal(findings):
    return [m for sev, m in findings if sev == "치명"]


def _warn(findings):
    return [m for sev, m in findings if sev == "경고"]


# 공식 흐름을 줄인 시작 G-code: 호밍 → B0 C0 → 베드 중앙 → 원점 선언 → TCP
GOOD_START = ("G49", "M82", "G28 X", "G28", "G0 C0 B0 F3000", "G1 Z15 F3000",
              "G0 X100 Y100 F2400", "G92 X0 Y0 C0 B0", "G43.4")


# ─────────────────────────────────────────────────────────────
# A. 핫엔드 모델과 B_safe
# ─────────────────────────────────────────────────────────────
def test_viewer_hotend_model_matches_facts_doc():
    """뷰어 모델의 치수와 '몇 도에서 닿나' 가 사실표와 같다.

    이 숫자들은 조사로 얻은 것이라 조용히 바뀌면 근거를 잃는다.
    """
    h = REP5X_V3SE_HOTEND
    assert "실측 전 추정" in h.name and "REP5X viewer model" in h.name
    assert (h.body_radius, h.body_z0, h.body_z1) == (4.5, 2.0, 8.0)
    assert (h.block_z0, h.block_height) == (8.0, 20.0)
    assert h.bed_rims() == ((2.0, 4.5, 4.5), (8.0, 14.0, 10.0), (15.0, 0.0, 20.0))
    # 팁이 베드면에 있을 때 닿기 시작하는 각도: 노즐 몸통 약 24°
    assert b_safe(0.0, h, clearance=0.0) == pytest.approx(
        math.degrees(math.atan(2.0 / 4.5)), abs=1e-9)
    assert b_safe(0.0, h, clearance=0.0) == pytest.approx(23.96, abs=0.01)
    # 블록 모서리 30~39°: +14 쪽 29.7°, −10 쪽 38.7° (우리는 큰 쪽을 쓴다)
    assert math.degrees(math.atan(8.0 / 14.0)) == pytest.approx(29.74, abs=0.01)
    assert REP5X.hotend is h, "REP5X 프로파일의 기본 핫엔드가 뷰어 모델이 아니다"


def test_old_hotend_default_is_unchanged():
    """예전 기본 모델은 그대로 남아 있다 (옛 수치 재현용)."""
    h = HotendProfile()
    assert (h.tip_radius, h.cone_half_deg, h.cone_height) == (0.6, 30.0, 3.0)
    assert (h.block_radius, h.block_z0, h.block_height) == (12.0, 5.0, 12.0)
    assert h.body_radius == 0.0 and h.rims == ()
    # 팁 평면(반경 0.6)이 있는 모델: 기울이면 그 가장자리가 먼저 내려간다
    assert b_safe(0.15, h, clearance=0.2) == pytest.approx(
        math.degrees(math.asin(0.15 / 0.6)), abs=1e-6)


def test_b_safe_is_the_exact_root_of_bed_gap():
    """닫힌 식 `b_safe` 가 `bed_gap = 0` 의 근이고, 그보다 크면 침범이다."""
    for clr in (0.0, 0.2, 0.5):
        for h in (0.0, 0.1, 0.15, 0.3, 1.0, 2.5, 6.0):
            b = b_safe(h, clearance=clr)
            if b <= 0.0:
                continue
            assert bed_gap(h, b, clearance=clr) == pytest.approx(0.0, abs=1e-9)
            assert bed_gap(h, b - 0.5, clearance=clr) > 0.0
            assert bed_gap(h, b + 0.5, clearance=clr) < 0.0
            assert bed_gap(h, -b, clearance=clr) == pytest.approx(0.0, abs=1e-9), \
                "B 부호에 따라 답이 달라졌다 (축 통과 때 부호가 뒤집힌다)"
            # 무차별 훑기와 대조 — 닫힌 식이 구간을 잘못 고르지 않았는지
            scan = max((k / 100.0 for k in range(0, 8900)
                        if bed_gap(h, k / 100.0, clearance=clr) >= 0.0), default=0.0)
            assert scan == pytest.approx(b, abs=0.011)


def test_b_safe_grows_with_height_and_shrinks_with_clearance():
    hs = [0.0, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
    vals = [b_safe(h) for h in hs]
    assert all(b > a for a, b in zip(vals, vals[1:], strict=False)), vals
    assert b_safe(0.15, clearance=0.4) < b_safe(0.15, clearance=0.2) < \
        b_safe(0.15, clearance=0.0)
    assert b_safe(-0.1) == 0.0, "팁이 베드 아래인데 기울여도 된다고 했다"
    assert b_safe(0.1, clearance=3.0) == 0.0, "수직으로도 여유를 못 지키는데 0 이 아니다"
    # 역함수
    for b in (5.0, 20.0, 30.0, 45.0):
        assert b_safe(max(0.0, tip_height_needed(b)) + 1e-9) >= b - 1e-6


def test_profile_carries_machine_facts():
    """새로 붙인 기계 상수 (facts §4, §5, §7)."""
    assert REP5X.native_x == (0.0, 200.0) and REP5X.native_y == (-40.0, 200.0)
    assert REP5X.bed_center == (100.0, 100.0)          # [실기 확인]
    assert REP5X.home_b == -135.0 and REP5X.home_c == 0.0
    assert REP5X.omega_max == 90.0
    assert REP5X.bed_clearance == pytest.approx(0.2)


# ─────────────────────────────────────────────────────────────
# B(i). 베드 간섭 검사
# ─────────────────────────────────────────────────────────────
def _ring(z, b, r=5.0, n=8, f=1800.0):
    out = []
    for k in range(n + 1):
        a = 2 * math.pi * k / n
        out.append(("move", Move(g=1, x=r * math.cos(a), y=r * math.sin(a), z=z,
                                 e=0.05 * (k + 1), f=f,
                                 extra=f"B{b:.3f} C{math.degrees(a):.3f}")))
    return out


def test_bed_collision_is_fatal_when_tilted_at_first_layer():
    """팁 Z 0.3 에서 B 30° → 치명, 20° → 통과. 수치도 맞는지."""
    f, st = check_rep5x(_raw("G43.4") + _ring(0.3, 30.0))
    msgs = [m for m in _fatal(f) if "베드 여유" in m]
    assert msgs, f
    assert st["bed_hits"] == 9 and st["bed_hits_extruding"] == 9
    want = 0.3 + 2.0 * math.cos(math.radians(30)) - 4.5 * math.sin(math.radians(30)) - 0.2
    assert st["bed_gap_min"] == pytest.approx(want, abs=1e-6)

    f, st = check_rep5x(_raw("G43.4") + _ring(0.3, 20.0))
    assert st["bed_hits"] == 0 and not [m for m in _fatal(f) if "베드 여유" in m]
    # 높이 올리면 30° 도 된다 — 검사가 각도만 보는 게 아니다
    _f, st = check_rep5x(_raw("G43.4") + _ring(3.0, 30.0))
    assert st["bed_hits"] == 0


def test_bed_check_interpolates_inside_a_move_and_sees_travel():
    """이동 **도중**의 자세도 본다. 압출이 아니어도 친다."""
    # ① 높은 곳에서 B=40° 로 기운 채 내려온다 (트래블) → 내려오는 이동이 친다.
    # ② 거기서 올라가며 세운다 → **끝**(Z10, B0)은 안전하지만 출발 직후가 아직 낮고
    #    기울어 있다. 끝 자세만 보면 놓친다.
    items = _raw("G43.4") + [
        ("move", Move(g=0, x=5.0, y=0.0, z=10.0, f=3000.0, extra="B40.000 C0.000")),
        ("move", Move(g=0, x=5.0, y=0.0, z=0.3, f=3000.0, extra="B40.000 C0.000")),
        ("move", Move(g=0, x=5.0, y=0.0, z=10.0, f=3000.0, extra="B0.000 C0.000"))]
    _f, st = check_rep5x(items)
    assert st["bed_hits"] == 2 and st["bed_hits_extruding"] == 0
    # ③ 제자리에서 눕혔다 세운다: 두 번째 이동의 끝(B=0)은 안전, 도중(B 60→0)이 친다
    items = _raw("G43.4") + [
        ("move", Move(g=0, x=5.0, y=0.0, z=0.3, f=3000.0, extra="B60.000 C0.000")),
        ("move", Move(g=0, x=5.0, y=0.0, z=0.3, f=3000.0, extra="B0.000 C0.000"))]
    _f, st = check_rep5x(items)
    assert st["bed_hits"] == 2, "두 번째 이동의 도중 자세(B 60→0)를 못 봤다"


def test_tip_below_bed_is_fatal():
    items = _raw("G43.4") + [
        ("move", Move(g=1, x=1.0, y=0.0, z=-0.2, e=0.1, f=1800.0, extra="B0.000 C0.000"))]
    f, st = check_rep5x(items)
    assert st["tip_below_bed"] == 1
    assert any("베드 아래" in m for m in _fatal(f))


# ─────────────────────────────────────────────────────────────
# B(ii)(iii)(v). 모달 상태 기계
# ─────────────────────────────────────────────────────────────
def _body(b=15.0, z=1.0):
    # 반경 5 의 고리를 45° 씩 8걸음: 한 걸음 3.83mm. F300 이면 59°/s 로 상한 안이다.
    return _ring(z, b, f=300.0)


def test_good_start_sequence_has_no_state_findings():
    f, st = check_rep5x(_raw(*GOOD_START) + _body())
    assert not _fatal(f), _fatal(f)
    assert st["state_fatal"] == 0 and st["cold_extrusions"] == 0
    assert st["rtcp"] and st["rtcp_on_count"] == 1
    assert not st["origin_assumed"]
    # native = 부품좌표 + (100,100). 홈 자세(200, −40)도 지나간다
    assert st["native_box"] == pytest.approx((95.0, 200.0, -40.0, 105.0))


def test_missing_b0_c0_after_homing_is_fatal():
    """G28 뒤 `G0 C0 B0` 를 빼먹으면: 기운 채 프라임 + 기운 채 TCP 전환."""
    start = ("G49", "M82", "G28", "G1 Z5 F3000", "G1 X20 Y5 F3000",
             "G1 X120 Y5 E12 F1000", "G92 E0", "G0 X100 Y100", "G92 X0 Y0", "G43.4")
    f, st = check_rep5x(_raw(*start) + _body())
    msgs = _fatal(f)
    assert any("압출" in m and "G0 C0 B0" in m for m in msgs), msgs
    assert any("G43.4" in m and "B0 C0" in m and "-135" in m for m in msgs), msgs
    assert st["cold_extrusions"] == 1


def test_tcp_toggle_away_from_zero_is_fatal():
    # 켤 때 C 가 0 이 아니다
    f, _ = check_rep5x(_raw("G49", "G28", "G0 C30 B0 F3000", "G43.4") + _body())
    assert any("`G43.4`" in m and "C=30.0" in m for m in _fatal(f)), f
    # 끌 때 B 가 0 이 아니다 (종료 G-code 가 회전축 복귀보다 G49 를 먼저 하는 경우)
    f, _ = check_rep5x(_raw(*GOOD_START) + _body() + _raw("G49"))
    assert any("`G49`" in m and "B=15.0" in m for m in _fatal(f)), f
    # 되돌린 뒤에 끄면 통과
    f, _ = check_rep5x(_raw(*GOOD_START) + _body()
                       + _raw("G91", "G1 Z10 F1200", "G90", "G0 B0 C0 F1800",
                              "G49", "G28 Z"))
    assert not _fatal(f), _fatal(f)


def test_wrong_tool_is_fatal():
    for bad in ("T1", "T2"):
        f, _ = check_rep5x(_raw(*GOOD_START, bad) + _body())
        assert any(bad in m and "T0" in m for m in _fatal(f)), f
    f, _ = check_rep5x(_raw(*GOOD_START, "T0") + _body())
    assert not _fatal(f)


def test_corner_origin_puts_tip_outside_native_bounds():
    """모서리를 원점으로 선언하면(예전 기본값 0,0) 부품 절반이 native X<0 이다."""
    start = ("G49", "G28", "G0 C0 B0 F3000", "G1 Z15 F3000", "G0 X0 Y0 F2400",
             "G92 X0 Y0 C0 B0", "G43.4")
    f, st = check_rep5x(_raw(*start) + _body())
    assert any("native 범위" in m and "버려진다" in m for m in _fatal(f)), f
    assert st["native_xy_out"] > 0 and st["native_box"][0] == pytest.approx(-5.0)
    # 시작 G-code 가 없는 파일은 베드 중앙을 가정한다 — 가정했다고 알린다
    f, st = check_rep5x(_raw("G43.4") + _body())
    assert st["origin_assumed"] and st["native_xy_out"] == 0
    # 가정해도 부품이 크면 잡는다 (반경 150 → native 250)
    _f, st = check_rep5x(_raw("G43.4") + _ring(5.0, 10.0, r=150.0))
    assert st["native_xy_out"] > 0


def test_joint_z_below_zero_is_a_warning_with_the_number():
    """joint Z = Ztip + (cosB−1)·LB. 치명이 아니라 경고 — 숫자가 들어 있어야 한다."""
    f, st = check_rep5x(_raw(*GOOD_START) + _ring(3.0, 30.0, f=300.0))
    want = 3.0 + (math.cos(math.radians(30.0)) - 1.0) * REP5X.lb
    assert want == pytest.approx(-4.32, abs=0.01)
    assert st["joint_z_min"] == pytest.approx(want, abs=1e-6)
    assert any("joint Z" in m and f"{want:.2f}" in m for m in _warn(f)), f
    assert not any("joint" in m for m in _fatal(f))
    # LB 가 다르면(M665 로 읽은 값) 숫자가 따라 바뀐다
    import dataclasses
    _f, st2 = check_rep5x(_raw(*GOOD_START) + _ring(3.0, 30.0, f=300.0),
                          dataclasses.replace(REP5X, lb=47.9))
    assert st2["joint_z_min"] > st["joint_z_min"]


def test_soft_endstop_off_and_unstated_tcp_are_warned():
    f, _ = check_rep5x(_raw(*GOOD_START, "M211 S0") + _body())
    assert any("M211 S0" in m for m in _warn(f))
    f, _ = check_rep5x(_raw("G28", "G0 C0 B0 F3000", "G1 Z15", "G0 X100 Y100",
                            "G92 X0 Y0 C0 B0", "G43.4") + _body())
    assert any("TCP 상태를 밝히지 않은" in m for m in _warn(f))


def test_start_and_end_rotations_do_not_confuse_tilt_checks():
    """시작의 `G0 C0 B0`, 종료의 `G0 B0 C0` 때문에 '틸트가 여러 값' 이 뜨면 안 된다."""
    items = _raw(*GOOD_START) + _body(15.0) + _raw("G0 B0 C0 F1800", "G49")
    f, st = check_rep5x(items)
    assert not any("틸트" in m for _s, m in f), f
    assert st["b_min"] == st["b_max"] == pytest.approx(15.0)
    assert st["c_max_step_deg"] <= 45.0 + 1e-9, "회전만 하는 줄을 급회전으로 셌다"


def test_print_body_keeps_only_the_tcp_section():
    items = _raw("G28", "G0 C0 B0") + [
        ("move", Move(g=1, x=120.0, y=5.0, e=12.0))] + _raw("G92 E0", "G43.4") \
        + _body() + _raw("G49", "G28 Z")
    body = print_body(items)
    assert len([1 for k, _ in body if k == "move"]) == 9
    assert all(not (k == "move" and p.x == 120.0) for k, p in body), "프라임 선이 남았다"
    # TCP 줄이 없는 파일(경로만)은 그대로
    assert len(print_body(_body())) == 9


# ─────────────────────────────────────────────────────────────
# B(iv) + C(i). 회전축 속도 상한
# ─────────────────────────────────────────────────────────────
def _mv(x, y, z, c, b=20.0, e=None, f=None, g=1):
    return ("move", Move(g=g, x=x, y=y, z=z, e=e, f=f, extra=f"B{b:.3f} C{c:.3f}"))


def test_feed_cap_on_mixed_move():
    """t = max(L/F, Δθ/ω), F′ = L/t."""
    items = [_mv(1.0, 0.0, 5.0, 0.0, f=1800.0, g=0),
             _mv(1.03, 0.0, 5.0, 45.0, e=0.01, f=1800.0),     # 0.03mm 에 45°
             _mv(11.03, 0.0, 5.0, 46.0, e=0.5, f=1800.0)]     # 10mm 에 1° — 안 깎인다
    out, st = limit_rotary_speed(items)
    ms = [p for k, p in out if k == "move"]
    # 첫 자세(B20 C0)가 0 이 아니라 회전만 하는 줄이 앞에 붙는다
    assert ms[0].x is None and ms[0].extra == "B20.000 C0.000" and ms[0].f == 1800.0
    want = 60.0 * 0.03 * 90.0 / 45.0
    assert want == pytest.approx(3.6)
    assert ms[2].f == pytest.approx(want, abs=1e-3) and ms[2].f <= want + 1e-12
    assert ms[3].f == 1800.0
    assert st["capped"] == 1 and st["oriented"] == 1
    # 파일로 썼을 때도 유지된다 (예전 형식 `.0f` 면 F3.6 이 F4 가 돼 상한을 넘는다)
    assert "F3.6 " in ms[2].to_line()
    f, cst = check_rep5x(gc.parse(gc.to_lines(_raw("G43.4") + out)))
    assert cst["omega_violations"] == 0 and not _fatal(f), f
    assert cst["omega_max_deg_s"] == pytest.approx(90.0, rel=1e-3)
    # 안 깎은 것은 잡힌다 — 검사가 살아 있는지
    f, cst = check_rep5x(_raw("G43.4") + items)
    assert cst["omega_violations"] == 1
    assert cst["omega_max_deg_s"] == pytest.approx(45.0 / (0.03 / 30.0), rel=1e-6)
    assert any("회전축 속도" in m for m in _fatal(f))


def test_feed_cap_on_rotation_only_move_uses_degrees_per_minute():
    """XYZ 가 안 움직이면 펌웨어는 F 를 °/min 으로 읽는다 → ω_max·60 이하로."""
    items = [_mv(1.0, 0.0, 5.0, 0.0, b=0.0, f=9000.0, g=0),
             _mv(1.0, 0.0, 5.0, 90.0, b=0.0, f=9000.0, g=0),     # 회전만, 150°/s 요구
             _mv(1.0, 0.0, 5.0, 180.0, b=0.0, f=1200.0, g=0),    # 일부러 느린 것은 그대로
             _mv(1.0, 0.0, 5.0 + 0.0004, 270.0, b=0.0, f=9000.0, g=0)]  # 파일에선 길이 0
    out, st = limit_rotary_speed(items)
    ms = [p for k, p in out if k == "move"]
    assert [m.f for m in ms] == [9000.0, 5400.0, 1200.0, 5400.0]
    assert st["rotation_only"] == 3 and st["capped"] == 0
    f, cst = check_rep5x(gc.parse(gc.to_lines(_raw("G43.4") + out)))
    assert cst["omega_violations"] == 0, f
    _f, cst = check_rep5x(_raw("G43.4") + items)
    assert cst["omega_violations"] == 2


def test_feed_is_restored_after_a_capped_move_without_f():
    """F 는 모달이다. 깎은 줄 다음 줄에 F 가 없으면 원래 피드를 다시 적어야 한다."""
    items = [_mv(1.0, 0.0, 5.0, 0.0, b=0.0, f=1800.0, g=0),
             _mv(1.03, 0.0, 5.0, 45.0, b=0.0, e=0.01),          # F 없음 (모달 1800)
             _mv(11.03, 0.0, 5.0, 45.0, b=0.0, e=0.5)]          # F 없음
    out, _ = limit_rotary_speed(items)
    ms = [p for k, p in out if k == "move"]
    assert ms[1].f == pytest.approx(3.6, abs=1e-3)
    assert ms[2].f == 1800.0, "깎인 피드가 다음 이동으로 이어졌다"


def test_feed_cap_uses_coordinates_as_written():
    """numpy 스칼라 좌표의 반올림이 파일과 어긋나면 상한을 0.02% 넘는다 (실제로 났다)."""
    v = np.float64(7.9875)
    assert round(v, 3) != float(f"{v:.3f}"), "이 값이 더는 어긋나지 않으면 테스트를 고칠 것"
    items = [_mv(np.float64(1.0), 0.0, np.float64(7.9875), 0.0, f=1800.0, g=0),
             _mv(np.float64(1.05), 0.0, np.float64(7.9865), 40.0, e=0.01, f=1800.0)]
    out, _ = limit_rotary_speed(items)
    _f, cst = check_rep5x(gc.parse(gc.to_lines(_raw("G43.4") + out)))
    assert cst["omega_violations"] == 0


def test_real_path_has_no_rotary_violation_after_cap():
    """실제 경로(funnel 20°)에서 깎기 전에는 수천 건, 깎은 뒤에는 0건."""
    from conical.backtransform import backtransform
    from conical.planar_slicer import slice_mesh
    from conical.rep5x import add_c_rewinds
    from conical.transform import transform_cone
    mesh = center_on_axis(trimesh.load(ROOT / "examples" / "funnel.stl", force="mesh"))
    items = slice_mesh(trimesh.Trimesh(
        vertices=transform_cone(mesh.vertices, 20.0, "outward"), faces=mesh.faces,
        process=False), layer_height=0.6)
    real, _ = backtransform(items, 20.0, "outward")
    out, _ = to_rep5x(real, 20.0, "outward")
    out, _ = add_c_rewinds(out, REP5X)
    _f, before = check_rep5x(out)
    assert before["omega_violations"] > 100
    capped, st = limit_rotary_speed(out)
    f, after = check_rep5x(gc.parse(gc.to_lines(capped)))
    assert after["omega_violations"] == 0 and not _fatal(f), _fatal(f)
    assert st["capped"] > 100 and st["min_feed"] > 0.0
    # 좌표·E·B·C 는 그대로다 (첫 자세 맞춤 한 줄만 늘었다)
    a = [p for k, p in out if k == "move"]
    b = [p for k, p in capped if k == "move" and p.x is not None]
    assert len(a) == len(b)
    assert all((m.x, m.y, m.z, m.e, m.extra) == (n.x, n.y, n.z, n.e, n.extra)
               for m, n in zip(a, b, strict=True))


# ─────────────────────────────────────────────────────────────
# B(vi) + C(iii). M668 줄 형식
# ─────────────────────────────────────────────────────────────
def test_m668_line_format():
    ok = ["; comment z0.6", "G43.4", "M104 S210 ; 온도", "G1 X1.000 Y2.000 E0.10000 F1800",
          "G0 F1800 B22.790 C270.000"]
    f, st = check_m668_format(ok)
    assert not f and st["move_lines"] == 2
    f, st = check_m668_format(["G1 X1 Y2 F600 ; tilt head z0.6"])
    assert st["commented"] == 1 and any("주석" in m for m in _fatal(f))
    f, st = check_m668_format(["  G1 X1 Y2", "g1 X1 Y2"])
    assert st["indented"] == 2 and any("0열" in m for m in _fatal(f))
    f, st = check_m668_format(["G1 X1 " + "Y2 " * 50])
    assert st["too_long"] == 1 and any("127자" in m for m in _fatal(f))
    f, st = check_m668_format(["G2 X1 Y2 I3 J4"])
    assert st["arcs"] == 1 and _fatal(f)
    # 긴 주석 줄(;CONICAL_META)은 치명이 아니라 정보
    f, st = check_m668_format([";CONICAL_META " + "x" * 300])
    assert st["long_other_lines"] == 1 and not _fatal(f) and f[0][0] == "정보"
    # G43.4, G28, G92 는 이동 줄이 아니다
    assert check_m668_format(["G43.4", "G28 X", "G92 X0 Y0 C0 B0"])[1]["move_lines"] == 0


def test_header_has_no_commented_move_and_rtcp_only_when_asked():
    """`to_rep5x` 헤더: 주석 붙은 이동 줄 없음, G43.4 는 요청할 때만."""
    items = [("move", Move(g=1, x=5.0, y=0.0, z=1.0, e=0.1, f=1800.0))]
    out, _ = to_rep5x(items, 20.0, "outward")
    lines = gc.to_lines(out)
    assert lines.count("G43.4") == 1
    assert not _fatal(check_m668_format(lines)[0])
    assert not any("tilt head" in ln for ln in lines)
    out, _ = to_rep5x(items, 20.0, "outward", emit_rtcp=False)
    assert "G43.4" not in gc.to_lines(out)


# ─────────────────────────────────────────────────────────────
# C(ii). 베드 안전 프로필
# ─────────────────────────────────────────────────────────────
def _revolved(profile_rz):
    m = trimesh.creation.revolve(np.asarray(profile_rz, dtype=float), sections=64)
    if m.volume < 0:
        m.invert()
    return center_on_axis(m)


@pytest.fixture(scope="module")
def cylinder_rp():
    """원기둥 r=10, h=12 — 첫 층들이 반경 10 까지 나가 베드에 가장 넓게 닿는 형상."""
    mesh = _revolved([(0, 0), (10, 0), (10, 12), (0, 12)])
    v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=1.0)
    return RadiusProfile(trimesh.Trimesh(vertices=v, faces=f, process=False), n_bins=120)


def test_bed_safe_profile_leaves_safe_requests_alone(cylinder_rp):
    req = AngleProfile.constant(15.0)
    new, info = bed_safe_profile(req, cylinder_rp, 0.3)
    assert new is req and not info["changed"] and not info["notes"]
    assert info["theta_bed"] == pytest.approx(b_safe(0.15, clearance=0.25), abs=0.011)


def test_bed_safe_profile_lowers_the_bottom_and_ramps_up(cylinder_rp):
    """30° 요청 → 바닥은 B_safe 이하, 위에서 30° 로. 블렌드 제약도 지킨다."""
    lh = 0.3
    new, info = bed_safe_profile(AngleProfile.constant(30.0), cylinder_rp, lh)
    assert info["changed"] and info["notes"]
    th_bed = info["theta_bed"]
    assert th_bed < 24.0
    assert float(new.theta_at(0.0)) == pytest.approx(th_bed, abs=1e-6)
    assert float(new.theta_at(50.0)) == pytest.approx(30.0, abs=1e-6)
    z_a, z_b = info["ramps"]["outward"]
    # 원기둥은 Z′ < r·tanθ ≈ 4.2mm 인 레이어가 바닥 가장자리까지 내려온다
    assert z_a > 10.0 * math.tan(math.radians(th_bed)) - 0.5
    # 기존 블렌드 폭 제약(층간격 배율 [1/1.5, 1.5])을 지킨다
    assert new.check_spacing(cylinder_rp.global_max, "outward", 1.5, cylinder_rp) == []
    assert new.validate(cylinder_rp.global_max, "outward")
    # 어느 레이어도 그 레이어의 상한을 넘지 않는다
    zw = np.arange(0.0, 20.0, 0.05)
    cap = bed_tilt_cap(zw, cylinder_rp, lh, clearance=0.25)
    assert np.all(new.theta_at(zw) <= cap + 1e-6)
    assert np.all(cap >= th_bed - 1e-6), "상한이 B_safe(층고/2) 아래로 내려갔다"


def test_bed_safe_profile_clips_variable_and_inward_requests(cylinder_rp):
    # 가변각: 아래 밴드 35°, 위 밴드 0° — 위쪽 블렌드는 요청 그대로 남아야 한다
    req = AngleProfile([(0.0, 35.0), (8.0, 35.0), (11.0, 0.0), (12.0, 0.0)])
    new, info = bed_safe_profile(req, cylinder_rp, 0.3)
    assert info["changed"]
    assert float(new.theta_at(0.0)) == pytest.approx(info["theta_bed"], abs=1e-6)
    assert float(new.theta_at(11.5)) == pytest.approx(0.0, abs=1e-9)
    zw = np.arange(0.0, 14.0, 0.05)
    # (각도를 소수 6자리로 적으므로 tan 이 1e-8 쯤 흔들린다)
    assert np.all(new.tan_at(zw) <= req.tan_at(zw) + 1e-6), "요청보다 큰 각도가 생겼다"
    # inward (음수 각도): 크기가 같은 규칙으로 깎인다
    new_in, info_in = bed_safe_profile(AngleProfile.constant(-30.0), cylinder_rp, 0.3)
    assert info_in["changed"]
    assert float(new_in.theta_at(0.0)) == pytest.approx(-info_in["theta_bed"], abs=1e-6)
    assert float(new_in.theta_at(50.0)) == pytest.approx(-30.0, abs=1e-6)


def test_to_rep5x_bed_guard_clamps_and_reports():
    """이동별 방어선: 팁 높이의 B_safe 를 넘는 틸트는 깎고, 몇 개인지 센다."""
    items = [("move", Move(g=1, x=5.0, y=0.0, z=0.2, e=0.1, f=1800.0)),
             ("move", Move(g=1, x=0.0, y=5.0, z=0.2, e=0.2, f=1800.0)),
             ("move", Move(g=1, x=-5.0, y=0.0, z=6.0, e=0.3, f=1800.0))]
    out, st = to_rep5x(items, 30.0, "outward", bed_clearance=0.2)
    bs = [float(p.extra.split()[0][1:]) for k, p in out if k == "move"]
    lim = b_safe(0.2, clearance=0.205)
    assert bs[0] == pytest.approx(lim, abs=1e-3) and bs[0] <= lim
    assert bs[2] == pytest.approx(30.0)
    assert st["bed_clamped"] == 2 and st["bed_clamp_max_deg"] == pytest.approx(30.0 - bs[0])
    _f, cst = check_rep5x(out)
    assert cst["bed_hits"] == 0
    # 끄면(기본값) 예전 동작 그대로 — 그리고 검사기가 잡는다
    out0, st0 = to_rep5x(items, 30.0, "outward")
    assert st0["bed_clamped"] == 0
    assert check_rep5x(out0)[1]["bed_hits"] == 2


# ─────────────────────────────────────────────────────────────
# D. 기계 프로파일 rep5x_ender3v3se.ini
# ─────────────────────────────────────────────────────────────
CTX = {"layer_height": 0.3, "angle": "24.0", "direction": "outward",
       "mode": "rep5x", "source_stl": "m.stl"}


def _codes(items):
    return [ln.split(";", 1)[0].strip() for _k, ln in items
            if ln.split(";", 1)[0].strip()]


def test_new_machine_profile_order_is_safe():
    """시작/종료 G-code 의 **순서**를 고정한다 — 순서가 곧 안전이다."""
    mp = MachineProfile.from_file(NEW_INI)
    head, tail = _codes(mp.start_items(CTX)), _codes(mp.end_items(CTX))

    def at(seq, code):
        return seq.index(code)

    assert head[0] == "G49", "TCP 를 끄고 시작해야 한다"
    assert at(head, "G28 X") < at(head, "G28") < at(head, "G0 C0 B0 F3000")
    prime = next(i for i, c in enumerate(head) if c.startswith("G1") and " E" in c)
    assert at(head, "G0 C0 B0 F3000") < prime, "B0 C0 복귀 전에 프라임한다"
    assert prime < at(head, "G0 X100 Y100 F2400") < at(head, "G92 X0 Y0 C0 B0") \
        < at(head, "G43.4")
    assert head.count("G43.4") == 1
    assert "M82" in head and "M83" not in head, "이 파이프라인은 절대 E 다"
    assert not any(c.startswith("M211 S0") for c in head + tail), \
        "소프트 엔드스톱을 끄면 안 된다 (라이브 TCP 의 유일한 보호)"
    # 종료: 올리고 → 회전축 0 → TCP 끄기 → Z 호밍 → 모터(Z 는 남긴다)
    assert at(tail, "G92 E0") < at(tail, "G1 E-2 F2700"), \
        "절대 E 에서 G92 E0 없이 E-2 를 하면 통째로 되감는다"
    assert at(tail, "G91") < at(tail, "G1 Z10 F1200") < at(tail, "G90") \
        < at(tail, "G0 B0 C0 F1800") < at(tail, "G49") < at(tail, "G28 Z")
    assert tail[-1] == "M84 X Y E C B"
    assert "TEMPLATE" not in mp.name and "실기 확인" in mp.name
    # 이동 줄에 주석이 없다 (M668)
    lines = [ln for _k, ln in mp.start_items(CTX) + mp.end_items(CTX)]
    assert not _fatal(check_m668_format(lines)[0])


def test_new_machine_profile_passes_the_state_machine():
    mp = MachineProfile.from_file(NEW_INI)
    items = mp.start_items(CTX) + _ring(1.0, 20.0, f=300.0) + mp.end_items(CTX)
    f, st = check_rep5x(gc.parse(gc.to_lines(items)))
    assert not _fatal(f), _fatal(f)
    assert st["state_fatal"] == 0 and st["bed_hits"] == 0 and st["native_xy_out"] == 0
    assert not any("TCP 상태" in m or "M211" in m or "G28" in m for m in _warn(f)), f
    # 프라임 선은 native (20..120, 5), 부품은 native (100,100) 둘레
    assert st["native_box"][2] == pytest.approx(-40.0)        # 홈 Y
    assert st["native_box"][1] == pytest.approx(200.0)        # 홈 X


def test_old_template_is_not_rep5x_safe():
    """`machine.example.ini` 로 REP5X 파일을 만들면 검사기가 막는다 (B0 C0 복귀 없음)."""
    mp = MachineProfile.from_file(ROOT / "profiles" / "machine.example.ini")
    out, _ = to_rep5x([("move", Move(g=1, x=5.0, y=0.0, z=1.0, e=0.1, f=600.0))],
                      20.0, "outward")
    f, _ = check_rep5x(gc.parse(gc.to_lines(mp.start_items(CTX) + out)))
    assert any("G0 C0 B0" in m for m in _fatal(f)), f


# ─────────────────────────────────────────────────────────────
# E. 회귀: 예전 예시 파일은 치명, 새로 뽑은 파일은 치명 0
# ─────────────────────────────────────────────────────────────
def test_old_example_file_is_fatal_on_bed_and_start_state():
    """뽑아 둔 `lamp_expA_band2_lh03_rep5x.gcode` — 이대로 걸면 기계를 친다."""
    lines = OLD_EXAMPLE.read_text(encoding="utf-8").splitlines()
    f, st = check_rep5x(gc.parse(lines))
    msgs = _fatal(f)
    # 베드: 첫 층들에서 B=30° 로 압출하는 이동이 여유를 침범한다
    assert st["bed_hits_extruding"] > 100, st["bed_hits_extruding"]
    assert any("베드 여유" in m for m in msgs), msgs
    # 시작 상태: 기운 채(−135°) 프라임, 기운 채 G43.4
    assert st["cold_extrusions"] >= 1
    assert any("G0 C0 B0" in m for m in msgs), msgs
    assert any("`G43.4`" in m and "-135" in m for m in msgs), msgs
    # 그리고 나머지 결함들
    assert st["omega_violations"] > 1000 and st["omega_max_deg_s"] > 3600.0
    assert st["native_xy_out"] > 1000, "모서리 원점이라 부품 절반이 native X<0"
    assert st["joint_z_min"] == pytest.approx(-7.05, abs=0.3)
    fm, fst = check_m668_format(lines)
    assert fst["commented"] > 0 and _fatal(fm)


def _slice(tmp_path, name, *args, stl="examples/lamp.stl"):
    out = tmp_path / name
    r = subprocess.run(
        [sys.executable, "conical_slice.py", stl, "--mode", "rep5x",
         "--machine-profile", str(NEW_INI), "-o", str(out), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=900)
    return r, out


@pytest.mark.parametrize("label,args", [
    ("band2", ["--auto-bands", "2", "--layer-height", "0.6"]),
    ("uniform30", ["--angle", "30", "--layer-height", "0.6"]),
    ("planar", ["--angle", "0", "--layer-height", "0.6"]),
])
def test_new_files_have_zero_fatal(tmp_path, label, args):
    """새 프로파일로 뽑은 파일: 전체 검사에서 치명 0. (실제 CLI 를 돌려 파일을 읽는다)"""
    r, out = _slice(tmp_path, f"{label}.gcode", *args)
    assert r.returncode == 0, f"{label}:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}"
    assert "치명" not in r.stdout, r.stdout
    lines = out.read_text(encoding="utf-8").splitlines()
    items = gc.parse(lines)
    f, st = check_rep5x(items)
    fm, fst = check_m668_format(lines)
    assert not _fatal(f + fm), f"{label}: {_fatal(f + fm)}"
    assert st["bed_hits"] == 0 and st["bed_gap_min"] >= 0.0
    assert st["omega_violations"] == 0
    assert st["omega_max_deg_s"] <= REP5X.omega_max * (1 + 1e-6)
    assert st["native_xy_out"] == 0 and st["state_fatal"] == 0
    assert st["tip_below_bed"] == 0
    assert fst["commented"] == 0 and fst["indented"] == 0 and fst["too_long"] == 0
    # TCP 는 정확히 한 번, 시작 G-code 안에서 켠다 (경로 헤더가 다시 켜지 않는다)
    assert [ln.split(";", 1)[0].strip() for ln in lines].count("G43.4") == 1
    assert st["rtcp_on_count"] == 1
    assert not any("tilt head" in ln for ln in lines)
    if label != "planar":
        # 베드 안전 때문에 바닥 각도가 요청(30°)보다 낮아졌다고 **출력에 적혀 있다**
        assert "베드 안전(outward)" in r.stdout
        assert "베드 방어선" not in r.stdout, "프로필 계획이 못 잡은 이동이 있다"
        # 출력물과의 간섭도 없다 (각도를 낮춰 붙인 블렌드가 간섭을 만들지 않았다)
        _c, ci = check_head_interference(print_body(items), REP5X, stride=16)
        assert ci["collision_pct"] == 0.0, ci


def test_strict_refuses_to_lower_the_angle(tmp_path):
    """`--strict`: 요청 각도를 못 쓰면 고치지 않고 멈춘다 (균일 대조군용)."""
    r, out = _slice(tmp_path, "s.gcode", "--angle", "30", "--layer-height", "0.6",
                    "--strict")
    assert r.returncode != 0 and not out.exists()
    assert "--strict" in r.stderr and "B_safe" in r.stderr
    # 못 쓰는 각도가 아니면 --strict 여도 그냥 된다.
    # ⚠ 이 줄은 되감기 끝 자세 결함의 회귀 테스트도 겸한다: 링을 번갈아 돌리면 이 경로에서
    # 되감기가 직전 C 351.7° 를 −368.3° 로 보내 창 밖에 떨어졌다 (2026-11-10, add_c_rewinds
    # 가 c_prev 를 범위에 넣어 고침)
    r, out = _slice(tmp_path, "ok.gcode", "--angle", "15", "--layer-height", "0.6",
                    "--strict")
    assert r.returncode == 0 and out.exists(), r.stdout[-2000:] + r.stderr[-2000:]


def test_bare_rep5x_output_is_reported_not_silently_passed(tmp_path):
    """기계 프로파일 없이 뽑으면: 경로 자체는 치명 0 이지만 원점을 **가정**했다고 알린다."""
    out = tmp_path / "bare.gcode"
    r = subprocess.run(
        [sys.executable, "conical_slice.py", "examples/funnel.stl", "--mode", "rep5x",
         "--angle", "20", "--layer-height", "0.6", "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "기계 프로파일이 없다" in r.stdout
    lines = out.read_text(encoding="utf-8").splitlines()
    f, st = check_rep5x(gc.parse(lines))
    assert not _fatal(f), _fatal(f)
    assert st["origin_assumed"] and st["rtcp_on_count"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))



def test_m668_with_soft_endstops_and_negative_joint_z_is_fatal(tmp_path):
    """M668 은 joint 좌표로 실행한다 → 켜진 소프트 엔드스톱이 기울인 이동(joint Z<0)을 자른다."""
    out = tmp_path / "m668.gcode"
    r = subprocess.run(
        [sys.executable, "conical_slice.py", "examples/rep5x_ladder/lamp_small.stl",
         "--angle", "20", "--direction", "outward", "--layer-height", "0.6", "--mode", "rep5x",
         "--machine-profile", "profiles/rep5x_ender3v3se_m668.ini", "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    lines = out.read_text(encoding="utf-8").splitlines()
    f, _ = check_rep5x(gc.parse(lines))
    assert not _fatal(f), _fatal(f)                      # 프로파일이 M211 S0 을 넣으므로 통과
    bad = [ln.replace("M211 S0", "M211 S1") for ln in lines]
    f2, _ = check_rep5x(gc.parse(bad))
    assert any("M668" in m for m in _fatal(f2)), _fatal(f2)
