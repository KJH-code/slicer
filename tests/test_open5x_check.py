"""T15: Open5x 기계좌표 출력 사전 점검 (검사기 C).

왜 필요한가: `toolpath_check.py` 의 검사기 A/B 는 **3축 가정**(노즐 수직, 베드
고정)이라 5축 출력에는 안 맞는다. 다음 달 프린터가 나오면 이 G-code 가 실제
기계로 들어간다. 5축은 3축보다 사고가 쉽고, 사고가 나면 기계가 상한다.

모듈 docstring 의 '실기 체크리스트'(회전 누적, 축 근처 급회전)를 사람이 기억하는
대신 검사가 기억하게 만든 것이다. 실제 생성물에서 셋이 걸린다 —
배선 감김(175회전), V 179° 급회전, 기계 Z 음수.

    python3 tests/test_open5x_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.gcode import Move
from conical.open5x import PRUSA_UV, check_open5x

ROOT = Path(__file__).resolve().parent.parent


def _moves(vs, z=1.0, x=10.0, tilt=20.0):
    """틸트 한 번 + 주어진 V 값들로 이동을 만든다."""
    out = [("move", Move(g=1, x=0.0, y=0.0, z=z, f=600, extra=f"U{tilt:.3f}"))]
    out += [("move", Move(g=1, x=x, y=0.0, z=z, e=float(i) * 0.1, f=1200,
                          extra=f"V{v:.3f}"))
            for i, v in enumerate(vs)]
    return out


def _sev(findings):
    return {s for s, _ in findings}


def test_clean_output_has_no_fatal():
    """완만하게 도는 정상 출력은 아무것도 안 걸려야 한다."""
    findings, st = check_open5x(_moves([0, 10, 20, 30, 40]), PRUSA_UV)
    assert "치명" not in _sev(findings), findings
    assert st["tilt"] == 20.0
    assert st["v_max_step_deg"] == 10.0


def test_tilt_over_limit_is_fatal():
    findings, _ = check_open5x(_moves([0, 5], tilt=120.0), PRUSA_UV)
    assert any("틸트" in m for s, m in findings if s == "치명"), findings


def test_missing_tilt_is_fatal():
    items = [("move", Move(g=1, x=1.0, y=0.0, z=1.0, extra="V0.0"))]
    findings, _ = check_open5x(items, PRUSA_UV)
    assert any("틸트" in m for s, m in findings if s == "치명"), findings


def test_cable_wrap_is_fatal():
    """V 가 한 방향으로 계속 누적되면 배선이 감긴다 — 슬립링이 없으면 치명."""
    vs = [i * 30.0 for i in range(200)]          # 약 16.6회전
    findings, st = check_open5x(_moves(vs), PRUSA_UV, max_dv_deg=45.0)
    assert st["v_turns_accumulated"] > 15
    assert any("배선" in m for s, m in findings if s == "치명"), findings


def test_azimuth_flip_is_flagged():
    """축 근처에서 V 가 한 이동에 180° 뛰는 것 — docstring 체크리스트 (b)."""
    findings, st = check_open5x(_moves([0.0, 179.0]), PRUSA_UV)
    assert st["v_max_step_deg"] == 179.0
    assert any("뛴다" in m for s, m in findings if s == "치명"), findings


def test_negative_machine_z_is_fatal():
    findings, _ = check_open5x(_moves([0, 5], z=-1.0), PRUSA_UV)
    assert any("소프트리밋" in m for s, m in findings if s == "치명"), findings


def test_off_bed_is_fatal():
    findings, _ = check_open5x(_moves([0, 5], x=200.0), PRUSA_UV, bed_radius=90)
    assert any("베드" in m for s, m in findings if s == "치명"), findings


def test_real_pipeline_output_trips_known_risks():
    """실제 파이프라인 출력에서 알려진 위험 셋이 잡히는지 (통합).

    이 셋은 '고쳐야 할 결함'이 아니라 **실기 전에 사람이 알아야 할 사실**이다.
    되감기나 Z 오프셋 없이 그대로 걸면 기계가 상한다.
    """
    import subprocess
    import tempfile
    from conical import gcode as gc

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "o5.gcode"
        r = subprocess.run(
            [sys.executable, "conical_slice.py", "examples/funnel.stl",
             "--angle", "20", "--mode", "open5x", "-o", str(out)],
            cwd=ROOT, capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stderr[-2000:]
        items = gc.parse(out.read_text().splitlines(keepends=True))

    findings, st = check_open5x(items, PRUSA_UV)
    assert st["v_turns_accumulated"] > 50, f"배선 감김이 안 잡혔다: {st}"
    assert st["v_max_step_deg"] > 90, f"급회전이 안 잡혔다: {st}"
    assert st["z_min"] < 0, f"기계 Z 음수가 안 잡혔다: {st}"
    assert len([1 for s, _ in findings if s == "치명"]) >= 3, findings


if __name__ == "__main__":
    test_clean_output_has_no_fatal()
    test_tilt_over_limit_is_fatal()
    test_missing_tilt_is_fatal()
    test_cable_wrap_is_fatal()
    test_azimuth_flip_is_flagged()
    test_negative_machine_z_is_fatal()
    test_off_bed_is_fatal()
    test_real_pipeline_output_trips_known_risks()
    print("PASS: 정상 통과 / 틸트·배선·급회전·Z음수·베드이탈 검출 / 실제 출력 통합")
