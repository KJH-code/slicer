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
# `G92 E0` — E 원점 이동. 프라임 선 뒤나 층마다 나온다.
_G92_E = re.compile(r"^G92\b[^;]*?\bE(-?\d+(?:\.\d+)?)", re.I)


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
                else:
                    # G92 로 E 원점을 옮기면 '압출인가'의 기준도 같이 옮겨야 한다.
                    # 안 그러면 리셋 직후 한 구간이 '압출 아님'으로 빠진다
                    # (프라임 선 뒤 G92 E0 이 대표적). gcode.parse 는 G0/G1 만
                    # move 로 보므로 G92 는 여기 raw 로 온다.
                    mo = _G92_E.match(c)
                    if mo:
                        e_prev = float(mo.group(1))
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


OVERHANG, INSIDE = 0, 1
UNSUPPORTED_KINDS = {OVERHANG: "진짜 오버행", INSIDE: "아랫층 단면 안"}


def classify_unsupported(pts, move_id, kinds, layer, supported, width=0.45):
    """미지지 페리미터를 '진짜 오버행' / '아랫층 단면 안'으로 가른다.
    반환: label (N,), 해당 없으면 −1.

    검사기 A 는 수평 ≤ 압출폭(0.45mm) 안에 먼저 퇴적된 아랫점이 있어야 지지로
    친다. 그 창이 **아랫층 단면 안인데도 창 밖**인 경우를 전부 미지지로 세는데,
    그건 오버행이 아니다 — 위로 좁아지는 형상은 층마다 페리미터가 안쪽으로
    들어가 희소 인필(간격 2.5mm) 위에 놓인다.

    가장 깨끗한 시연: 위로 좁아지는 **순수 원뿔**(아래를 보는 면이 바닥뿐이라
    오버행이 정의상 0)이 좁아지는 속도에 따라 미지지 31~63% 로 보고된다.

    ⚠ **이 분류는 '단면 안'을 무죄라고 말하지 않는다.** 단면 안에도 성질이 다른
      둘이 섞여 있다 — ⓐ 아래 재료가 바로 밑에 있는 평범한 브리징(정상)과
      ⓑ 층간격이 벌어져 수직으로 떠 있는 것(결함). 둘을 수평·수직 창으로
      가르려 해봤으나 창 하나로는 갈라지지 않았다(2.5mm 로 두면 ⓑ가 전부
      ⓐ로, 0.45mm 로 두면 ⓐ가 전부 ⓑ로 간다). **층간격 팽창은 이 분류기가
      아니라 전용 해석식 검사(`AngleProfile.check_spacing`, 배율 m = 1−c·r·s)가
      맡는다** — 그쪽이 원인을 직접 보기 때문이다.
      대신 `support_breakdown` 이 '단면 안' 점들의 **수직 간격 통계**를 같이
      돌려주므로, 그 값이 층고보다 크면 브리징이 아니라 팽창을 의심하면 된다.
      (실측: 구 밴드2 배율 1.50 프로필에서 수직 간격 중앙값 1.20mm, 층고 0.40)

    단면은 `layer_cross_sections` 가 페리미터 압출선만으로 복원한다(메시 불필요).
    층을 모르면(첫 층·주석 없음) 판정할 수 없으므로 오버행으로 둔다 — 모르는
    것을 유리하게 세지 않는다.
    """
    n = len(pts)
    label = np.full(n, -1, dtype=int)
    target = (kinds == 0) & ~supported
    if not target.any():
        return label
    idx = np.where(target)[0]
    label[idx] = OVERHANG
    sections = layer_cross_sections(pts, move_id, kinds, layer, width)
    for i in idx:
        below = sections.get(int(layer[i]) - 1)
        if below is not None and below.contains(Point(pts[i, 0], pts[i, 1])):
            label[i] = INSIDE
    return label


def vertical_gaps(pts, mask, width=0.45, max_depth=4.0):
    """`mask` 점들에 대해 **먼저 퇴적된** 아래 재료까지의 수직 거리 (수평 ≤ width).

    ⚠ 이 값은 층간격 팽창의 지표가 **아니다.** 희소 인필 격자에 지배된다 —
      인필은 층마다 0/90° 로 방향이 바뀌고 간격이 2.5mm 라, 좁은 수평 창 안에서
      바로 아랫층에 선이 없는 일이 흔하고 몇 층 내려가야 만난다. 실제로
      **팽창이 정의상 없는 평면 0° 슬라이싱에서도 중앙값 1.20mm** 가 나온다
      (층고 0.40). 그래서 절대값이 아니라 **평면 0° 대조군과의 차이**로만 읽어야
      하고, 그조차 신뢰도가 낮다(램프 배율 5.8배에서는 2.14mm 로 뜨는데 구
      배율 15.5배에서는 1.20mm 로 안 뜬다).

    층간격 팽창의 판정은 전용 해석식 검사(`AngleProfile.check_spacing`,
    배율 m = 1 − c·r·s)가 맡는다. 이 함수는 참고 수치일 뿐이다.
    창 안에 아무것도 없으면 nan.
    """
    out = np.full(int(mask.sum()), np.nan)
    if not mask.any():
        return out
    idx = np.where(mask)[0]
    tree = cKDTree(pts[:, :2])
    neigh = tree.query_ball_point(pts[idx][:, :2], r=width)
    for k, i in enumerate(idx):
        nb = np.asarray(neigh[k], dtype=int)
        nb = nb[nb < i]                       # G-code 순서: 먼저 퇴적된 것만
        if len(nb) == 0:
            continue
        dz = pts[i, 2] - pts[nb, 2]
        dz = dz[(dz > 1e-9) & (dz <= max_depth)]
        if len(dz):
            out[k] = dz.min()
    return out


def support_breakdown(pts, move_id, kinds, layer, supported, weight,
                      width=0.45):
    """페리미터 미지지를 갈라 % 로 돌려준다 + '단면 안' 수직 간격 진단.

    반환: dict(perimeter_unsupported_pct, overhang_pct, inside_pct,
               inside_gap_median, inside_gap_p90)
      overhang_pct + inside_pct == perimeter_unsupported_pct
    **서포트 판단은 `overhang_pct` 로 한다.** `inside_pct` 는 오버행이 아니지만
    무죄도 아니다 — 수직 간격이 층고 수준이면 브리징(정상), 크게 넘으면
    층간격 팽창(결함)을 의심하고 `check_spacing` 으로 확인한다.
    """
    peri = kinds == 0
    tot = weight[peri].sum()
    keys = ("perimeter_unsupported_pct", "overhang_pct", "inside_pct",
            "inside_gap_median", "inside_gap_p90")
    if tot <= 0:
        return dict.fromkeys(keys, float("nan"))
    lab = classify_unsupported(pts, move_id, kinds, layer, supported, width)
    bad = peri & ~supported
    ins = lab == INSIDE
    gaps = vertical_gaps(pts, ins, width)
    fin = gaps[~np.isnan(gaps)]
    return {"perimeter_unsupported_pct": float(weight[bad].sum() / tot * 100.0),
            "overhang_pct": float(weight[lab == OVERHANG].sum() / tot * 100.0),
            "inside_pct": float(weight[ins].sum() / tot * 100.0),
            "inside_gap_median": float(np.median(fin)) if len(fin) else float("nan"),
            "inside_gap_p90": float(np.percentile(fin, 90)) if len(fin) else float("nan")}


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
