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
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree


# ─────────────────────────────────────────────────────────────
# 샘플링
# ─────────────────────────────────────────────────────────────
def sample_extrusions(items, width=0.45):
    """압출(dE>0) 세그먼트를 간격 width/2 로 점 샘플링 (G-code 순서 유지).

    반환: pts (N,3), move_id (N,), weight (N,)  — weight = 각 점이 대표하는 경로 길이(mm)
    """
    spacing = width / 2.0
    pts, mids, wts = [], [], []
    x = y = z = None
    e_prev = 0.0
    mid = 0
    for kind, p in items:
        if kind != "move":
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
        if p.e is not None:
            e_prev = p.e
        x, y, z = nx, ny, nz
        mid += 1
    return (np.array(pts) if pts else np.zeros((0, 3)),
            np.array(mids, dtype=int), np.array(wts))


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


def check_nozzle(pts, move_id, hotend=None, batch_samples=2000):
    """노즐 간섭 검사 (3축, 노즐 수직). 반환: collision(bool), 통계 dict.

    이전 배치=트리, 같은 배치 안 앞선 점=브루트포스 (check_support 와 동일 구조).
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
        cone = (dz > 1e-9) & (dz <= h.cone_height) & \
               (horiz < h.tip_radius + dz * tan_half)
        block = (dz > h.block_z0) & (dz <= dz_max) & (horiz < h.block_radius)
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
