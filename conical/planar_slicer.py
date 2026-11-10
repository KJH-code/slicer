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

없는 것(정직): 솔리드 상/하면, 브릿지, 리트랙션 튜닝, 냉각, 시임 최적화 등.
연구 검증·소형 테스트 출력용이지 품질 출력용이 아니다.
"""

import math

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from .gcode import Move

FILAMENT_D = 1.75


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
               alternate_rings=False):
    """메시를 평면 슬라이싱해 (kind, payload) 리스트(G-code 아이템)를 돌려준다.

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
             ("raw", f"; layers={n_layers} layer_h={layer_height} width={extrusion_width}"),
             ("raw", "G21"), ("raw", "G90"), ("raw", "M82")]  # mm, 절대좌표, 절대 E(M82)
    state = {"e": 0.0}
    wind = [0]               # 축을 감싸는 링이 감은 횟수 (반시계 +1)

    for i in range(n_layers):
        z_cut = z0 + (i + 0.5) * layer_height          # 층 '중앙'에서 자름
        z_out = z0 + (i + 1) * layer_height            # 노즐 높이
        polys = _layer_polygons(mesh, z_cut, simplify_tol)
        if not polys:
            continue
        items.append(("raw", f"; layer {i} z={z_out:.3f}"))

        infill_region = []
        for poly in polys:
            # 페리미터: 바깥에서 안으로 (w/2, 3w/2, ...) 오프셋
            items.append(("raw", ";TYPE:PERIMETER"))   # Slic3r/PrusaSlicer 관례
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
                                items.append(("move", it))
            inner = poly.buffer(-(extrusion_width * (perimeters + 0.2)))
            if not inner.is_empty:
                infill_region.append(inner)

        # 희소 인필: 레이어마다 0/90도 교차 직선
        if infill_region and infill_spacing > 0:
            items.append(("raw", ";TYPE:FILL"))        # Slic3r/PrusaSlicer 관례
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
                    items.append(("move", Move(g=0, x=xa, y=ya, z=z_out, f=feed * 2)))
                    state["e"] += g.length * e_per_mm
                    items.append(("move", Move(g=1, x=xb, y=yb, e=state["e"], f=feed)))

    items.append(("raw", "; end"))
    return items
