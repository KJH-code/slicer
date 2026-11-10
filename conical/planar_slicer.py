"""
planar_slicer.py — 내장 미니 평면 슬라이서 (연구용 최소 기능).

⚠ 포지션을 분명히: PrusaSlicer/Orca 를 대체하려는 게 아니다. 파이프라인의
'평면 슬라이싱' 단계는 원래 외부 슬라이서(CLI)를 꽂는 자리인데(pipeline.py 참고),
외부 슬라이서가 없는 환경에서도 파이프라인 전체를 돌려보고 검증할 수 있도록
최소한의 슬라이서를 내장한 것이다. 지원 기능:

  · 레이어별 단면(trimesh.section) → 다각형(구멍 포함)
  · 페리미터 n개 (shapely 음수 버퍼로 안쪽 오프셋)
  · 희소 rectilinear 인필 (각도 레이어마다 90도 교차)
  · 압출량 E = 단면적 모델 (layer_h × width / 필라멘트 단면적)
  · (선택, 기본 끔) 최소 층 시간·팬·첫 층 브림 — 아래 「냉각·부착」

없는 것(정직): 솔리드 상/하면, 브릿지, 리트랙션 튜닝, 시임 최적화 등.
연구 검증·소형 테스트 출력용이지 품질 출력용이 아니다.

## 냉각·부착 (2026-11-10, docs/gap_audit.md G8 / F5)

REP5X 시험 출력물은 작다(lamp_small 지름 9.6mm). 층 하나가 1~3초에 끝나서(22° 에서
중앙 1.4초, 가장 긴 층 3.1초) 앞 층이 굳기 전에 다음 층이 올라간다. 셋 다 **기본값은
꺼짐**이고, 꺼져 있으면 출력이 예전과 비트 단위로 같다
(tests/test_layer_time.py, tests/test_brim.py).

  · `min_layer_time` — 층의 추정 시간(압출+트래블 길이 / 명령 피드)이 이보다 짧으면
    그 층의 **압출 피드만** 낮춘다. `min_print_speed` 아래로는 안 내린다.
    피드는 **내리기만** 한다 — 어떤 줄의 F 도 올라가지 않는다. 그래서 뒤에 오는
    `rep5x.limit_rotary_speed`(회전축 상한으로 F 를 더 깎는다)와 순서가 엇갈려도
    서로를 무르지 않는다: 최종 F = min(여기서 낮춘 값, 회전 상한).
    ⚠ 작은 층은 하한에 걸린다. lamp_small 22° 는 층당 경로가 40mm 안팎이라 10mm/s 로도
      4초다 — 8초를 요청하면 65층 중 55층이 못 채운다(중앙 1.4 → 3.9초). 느리게 가는
      것만으로는 한계가 있고, 그 너머는 머무름·여러 개 동시 출력의 영역이다(없다).
  · `fan` — 처음 `FAN_AFTER_LAYERS`(2) 층 뒤에 `M106 S255`. 첫 층들은 베드 부착 때문에
    팬 없이 찍는다. 켰으면 끝에 `M106 S0` 으로 끈다.
  · `brim` — **층 0 에만**, 첫 층 윤곽 바깥에, 페리미터보다 먼저.

⚠ 여기서 재는 시간은 **변환공간**의 길이다. 이 슬라이서는 원뿔 변환한 메시를 받으므로
  역변환 뒤에는 길이가 조금 달라진다: 둘레 방향은 cosθ 배, 반경 방향은 그대로
  (r = R·cosθ, dz = −sinθ·dR → 3차원 길이는 dR). F 는 그대로 넘어가므로 **실공간 층
  시간은 여기 추정의 cosθ~1 배**다 (22° 에서 0.93배까지). 즉 `min_layer_time=8` 이면
  실제로는 7.4초까지 나올 수 있다. 보정하지 않았다 — 추정 자체가 가속을 무시해
  실제보다 짧게 나오는 쪽이고(작은 고리에서는 명령 피드에 닿지도 못한다), REP5X 는
  회전축 상한이 F 를 더 깎아 실제 층 시간이 이보다 길어진다. 실측값은
  `layer_times(역변환한 아이템)` 로 잰다 (`conical_slice.py` 가 출력한다).

⚠ 브림과 원뿔 (tests/test_brim.py): 변환공간의 층 0 은 평면이지만 실공간에서는
  **원뿔면 z = Z′₀ − c·r·tanθ** 다 (`transform.py` 의 역). outward(c=+1)는 축에서
  멀어질수록 내려가므로 층 0 이 베드 위에 있는 곳은 축 둘레 r < Z′₀/tanθ 뿐이다
  (층고 0.3, 22° 면 0.74mm). 첫 층 윤곽은 이미 그 안쪽(팁 높이 ≥ 층고/2)을 쓰고
  있어서, **윤곽 바깥의 브림은 첫 바퀴부터 팁이 층고/2 아래이고 곧 베드 밑이다**
  (lamp_small 22°: 첫 바퀴 z 0.08~0.10mm, 둘째 바퀴 −0.09mm). inward(c=−1)는 반대로
  바깥으로 갈수록 떠오른다. 즉 원뿔 층 0 의 브림은 베드 접촉을 넓혀 주지 못한다 —
  온전히 성립하는 것은 바닥이 θ=0 인 경우뿐이다. 이 모듈은 변환을 모르므로 고리를
  그대로 내고, 실공간 높이 검사는 호출자(`conical_slice.brim_problem`)가 역변환한
  뒤에 한다.
"""

import math
import re

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from .gcode import Move

FILAMENT_D = 1.75
FAN_AFTER_LAYERS = 2          # 이만큼의 층을 낸 **뒤에** 팬을 켠다 (첫 층들은 베드 부착)
FAN_ON, FAN_OFF = "M106 S255", "M106 S0"
BRIM_TYPE = ";TYPE:BRIM"      # toolpath._type_of 가 페리미터로 분류한다

_LAYER_MARK = re.compile(r"^; layer (\d+) z=")
_ROT_WORD = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")


def _floor_feed(f):
    """`gcode.format_feed` 가 적는 자릿수로 **내린** F (100 이상은 정수, 아래는 소수 3자리).

    반올림으로 적으면 F 가 계산값보다 커질 수 있다 — 층 시간이 요청보다 짧아진다.
    메모리의 값과 파일에 적히는 값을 같게 두려는 것이기도 하다
    (`rep5x._floor_feed` 와 같은 규칙. 평면 슬라이서가 5축 모듈을 끌어오지 않게 따로 둔다).
    """
    if f >= 100.0:
        return float(math.floor(f))
    return max(0.001, math.floor(f * 1000.0) / 1000.0)


def _block_time(block, pos):
    """아이템 블록(층 하나)의 (트래블 초, 압출 초, 끝 위치). 명령 피드 기준, 가속 무시.

    pos = 블록에 들어올 때의 (x, y, z). 아직 모르면 None 이 섞여 있고, 그 이동은
    길이를 몰라 세지 않는다 (파일의 첫 이동).
    """
    x, y, z = pos
    t_travel = t_extrude = 0.0
    for kind, mv in block:
        if kind != "move":
            continue
        nx = mv.x if mv.x is not None else x
        ny = mv.y if mv.y is not None else y
        nz = mv.z if mv.z is not None else z
        if mv.f and None not in (x, y, z, nx, ny, nz):
            t = math.dist((x, y, z), (nx, ny, nz)) * 60.0 / mv.f
            if mv.e is not None:
                t_extrude += t
            else:
                t_travel += t
        x, y, z = nx, ny, nz
    return t_travel, t_extrude, (x, y, z)


def _slow_down(block, pos, min_layer_time, f_floor):
    """층 시간이 `min_layer_time` 에 못 미치면 그 층의 **압출 피드**를 낮춘다 (제자리 수정).

        T = T_트래블 + T_압출  <  T_min   →   s = T_압출 / (T_min − T_트래블)   (< 1)
        F′ = min(F, max(⌊F·s⌋, F_하한))

    트래블은 건드리지 않는다(느리게 가면 흘러내린 실이 묻는다). F′ ≤ F·s 로 **내려**
    적으므로 하한에 안 걸린 층은 T′ ≥ T_min 이다. `min(F, …)` 가 있어서 하한이 원래
    피드보다 높아도 피드가 **올라가지 않는다.**

    반환: (감속 전 초, 감속 후 초, 하한 때문에 못 채웠나, 끝 위치)
    """
    t_travel, t_extrude, end = _block_time(block, pos)
    before = t_travel + t_extrude
    if min_layer_time <= 0.0 or before >= min_layer_time or t_extrude <= 0.0:
        return before, before, False, end
    s = t_extrude / (min_layer_time - t_travel)       # 분모 > T_압출 > 0
    for kind, mv in block:
        if kind == "move" and mv.e is not None and mv.f:
            mv.f = min(mv.f, max(_floor_feed(mv.f * s), f_floor))
    t_travel, t_extrude, _ = _block_time(block, pos)
    after = t_travel + t_extrude
    return before, after, after < min_layer_time - 1e-9, end


def layer_times(items):
    """아이템 목록의 층별 추정 시간 {층 번호: 초} — `; layer N z=…` 표식으로 나눈다.

    변환공간 아이템(이 모듈의 출력)에도, 역변환한 실공간 아이템에도, 5축 변환까지
    끝난 아이템에도 쓴다. `_slow_down` 과 같은 모형이다: 이동마다 길이 / 명령 피드,
    가속 무시, F 는 모달.

    XYZ 가 안 움직이고 회전축 워드(`Move.extra` 의 B/C 등)만 바뀌는 이동은 펌웨어가
    F 를 °/min 으로 읽으므로(REP5X Marlin, docs/rep5x_machine_facts.md §7) 가장 많이
    도는 축의 각도 / F 로 센다 — C 되감기가 여기 해당한다. 첫 표식 앞의 이동(시작
    G-code)은 세지 않는다.
    """
    times = {}
    layer = None
    x = y = z = f = None
    rot = {}
    for kind, p in items:
        if kind != "move":
            mo = _LAYER_MARK.match(p) if isinstance(p, str) else None
            if mo:
                layer = int(mo.group(1))
                times.setdefault(layer, 0.0)
            continue
        nx = p.x if p.x is not None else x
        ny = p.y if p.y is not None else y
        nz = p.z if p.z is not None else z
        if p.f:
            f = p.f
        new_rot = {k.upper(): float(v) for k, v in _ROT_WORD.findall(p.extra or "")}
        if layer is not None and f:
            d = (math.dist((x, y, z), (nx, ny, nz))
                 if None not in (x, y, z, nx, ny, nz) else 0.0)
            if d >= 5e-4:                  # 파일에 적히는 자릿수(소수 3자리)에서 0 이 아닌 길이
                times[layer] += d * 60.0 / f
            else:
                turn = max((abs(v - rot[k]) for k, v in new_rot.items() if k in rot),
                           default=0.0)
                times[layer] += turn * 60.0 / f
        x, y, z = nx, ny, nz
        rot.update(new_rot)
    return times


def brim_rings(polys, extrusion_width, n, simplify_tol=0.0):
    """첫 층 윤곽 **바깥**의 브림 고리 → [(k, 좌표 리스트)], 바깥 고리(k=n−1)부터.

    윤곽 = 층 다각형들의 바깥 테두리(구멍은 메운다 — 구멍 안쪽에는 브림을 놓지 않는다).
    k번째 고리의 중심선은 윤곽에서 w·(k+½) 바깥이다: 첫 고리(k=0)가 가장 바깥
    페리미터(윤곽에서 w/2 안쪽)와 중심 간격 w 로 붙는다.

    바깥 고리부터 내는 것은 노즐이 부품 옆에서 끝나게 하려는 것이다 (바로 이어서
    페리미터를 찍는다).
    """
    if n <= 0 or not polys:
        return []
    outline = unary_union([Polygon(p.exterior) for p in polys])
    rings = []
    for k in range(n - 1, -1, -1):
        off = outline.buffer(extrusion_width * (0.5 + k))
        geoms = off.geoms if isinstance(off, MultiPolygon) else [off]
        for g in geoms:
            ring = g.exterior
            if simplify_tol > 0:
                ring = ring.simplify(simplify_tol, preserve_topology=True)
            coords = list(ring.coords)
            if len(coords) >= 3:
                rings.append((k, coords))
    return rings


def _layer_polygons(mesh, z, simplify_tol):
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return []
    path2d, _ = sec.to_2D()
    polys = []
    for p in path2d.polygons_full:
        if not p or p.area <= 1e-6:
            continue
        # 세분화된 메시 윤곽은 정점이 촘촘함 → 현 오차 tol 안에서 단순화
        # (안 하면 G-code가 0.05mm급 세그먼트로 폭발: 우리 gcode_stats 발견 그대로)
        if simplify_tol > 0:
            p = p.simplify(simplify_tol, preserve_topology=True)
        if p and p.area > 1e-6:
            polys.append(p)
    return polys


def _ring_to_moves(coords, z, e_per_mm, feed, state):
    """닫힌 링 좌표를 이동으로. state=dict(x,y,e) 이어붙이기용."""
    out = []
    x0, y0 = coords[0]
    out.append(Move(g=0, x=x0, y=y0, z=z, f=feed * 2))          # 이동(비압출)
    px, py = x0, y0
    for x, y in coords[1:]:
        d = math.hypot(x - px, y - py)
        if d < 1e-6:                       # 중복점(0길이 세그먼트) 제거
            continue
        state["e"] += d * e_per_mm
        out.append(Move(g=1, x=x, y=y, e=state["e"], f=feed))
        px, py = x, y
    return out


def _alternate_about_axis(coords, wind):
    """축(원점)을 감싸는 링의 방향과 시작점을 정한다 (헤드 회전식 5축용).

    - 시작점(시임)은 방위각 180°(−X 쪽)에 가장 가까운 꼭짓점으로 맞춘다. 시임이 링마다
      제멋대로면 링 사이 트래블의 최단 회전이 한쪽으로 쌓여 층마다 C 가 약 0.35회전씩
      흘렀다 (flare, 2026-11-10 실측)
    - 방향은 **감긴 횟수 w 가 {0, 1} 안에만 있게** 고른다 (w=0 → 반시계, w=1 → 시계).
      '직전과 반대'만으로는 첫 링 방향에 따라 C 가 [180°, 540°] 에서 왕복할 수 있어
      펌웨어 창(±360°)을 넘었다. 이 규칙이면 C 가 언제나 한 바퀴 폭 안에 머물고,
      되감기 패스의 시작 오프셋이 그 폭을 창 가운데(−180~180°)로 옮긴다
    축을 감싸지 않는 링은 한 바퀴 돌아도 C 가 제자리라 건드리지 않는다.
    """
    if len(coords) < 4 or not Polygon(coords).contains(Point(0.0, 0.0)):
        return coords
    pts = coords[:-1] if coords[0] == coords[-1] else list(coords)
    az = [math.pi - abs(math.atan2(y, x)) for x, y in pts]   # 0 = 방위각 180°
    i0 = int(np.argmin(az))
    pts = pts[i0:] + pts[:i0]
    coords = pts + [pts[0]]
    xs = np.asarray(coords)
    area2 = float(np.sum(xs[:-1, 0] * xs[1:, 1] - xs[1:, 0] * xs[:-1, 1]))
    d = 1 if area2 > 0 else -1           # +1 반시계 (C 증가)
    want = 1 if wind[0] <= 0 else -1
    if d != want:
        coords = coords[::-1]
    wind[0] += want
    return coords


def slice_mesh(mesh, layer_height=0.3, extrusion_width=0.45, perimeters=2,
               infill_spacing=2.5, feed=1800.0, simplify_tol=0.05,
               alternate_rings=False, min_layer_time=0.0, min_print_speed=10.0,
               fan=False, brim=0, stats=None):
    """메시를 평면 슬라이싱해 (kind, payload) 리스트(G-code 아이템)를 돌려준다.

    min_layer_time (초, 0=끔): 층의 추정 시간이 이보다 짧으면 그 층의 압출 피드를
      낮춘다. min_print_speed (mm/s) 아래로는 안 내리므로 아주 작은 층은 요청 시간을
      못 채울 수 있다 — `stats["floor_limited"]` 로 센다. 시간 모형과 역변환 뒤의
      차이(cosθ)는 모듈 docstring 「냉각·부착」.
    fan: 처음 `FAN_AFTER_LAYERS` 층을 낸 뒤 `M106 S255`, 끝에 `M106 S0` (raw 줄).
    brim: 층 0(처음 낸 층)의 윤곽 바깥에 고리 n개. 페리미터보다 먼저, `;TYPE:BRIM`.
      ⚠ 원뿔 변환한 메시면 이 고리들은 실공간에서 베드 아래나 공중에 놓일 수 있다 —
        역변환한 뒤에 호출자가 검사할 것 (모듈 docstring).
    stats: dict 를 주면 채운다 — layer_times [(층, 감속 전 초, 감속 후 초)] (이동이 있는
      층만), slowed_layers, floor_limited, min_feed, fan_on (팬을 실제로 켰나),
      brim_ring_k [고리마다 k, 낸 순서].
      (반환값은 여러 스크립트가 아이템 목록으로 쓰고 있어 그대로 둔다.)
    셋 다 기본값이면 출력은 이 인자들이 생기기 전과 비트 단위로 같다.

    alternate_rings: 닫힌 링(페리미터)을 하나 걸러 **반대 방향**으로 돈다.
      헤드 회전식 5축(REP5X)에서 C 는 방위각을 따라가므로, 축을 감싸는 링을 늘
      같은 방향으로 돌면 링마다 C 가 360° 씩 쌓인다 → 펌웨어 창(±360°)을 넘어
      트래블 중 되감기가 필요해진다 (램프 131회, 출력 시간의 2/3). 번갈아 돌면 C 가
      쌓이지 않고 왕복만 한다. 시작점(시임)은 그대로다 — 닫힌 링이라 뒤집어도
      첫 점이 같다. 3축 출력에는 의미가 없어서 기본은 끔.

      ⚠ 기준은 '링 개수'가 아니라 **축(원점)을 감싸는 링의 회전 방향**이다. 구멍 있는
      단면은 바깥 링과 안쪽 링이 이미 반대 방향으로 나오는데(shapely), 개수로 하나
      걸러 뒤집으면 둘이 같은 방향이 돼 오히려 층마다 C 가 4회전씩 쌓였다
      (flare 34층 이후, 2026-11-10 실측). 축을 감싸지 않는 링은 한 바퀴 돌아도 C 가
      제자리라 건드리지 않는다.
    """
    e_per_mm = (layer_height * extrusion_width) / (math.pi * (FILAMENT_D / 2) ** 2)
    z0, z1 = mesh.bounds[0][2], mesh.bounds[1][2]
    n_layers = max(1, int(round((z1 - z0) / layer_height)))

    items = [("raw", "; conical built-in planar slicer"),
             ("raw", f"; layers={n_layers} layer_h={layer_height} width={extrusion_width}")]
    opts = ([f"min_layer_time={min_layer_time:g}s min_print_speed={min_print_speed:g}mm/s"]
            if min_layer_time > 0 else []) \
        + ([f"fan=on after {FAN_AFTER_LAYERS} layers"] if fan else []) \
        + ([f"brim={brim}"] if brim > 0 else [])
    if opts:                 # 기본값이면 이 줄이 없다 → 예전 출력과 같다
        items.append(("raw", "; " + " ".join(opts)))
    items += [("raw", "G21"), ("raw", "G90"), ("raw", "M82")]  # mm, 절대좌표, 절대 E(M82)
    state = {"e": 0.0}
    wind = [0]               # 축을 감싸는 링이 감은 횟수 (반시계 +1)
    # 속도 하한 (mm/min). 파일에 정수로 적히는 구간에서는 올려 적는다 — 반올림으로
    # 하한보다 낮은 값이 적히지 않게.
    f_floor = min_print_speed * 60.0
    if f_floor >= 100.0:
        f_floor = float(math.ceil(f_floor - 1e-9))
    pos = (None, None, None)  # 직전 층이 끝난 자리 (층 시간에 층 간 트래블을 넣으려고)
    printed = 0               # 실제로 낸 층 수 (단면이 빈 층은 세지 않는다)
    fan_on = False
    times, ring_k = [], []
    n_slowed = n_floor = 0
    f_min = None

    for i in range(n_layers):
        z_cut = z0 + (i + 0.5) * layer_height          # 층 '중앙'에서 자름
        z_out = z0 + (i + 1) * layer_height            # 노즐 높이
        polys = _layer_polygons(mesh, z_cut, simplify_tol)
        if not polys:
            continue
        layer = [("raw", f"; layer {i} z={z_out:.3f}")]   # 이 층의 아이템 (끝에 한꺼번에 붙인다)
        if fan and printed == FAN_AFTER_LAYERS:
            layer.append(("raw", FAN_ON))
            fan_on = True

        if brim > 0 and printed == 0:
            rings = brim_rings(polys, extrusion_width, brim, simplify_tol)
            if rings:
                layer.append(("raw", BRIM_TYPE))
            for k, coords in rings:
                if alternate_rings:
                    coords = _alternate_about_axis(coords, wind)
                ring_k.append(k)
                for it in _ring_to_moves(coords, z_out, e_per_mm, feed, state):
                    layer.append(("move", it))

        infill_region = []
        for poly in polys:
            # 페리미터: 바깥에서 안으로 (w/2, 3w/2, ...) 오프셋
            layer.append(("raw", ";TYPE:PERIMETER"))   # Slic3r/PrusaSlicer 관례
            for k in range(perimeters):
                off = poly.buffer(-(extrusion_width * (0.5 + k)))
                if off.is_empty:
                    break
                geoms = off.geoms if isinstance(off, MultiPolygon) else [off]
                for g in geoms:
                    for ring in [g.exterior, *g.interiors]:
                        coords = list(ring.coords)
                        if alternate_rings:
                            coords = _alternate_about_axis(coords, wind)
                        if len(coords) >= 3:
                            for it in _ring_to_moves(coords, z_out, e_per_mm, feed, state):
                                layer.append(("move", it))
            inner = poly.buffer(-(extrusion_width * (perimeters + 0.2)))
            if not inner.is_empty:
                infill_region.append(inner)

        # 희소 인필: 레이어마다 0/90도 교차 직선
        if infill_region and infill_spacing > 0:
            layer.append(("raw", ";TYPE:FILL"))        # Slic3r/PrusaSlicer 관례
            region = unary_union(infill_region)
            minx, miny, maxx, maxy = region.bounds
            vertical = i % 2 == 0
            coords_iter = (np.arange(minx, maxx, infill_spacing) if vertical
                           else np.arange(miny, maxy, infill_spacing))
            for c in coords_iter:
                line = (LineString([(c, miny - 1), (c, maxy + 1)]) if vertical
                        else LineString([(minx - 1, c), (maxx + 1, c)]))
                seg = region.intersection(line)
                geoms = getattr(seg, "geoms", [seg])
                for g in geoms:
                    if g.is_empty or g.length < extrusion_width:
                        continue
                    (xa, ya), (xb, yb) = g.coords[0], g.coords[-1]
                    layer.append(("move", Move(g=0, x=xa, y=ya, z=z_out, f=feed * 2)))
                    state["e"] += g.length * e_per_mm
                    layer.append(("move", Move(g=1, x=xb, y=yb, e=state["e"], f=feed)))

        # 최소 층 시간: 이 층의 압출 피드만 낮춘다 (꺼져 있으면 재기만 한다)
        before, after, short, pos = _slow_down(layer, pos, min_layer_time, f_floor)
        if any(kind == "move" for kind, _ in layer):
            # 단면은 있는데 페리미터가 안 들어가는 층(꼭대기 한 점 등)은 표식만 남는다 —
            # 찍는 게 없으니 식힐 것도 없다. 통계에서 뺀다.
            times.append((i, before, after))
        n_floor += int(short)              # 하한 때문에 요청 시간을 못 채운 층
        if after > before:
            n_slowed += 1
            f_layer = min(mv.f for kind, mv in layer
                          if kind == "move" and mv.e is not None)
            f_min = f_layer if f_min is None else min(f_min, f_layer)
        items += layer
        printed += 1

    if fan_on:
        items.append(("raw", FAN_OFF))
    items.append(("raw", "; end"))
    if stats is not None:
        stats.update(layer_times=times, slowed_layers=n_slowed, floor_limited=n_floor,
                     min_feed=f_min, fan_on=fan_on, brim_ring_k=ring_k)
    return items
