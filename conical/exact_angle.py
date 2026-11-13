"""
exact_angle.py — 균일각의 **정확 탐색** (성질 A′, docs/exact_angle.md).

판정식 g(θ) = n_z·cosθ + d·n_r·sinθ 는 면마다 θ 의 연속함수(R·sin(θ+δ))라서
면 하나의 판정은 g(θ) = κ 인 각도에서만 바뀐다. 그러므로 면적 가중 서포트 S(θ) 는
**계단함수**이고, 균일각 목적함수

    J(θ, 방향) = S(0) − S(θ) − k·θ          (selector.evaluate_J 와 같은 꼴)

는 각 계단 안에서 θ 에 대해 강하게 감소한다(k > 0). 따라서 최적해는 유한 개 후보 —
0° 와 각 면의 '올라가는 근'(면이 고쳐지는 각) — 중에 있다. 격자(`ANGLE_STEP`)로 훑을
필요가 없다.

판정은 `analytic.py` 와 **똑같이** 맞춘다:
  · n_r 은 `analytic.radial_normal` 그대로
  · 엄격 부등호 g < κ (R ≤ |κ| 인 면은 근이 없고 늘 통과)
  · 바닥면을 빼지 않는다 (`support_fraction` 이 안 뺀다)

범위: **각도 하나**(모델 전체 또는 mask 하나)를 고르는 경우만. 밴드 프로필의 J
(`varangle.select_banded_j` 의 블렌드 벌점 포함) 는 계단함수가 아니라 이 논법 밖이다.

기존 격자 경로는 그대로 두고, `selector.select_cone(method="exact")` 와
`varangle.best_angle_for_mask(method="exact")` 로만 부른다. **기본값은 격자다.**
"""

import math

import numpy as np

from .analytic import radial_normal
from .config import MAX_ANGLE_DEG, THRESHOLD_DEG

# 근 바로 위로 옮기는 폭(도). 근에서 바로 평가하면 반올림으로 그 면이 아직 실패로
# 셀 수 있다 — 근이 아닌 일반점에서 평가하면 엄격/비엄격 구분이 사라진다.
# J 손실은 최대 k·EPS_DEG (k=0.2 에서 2e-8).
EPS_DEG = 1e-7
# 이 거리(라디안) 안의 근들은 같은 점으로 묶는다 (회전체 메시의 한 고리처럼
# 법선이 같은 면들의 근은 마지막 비트만 다르다).
_CLUSTER_RAD = 1e-13
# 이보다 작은 근은 '0 에 있는 근' 으로 보고, 시작 상태를 θ=_THETA0 에서 직접 잰다.
_THETA0 = 1e-10


def _weights(mesh, mask=None):
    """면 가중치(%). mask 가 있으면 그 면들의 넓이로 정규화 (best_angle_for_mask 와 같다)."""
    a = mesh.area_faces
    if mask is None:
        return a / a.sum() * 100.0
    w = np.where(mask, a, 0.0)
    return w / w.sum() * 100.0


def face_roots(nz, b, kappa, max_rad):
    """면마다 g(θ)=n_z cosθ + b sinθ = κ 의 근 중 (_THETA0, max_rad] 에 드는 것.

    반환 (face_idx, root_rad, sign): sign = −1 이면 그 근에서 면이 **고쳐짐**
    (g 가 κ 를 아래→위로 통과, '올라가는 근'), +1 이면 **다시 실패**(둘째 근).
    R ≤ |κ| 인 면은 g < κ 가 불가능하므로 근이 없다.
    """
    R = np.hypot(nz, b)
    valid = R > abs(kappa) * (1.0 + 1e-12)
    idx = np.nonzero(valid)[0]
    s = np.arcsin(kappa / R[idx])
    delta = np.arctan2(nz[idx], b[idx])
    two_pi = 2.0 * math.pi
    out_f, out_r = [], []
    for base in (s - delta, math.pi - s - delta):
        r = np.mod(base, two_pi)
        keep = (r > _THETA0) & (r <= max_rad)
        out_f.append(idx[keep])
        out_r.append(r[keep])
    f = np.concatenate(out_f)
    r = np.concatenate(out_r)
    # g'(r) = −n_z sin r + b cos r  > 0 → 올라감(고쳐짐)
    gp = -nz[f] * np.sin(r) + b[f] * np.cos(r)
    sign = np.where(gp > 0, -1.0, 1.0)
    return f, r, sign


def support_step(mesh, direction, threshold_deg=THRESHOLD_DEG,
                 max_angle=MAX_ANGLE_DEG, mask=None, radial=None):
    """한 방향의 S(θ) 계단함수를 만든다.

    반환 dict:
      S0          : θ=0 에서의 S (analytic.support_fraction 과 같은 엄격 판정)
      roots_deg   : 근(묶은 뒤 대표값), 오름차순
      rising      : 각 근 묶음에 '올라가는 근'(면이 고쳐짐)이 있는가
      cand_deg    : 후보 평가점 p = 근 + min(ε, 다음 근까지/2)   (MAX 로 자름)
      S_cand      : p 에서의 S
      width_deg   : p 가 속한 계단의 폭(그 근 ~ 다음 근, 마지막은 MAX 까지)
      eval        : 임의 각도(도) 배열 → S 를 돌려주는 함수 (근 위가 아닌 점에서 정확)
    """
    nz = mesh.face_normals[:, 2]
    nr = radial_normal(mesh) if radial is None else radial
    d = 1.0 if direction == "outward" else -1.0
    b = d * nr
    kappa = -math.sin(math.radians(threshold_deg))
    max_rad = math.radians(max_angle)
    w = _weights(mesh, mask)

    S0 = float(w[nz < kappa].sum())
    # 시작 상태는 θ0(0 바로 위)에서 직접 잰다 — 0 에 걸친 근을 이벤트로 안 다루려고.
    g0 = nz * math.cos(_THETA0) + b * math.sin(_THETA0)
    S_init = float(w[g0 < kappa].sum())

    f, r, sign = face_roots(nz, b, kappa, max_rad)
    order = np.argsort(r, kind="stable")
    r, f, sign = r[order], f[order], sign[order]
    cum = S_init + np.cumsum(sign * w[f])

    def eval_rad(theta_rad):
        theta_rad = np.atleast_1d(np.asarray(theta_rad, dtype=float))
        if len(cum) == 0:
            return np.where(theta_rad <= 0.0, S0, S_init)
        j = np.searchsorted(r, theta_rad, side="right") - 1
        out = np.where(j >= 0, cum[np.maximum(j, 0)], S_init)
        return np.where(theta_rad <= 0.0, S0, out)

    # 근 묶기: 간격이 _CLUSTER_RAD 이하면 같은 점
    if len(r):
        new = np.concatenate([[True], np.diff(r) > _CLUSTER_RAD])
        gid = np.cumsum(new) - 1
        n_g = int(gid[-1]) + 1
        rep = np.zeros(n_g)
        np.maximum.at(rep, gid, r)
        first = np.full(n_g, np.inf)
        np.minimum.at(first, gid, r)
        rising = np.zeros(n_g, dtype=bool)
        np.logical_or.at(rising, gid, sign < 0)
        nxt = np.append(first[1:], max_rad)
        gap = nxt - rep
        p = np.minimum(rep + np.minimum(math.radians(EPS_DEG), gap / 2.0), max_rad)
        # 마지막 묶음이 MAX 와 같을 때 gap=0 → p = rep (=MAX). 그 점은 analytic 이
        # 직접 판정하는 경계점이라 반올림 위험이 남는다 — 아래 (b) 검사가 잡는다.
        width = np.degrees(gap)
    else:
        rep = np.zeros(0)
        rising = np.zeros(0, dtype=bool)
        p = np.zeros(0)
        width = np.zeros(0)

    return {
        "direction": direction, "S0": S0,
        "roots_deg": np.degrees(rep), "rising": rising,
        "cand_deg": np.degrees(p), "S_cand": eval_rad(p) if len(p) else np.zeros(0),
        "width_deg": width,
        "n_face_roots": int(len(r)),
        "eval": lambda deg: eval_rad(np.radians(np.asarray(deg, dtype=float))),
    }


def select_uniform_exact(mesh, k, max_angle=MAX_ANGLE_DEG,
                         threshold_deg=THRESHOLD_DEG, mask=None):
    """J = S(0) − S(θ) − k·θ 를 **정확히** 최대화하는 (각도, 방향).

    후보: 0°, MAX, 그리고 두 방향의 모든 근 바로 위(p). 내려가는 근과 MAX 는 이론상
    후보가 될 수 없지만(docs/exact_angle.md §1) 넣어도 결과는 같으므로 넣는다.

    타이브레이크는 `selector.select_cone` 과 같다: outward 먼저, 같은 방향 안에서는
    작은 각도 먼저 (J 가 1e-12 안이면 동률).

    반환: (best, info)  best 는 select_cone 의 후보 dict 와 같은 키
          (angle, direction, support, gain, cost, J) + width_deg.
    """
    radial = radial_normal(mesh)
    rows = []
    steps = {}
    for direction in ("outward", "inward"):
        st = support_step(mesh, direction, threshold_deg, max_angle, mask, radial)
        steps[direction] = st
        angs = np.concatenate([[0.0], st["cand_deg"], [float(max_angle)]])
        sups = np.concatenate([[st["S0"]], st["S_cand"],
                               st["eval"]([float(max_angle)])])
        widths = np.concatenate([[st["roots_deg"][0] if len(st["roots_deg"])
                                  else float(max_angle)],
                                 st["width_deg"], [0.0]])
        o = np.argsort(angs, kind="stable")
        for a, s, wd in zip(angs[o], sups[o], widths[o], strict=True):
            rows.append((direction, float(a), float(s), float(wd)))

    baseline = steps["outward"]["S0"]
    best = None
    for direction, a, s, wd in rows:
        J = (baseline - s) - k * a
        if best is None or J > best["J"] + 1e-12:
            best = {"angle": a, "direction": direction, "support": s,
                    "gain": baseline - s, "cost": k * a, "J": J, "width_deg": wd}
    info = {"n_candidates": len(rows),
            "n_face_roots": sum(st["n_face_roots"] for st in steps.values()),
            "baseline": baseline, "steps": steps}
    return best, info
