"""
backtransform.py — 변환공간 G-code → 실공간 G-code 역변환 (RotBot 3단계의 마지막).

수학 (transform.py 의 역):
    정변환:  X = x/cosθ,  Y = y/cosθ,  Z' = z + c·r·tanθ   (r = √(x²+y²))
    역변환:  x = X·cosθ,  y = Y·cosθ,  z = Z' − c·√(X²+Y²)·sinθ
    (유도: r_real = cosθ·√(X²+Y²) 이므로 c·r_real·tanθ = c·√(X²+Y²)·sinθ)

재분할 — 적응 균등 분할 + 실제 편차로 재귀 이등분:
    변환공간의 직선은 실공간에서 곡선이 된다. 고정 간격으로 잘게 쪼개면 G-code 가
    폭발하므로(docs/gcode_size_notes.md), 실공간 반경 r 에서 허용 현 길이
    L = 2·√(2·r·ε) 로 '적응' 균등 분할한다 (ε = 허용 현 오차. 축에서 멀수록 긴 직선).

    ⚠ 그 식만으로는 ε 를 못 지킨다 (2026-11-10 고침, docs/gap_audit.md G11).
      r 로 끝점 반경의 평균을 쓰는데, 실제 곡률을 정하는 것은 '직선이 축에 가장
      가까워지는 거리 d' 다. 축 근처를 지나는 인필·트래블은 r ≫ d 라 ε=0.05 인데
      0.33~0.48mm 어긋났고, 방향이 전부 아래였다(노즐이 앞 층을 판다).

    그래서 균등 분할한 조각마다 **정확 곡선과 현 사이의 실제 편차**를 구하고,
    ε 를 넘는 조각만 — 가장 많이 어긋난 것부터 — 이등분한다. 레이어 안의 이동
    (Z′ 일정 — 평면 슬라이서 출력의 거의 전부)은 편차가 닫힌 식이다:

        ρ(t) = √(d² + ℓ²(t−t*)²)      변환공간 직선의 축까지 거리 (ℓ = XY 길이)
        x, y 는 t 에 선형  →  현과의 차이는 z 뿐:
        δ(t) = |sinθ|·( lerp(ρ₀, ρ₁; t) − ρ(t) ) ≥ 0      (ρ 가 볼록)
        최대는 ρ′(t_c) = (ρ₁−ρ₀)/(t₁−t₀) =: k 인 곳,  t_c = t* + k·d/(ℓ·√(ℓ²−k²))

    즉 표본 추정이 아니라 **그 조각의 최대 수직 편차 그 자체**이고, 현까지의
    거리는 수직 편차를 넘지 못하므로 `편차 ≤ ε` 가 보장된다
    (tests/test_backtransform_chord.py).

    설계 선택 둘:
    · **균등 분할을 버리지 않고 그 위에 얹었다.** 편차만으로 쪼개면 이동 수는 6~14%
      줄지만(감사 문서의 제안), 조각이 길어진다 — 위치 편차가 작아도 방위각은 크게
      도는 조각(축 근처를 스치는 긴 선)이 생기고, 5축 출력은 조각 안에서 B/C 를
      선형 보간하므로 공구 방향이 층 법선에서 벗어난다. 균등 분할의 꼭짓점을 전부
      남기면 **ε 를 지키던 이동은 좌표가 예전과 비트 단위로 같고**, 바뀌는 것은
      ε 를 넘던 조각의 안쪽뿐이다.
    · ε 를 넘는 조각이 축 최근접점 t* 를 품으면 **t* 의 양옆 ±a 에서 먼저 자른다**
      (a = √(τ² + 2dτ), τ = ε/|sinθ| — 조각 [t*−a, t*+a] 의 편차가 정확히 ε).
      꺾임(d→0 이면 V 자)을 품는 조각을 허용 한도까지 넓게 잡는 것이라 조각 수가
      가장 적고, t* 바로 위에 꼭짓점을 두지 않는다 — 거기는 방위각이 경로와 직각이라
      5축 변환(`rep5x.to_rep5x`)이 축 통과를 B 부호 반전 대신 C 90°+90° 로 풀게 된다.
      ⚠ 그래도 축 근처 꼭짓점이 늘어나므로 5축 출력의 축 통과 처리는 달라진다 —
        ε 를 지키는 것과 맞바꾼 것이다.
    Z′ 가 변하는 이동(층 전환 트래블 등)은 닫힌 식이 없어 사분점 표본으로 잰다.
    오목 단봉 편차에서 사분점 표본은 최댓값의 75% 이상을 잡으므로 표본값/0.75 를
    쓴다 — 이쪽은 보수적 추정이지 엄밀한 상한이 아니다.

압출량 보정 — 체적 야코비안 cos²θ·m (2026-11-10, docs/gap_audit.md G2·G14):
    평면 슬라이서는 변환공간에서 비드 하나가 체적 w·h·L′ 을 채운다고 보고 E 를
    낸다 (w = 이웃 비드 간격, h = 층 간격). 그 체적이 실공간에서 차지하는 크기는
    역변환의 체적 야코비안만큼 달라진다.

    유도 (원통좌표, R = √(X²+Y²), θ = θ(Z′), T = tanθ, s = dT/dZ′, φ 는 그대로):
        r = R·cosθ,   z = Z′ − c·R·sinθ
        ∂r/∂R = cosθ            ∂r/∂Z′ = −R·sinθ·θ′
        ∂z/∂R = −c·sinθ         ∂z/∂Z′ = 1 − c·R·cosθ·θ′
        det₂ = cosθ·(1 − c·R·cosθ·θ′) − c·R·sin²θ·θ′ = cosθ − c·R·θ′
        dV/dV′ = (r/R)·det₂ = cos²θ − c·R·cosθ·θ′
        θ′ = s·cos²θ,  R = r/cosθ  →  c·R·cosθ·θ′ = c·r·s·cos²θ
        ⇒  dV/dV′ = cos²θ·(1 − c·r·s) = cos²θ·m          (m = 층간격 배율, profile.py)

    방향과 무관하다 — 같은 값을 비드 치수로 다시 세면:
        둘레 방향:  길이 L′·cosθ × 층 면 안 폭 w        × 두께 h·m·cosθ
        반경 방향:  길이 L′      × 층 면 안 폭 w·cosθ   × 두께 h·m·cosθ
    (두께 = 층 법선 방향 간격 t_n = h·m·cosθ. 상수각이면 m=1.)
    유한차분 야코비안과의 일치는 tests/test_backtransform_extrusion.py 가 강제한다.

    ⚠ 예전 보정은 '실길이/변환길이'(RotBot 관례)였다. 그 비는 둘레 cosθ·반경 1 이라
      필요량보다 1/(cosθ·m) ~ 1/(cos²θ·m) 배 많다 — 층이 얇아지는 것(t_n)을 안 센다.
      게다가 **그 보정조차 걸리지 않았다**: ΔE 를 `입력 E − 직전 출력 E` 로 구해서
      앞 이동에서 줄인 양이 다음 이동에 도로 붙었다(O_i = O_{i−1} + s·(E_i − O_{i−1})).
      낸 E 는 입력 E 의 1.000배였다. 지금은 입력 누적 E 와 출력 누적 E 를 **따로** 둔다.
    ⚠ 정직한 한계: 야코비안은 '슬라이서가 준 간격으로 이웃한 비드가 체적을 채운다'
      는 전제에서 정확하다. 이웃이 없는 **외톨이 반경 방향 선**은 폭이 w·cosθ 로
      나온다(둘레 방향 단벽은 w 그대로 — 페리미터가 이쪽이다).
    ⚠ 배율의 형태(길이 비 vs 야코비안)는 단벽 시험편 벽 두께로 실물 확인할 것
      (docs/gap_audit.md J11). 회계 결함은 어느 쪽이든 고쳐야 하는 것이었다.

E 회계 규칙:
    · 입력은 절대 E(M82) 전제 — 프리셋에 못박혀 있다. M83(상대 E)은 지원하지 않는다
    · `G92 E<n>`(raw 줄)을 만나면 입력·출력 누적값을 함께 n 으로 맞춘다. 외부
      슬라이서는 절대 E 에서도 리트랙션·층 전환마다 이 줄을 낸다
    · 순수 E 이동(XYZ 변화 없는 리트랙트/프라임)과 **ΔE ≤ 0 인 이동**(와이프 등)은
      퇴적이 아니므로 ΔE 를 배율 없이 그대로 옮긴다 — 필라멘트 길이는 기계량이다
    · 퇴적(ΔE > 0 이고 XYZ 가 움직임)만 조각별 cos²θ·m 을 곱한다
"""

import heapq
import math

from .gcode import _WORD, Move
from .profile import AngleProfile


def _inv_point(X, Y, Zw, profile, c):
    """역변환 (가변각 일반화): θ = θ(Zw) 를 점별로 조회 — 닫힌 식, 반복 불필요."""
    th = math.radians(float(profile.theta_at(Zw)))
    ct = math.cos(th)
    x = X * ct
    y = Y * ct
    z = Zw - c * math.hypot(X, Y) * math.sin(th)
    return x, y, z


def _crosses_blend(blends, z0, z1):
    """[z0, z1] 이 블렌드 구간(각도가 변하는 Z′ 구간)과 겹치는가."""
    lo, hi = (z0, z1) if z0 <= z1 else (z1, z0)
    return any(a < hi and b > lo for a, b in blends)


def volume_scale(profile, X, Y, Zw, c=1.0):
    """변환공간 점 (X, Y, Zw) 에서의 체적 야코비안 dV/dV′ = cos²θ·m.

    m = 1 − c·r·s (층간격 배율), r = cosθ·√(X²+Y²), s = dtanθ/dZ′.
    유도는 모듈 docstring. 퇴적 ΔE 에 곱하는 배율이 이것이다.
    """
    th = math.radians(float(profile.theta_at(Zw)))
    ct = math.cos(th)
    s = float(profile.slope_at(Zw))
    return ct * ct * (1.0 - c * math.hypot(X, Y) * ct * s)


def _g92_e(line):
    """raw 줄이 `G92 ... E<n>` 이면 n, 아니면 None."""
    words = _WORD.findall(line.split(";", 1)[0])
    if not words or words[0][0].upper() != "G" or float(words[0][1]) != 92.0:
        return None
    for k, v in words[1:]:
        if k.upper() == "E":
            return float(v)
    return None


def _uniform_count(real_len, r_mid, chord_tol, in_blend, max_sub):
    """적응 균등 분할 수: 허용 현 길이 L = 2√(2·r·ε), 블렌드를 지나면 절반."""
    allowed = 2.0 * math.sqrt(max(2.0 * r_mid * chord_tol, 1e-12))
    if in_blend:
        allowed *= 0.5     # ⚠ 블렌드 통과 이동: θ 변화가 z 곡률 추가 → 분할 2배
    return max(1, min(max_sub, math.ceil(real_len / max(allowed, 1e-9))))


def _refine(dev, n, tol, max_new, inner=(), gap=0.0):
    """균등 분할 n 조각에서 편차가 tol 을 넘는 조각만 더 쪼갠다.

    dev(a, b): 매개변수 구간 [a, b] 조각의 편차. inner: 넘는 조각 안에 들면 먼저
    넣을 분할점(축 최근접점의 양옆, 많아야 둘) — 조각 끝에서 gap 안쪽인 것만 쓴다.
    그 뒤로는 가장 많이 어긋난 조각부터 이등분하고, 새 분할점이 max_new 개가 되면
    멈춘다. 반환: (조각 끝 매개변수 오름차순, tol 을 못 지킨 조각 수).
    """
    grid = [i / n for i in range(n + 1)]
    devs = [dev(a, b) for a, b in zip(grid[:-1], grid[1:], strict=True)]
    if max(devs) <= tol:
        return grid[1:], 0
    heap = []
    added = 0
    for a, b, dv in zip(grid[:-1], grid[1:], devs, strict=True):
        cut = [t for t in inner if a + gap < t < b - gap] if dv > tol else []
        if cut:
            pts = [a, *cut, b]
            added += len(cut)
            heap += [(-dev(x, y), x, y) for x, y in zip(pts[:-1], pts[1:], strict=True)]
        else:
            heap.append((-dv, a, b))
    heapq.heapify(heap)
    while -heap[0][0] > tol and added < max_new:
        _, a, b = heap[0]
        m = 0.5 * (a + b)
        if not a < m < b:                    # 부동소수 한계 — 더 못 쪼갠다
            break
        heapq.heapreplace(heap, (-dev(a, m), a, m))
        heapq.heappush(heap, (-dev(m, b), m, b))
        added += 1
    return sorted(h[2] for h in heap), sum(1 for h in heap if -h[0] > tol)


def backtransform(items, cone_angle_deg, cone_type, chord_tol=0.05, max_sub=400):
    """파싱된 G-code 아이템들을 역변환한다. raw 줄은 그대로 통과.

    cone_angle_deg 자리에 float(고정각) 또는 AngleProfile(가변각 θ(Z′)) 허용 —
    float 는 상수 프로필로 감싸므로 기존 호출부는 무수정 호환.

    chord_tol: 정확 곡선과 출력 폴리라인 사이의 허용 편차 ε (mm).
    max_sub : 이동 하나의 균등 분할 수 상한. ε 를 지키려고 더 넣는 분할점도 이
              개수까지다. 한도에 걸려 ε 를 못 지킨 조각 수는 통계 `over_tol` 에 남는다.

    반환: (새 아이템 리스트, 통계 dict)
    """
    profile = cone_angle_deg if isinstance(cone_angle_deg, AngleProfile) \
        else AngleProfile.constant(cone_angle_deg)
    c = 1.0 if cone_type == "outward" else -1.0
    blends = profile.blend_intervals()

    layer = {}                   # Z′ → (cosθ, sinθ, s) — 레이어 하나에 이동 수천 개

    def consts(zw):
        k = layer.get(zw)
        if k is None:
            th = math.radians(float(profile.theta_at(zw)))
            k = layer[zw] = (math.cos(th), math.sin(th), float(profile.slope_at(zw)))
        return k

    out = []
    X = Y = Zw = None            # 변환공간 현재 위치 (모달)
    e_in = e_out = 0.0           # 입력 누적 E / 출력 누적 E — **따로** 센다
    n_in = n_out = n_over = 0

    for kind, payload in items:
        if kind != "move":
            if isinstance(payload, str):
                e_set = _g92_e(payload)
                if e_set is not None:
                    e_in = e_out = e_set
            out.append((kind, payload))
            continue
        mv = payload
        nX = mv.x if mv.x is not None else X
        nY = mv.y if mv.y is not None else Y
        nZ = mv.z if mv.z is not None else Zw
        dE = (mv.e - e_in) if mv.e is not None else None
        n_in += 1

        if nX is None or nY is None or nZ is None or X is None:
            # 아직 위치가 정해지기 전(첫 이동 등): 길이를 모르므로 ΔE 는 그대로 옮기고
            # 점만 역변환해 내보낸다
            e_val = None
            if dE is not None:
                e_in, e_out = mv.e, e_out + dE
                e_val = e_out
            if nX is not None and nY is not None and nZ is not None:
                x, y, z = _inv_point(nX, nY, nZ, profile, c)
                out.append(("move", Move(g=mv.g, x=x, y=y, z=z, e=e_val, f=mv.f,
                                         extra=mv.extra)))
            else:
                out.append(("move", Move(g=mv.g, x=mv.x, y=mv.y, z=mv.z, e=e_val,
                                         f=mv.f, extra=mv.extra)))
            X, Y, Zw = nX, nY, nZ
            n_out += 1
            continue

        dX, dY, dZ = nX - X, nY - Y, nZ - Zw
        warp_len = math.sqrt(dX * dX + dY * dY + dZ * dZ)

        # 순수 E 이동(리트랙트/프라임: XYZ 변화 없음)은 분할·배율 대상이 아니다.
        # (한때 warp_len≈0 → 배율 0 으로 ΔE 가 사라져 리트랙션이 전부 무력화됐었다.)
        if dE is not None and warp_len < 1e-9:
            e_in, e_out = mv.e, e_out + dE
            out.append(("move", Move(g=mv.g, e=e_out, f=mv.f, extra=mv.extra)))
            n_out += 1
            continue

        deposit = dE is not None and dE > 0.0

        if dZ == 0.0:
            # ── 레이어 안의 이동: 편차가 닫힌 식 (모듈 docstring) ──
            ct, st, s = consts(Zw)
            amp = abs(st)
            l2 = dX * dX + dY * dY
            ell = math.sqrt(l2)
            ts = -(X * dX + Y * dY) / l2 if l2 > 1e-18 else 0.0   # 축 최근접점
            d2 = max(X * X + Y * Y - l2 * ts * ts, 0.0)
            d = math.sqrt(d2)

            def rho(t, l2=l2, ts=ts, d2=d2):
                u = t - ts
                return math.sqrt(d2 + l2 * u * u)

            def dev(a, b, l2=l2, ts=ts, d=d, ell=ell, amp=amp, rho=rho):
                ra = rho(a)
                k = (rho(b) - ra) / (b - a)
                q = l2 - k * k
                if q <= 1e-12 * l2:          # ρ 가 직선 (축을 지나는 선의 한쪽)
                    return 0.0
                tc = min(max(ts + k * d / (ell * math.sqrt(q)), a), b)
                return amp * (ra + k * (tc - a) - rho(tc))

            r0, r1 = math.hypot(X, Y), math.hypot(nX, nY)
            n = _uniform_count(
                math.dist((X * ct, Y * ct, Zw - c * r0 * st),
                          (nX * ct, nY * ct, Zw - c * r1 * st)),
                0.5 * (math.hypot(X * ct, Y * ct) + math.hypot(nX * ct, nY * ct)),
                chord_tol, bool(blends) and _crosses_blend(blends, Zw, nZ), max_sub)
            if amp == 0.0 or l2 <= 1e-18:
                cuts, over = [i / n for i in range(1, n + 1)], 0
            else:
                tau = chord_tol / amp
                a_t = math.sqrt(tau * tau + 2.0 * d * tau) * (1.0 - 1e-6) / ell
                cuts, over = _refine(dev, n, chord_tol, max_sub,
                                     (ts - a_t, ts + a_t), 1e-3 / ell)
            n_over += over
            ta, ra = 0.0, r0
            for tb in cuts:
                Xb, Yb = X + dX * tb, Y + dY * tb
                rb = math.hypot(Xb, Yb)
                e_val = None
                if dE is not None:
                    k = 1.0
                    if deposit:
                        k = ct * ct
                        if s != 0.0:           # 블렌드: m = 1 − c·r·s, r 은 조각 평균
                            rbar = (ra + 4.0 * rho(0.5 * (ta + tb)) + rb) / 6.0
                            k *= max(1.0 - c * s * ct * rbar, 0.0)
                    e_out += dE * (tb - ta) * k
                    e_val = e_out
                out.append(("move", Move(g=mv.g, x=Xb * ct, y=Yb * ct,
                                         z=Zw - c * rb * st, e=e_val, f=mv.f,
                                         extra=mv.extra)))
                ta, ra = tb, rb
            n_out += len(cuts)
        else:
            # ── Z′ 가 변하는 이동: θ 도 따라 변한다 → 사분점 표본 ──
            seen = {}

            def pt(t, seen=seen, X=X, Y=Y, Zw=Zw, dX=dX, dY=dY, dZ=dZ):
                p = seen.get(t)
                if p is None:
                    p = seen[t] = _inv_point(X + dX * t, Y + dY * t, Zw + dZ * t,
                                             profile, c)
                return p

            def dev_s(a, b, pt=pt):
                pa, pb = pt(a), pt(b)
                worst = 0.0
                for f in (0.25, 0.5, 0.75):
                    p = pt(a + (b - a) * f)
                    worst = max(worst, math.dist(
                        p, [pa[i] + (pb[i] - pa[i]) * f for i in range(3)]))
                return worst / 0.75

            p0, p1 = pt(0.0), pt(1.0)
            n = _uniform_count(
                math.dist(p0, p1),
                0.5 * (math.hypot(p0[0], p0[1]) + math.hypot(p1[0], p1[1])),
                chord_tol, bool(blends) and _crosses_blend(blends, Zw, nZ), max_sub)
            cuts, over = _refine(dev_s, n, chord_tol, max_sub)
            n_over += over
            ta = 0.0
            for tb in cuts:
                e_val = None
                if dE is not None:
                    k = 1.0
                    if deposit:
                        tm = 0.5 * (ta + tb)
                        k = max(volume_scale(profile, X + dX * tm, Y + dY * tm,
                                             Zw + dZ * tm, c), 0.0)
                    e_out += dE * (tb - ta) * k
                    e_val = e_out
                x, y, z = pt(tb)
                out.append(("move", Move(g=mv.g, x=x, y=y, z=z, e=e_val, f=mv.f,
                                         extra=mv.extra)))
                ta = tb
            n_out += len(cuts)

        if dE is not None:
            e_in = mv.e
        X, Y, Zw = nX, nY, nZ

    stats = {"moves_in": n_in, "moves_out": n_out,
             "expansion": n_out / max(n_in, 1), "over_tol": n_over}
    return out, stats
