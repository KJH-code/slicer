"""시작 G-code 의 프라임 선이 부품 자리·출력 가능 반경과 겹치지 않는지.

왜 필요한가: 파이프라인은 부품을 XY 원점(원뿔 축)에 놓는데, 템플릿 프라임 선이
(5,5)→(100,5) 라 부품 한가운데를 지나갔다 — 첫 층이 프라임 선 위에 올라간다.
REP5X 에서는 끝점(반경 100.1)이 PRINTABLE_RADIUS 100 도 넘었다. 2026-10-16
`rep5x_check` 로 새 모델을 돌리다 발견했다.

    python3 -m pytest tests/test_prime_clearance.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conical.machine import MachineProfile, check_start_extrusion

ROOT = Path(__file__).resolve().parent.parent


def _raw(*lines):
    return [("raw", ln) for ln in lines]


def test_old_template_prime_crosses_part():
    """예전 템플릿 좌표는 반경 12mm 부품 위를 지난다 → 치명."""
    head = _raw("G92 E0", "G1 Z0.4", "G1 X5 Y5 F3000", "G1 X100 Y5 E12 F1000")
    f = check_start_extrusion(head, part_radius=12.0, printable_radius=100.0)
    sev = [s for s, _ in f]
    assert sev.count("치명") == 2          # 부품 겹침 + 반경 초과(100.1)
    assert any("부품 자리" in m for _, m in f)
    assert any("출력 가능 반경" in m for _, m in f)


def test_travel_is_not_extrusion():
    """압출 없는 이동은 부품 위를 지나가도 문제 삼지 않는다."""
    head = _raw("G1 X-50 Y0 F3000", "G1 X50 Y0 F3000")
    assert check_start_extrusion(head, part_radius=12.0) == []


def test_g92_reset_respected():
    """G92 E0 뒤 E 가 다시 작아도(프라임 뒤) 압출로 오인하지 않는다."""
    head = _raw("G1 X-40 Y-80", "G1 X40 Y-80 E12", "G92 E0", "G1 X0 Y0 E0")
    assert check_start_extrusion(head, part_radius=12.0) == []


def test_relative_xy_is_reported_not_passed():
    head = _raw("G91", "G1 X10 E1")
    f = check_start_extrusion(head, part_radius=12.0)
    assert f and f[0][0] == "정보"


def test_example_template_is_clear():
    """레포 템플릿이 반경 12mm 부품·REP5X 반경 100 기준으로 통과한다."""
    mp = MachineProfile.from_file(ROOT / "profiles" / "machine.example.ini")
    ctx = {"layer_height": 0.3, "angle": "20.0", "direction": "outward",
           "mode": "rep5x", "source_stl": "m.stl"}
    head = mp.start_items(ctx)
    assert check_start_extrusion(head, part_radius=12.0, printable_radius=100.0) == []
    # 부품이 크면(반경 80) 겹친다고 알려야 한다 — 검사가 살아 있는지
    assert check_start_extrusion(head, part_radius=80.0)
