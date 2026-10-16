"""REP5X: 축 통과(극) 처리와 가변각 5축 (2026-10-16).

왜 필요한가:
  · 경로가 원뿔 축을 지나가면 방위각이 180° 뒤집힌다. 예전에는 그때마다 C 를 180°
    돌렸다 — 헤드 급회전(`rep5x_check` 경고 "C 한 걸음 180°"). 공구 방향은
    (B, C) 와 (−B, C+180°) 가 같으므로 **B 부호를 넘기면** 2θ 만 움직인다.
  · 가변각(밴드) 프로필은 5축으로 아예 못 뽑았다("향후 과제"). 그런데 실험 A 의
    판정 모델(램프 밴드2)이 바로 가변각이다. 레이어 하나는 각도 하나짜리 원뿔이므로
    점의 레이어 Z′ 를 되풀어 B = θ(Z′) 로 두면 된다.

고정하는 성질:
  ① 극 처리 뒤에도 **모든 이동**의 공구 방향이 원뿔 법선의 반대와 같다 (실제 경로)
  ② 축을 지나는 직선에서 C 가 180° 뛰지 않고 B 부호가 바뀐다
  ③ θ=0 이면 C 를 돌리지 않는다 (수직 공구에 방위각은 의미가 없다)
  ④ 가변각: 점마다 |B| = 그 점 레이어의 θ(Z′), 공구 방향 = 그 레이어 원뿔 법선의 반대
  ⑤ 검사기가 ±θ(극 처리)와 가변각을 '틸트가 여러 값' 으로 오판하지 않는다
  ⑥ 실제 파이프라인(funnel)에서 150° 넘는 C 걸음이 사라진다

    python3 -m pytest tests/test_rep5x_pole_varangle.py -q
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import trimesh

from conical.backtransform import backtransform
from conical.gcode import Move
from conical.meshio import center_on_axis
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile
from conical.rep5x import (
    _c_of,
    check_rep5x,
    cone_tool_direction,
    to_rep5x,
    tool_direction,
)
from conical.transform import transform_cone

ROOT = Path(__file__).resolve().parent.parent


def _moves(items):
    return [p for k, p in items if k == "move"]


def _b_of(extra):
    for tok in (extra or "").split():
        if tok.upper().startswith("B"):
            return float(tok[1:])
    return None


def _close(a, b, tol=1e-5):
    return all(abs(x - y) < tol for x, y in zip(a, b, strict=True))


@pytest.fixture(scope="module")
def funnel20():
    mesh = center_on_axis(trimesh.load(ROOT / "examples" / "funnel.stl", force="mesh"))
    warped = transform_cone(mesh.vertices, 20.0, "outward")
    items = slice_mesh(trimesh.Trimesh(vertices=warped, faces=mesh.faces,
                                       process=False), layer_height=0.3)
    real, _ = backtransform(items, 20.0, "outward")
    return real


def test_pole_flip_keeps_tool_direction_exact(funnel20):
    out, st = to_rep5x(funnel20, 20.0, "outward")
    assert st["pole_flips"] > 0, "실제 경로에는 축 통과가 있어야 한다"
    for mv in _moves(out):
        if math.hypot(mv.x or 0, mv.y or 0) < 1e-6:
            continue
        got = tool_direction(_b_of(mv.extra), _c_of(mv.extra, "C"))
        want = cone_tool_direction(mv.x, mv.y, 20.0, "outward")
        assert _close(got, want), f"({mv.x},{mv.y}): {got} vs {want}"


def test_line_through_axis_flips_b_not_c():
    pts = [(-5.0, 0.0), (-1.0, 0.0), (1.0, 0.0), (5.0, 0.0)]
    items = [("move", Move(g=1, x=x, y=y, z=1.0, e=0.1 * i, f=1200.0))
             for i, (x, y) in enumerate(pts)]
    out, st = to_rep5x(items, 20.0, "outward")
    ms = _moves(out)
    cs = [_c_of(m.extra, "C") for m in ms]
    bs = [_b_of(m.extra) for m in ms]
    assert max(abs(b - a) for a, b in zip(cs, cs[1:], strict=False)) < 1e-6
    assert bs[0] == pytest.approx(-bs[-1]) and abs(bs[0]) == pytest.approx(20.0)
    assert st["pole_flips"] == 1
    # 끄면 예전처럼 C 가 180° 뛴다 — 비교 기준이 살아 있는지
    old, _ = to_rep5x(items, 20.0, "outward", pole_flip=False)
    co = [_c_of(m.extra, "C") for m in _moves(old)]
    assert max(abs(b - a) for a, b in zip(co, co[1:], strict=False)) == pytest.approx(180.0)


def test_vertical_tool_does_not_spin_c():
    items = [("move", Move(g=1, x=5 * math.cos(t), y=5 * math.sin(t), z=1.0,
                           e=0.1 * i, f=1200.0))
             for i, t in enumerate(k * 0.7 for k in range(20))]
    out, st = to_rep5x(items, 0.0, "outward")
    cs = {_c_of(m.extra, "C") for m in _moves(out)}
    assert cs == {0.0}
    assert st["c_turns"] == 0.0


def test_variable_angle_tilt_follows_layer_theta():
    prof = AngleProfile([(0.0, 30.0), (10.0, 30.0), (12.0, 0.0), (30.0, 0.0)])
    items, want = [], []
    i = 0
    for zp in (2.0, 9.0, 10.5, 11.0, 11.7, 20.0):
        t = float(prof.tan_at(zp))
        th = math.degrees(math.atan(t))
        for k in range(8):
            phi = 0.9 * k
            r = 3.0 + 0.5 * k
            x, y = r * math.cos(phi), r * math.sin(phi)
            items.append(("move", Move(g=1, x=x, y=y, z=zp - r * t, e=0.1 * i, f=1200.0)))
            want.append(th)
            i += 1
    out, st = to_rep5x(items, prof, "outward")
    assert st["variable"]
    for mv, th in zip(_moves(out), want, strict=True):
        b, c = _b_of(mv.extra), _c_of(mv.extra, "C")
        assert abs(b) == pytest.approx(abs(th), abs=1e-3)
        assert _close(tool_direction(b, c),
                      cone_tool_direction(mv.x, mv.y, th, "outward"), tol=1e-4)


def _with_meta(items, thetas):
    meta = {"version": 1, "profile": [[float(i), t] for i, t in enumerate(thetas)]}
    return [("raw", ";CONICAL_META " + json.dumps(meta))] + items


def test_checker_accepts_pole_flip_and_variable_tilt(funnel20):
    out, _ = to_rep5x(funnel20, 20.0, "outward")
    f, st = check_rep5x(_with_meta(out, [20.0]))
    assert not any("틸트" in m for _, m in f), f
    assert st["b_min"] == pytest.approx(-20.0) and st["b_max"] == pytest.approx(20.0)

    prof = AngleProfile([(0.0, 30.0), (10.0, 30.0), (12.0, 0.0), (30.0, 0.0)])
    items = [("move", Move(g=1, x=4.0, y=0.0, z=z, e=0.1 * k, f=1200.0))
             for k, z in enumerate((1.0, 5.0, 14.0, 20.0))]
    out_v, _ = to_rep5x(items, prof, "outward")
    f, _ = check_rep5x(_with_meta(out_v, [30.0, 30.0, 0.0, 0.0]))
    assert not any("틸트" in m for _, m in f), f
    # 프로필 범위 밖 틸트는 잡는다
    f, _ = check_rep5x(_with_meta(out_v, [10.0, 0.0]))
    assert any("프로필 각도 범위" in m for _, m in f)


def test_no_half_turn_c_steps_on_real_path(funnel20):
    def worst(pf):
        out, _ = to_rep5x(funnel20, 20.0, "outward", pole_flip=pf)
        cs = [_c_of(m.extra, "C") for m in _moves(out)]
        return max(abs(b - a) for a, b in zip(cs, cs[1:], strict=False))
    assert worst(False) > 170.0
    assert worst(True) < 150.0


def test_checker_interpolates_orientation_within_a_move():
    """검사기는 이동 안에서 (B, C) 를 선형 보간해야 한다 (펌웨어가 그렇게 움직인다).

    축을 가로지르는 이동의 끝 자세를 이동 전체에 붙이면, 축 앞쪽 절반이 2θ 반대로
    기운 것으로 평가돼 간섭을 지어낸다(램프 밴드2 0.3mm 의 '치명' 0.01% 가 그랬다).
    """
    from conical.rep5x import sample_tool_frames
    items = [("move", Move(g=1, x=-2.0, y=0.0, z=1.0, e=0.0, f=1200.0, extra="B30 C180")),
             ("move", Move(g=1, x=2.0, y=0.0, z=1.0, e=0.4, f=1200.0, extra="B-30 C180"))]
    pts = [(-1.0, 0.0, 1.0), (0.0, 0.0, 1.0), (1.0, 0.0, 1.0)]
    ups = sample_tool_frames(items, pts, [1, 1, 1])
    tilt = [math.degrees(math.acos(u[2])) for u in ups]
    assert tilt[0] == pytest.approx(15.0, abs=1e-6)   # 4분의 1 지점: B=+15
    assert tilt[1] == pytest.approx(0.0, abs=1e-6)    # 축 위: 수직
    assert tilt[2] == pytest.approx(15.0, abs=1e-6)
