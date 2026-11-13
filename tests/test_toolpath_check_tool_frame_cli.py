"""toolpath_check.py --tool-frame: ;CONICAL_META 로 층 법선 프레임 판정 (gap_audit G6, F4 연결)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=600)


def test_tool_frame_cli_uses_meta_profile(tmp_path):
    out = tmp_path / "c.gcode"
    r = _run("conical_slice.py", "examples/rep5x_ladder/cylinder.stl", "--angle", "15",
             "--direction", "outward", "--layer-height", "0.6", "-o", str(out))
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    v = _run("toolpath_check.py", str(out))
    t = _run("toolpath_check.py", str(out), "--tool-frame")
    assert v.returncode == 0 and t.returncode == 0, t.stderr[-1500:]
    assert "프레임=연직(3축)" in v.stdout
    assert "프레임=공구(층 법선)" in t.stdout
    assert "진짜 오버행" in t.stdout


def test_tool_frame_cli_refuses_without_meta(tmp_path):
    g = tmp_path / "plain.gcode"
    g.write_text("G21\nG90\nM82\n; layer 0 z=0.3\n;TYPE:PERIMETER\n"
                 "G0 X0 Y0 Z0.3\nG1 X10 Y0 E1 F1200\nG1 X10 Y10 E2\n", encoding="utf-8")
    t = _run("toolpath_check.py", str(g), "--tool-frame", "--layer-height", "0.3")
    assert t.returncode != 0 and "CONICAL_META" in (t.stdout + t.stderr)
