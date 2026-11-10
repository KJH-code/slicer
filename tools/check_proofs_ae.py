"""check_proofs_ae.py — T6: 증명 A 와 증명 E(iii) 의 수치 확인.

사전 등록·판정 기준: `docs/test_t2_t6.md` §2.

A   유효 오버행 = 원래 오버행 − θ (경선 평면 안의 법선), 일반식 g(θ) = n_z·cosθ + c·n_r·sinθ.
    층 법선은 닫힌 식이 아니라 **실제 원뿔 층을 만들어** 잰다: 점의 변환높이 Z′ 를
    `AngleProfile.solve_forward` 로 찾고, 변환공간의 평면 Z′ 를 역변환식
    (x = X·cosθ, z = Z′ − R·sinθ) 으로 실공간에 그린 곡면의 (R, φ) 중앙차분 접벡터의 외적.
E(iii) 곡면 층 z = Z′ − a·r − b·r² 와 접하는 원뿔(값·기울기를 수치로 맞춘 1차 근사)의
    높이 오차가 거리² 에 비례하는가 (로그-로그 기울기 2).

    python3 tools/check_proofs_ae.py      # 수 초. results/t6_proofs_ae.json + docs/figures/t6_e3_tangent_cone.png
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conical.profile import AngleProfile  # noqa: E402

SEED = 20261110
N_SHAPES = 10
H = 20.0
C = 1.0                     # 부호 각도 규약 (θ<0 = inward)
A_TOL_DEG = 0.01            # 사전 기준


# ─────────────────────────────────────────────────────────────
# 증명 A
# ─────────────────────────────────────────────────────────────
def random_shape(rng):
    """매끈한 회전체 프로필 r(z) 와 r′(z) (z ∈ [0, H])."""
    k = np.arange(1, 5)
    amp = rng.uniform(-1.0, 1.0, 4) * 3.0 / k
    ph = rng.uniform(0, 2 * np.pi, 4)
    r0 = rng.uniform(6.0, 9.0)

    def r(z):
        z = np.asarray(z, float)
        return r0 + np.sum(amp[:, None] * np.sin(np.outer(k, z) * np.pi / H + ph[:, None]), 0)

    def dr(z):
        z = np.asarray(z, float)
        return np.sum((amp * k * np.pi / H)[:, None]
                      * np.cos(np.outer(k, z) * np.pi / H + ph[:, None]), 0)
    return r, dr


def random_profile(rng, r_max):
    """부호 있는 θ ∈ [−30°, 45°] 3 구간, 블렌드 폭은 가역성(c·r·s<1)을 넉넉히 지키게."""
    th = rng.uniform(-30.0, 45.0, 3)
    bps = [(0.0, th[0])]
    z = rng.uniform(4.0, 10.0)
    for i in (1, 2):
        dtan = abs(math.tan(math.radians(th[i])) - math.tan(math.radians(th[i - 1])))
        w = 3.0 * r_max * dtan + 1.0
        bps += [(z, th[i - 1]), (z + w, th[i])]
        z += w + rng.uniform(3.0, 8.0)
    return AngleProfile(bps)


def layer_normal(prof, p):
    """점 p (N,3) 를 지나는 실제 원뿔 층의 위쪽 단위 법선 (수치)."""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    r = np.hypot(x, y)
    phi = np.arctan2(y, x)
    zw = prof.solve_forward(z, r, "outward")
    th = np.radians(prof.theta_at(zw))
    big_r = r / np.cos(th)

    def surf(rr, pp):          # 변환공간 평면 Z′ 의 점 (R, φ) → 실공간 (역변환)
        return np.column_stack([rr * np.cos(th) * np.cos(pp), rr * np.cos(th) * np.sin(pp),
                                zw - C * rr * np.sin(th)])
    back = surf(big_r, phi)
    recon = float(np.abs(back - p).max())        # 층이 정말 그 점을 지나는가
    e = 1e-6
    t_r = (surf(big_r + e, phi) - surf(big_r - e, phi)) / (2 * e)
    t_p = (surf(big_r, phi + e) - surf(big_r, phi - e)) / (2 * e)
    n = np.cross(t_r, t_p)
    n /= np.linalg.norm(n, axis=1)[:, None]
    n *= np.sign(n[:, 2])[:, None]
    return n, np.degrees(th), recon


def overhang(n, b):
    """ω = atan2(−n·b, |n − (n·b)b|)  (0 = 수직벽, 90° = 아래보기 수평면)."""
    d = np.sum(n * b, 1)
    perp = np.linalg.norm(n - d[:, None] * b, axis=1)
    return np.degrees(np.arctan2(-d, perp))


def overhang_from_g(g):
    return np.degrees(np.arctan2(-g, np.sqrt(np.clip(1 - g * g, 0, None))))


def proof_a():
    rng = np.random.default_rng(SEED)
    zhat = np.array([0.0, 0.0, 1.0])
    rows = []
    worst_a1 = worst_a2 = 0.0
    excluded = 0
    for i in range(N_SHAPES):
        rf, drf = random_shape(rng)
        zz = np.linspace(0, H, 400)
        r_max = float(rf(zz).max())
        prof = random_profile(rng, r_max)

        # (A1) 해석적 표본점: 법선이 경선 평면 안 (n_t = 0)
        zs = rng.uniform(0.2, H - 0.2, 4000)
        phi = rng.uniform(-np.pi, np.pi, 4000)
        rs, d = rf(zs), drf(zs)
        p = np.column_stack([rs * np.cos(phi), rs * np.sin(phi), zs])
        nr, nz = 1 / np.sqrt(1 + d * d), -d / np.sqrt(1 + d * d)
        n = np.column_stack([nr * np.cos(phi), nr * np.sin(phi), nz])
        b, th, recon1 = layer_normal(prof, p)
        w0 = overhang(n, np.broadcast_to(zhat, n.shape))
        w_eff = overhang(n, b)
        pred = w0 - th                        # 바깥을 보는 면(n_r > 0) 이라 ω₀ − θ
        ok = np.abs(pred) < 89.9              # 수평을 넘는 경우는 ω 정의역 밖 → 제외(개수 기록)
        excluded += int((~ok).sum())
        d1 = np.abs(w_eff - pred)[ok]
        g1 = nz * np.cos(np.radians(th)) + C * nr * np.sin(np.radians(th))
        d1g = np.abs(w_eff - overhang_from_g(g1))

        # (A2) 회전체 메시의 모든 면 (n_t ≠ 0 포함)
        zg = np.linspace(0, H, 41)
        pts = [(0.0, 0.0)] + list(zip(rf(zg).tolist(), zg.tolist(), strict=True)) + [(0.0, H)]
        m = trimesh.creation.revolve(np.array(pts), sections=24)
        m.fix_normals()
        cen, fn = m.triangles_center, m.face_normals
        rc = np.hypot(cen[:, 0], cen[:, 1])
        keep = rc > 1e-6
        cen, fn, rc = cen[keep], fn[keep], rc[keep]
        er = np.column_stack([cen[:, 0] / rc, cen[:, 1] / rc, np.zeros_like(rc)])
        n_r = np.sum(fn * er, 1)
        n_t = np.sqrt(np.clip(1 - n_r ** 2 - fn[:, 2] ** 2, 0, None))
        b2, th2, recon2 = layer_normal(prof, cen)
        g2 = fn[:, 2] * np.cos(np.radians(th2)) + C * n_r * np.sin(np.radians(th2))
        d2 = np.abs(overhang(fn, b2) - overhang_from_g(g2))

        worst_a1 = max(worst_a1, float(d1.max()), float(d1g.max()))
        worst_a2 = max(worst_a2, float(d2.max()))
        rows.append({
            "shape": i, "r_range": [float(rf(zz).min()), r_max],
            "profile": [[float(z), float(t)] for z, t in zip(prof.zs, prof.thetas_deg, strict=True)],
            "A1_n": int(ok.sum()), "A1_excluded_beyond_horizontal": int((~ok).sum()),
            "A1_max_diff_deg_vs_w0_minus_theta": float(d1.max()),
            "A1_max_diff_deg_vs_g": float(d1g.max()),
            "A1_w0_range": [float(w0.min()), float(w0.max())],
            "A1_theta_range": [float(th.min()), float(th.max())],
            "A2_n_faces": int(len(fn)), "A2_n_t_max": float(n_t.max()),
            "A2_max_diff_deg_vs_g": float(d2.max()),
            "layer_through_point_max_err_mm": max(recon1, recon2),
        })
    return {"shapes": rows, "A1_max_diff_deg": worst_a1, "A2_max_diff_deg": worst_a2,
            "A1_excluded_total": excluded,
            "pass_A1": worst_a1 < A_TOL_DEG, "pass_A2": worst_a2 < A_TOL_DEG}


# ─────────────────────────────────────────────────────────────
# 증명 E(iii)
# ─────────────────────────────────────────────────────────────
ZP = 10.0


def tangent_cone(f, r0, hstep=1e-5):
    """곡면 층 z = Z′ − f(r) 에 r0 에서 접하는 원뿔 (경선의 접선을 회전) — 값·기울기는 수치로.

    반환: 원뿔 높이 함수 z_c(r) = Zc − t·r  (축 위 꼭짓점, 원뿔)."""
    def zl(r):
        return ZP - f(r)
    if r0 == 0.0:      # 축에서는 한쪽 차분 (2차 정확)
        slope = (-3 * zl(0.0) + 4 * zl(hstep) - zl(2 * hstep)) / (2 * hstep)
    else:
        slope = (zl(r0 + hstep) - zl(r0 - hstep)) / (2 * hstep)
    t = -slope
    zc = zl(r0) + t * r0
    return (lambda r: zc - t * r), t


def loglog_slope(x, y):
    return float(np.polyfit(np.log(x), np.log(y), 1)[0])


def proof_e():
    out = {"quadratic": [], "general": []}
    for a in (0.0, math.tan(math.radians(20.0))):
        for b in (0.002, 0.01, 0.05):
            def f(r, a=a, b=b):
                return a * r + b * np.asarray(r) ** 2
            # E1: 축에서 접함
            r = np.geomspace(0.1, 20.0, 60)
            zc, t = tangent_cone(f, 0.0)
            e = np.abs((ZP - f(r)) - zc(r))
            s1, q1 = loglog_slope(r, e), e / (b * r ** 2)
            # E2: r0 = 8 에서 접함, 양쪽
            r0 = 8.0
            zc2, t2 = tangent_cone(f, r0)
            dd = np.geomspace(0.01, 8.0, 60)
            res = {}
            for side, rr in (("in", r0 - dd), ("out", r0 + dd)):
                e2 = np.abs((ZP - f(rr)) - zc2(rr))
                res[side] = (loglog_slope(dd, e2), e2 / (b * dd ** 2))
            out["quadratic"].append({
                "a": a, "b": b,
                "E1_slope": s1, "E1_ratio_range": [float(q1.min()), float(q1.max())],
                "E1_cone_tan": t,
                "E2_slope_in": res["in"][0], "E2_slope_out": res["out"][0],
                "E2_ratio_range": [float(min(res["in"][1].min(), res["out"][1].min())),
                                   float(max(res["in"][1].max(), res["out"][1].max()))],
                "pass": bool(all(abs(s - 2) <= 0.01 for s in (s1, res["in"][0], res["out"][0]))
                             and all(abs(v - 1) <= 1e-3 for v in
                                     (q1.min(), q1.max(), *res["in"][1][[0, -1]],
                                      *res["out"][1][[0, -1]]))
                             and float(max(np.abs(q1 - 1).max(), np.abs(res["in"][1] - 1).max(),
                                           np.abs(res["out"][1] - 1).max())) <= 1e-3),
            })
    # 일반 곡선: f = a·r + β·(cosh(r/L) − 1)
    a, beta, L = math.tan(math.radians(20.0)), 0.5, 5.0

    def fg(r):
        return a * np.asarray(r) + beta * (np.cosh(np.asarray(r) / L) - 1.0)
    for r0 in (4.0, 8.0, 12.0):
        f2 = beta * math.cosh(r0 / L) / L ** 2
        zc, _t = tangent_cone(fg, r0)
        dd = np.geomspace(0.01, 0.5, 40)
        row = {"r0": r0, "f2": f2,
               "meridian_curvature": f2 / (1 + (a + beta * math.sinh(r0 / L) / L) ** 2) ** 1.5}
        ok = True
        for side, rr in (("in", r0 - dd), ("out", r0 + dd)):
            e = np.abs((ZP - fg(rr)) - zc(rr))
            s = loglog_slope(dd, e)
            q0 = float(e[0] / (f2 / 2 * dd[0] ** 2))
            row[f"slope_{side}"] = s
            row[f"ratio_at_0.01_{side}"] = q0
            row[f"ratio_at_0.5_{side}"] = float(e[-1] / (f2 / 2 * dd[-1] ** 2))
            ok &= abs(s - 2) <= 0.05 and abs(q0 - 1) <= 0.01
        row["pass"] = bool(ok)
        out["general"].append(row)
    out["pass_quadratic"] = all(r["pass"] for r in out["quadratic"])
    out["pass_general"] = all(r["pass"] for r in out["general"])
    return out


def figure(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, ink2, grid = "#0b0b0b", "#52514e", "#e4e3df"
    cols = ["#2a78d6", "#eb6834", "#1baf7a"]
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": ink2, "axes.labelcolor": ink,
                         "xtick.color": ink2, "ytick.color": ink2})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 4.0), dpi=200)

    # 왼쪽: 단면
    a, b = math.tan(math.radians(20.0)), 0.01
    r = np.linspace(-15, 15, 400)
    zl = ZP - a * np.abs(r) - b * r ** 2
    ax1.plot(r, zl, color=ink, lw=2, label="curved layer  z = Z′ − a·r − b·r²")
    zc0, _ = tangent_cone(lambda x: a * x + b * np.asarray(x) ** 2, 0.0)
    ax1.plot(r, zc0(np.abs(r)), color=cols[0], lw=2, ls="--", label="cone tangent at axis")
    zc8, _ = tangent_cone(lambda x: a * x + b * np.asarray(x) ** 2, 8.0)
    ax1.plot(r, zc8(np.abs(r)), color=cols[1], lw=2, ls="--", label="cone tangent at r₀ = 8")
    ax1.plot([8, -8], [ZP - a * 8 - b * 64] * 2, "o", ms=5, color=cols[1])
    ax1.fill_between(r, zl, zc0(np.abs(r)), color=cols[0], alpha=0.12, lw=0)
    ax1.set_xlabel("r (mm)  — meridian section")
    ax1.set_ylabel("z (mm)")
    ax1.set_title(f"Layer vs tangent cone  (a = tan20°, b = {b} /mm)", fontsize=9, color=ink)
    ax1.grid(color=grid, lw=0.6)
    ax1.legend(frameon=False, fontsize=8, loc="lower center")
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)

    # 오른쪽: 로그-로그
    rr = np.geomspace(0.1, 20.0, 60)
    for b_, c_ in zip((0.002, 0.01, 0.05), cols, strict=True):
        def f(x, b_=b_):
            return a * x + b_ * np.asarray(x) ** 2
        zc, _ = tangent_cone(f, 0.0)
        e = np.abs((ZP - f(rr)) - zc(rr))
        ax2.plot(rr, b_ * rr ** 2, color=c_, lw=1.2, alpha=0.6)
        ax2.plot(rr[::4], e[::4], "o", ms=4.5, color=c_, mec="white", mew=0.8,
                 label=f"b = {b_} /mm  (slope {loglog_slope(rr, e):.3f})")
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.set_xlabel("distance from tangent point (mm)")
    ax2.set_ylabel("height error |z_layer − z_cone| (mm)")
    ax2.set_title("Error ∝ b·r²  (markers: measured, lines: b·r²)", fontsize=9, color=ink)
    ax2.axhline(0.3, color=ink2, lw=0.8, ls=":")
    ax2.text(0.11, 0.33, "layer height 0.3 mm", fontsize=7.5, color=ink2)
    ax2.grid(color=grid, lw=0.6, which="major")
    ax2.legend(frameon=False, fontsize=8, loc="upper left")
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor="white")


def main():
    a = proof_a()
    e = proof_e()
    print(f"A1 (경선 평면 법선, ω_eff vs ω₀−θ 와 g): 최대 차 {a['A1_max_diff_deg']:.2e}° "
          f"(제외 {a['A1_excluded_total']}) → {'통과' if a['pass_A1'] else '실패'}")
    print(f"A2 (메시 전 면, ω_eff vs g): 최대 차 {a['A2_max_diff_deg']:.2e}° "
          f"→ {'통과' if a['pass_A2'] else '실패'}")
    for s in a["shapes"]:
        print(f"  형상 {s['shape']}: r {s['r_range'][0]:.1f}~{s['r_range'][1]:.1f}, "
              f"θ {s['A1_theta_range'][0]:.1f}~{s['A1_theta_range'][1]:.1f}°, "
              f"A1 {s['A1_max_diff_deg_vs_w0_minus_theta']:.1e}° / A2 {s['A2_max_diff_deg_vs_g']:.1e}° "
              f"(면 {s['A2_n_faces']}, n_t 최대 {s['A2_n_t_max']:.2f})")
    for q in e["quadratic"]:
        print(f"E 2차 a={q['a']:.3f} b={q['b']}: 기울기 E1 {q['E1_slope']:.5f}, "
              f"E2 {q['E2_slope_in']:.5f}/{q['E2_slope_out']:.5f}, 비 {q['E2_ratio_range']} "
              f"→ {'통과' if q['pass'] else '실패'}")
    for g in e["general"]:
        print(f"E 일반 r0={g['r0']}: 기울기 {g['slope_in']:.4f}/{g['slope_out']:.4f}, "
              f"비(Δ=0.01) {g['ratio_at_0.01_in']:.4f}/{g['ratio_at_0.01_out']:.4f} "
              f"→ {'통과' if g['pass'] else '실패'}")
    fig = ROOT / "docs" / "figures" / "t6_e3_tangent_cone.png"
    figure(fig)
    out = ROOT / "results" / "t6_proofs_ae.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"criteria": "docs/test_t2_t6.md §2", "seed": SEED,
                               "A": a, "E": e}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}\n→ {fig}")


if __name__ == "__main__":
    main()
