"""
toolpath.py — 툴패스(G-code) 기반 가상 검증기. 하드웨어 없이 출력 가능성을 검사.

검사기 A (지지 검사):
    압출 세그먼트를 점 샘플링(간격=압출폭/2)하고, 각 점이
      (1) 베드 위 첫층(z ≤ layer_height×1.5), 또는
      (2) '이전에 퇴적된'(G-code 순서 기준) 샘플점 중 수평거리 ≤ 압출폭,
          수직으로 (0, layer_height×1.5] 아래에 존재
    하면 지지로 판정. 배치(이동 500개)마다 cKDTree 재구축 → O(n log n).

검사기 B (노즐 간섭):
    3축 가정(노즐 수직). 각 압출점에 팁을 놓고, 이미 퇴적된 점 q 중
    dz = q.z − tip.z ∈ (0, 원뿔높이] 이면서 수평거리 < 팁반경 + dz·tan(반각)
    이면 간섭 (히트블록 구간은 반경 상수로 동일 논리).

⚠ 정직: 이 검사는 브리징·수축·유변학을 무시한 '기하 판정'이며, 메시 기반
  예측과 측정 대상이 다르다(툴패스에는 인필·트래블·시임이 있음). 절대값이
  아니라 각도 간 '순위·경향' 비교가 목적이다.
"""

import math
import re
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union


# ─────────────────────────────────────────────────────────────
# 샘플링
# ─────────────────────────────────────────────────────────────
EXTRUSION_TYPES = ("perimeter", "infill", "other")


def _type_of(comment):
    """`;TYPE:...` 주석 → 우리 분류. Slic3r/PrusaSlicer·Cura 표기 모두 수용."""
    t = comment.split(":", 1)[1].strip().upper() if ":" in comment else ""
    if "PERIMETER" in t or "WALL" in t or "SKIRT" in t or "BRIM" in t:
        return 0                       # perimeter
    if "FILL" in t or "SKIN" in t or "SUPPORT" in t:
        return 1                       # infill
    return 2                           # other


# `; layer 3`(우리), `;LAYER:3`(Cura), `;LAYER_CHANGE`(PrusaSlicer) 를 모두 받는다.
# `; layers=50 ...` 같은 헤더에 걸리지 않게 숫자 앞에 구분자를 요구한다.
_LAYER_NUM = re.compile(r"^;\s*layer\s*[:#]?\s+(\d+)|^;\s*LAYER\s*[:#]\s*(\d+)", re.I)
_LAYER_CHANGE = re.compile(r"^;\s*LAYER_CHANGE\b", re.I)


def _layer_of(comment, current):
    """레이어 주석 → 층 번호. 해당 없으면 current 를 그대로 돌려준다."""
    mo = _LAYER_NUM.match(comment)
    if mo:
        return int(mo.group(1) or mo.group(2))
    if _LAYER_CHANGE.match(comment):
        return current + 1
    return current


def sample_extrusions(items, width=0.45, return_types=False, return_layers=False):
    """압출(dE>0) 세그먼트를 간격 width/2 로 점 샘플링 (G-code 순서 유지).

    반환: pts (N,3), move_id (N,), weight (N,)  — weight = 각 점이 대표하는 경로 길이(mm)
    return_types=True 면 kinds (N,) 를, return_layers=True 면 layer (N,) 를
    그 순서로 덧붙여 반환한다 (0=페리미터, 1=인필, 2=기타 / 층 번호, 미상은 −1).

    층 번호가 왜 필요한가: 원뿔 경로는 역변환 뒤 z 가 층으로 나뉘지 않는다.
    z 로 비닝하면 원뿔면 하나가 여러 층으로 쪼개지므로, 층은 G-code 주석에서
    읽는다 (`; layer N` / `;LAYER:N` / `;LAYER_CHANGE`).

    왜 종류를 나누나: 희소 인필은 레이어마다 방향이 바뀌어 '아래에 아무것도 없는'
    구간이 원래 많다(브리징으로 정상 출력됨). 이걸 오버행 미지지와 같이 세면
    우리가 재려던 표면 지지가 인필 브리징에 묻힌다 — 실제로 램프 모델에서
    상단부 수치를 좌우한 것이 인필이었다.
    """
    spacing = width / 2.0
    pts, mids, wts, kinds, lays = [], [], [], [], []
    x = y = z = None
    e_prev = 0.0
    mid = 0
    cur_type = 2
    cur_layer = -1
    for kind, p in items:
        if kind != "move":
            if isinstance(p, str):
                c = p.lstrip()
                if c.upper().startswith(";TYPE:"):
                    cur_type = _type_of(c)
                elif c.startswith(";"):
                    cur_layer = _layer_of(c, cur_layer)
            continue
        nx = p.x if p.x is not None else x
        ny = p.y if p.y is not None else y
        nz = p.z if p.z is not None else z
        extrude = p.e is not None and p.e > e_prev + 1e-9
        if extrude and None not in (x, y, z, nx, ny, nz):
            L = math.dist((x, y, z), (nx, ny, nz))
            if L > 1e-9:
                n = max(1, math.ceil(L / spacing))
                for i in range(1, n + 1):
                    t = i / n
                    pts.append((x + (nx - x) * t, y + (ny - y) * t,
                                z + (nz - z) * t))
                    mids.append(mid)
                    wts.append(L / n)
                    kinds.append(cur_type)
                    lays.append(cur_layer)
        if p.e is not None:
            e_prev = p.e
        x, y, z = nx, ny, nz
        mid += 1
    out = (np.array(pts) if pts else np.zeros((0, 3)),
           np.array(mids, dtype=int), np.array(wts))
    if return_types:
        out = out + (np.array(kinds, dtype=int),)
    if return_layers:
        out = out + (np.array(lays, dtype=int),)
    return out


# ─────────────────────────────────────────────────────────────
# 검사기 A: 지지
# ─────────────────────────────────────────────────────────────
def check_support(pts, move_id, weight, layer_height=0.3, width=0.45,
                  batch_samples=2000):
    """각 샘플점의 지지 여부. 반환: supported(bool 배열), 통계 dict.

    '이전에 퇴적'은 G-code 순서를 엄밀히 따른다: 이전 배치들은 cKDTree 로,
    같은 배치 안의 앞선 점들은 브루트포스(작은 행렬)로 검사 — 근사 없음.
    """
    n = len(pts)
    supported = np.zeros(n, dtype=bool)
    if n == 0:
        return supported, {"unsupported_pct": 0.0, "layers": {}}
    vwin = layer_height * 1.5
    supported |= pts[:, 2] <= vwin + 1e-9          # 베드 지지
    radius = math.sqrt(width ** 2 + vwin ** 2)

    tree = None
    for s0 in range(0, n, batch_samples):
        idx = np.arange(s0, min(s0 + batch_samples, n))
        # (1) 이전 배치들 (트리)
        if tree is not None:
            need = idx[~supported[idx]]
            if len(need):
                neigh = tree.query_ball_point(pts[need], r=radius)
                for k, nb in zip(need, neigh):
                    if not nb:
                        continue
                    q = pts[np.array(nb)]
                    dz = pts[k, 2] - q[:, 2]
                    horiz = np.hypot(pts[k, 0] - q[:, 0], pts[k, 1] - q[:, 1])
                    if np.any((dz > 1e-9) & (dz <= vwin + 1e-9) &
                              (horiz <= width + 1e-9)):
                        supported[k] = True
        # (2) 같은 배치 안의 앞선 점들 (브루트포스, G-code 순서 엄수)
        b = pts[idx]
        dzm = b[:, 2][:, None] - b[:, 2][None, :]          # p_i.z − p_j.z
        horizm = np.hypot(b[:, 0][:, None] - b[:, 0][None, :],
                          b[:, 1][:, None] - b[:, 1][None, :])
        earlier = np.tril(np.ones((len(b), len(b)), dtype=bool), k=-1)
        ok = earlier & (dzm > 1e-9) & (dzm <= vwin + 1e-9) & \
             (horizm <= width + 1e-9)
        supported[idx] |= ok.any(axis=1)
        tree = cKDTree(pts[:idx[-1] + 1])

    total = weight.sum()
    bad = weight[~supported].sum()
    # 층별 통계 (z 를 layer_height 로 비닝)
    zbin = np.floor(pts[:, 2] / layer_height).astype(int)
    layers = {}
    for zb in np.unique(zbin):
        m = zbin == zb
        wl = weight[m].sum()
        layers[int(zb)] = (float(weight[m & ~supported].sum() / wl * 100.0)
                          if wl > 0 else 0.0)
    return supported, {"unsupported_pct": float(bad / total * 100.0),
                       "layers": layers}


def layer_cross_sections(pts, move_id, kinds, layer, width=0.45):
    """층별 단면 폴리곤을 **페리미터 압출선만으로** 복원한다 (메시 불필요).

    왜 메시를 안 쓰나: 이 검사기는 외부 슬라이서가 낸 G-code 에도 써야 한다.
    페리미터는 단면 경계를 그대로 그리므로, 같은 층 페리미터 선분을 압출폭의
    절반으로 부풀려 합치면 경계를 두른 띠가 되고, 그 띠의 바깥 고리를 채우면
    단면이 된다. 구 모델에서 진짜 단면과 IoU 최소 0.9976 으로 일치한다.

    ⚠ 정직: 바깥 고리만 채우므로 **부품 내부의 진짜 구멍도 메워진다.** 구멍 위를
      지나는 압출은 '단면 안'으로 잘못 분류된다. 우리 실험 모델에는 내부 구멍이
      없어서 지금은 안 물리지만, 구멍 있는 모델에 쓰기 전에 손봐야 한다.
    """
    out = {}
    peri = kinds == 0
    for L in np.unique(layer[peri]):
        if L < 0:
            continue
        sel = peri & (layer == L)
        segs = []
        for mv in np.unique(move_id[sel]):
            q = pts[sel & (move_id == mv)][:, :2]
            if len(q) >= 2:
                segs.append(LineString(q))
            elif len(q) == 1:
                segs.append(Point(q[0]).buffer(width * 0.02))
        if not segs:
            continue
        band = unary_union([g.buffer(width * 0.5 + 1e-4) for g in segs])
        geoms = band.geoms if isinstance(band, MultiPolygon) else [band]
        filled = [Polygon(g.exterior) for g in geoms if not g.is_empty]
        if filled:
            out[int(L)] = unary_union(filled)
    return out


def classify_unsupported(pts, move_id, kinds, layer, supported, width=0.45):
    """미지지 페리미터를 '진짜 돌출' / '희소 인필 위'로 가른다.

    왜 필요한가: 검사기 A 는 수평 ≤ 압출폭(0.45mm) 안에 아랫점이 있어야 지지로
    친다. 그런데 **위로 좁아지는** 형상은 층마다 페리미터가 안쪽으로 들어가
    아랫층 페리미터를 벗어나고, 그 자리 아래에는 희소 인필(간격 2.5mm)밖에
    없다. 그러면 '미지지'로 찍히지만 물리적으로는 아랫층 단면 **안**이라
    몇 mm 건너뛰는 평범한 브리징이다 — 오버행이 아니다.

    실측(2026-09-19): `slicing-comparison-model.stl` 의 페리미터 미지지 11.53%가
    **전부** 이 경우였다(진짜 돌출 0.00%p). 메시 예측은 "오버행 없음"이라 했고
    그쪽이 옳았다. 구(평면 0°)에서도 7.51% 중 2.62%p(35%)가 이 경우다.
    허상 비율이 모델마다 0~100% 로 달라지므로, 가르지 않은 '페리미터 미지지 %'는
    **모델 간 비교에 그대로 쓰면 안 된다.**

    판정: 점이 **바로 아래 층**의 단면 폴리곤 안에 있으면 '희소 인필 위'(허상),
    밖이면 '진짜 돌출'. 아래 층 단면을 모르면(층 미상·첫 층) 진짜 돌출로 둔다 —
    모르는 것을 유리하게 세지 않는다.

    반환: over_section (bool 배열). True = 아랫층 단면 안 = 허상.
    """
    over = np.zeros(len(pts), dtype=bool)
    target = (kinds == 0) & ~supported & (layer > 0)
    if not target.any():
        return over
    sections = layer_cross_sections(pts, move_id, kinds, layer, width)
    for i in np.where(target)[0]:
        below = sections.get(int(layer[i]) - 1)
        if below is not None and below.contains(Point(pts[i, 0], pts[i, 1])):
            over[i] = True
    return over


def support_breakdown(pts, move_id, kinds, layer, supported, weight,
                      width=0.45):
    """페리미터 미지지를 갈라 % 로 돌려준다.

    반환: dict(perimeter_unsupported_pct, overhang_pct, infill_gap_pct)
      overhang_pct + infill_gap_pct == perimeter_unsupported_pct
    """
    peri = kinds == 0
    tot = weight[peri].sum()
    if tot <= 0:
        return {"perimeter_unsupported_pct": float("nan"),
                "overhang_pct": float("nan"), "infill_gap_pct": float("nan")}
    over = classify_unsupported(pts, move_id, kinds, layer, supported, width)
    bad = peri & ~supported
    return {"perimeter_unsupported_pct": float(weight[bad].sum() / tot * 100.0),
            "overhang_pct": float(weight[bad & ~over].sum() / tot * 100.0),
            "infill_gap_pct": float(weight[bad & over].sum() / tot * 100.0)}


# ─────────────────────────────────────────────────────────────
# 검사기 B: 노즐 간섭
# ─────────────────────────────────────────────────────────────
@dataclass
class HotendProfile:
    """노즐/히트블록 기하. ⚠ 기본값은 Ender 3 V2 계열 '추정치' —
    실측 전 추정값이며 반드시 캘리퍼스로 잴 것."""
    tip_radius: float = 0.6        # 노즐 팁 평면 반경 (mm)
    cone_half_deg: float = 30.0    # 노즐 원뿔 반각 (도)
    cone_height: float = 3.0       # 원뿔 구간 높이 (mm)
    block_radius: float = 12.0     # 히트블록 유효 반경 (mm)
    block_z0: float = 5.0          # 히트블록 시작 높이 (팁 기준, mm)
    block_height: float = 12.0     # 히트블록 높이 (mm)


def check_nozzle(pts, move_id, hotend=None, batch_samples=2000,
                 clearance=0.3):
    """노즐 간섭 검사 (3축, 노즐 수직). 반환: collision(bool), 통계 dict.

    이전 배치=트리, 같은 배치 안 앞선 점=브루트포스 (check_support 와 동일 구조).
    clearance: 간섭으로 세지 않는 팁 위 여유(기본 층고 1배). 방금 찍은 자기
    비드는 정의상 노즐에 닿아 있으므로 — 원뿔 경로는 진행 방향으로 미세하게
    내려가 직전 샘플이 µm 단위로 '위'가 되는데, 이걸 간섭으로 오검출하는 버그를
    스윕 실측(4°에서 51% 오검출)으로 잡아 추가한 하한이다.
    """
    h = hotend or HotendProfile()
    n = len(pts)
    collision = np.zeros(n, dtype=bool)
    if n == 0:
        return collision, {"collision_pct": 0.0, "first_collision_z": None}
    tan_half = math.tan(math.radians(h.cone_half_deg))
    dz_max = h.block_z0 + h.block_height
    r_h_max = max(h.block_radius, h.tip_radius + h.cone_height * tan_half)
    radius = math.sqrt(r_h_max ** 2 + dz_max ** 2)

    def hit(dz, horiz):
        cone = (dz > clearance) & (dz <= h.cone_height) & \
               (horiz < h.tip_radius + dz * tan_half)
        block = (dz > max(h.block_z0, clearance)) & (dz <= dz_max) & \
                (horiz < h.block_radius)
        return cone | block

    tree = None
    for s0 in range(0, n, batch_samples):
        idx = np.arange(s0, min(s0 + batch_samples, n))
        if tree is not None:
            neigh = tree.query_ball_point(pts[idx], r=radius)
            for k, nb in zip(idx, neigh):
                if not nb:
                    continue
                q = pts[np.array(nb)]
                dz = q[:, 2] - pts[k, 2]              # 팁보다 '위'의 기퇴적물
                horiz = np.hypot(pts[k, 0] - q[:, 0], pts[k, 1] - q[:, 1])
                if np.any(hit(dz, horiz)):
                    collision[k] = True
        b = pts[idx]
        dzm = b[:, 2][None, :] - b[:, 2][:, None]      # q_j.z − tip_i.z
        horizm = np.hypot(b[:, 0][:, None] - b[:, 0][None, :],
                          b[:, 1][:, None] - b[:, 1][None, :])
        earlier = np.tril(np.ones((len(b), len(b)), dtype=bool), k=-1)
        collision[idx] |= (earlier & hit(dzm, horizm)).any(axis=1)
        tree = cKDTree(pts[:idx[-1] + 1])

    stats = {"collision_pct": float(collision.mean() * 100.0),
             "first_collision_z": (float(pts[collision, 2].min())
                                   if collision.any() else None)}
    return collision, stats
