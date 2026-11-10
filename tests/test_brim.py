"""첫 층 브림 (docs/gap_audit.md G8 / F5) — 그리고 **원뿔에서는 왜 거의 못 쓰는가.**

브림은 변환공간의 층 0(평면)에 놓인다. 그 평면은 실공간에서 원뿔면이다:

    z = Z′₀ − c·r·tanθ         (transform.py 의 역. c = +1 outward / −1 inward)

outward 는 축에서 멀수록 내려가므로 층 0 이 베드 위에 있는 곳은 축 둘레 r < Z′₀/tanθ
뿐이다. 첫 층 윤곽이 이미 그 안쪽(팁 높이 ≥ 층고/2)을 쓰고 있어서 **윤곽 바깥의 브림은
한 바퀴째부터 팁이 층고/2 아래이고 곧 베드 밑이다.** inward 는 반대로 떠오른다.

    (a) 기본(0)이면 브림이 없다
    (b) 평면: 층 0 에만, 페리미터보다 먼저, 윤곽 바깥에, 바깥 고리부터. 나머지 경로는
        E 가 브림만큼 밀리는 것 말고 그대로
    (c) 역변환한 높이: θ=0 이면 층고 그대로 / outward 는 베드 아래 → 거른다 /
        inward 는 뜬다 → 거른다 / [rep5x] 기운 핫엔드가 베드 여유를 침범 → 거른다
    (d) CLI (lamp_small 22° rep5x): 2바퀴는 건너뛰고 알리며 파일이 브림 없는 것과 같다.
        1바퀴는 들어가고, 파일의 브림 이동은 전부 z ≥ 0, 층 0 에만 있다

    python3 -m pytest tests/test_brim.py -q
"""

import dataclasses
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conical import gcode as gc  # noqa: E402
from conical.backtransform import backtransform  # noqa: E402
from conical.meshio import center_on_axis  # noqa: E402
from conical.planar_slicer import (  # noqa: E402
    BRIM_TYPE,
    FILAMENT_D,
    _layer_polygons,
    brim_rings,
    slice_mesh,
)
from conical.rep5x import REP5X  # noqa: E402
from conical.transform import transform_cone  # noqa: E402
from conical_slice import BRIM_MAX_LIFT, brim_problem, refine  # noqa: E402

LADDER = ROOT / "examples" / "rep5x_ladder"
L3A_ARGS = ["examples/rep5x_ladder/lamp_small.stl", "--angle", "22",
            "--direction", "outward", "--omega-max", "180", "--strict",
            "--mode", "rep5x", "--layer-height", "0.3",
            "--machine-profile", "profiles/rep5x_ender3v3se.ini"]
H, W, R_CYL = 0.3, 0.45, 5.0


def _cylinder():
    return center_on_axis(trimesh.creation.cylinder(radius=R_CYL, height=6.0))


def _warped(angle, direction):
    fine = refine(_cylinder(), 1.5)
    return trimesh.Trimesh(vertices=transform_cone(fine.vertices, angle, direction),
                           faces=fine.faces, process=False)


def _blocks(items):
    """(층 번호, 종류) 별 이동 목록. 종류는 직전 `;TYPE:` 줄."""
    out, layer, typ = {}, None, None
    for k, p in items:
        if k == "raw":
            if p.startswith("; layer "):
                layer, typ = int(p.split()[2]), None
            elif p.upper().startswith(";TYPE:"):
                typ = p.split(":", 1)[1]
        elif layer is not None:
            out.setdefault((layer, typ), []).append(p)
    return out


def _rings(moves):
    """이동 목록을 고리로 (고리 = 트래블 뒤의 압출들) → [[(x, y), …]]."""
    rings, prev_g = [], None
    for mv in moves:
        if mv.g == 0 and prev_g != 0:
            rings.append([])
        rings[-1].append((mv.x, mv.y))
        prev_g = mv.g
    return rings


# ───────── (a) 기본: 없다 ─────────
def test_no_brim_by_default():
    st = {}
    items = slice_mesh(_cylinder(), stats=st)
    assert st["brim_ring_k"] == []
    assert not any(k == "raw" and "BRIM" in p.upper() for k, p in items)
    assert brim_rings([], W, 3) == [] and brim_problem(items, 0.0, "outward", H)[0] is None


# ───────── (b) 평면에서의 브림 ─────────
def test_brim_is_on_layer0_only_before_perimeters_outside_outline():
    mesh = _cylinder()
    st = {}
    items = slice_mesh(mesh, brim=3, stats=st)
    lines = gc.to_lines(items)
    assert lines.count(BRIM_TYPE) == 1
    i_brim = lines.index(BRIM_TYPE)
    assert lines[i_brim - 1] == "; layer 0 z=0.300", "층 0 표식 바로 뒤 = 페리미터보다 먼저"
    assert i_brim < lines.index(";TYPE:PERIMETER") < lines.index("; layer 1 z=0.600")
    blocks = _blocks(items)
    assert [key for key in blocks if key[1] == "BRIM"] == [(0, "BRIM")], "층 0 에만"
    assert "; brim=3" in lines

    brim = blocks[(0, "BRIM")]
    assert brim[0].z == pytest.approx(H) and all(m.z in (None, brim[0].z) for m in brim)
    rings = _rings(brim)
    assert len(rings) == 3 and st["brim_ring_k"] == [2, 1, 0], "바깥 고리부터"

    # 윤곽 바깥: 층 0 다각형(구멍 메움)에서 w·(k+½) 떨어진 고리
    outline = unary_union([Polygon(p.exterior)
                           for p in _layer_polygons(mesh, 0.5 * H, 0.05)])
    for k, ring in zip(st["brim_ring_k"], rings, strict=True):
        assert ring[0] == ring[-1], "닫힌 고리"
        off = W * (k + 0.5)
        for x, y in ring:
            assert not outline.contains(Point(x, y))
            assert outline.exterior.distance(Point(x, y)) == pytest.approx(off, abs=0.06)
            # 원기둥이라 해석값으로도: 반경 5 + w·(k+½) (32각형·단순화 오차 안)
            assert math.hypot(x, y) == pytest.approx(R_CYL + off, abs=0.09)
    # 가장 안쪽 고리는 가장 바깥 페리미터(윤곽에서 w/2 안쪽)와 중심 간격 w 로 붙는다
    r_peri = max(math.hypot(m.x, m.y) for m in blocks[(0, "PERIMETER")])
    r_brim0 = min(math.hypot(x, y) for x, y in rings[-1])
    assert r_brim0 - r_peri == pytest.approx(W, abs=0.08)


def test_brim_leaves_the_rest_of_the_path_alone():
    """브림을 넣어도 나머지 경로는 그대로다 — E 만 브림 압출량만큼 밀린다."""
    mesh = _cylinder()
    base = [mv for k, mv in slice_mesh(mesh) if k == "move"]
    items = slice_mesh(mesh, brim=2)
    brim = _blocks(items)[(0, "BRIM")]
    rest = [mv for k, mv in items if k == "move"][len(brim):]
    e_brim = max(m.e for m in brim if m.e is not None)
    length = sum(math.dist(a, b) for ring in _rings(brim)
                 for a, b in zip(ring[:-1], ring[1:], strict=True))
    assert e_brim == pytest.approx(length * H * W / (math.pi * (FILAMENT_D / 2) ** 2))
    assert len(rest) == len(base)
    for m0, m1 in zip(base, rest, strict=True):
        assert (m0.g, m0.x, m0.y, m0.z, m0.f) == (m1.g, m1.x, m1.y, m1.z, m1.f)
        if m0.e is not None:
            assert m1.e - m0.e == pytest.approx(e_brim, abs=1e-9)


def test_brim_rings_alternate_direction_for_head_rotating_machines():
    """rep5x: 축을 감싸는 고리는 번갈아 돈다 (C 가 쌓이지 않게) — 브림도 같은 규칙."""
    rings = _rings(_blocks(slice_mesh(_cylinder(), brim=4, alternate_rings=True))[(0, "BRIM")])

    def signed_area(ring):
        a = np.asarray(ring)
        return float(np.sum(a[:-1, 0] * a[1:, 1] - a[1:, 0] * a[:-1, 1]))

    signs = [math.copysign(1.0, signed_area(r)) for r in rings]
    assert signs == [1.0, -1.0, 1.0, -1.0]


# ───────── (c) 역변환한 높이 ─────────
def test_planar_brim_sits_at_layer_height():
    st = {}
    items = slice_mesh(_cylinder(), brim=3, stats=st)
    why, info = brim_problem(items, 0.0, "outward", H, ring_k=st["brim_ring_k"], mach=REP5X)
    assert why is None and info["reason"] is None
    assert info["rings"] == 3 and info["fit"] == 3
    assert info["z_min"] == info["z_max"] == pytest.approx(H)


def test_outward_cone_brim_dips_below_the_bed():
    """층 0 은 실공간에서 z = Z′₀ − r·tanθ. 22° 면 두 번째 고리가 이미 베드 밑이다."""
    theta = 22.0
    st = {}
    items = slice_mesh(_warped(theta, "outward"), brim=3, stats=st)
    why, info = brim_problem(items, theta, "outward", H, ring_k=st["brim_ring_k"])
    assert info["reason"] == "below" and "베드 아래" in why and "--brim 1" in why
    assert info["z_min"] < -0.2 and info["fit"] == 1

    # 독립 계산: 변환공간 고리의 반경 R 에서 z = Z′ − R·sinθ (backtransform.py 머리말)
    brim = _blocks(items)[(0, "BRIM")]
    zw = brim[0].z
    sin = math.sin(math.radians(theta))
    z_by_ring = [min(zw - math.hypot(x, y) * sin for x, y in ring) for ring in _rings(brim)]
    assert [z < 0 for z in z_by_ring] == [True, True, False], "바깥 두 고리가 베드 아래"
    assert min(z_by_ring) == pytest.approx(info["z_min"], abs=1e-3)
    # 층 0 원뿔면이 베드와 만나는 반경(실공간) = Z′₀/tanθ — 한 바퀴 폭 남짓이다
    assert zw / math.tan(math.radians(theta)) == pytest.approx(0.743, abs=0.01)

    # 실제 역변환 결과로도 같은 값 (검사는 브림 앞부분만 역변환한다 — 전체와 같아야 한다)
    real, _ = backtransform(items, theta, "outward")
    z_real = [m.z for m in _blocks(real)[(0, "BRIM")]]
    assert round(min(z_real), 3) == info["z_min"] and round(max(z_real), 3) == info["z_max"]

    # 한 바퀴는 z ≥ 0 이지만 팁이 층고의 절반 아래다 (윤곽 바깥은 늘 그렇다)
    st1 = {}
    one = slice_mesh(_warped(theta, "outward"), brim=1, stats=st1)
    why1, info1 = brim_problem(one, theta, "outward", H, ring_k=st1["brim_ring_k"])
    assert why1 is None and 0.0 <= info1["z_min"] < info1["z_max"] < H / 2


def test_small_angle_outward_brim_still_fits():
    st = {}
    items = slice_mesh(_warped(5.0, "outward"), brim=3, stats=st)
    why, info = brim_problem(items, 5.0, "outward", H, ring_k=st["brim_ring_k"])
    assert why is None and info["fit"] == 3 and 0.0 < info["z_min"] < H / 2


def test_inward_cone_brim_lifts_off_the_bed():
    """inward 는 층 0 이 바깥으로 갈수록 올라간다 — 공중의 고리는 브림이 아니다."""
    st = {}
    items = slice_mesh(_warped(20.0, "inward"), brim=3, stats=st)
    why, info = brim_problem(items, 20.0, "inward", H, ring_k=st["brim_ring_k"])
    assert info["reason"] == "lifted" and "뜬다" in why
    assert info["z_min"] > H and info["z_max"] > BRIM_MAX_LIFT * H and info["fit"] == 1


def test_rep5x_brim_rejected_when_tilted_hotend_would_touch_the_bed():
    """z ≥ 0 이어도 그 높이에서 기운 핫엔드가 베드 여유를 침범하면 거른다.

    `to_rep5x` 의 이동별 베드 방어선과 같은 식이다 — 통과시키면 방어선이 브림 이동의
    B 를 깎고 '프로필 계획이 못 잡았다' 고 경고하게 된다.
    """
    from conical.rep5x import BED_GUARD_MARGIN, b_safe, to_rep5x
    theta = 22.0
    st = {}
    items = slice_mesh(_warped(theta, "outward"), brim=1, stats=st)
    args = (items, theta, "outward", H)
    assert brim_problem(*args, ring_k=st["brim_ring_k"])[0] is None
    assert brim_problem(*args, ring_k=st["brim_ring_k"], mach=REP5X)[0] is None

    strict = dataclasses.replace(REP5X, bed_clearance=0.3)
    why, info = brim_problem(*args, ring_k=st["brim_ring_k"], mach=strict)
    assert info["reason"] == "bed_gap" and info["fit"] == 0 and "한 바퀴도" in why
    assert b_safe(info["z_min"], strict.hotend, 0.3 + BED_GUARD_MARGIN) < theta

    # 검사가 방어선과 같은 말을 하는가: 통과한 설정은 깎는 이동 0, 거른 설정은 > 0
    real, _ = backtransform(items, theta, "outward")
    assert to_rep5x(real, theta, "outward", REP5X, bed_clearance=0.2)[1]["bed_clamped"] == 0
    assert to_rep5x(real, theta, "outward", strict, bed_clearance=0.3)[1]["bed_clamped"] > 0


# ───────── (d) CLI: lamp_small 22° rep5x ─────────
def _run(out, *extra):
    r = subprocess.run([sys.executable, "conical_slice.py", *L3A_ARGS, "-o", str(out),
                        *extra], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    return r


def test_cli_skips_brim_that_would_go_below_bed(tmp_path):
    out = tmp_path / "brim2.gcode"
    r = _run(out, "--brim", "2")
    assert "브림 건너뜀: 요청 2바퀴" in r.stdout and "베드 아래" in r.stdout
    text = out.read_text(encoding="utf-8")
    assert "BRIM" not in text.upper() and "brim=" not in text
    assert out.read_bytes() == (LADDER / "L3a_lamp_u22.gcode").read_bytes(), \
        "건너뛴 출력은 브림 없는 출력과 같아야 한다"


def test_cli_brim_moves_are_on_layer0_and_above_bed(tmp_path):
    out = tmp_path / "brim1.gcode"
    r = _run(out, "--brim", "1")
    assert "브림        : 층 0 에 1바퀴" in r.stdout and "층고의 절반" in r.stdout
    assert "치명" not in r.stdout and "방어선" not in r.stdout, r.stdout
    items = gc.parse(out.read_text(encoding="utf-8").splitlines())
    blocks = _blocks(items)
    assert [key for key in blocks if key[1] == "BRIM"] == [(0, "BRIM")]
    brim = blocks[(0, "BRIM")]
    zs = [m.z for m in brim if m.z is not None]
    assert len(zs) >= 8 and min(zs) >= 0.0, f"브림이 베드 아래로 간다: z={min(zs)}"
    assert max(zs) < H / 2, "outward 원뿔의 윤곽 바깥은 팁이 층고 절반 아래다"
    # 브림은 첫 층 페리미터 바깥을 돈다 (실공간 반경으로)
    r_brim = min(math.hypot(m.x, m.y) for m in brim if m.e is not None)
    r_peri = max(math.hypot(m.x, m.y) for m in blocks[(0, "PERIMETER")] if m.e is not None)
    assert r_brim > r_peri
    # 브림 구간에서도 공구는 층 법선 그대로다 (베드 방어선이 B 를 깎지 않았다)
    assert all("B22.000" in m.extra or "B-22.000" in m.extra for m in brim if m.e is not None)
