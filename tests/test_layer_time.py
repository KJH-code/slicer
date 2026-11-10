"""최소 층 시간·팬 (docs/gap_audit.md G8 / F5) — 내장 슬라이서의 냉각 기능.

REP5X 시험 출력물은 작다(lamp_small 지름 9.6mm, 층 하나 1~3초). `slice_mesh` 가 층의
추정 시간이 `min_layer_time` 보다 짧으면 그 층의 **압출 피드만** 낮춘다.

    (a) 기본값이면 아무것도 안 바뀐다 — 커밋된 시험 사다리 파일을 다시 뽑으면 그대로다
    (b) 감속한 층은 요청 시간을 채운다 (변환공간). 경로·E·트래블 피드는 그대로
    (c) 속도 하한 아래로 안 내려가고, 못 채운 층은 센다. 하한이 원래 피드보다 높아도
        피드가 **올라가지 않는다**
    (d) 역변환 뒤(실공간)에는 cosθ 배까지 짧아진다 — 문서에 적은 그대로인지
    (e) rep5x 끝까지: `limit_rotary_speed` 를 지난 최종 파일의 어떤 이동도 F 가
        기본 출력보다 크지 않다
    (f) 팬: 처음 2층 뒤에 M106 S255 한 번, 끝에 M106 S0. 안 켜면 M106 이 없다

    python3 -m pytest tests/test_layer_time.py -q
"""

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conical import gcode as gc  # noqa: E402
from conical.backtransform import backtransform  # noqa: E402
from conical.meshio import center_on_axis  # noqa: E402
from conical.planar_slicer import (  # noqa: E402
    FAN_AFTER_LAYERS,
    layer_times,
    slice_mesh,
)
from conical.transform import transform_cone  # noqa: E402

LADDER = ROOT / "examples" / "rep5x_ladder"
# examples/rep5x_ladder/README.md 「다시 뽑기」의 L3a 명령 그대로
L3A_ARGS = ["examples/rep5x_ladder/lamp_small.stl", "--angle", "22",
            "--direction", "outward", "--omega-max", "180", "--strict",
            "--mode", "rep5x", "--layer-height", "0.3",
            "--machine-profile", "profiles/rep5x_ender3v3se.ini"]
FEED = 1800.0


def _cylinder(radius=5.0, height=6.0):
    return center_on_axis(trimesh.creation.cylinder(radius=radius, height=height))


def _lamp_warped(angle=22.0):
    from conical_slice import refine
    m = center_on_axis(trimesh.load(LADDER / "lamp_small.stl", force="mesh"))
    fine = refine(m, 1.5)
    return trimesh.Trimesh(vertices=transform_cone(fine.vertices, angle, "outward"),
                           faces=fine.faces, process=False)


def _run(out, *extra):
    r = subprocess.run([sys.executable, "conical_slice.py", *L3A_ARGS, "-o", str(out),
                        *extra], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    return r


def _moves(items):
    return [mv for k, mv in items if k == "move"]


def _modal_feeds(moves):
    """이동마다 실제로 걸리는 F (모달: 안 적힌 줄은 직전 값)."""
    out, f = [], None
    for mv in moves:
        if mv.f is not None:
            f = mv.f
        out.append(f)
    return out


# ───────── (a) 기본값: 예전과 같다 ─────────
def test_defaults_are_bit_identical_in_process():
    mesh = _cylinder()
    base = gc.to_lines(slice_mesh(mesh))
    off = gc.to_lines(slice_mesh(mesh, min_layer_time=0.0, min_print_speed=10.0,
                                 fan=False, brim=0, stats={}))
    assert base == off
    # 새 기능의 흔적이 하나도 없어야 한다 (머리말 형식 포함)
    assert base[:5] == ["; conical built-in planar slicer",
                        "; layers=20 layer_h=0.3 width=0.45", "G21", "G90", "M82"]
    assert not any("M106" in ln or "BRIM" in ln.upper() or "min_layer_time" in ln
                   for ln in base)
    # 압출은 전부 원래 피드, 트래블은 그 두 배
    for mv in _moves(slice_mesh(mesh)):
        assert mv.f == (FEED if mv.e is not None else 2 * FEED)


def test_default_regeneration_matches_committed_ladder_file(tmp_path):
    """README 의 명령으로 L3a 를 다시 뽑으면 커밋된 파일과 바이트 단위로 같다."""
    out = tmp_path / "L3a.gcode"
    r = _run(out)
    assert out.read_bytes() == (LADDER / "L3a_lamp_u22.gcode").read_bytes(), \
        "기본 옵션의 출력이 바뀌었다 — 시험 사다리 파일이 재현되지 않는다"
    # 꺼져 있어도 층이 짧다는 것은 알린다 (기계 프로파일의 권장값)
    assert "권장 최소 층 시간 8s" in r.stdout and "--min-layer-time 8" in r.stdout


# ───────── (b) 요청 시간을 채운다 ─────────
def test_min_layer_time_respected_and_only_extrusion_feed_changes():
    mesh = _cylinder()
    base = slice_mesh(mesh)
    st = {}
    slow = slice_mesh(mesh, min_layer_time=6.0, stats=st)
    t0, t1 = layer_times(base), layer_times(slow)
    assert len(t1) == 20 and max(t0.values()) < 3.5, "전제: 원래는 모든 층이 6초보다 짧다"
    assert st["floor_limited"] == 0 and st["slowed_layers"] == 20
    for i, before, after in st["layer_times"]:
        # 슬라이서가 적은 통계 = 아이템에서 독립적으로 다시 잰 값
        assert before == pytest.approx(t0[i], abs=1e-9)
        assert after == pytest.approx(t1[i], abs=1e-9)
        assert 6.0 - 1e-9 <= after < 6.05, f"층 {i}: {after:.3f}s"

    # 경로·E 는 그대로, F 만 — 그것도 압출 줄만 — 내려간다
    a, b = _moves(base), _moves(slow)
    assert len(a) == len(b)
    for m0, m1 in zip(a, b, strict=True):
        assert (m0.g, m0.x, m0.y, m0.z, m0.e) == (m1.g, m1.x, m1.y, m1.z, m1.e)
        if m0.e is None:
            assert m1.f == m0.f == 2 * FEED, "트래블 피드는 건드리지 않는다"
        else:
            assert 600.0 <= m1.f < m0.f == FEED
            assert m1.f == math.floor(m1.f), "파일에 적히는 정수 F 와 메모리 값이 같아야 한다"
    assert st["min_feed"] == min(m.f for m in b if m.e is not None)
    # 머리말에 무엇을 켰는지 남는다
    assert "; min_layer_time=6s min_print_speed=10mm/s" in gc.to_lines(slow)


def test_layers_already_slow_enough_are_untouched():
    mesh = _cylinder()
    st = {}
    items = slice_mesh(mesh, min_layer_time=2.0, stats=st)     # 모든 층이 2.8초 이상
    assert st["slowed_layers"] == 0 and st["floor_limited"] == 0 and st["min_feed"] is None
    assert [m.f for m in _moves(items)] == [m.f for m in _moves(slice_mesh(mesh))]


# ───────── (c) 속도 하한 ─────────
def test_speed_floor_is_kept_and_reported():
    mesh = _lamp_warped()
    st = {}
    items = slice_mesh(mesh, min_layer_time=8.0, min_print_speed=10.0, stats=st)
    feeds = [m.f for m in _moves(items) if m.e is not None]
    assert min(feeds) == 600.0 == st["min_feed"], "10mm/s 아래로 내려가면 안 된다"
    assert max(feeds) <= FEED
    after = {i: a for i, _b, a in st["layer_times"]}
    short = [i for i, a in after.items() if a < 8.0 - 1e-9]
    assert st["floor_limited"] == len(short) > 0, "작은 층은 하한에 걸려 8초를 못 채운다"
    # 못 채운 층은 압출이 전부 하한 속도다 (더 내릴 수 있는데 안 내린 게 아니다)
    cur, by_layer = None, {}
    for k, p in items:
        if k == "raw" and p.startswith("; layer "):
            cur = int(p.split()[2])
        elif k == "move" and p.e is not None:
            by_layer.setdefault(cur, set()).add(p.f)
    assert all(by_layer[i] == {600.0} for i in short)
    assert all(after[i] >= 8.0 - 1e-9 for i in after if i not in short)


@pytest.mark.parametrize("v_min", [30.0, 50.0])
def test_floor_at_or_above_feed_never_raises_feed(v_min):
    """하한이 원래 피드(30mm/s) 이상이면 낮출 수 없다 — 그렇다고 올리지도 않는다."""
    mesh = _cylinder()
    st = {}
    items = slice_mesh(mesh, min_layer_time=8.0, min_print_speed=v_min, stats=st)
    assert [m.f for m in _moves(items)] == [m.f for m in _moves(slice_mesh(mesh))]
    assert st["slowed_layers"] == 0 and st["floor_limited"] == 20


# ───────── (d) 역변환 뒤 ─────────
def test_backtransform_keeps_feed_and_shortens_by_at_most_cos_theta():
    """F 는 역변환을 그대로 지나고, 실공간 층 시간은 변환공간 추정의 cosθ~1 배다.

    둘레 방향 길이가 cosθ 배로 줄기 때문이다(반경 방향은 그대로). 층을 바꾸는 트래블
    한 번은 cosθ 보다 조금 더 줄 수 있어서(√(1−sinθ) 배까지) 여유 0.5% 를 둔다.
    """
    theta = 22.0
    mesh = _lamp_warped(theta)
    st = {}
    items = slice_mesh(mesh, min_layer_time=8.0, min_print_speed=1.0, stats=st)
    real, _ = backtransform(items, theta, "outward")
    assert {m.f for m in _moves(real)} == {m.f for m in _moves(items)}, \
        "역변환이 F 를 바꾸면 안 된다 (조각마다 원래 이동의 F 를 물려받는다)"
    tp, tr = layer_times(items), layer_times(real)
    assert tp.keys() == tr.keys() and len(tp) == 66
    empty = [i for i in tp if tp[i] == 0.0]
    assert empty == [65] and tr[65] == 0.0, "꼭대기 층은 표식만 있다 (페리미터가 안 들어간다)"
    assert [i for i, _b, _a in st["layer_times"]] == list(range(65)), "빈 층은 통계에서 뺀다"
    cos = math.cos(math.radians(theta))
    ratio = np.array([tr[i] / tp[i] for i in tp if tp[i] > 0])
    assert ratio.min() >= cos - 0.005 and ratio.max() <= 1.0 + 1e-9, (ratio.min(), ratio.max())
    assert ratio.min() < 0.95, "전제: 이 모델은 둘레 방향 경로가 대부분이라 실제로 줄어든다"
    ok = [i for i, _b, a in st["layer_times"] if a >= 8.0 - 1e-9]
    assert len(ok) >= 60
    assert all(tr[i] >= 8.0 * (cos - 0.005) for i in ok)
    assert min(tr[i] for i in ok) < 8.0, "문서에 적은 대로 실공간은 요청보다 짧을 수 있다"


# ───────── (e) rep5x 끝까지: F 가 올라가지 않는다 ─────────
def test_rep5x_final_feeds_never_exceed_default(tmp_path):
    """`--min-layer-time` 을 켠 최종 파일의 모든 이동은 F 가 기본 출력 이하다.

    `rep5x.limit_rotary_speed` 가 마지막에 회전 상한으로 F 를 더 깎는다. 최소 층
    시간이 그 뒤에 F 를 다시 올리면 회전축이 상한을 넘는다.
    """
    out = tmp_path / "slow.gcode"
    r = _run(out, "--min-layer-time", "8", "--fan")
    assert "치명" not in r.stdout, r.stdout
    assert "층 시간(파일)" in r.stdout and "속도 하한 10mm/s" in r.stdout
    base = gc.parse((LADDER / "L3a_lamp_u22.gcode").read_text(encoding="utf-8").splitlines())
    slow = gc.parse(out.read_text(encoding="utf-8").splitlines())
    a, b = _moves(base), _moves(slow)
    assert len(a) == len(b)
    n_lower = 0
    for m0, m1, f0, f1 in zip(a, b, _modal_feeds(a), _modal_feeds(b), strict=True):
        assert (m0.g, m0.x, m0.y, m0.z, m0.e, m0.extra) == \
            (m1.g, m1.x, m1.y, m1.z, m1.e, m1.extra), "경로·E·B/C 는 그대로여야 한다"
        assert f1 <= f0, f"F 가 올라갔다: {m0.to_line()} → {m1.to_line()}"
        n_lower += f1 < f0
    assert n_lower > 500, "켰는데 낮아진 이동이 거의 없다"
    # 그래서 층 시간은 어느 층도 줄지 않는다
    t0, t1 = layer_times(base), layer_times(slow)
    assert t0.keys() == t1.keys() and len(t0) == 66
    assert all(t1[i] >= t0[i] - 1e-9 for i in t0)
    assert np.median(list(t1.values())) > np.median(list(t0.values()))
    # 팬: 켜는 줄은 층 2 표식 바로 뒤, 끄는 줄은 경로 끝(기계 종료 코드보다 앞)
    lines = out.read_text(encoding="utf-8").splitlines()
    on = [i for i, ln in enumerate(lines) if ln == "M106 S255"]
    assert len(on) == 1 and lines[on[0] - 1].startswith("; layer 2 ")
    off = [i for i, ln in enumerate(lines) if ln == "M106 S0"]
    assert len(off) == 2 and off[0] < lines.index("; end") < off[1]


# ───────── (f) 팬 ─────────
def test_fan_turns_on_once_after_first_layers():
    mesh = _cylinder()
    st = {}
    lines = gc.to_lines(slice_mesh(mesh, fan=True, stats=st))
    assert st["fan_on"] is True
    on = [i for i, ln in enumerate(lines) if ln == "M106 S255"]
    assert len(on) == 1
    assert lines[on[0] - 1] == f"; layer {FAN_AFTER_LAYERS} z=0.900", "처음 2층은 팬 없이"
    assert lines[-2:] == ["M106 S0", "; end"]
    assert "; fan=on after 2 layers" in lines
    # 팬 줄을 빼면 기본 출력과 같다 (경로를 건드리지 않는다)
    rest = [ln for ln in lines if not ln.startswith("M106") and "fan=on" not in ln]
    assert rest == gc.to_lines(slice_mesh(mesh))


def test_fan_stays_off_when_part_has_too_few_layers():
    mesh = _cylinder(height=0.6)                   # 2층뿐 — 켤 자리가 없다
    st = {}
    lines = gc.to_lines(slice_mesh(mesh, fan=True, stats=st))
    assert st["fan_on"] is False
    assert sum(ln.startswith("; layer ") for ln in lines) == 2
    assert not any(ln.startswith("M106") for ln in lines), "켜지 않았으면 끄는 줄도 없다"


def test_layer_times_counts_rotation_only_moves_in_degrees():
    """회전만 하는 이동은 F 가 °/min 이다 (REP5X Marlin) — C 되감기가 여기 해당한다."""
    items = gc.parse(["; layer 0 z=0.300",
                      "G0 X0 Y0 Z0.3 F3600 B22 C0",
                      "G1 X10 Y0 E1 F600 B22 C0",          # 10mm @ 600mm/min = 1s
                      "G0 F1200 B22 C360",                  # 360° @ 1200°/min = 18s
                      "; layer 1 z=0.600",
                      "G0 X10 Y0 Z0.6 F3600 B22 C360"])     # 0.3mm @ 3600 = 0.005s
    t = layer_times(items)
    assert t[0] == pytest.approx(19.0) and t[1] == pytest.approx(0.005)
