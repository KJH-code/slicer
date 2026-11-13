"""theta_star_check — 면별 임계각 닫힌 식 θ* = asin(κ/R) − atan2(n_z, c·n_r) 대 0~90° 전수 탐색.

저장소 코드(conical/*)를 쓰지 않는 독립 numpy 구현(tools/verify_proofs.py 의 check_theta_star 와 같은 방식).
무작위 단위 법선 3,000개(시드 0), 방향 c = ±1 무작위. 전수 탐색은 0.001° 간격에서
g(θ) = n_z cosθ + c·n_r sinθ ≥ κ (κ = −sin45°) 가 처음 성립하는 θ.
0° 에서 이미 지지되는 면과 0~90° 어디서도 안 풀리는 면은 비교에서 빼고 개수만 적는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.report_figs.style import (  # noqa: E402
    COLORS,
    figure,
    panel_label,
    save,
    setup,
)

N = 3000
STEP = 0.001
KAPPA = -np.sin(np.radians(45.0))


def main():
    rng = np.random.default_rng(0)
    v = rng.normal(size=(N, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    nr, nz = v[:, 0], v[:, 2]
    c = rng.choice([1.0, -1.0], size=N)
    ts = np.radians(np.arange(0.0, 90.0 + STEP / 2, STEP))
    cos_t, sin_t = np.cos(ts), np.sin(ts)
    brute = np.full(N, np.nan)
    already = nz >= KAPPA
    for i in np.where(~already)[0]:
        ok = nz[i] * cos_t + c[i] * nr[i] * sin_t >= KAPPA
        if ok.any():
            brute[i] = np.degrees(ts[ok.argmax()])
    used = ~already & np.isfinite(brute)
    rn = np.hypot(nz, nr)
    with np.errstate(invalid="ignore"):         # |κ/R| > 1 인 면은 늘 지지 — 비교에서 빠짐
        closed = np.degrees(np.arcsin(KAPPA / rn) - np.arctan2(nz, c * nr)) % 360.0
    diff = closed[used] - brute[used]
    n_used, n_never = int(used.sum()), int((~already & ~np.isfinite(brute)).sum())

    setup()
    fig, (a1, a2) = figure("full", 7.0, ncols=2)
    a1.plot([0, 90], [0, 90], color="0.6", lw=0.8, zorder=1, label="y = x")
    a1.plot(brute[used], closed[used], ".", ms=2, color=COLORS[0], label=f"면 {n_used}개")
    a1.set_xlabel("전수 탐색 θ* (°, 0.001° 간격)")
    a1.set_ylabel("닫힌 식 θ* (°)")
    a1.set_xlim(0, 90)
    a1.set_ylim(0, 90)
    a1.set_aspect("equal")
    a1.legend(loc="upper left")
    panel_label(a1, "a")
    a2.hist(diff * 1000, bins=50, color=COLORS[0], lw=0)
    a2.set_xlabel("닫힌 식 - 전수 탐색 (단위 0.001°)")
    a2.set_ylabel("면 수")
    md = float(np.abs(diff).max())
    a2.text(0.03, 0.95, f"최대 |차| = {md:.2e}°\n(격자 간격 {STEP}° 이하)\n"
            f"비교 {n_used}면 · 0°에서 이미 지지 {int(already.sum())} · 0~90° 불가 {n_never}",
            transform=a2.transAxes, va="top", fontsize=7.5,
            bbox={"fc": "white", "ec": "0.7", "lw": 0.5, "pad": 3})
    a2.set_ylim(0, a2.get_ylim()[1] * 1.35)
    panel_label(a2, "b")
    save(fig, "theta_star_check", __file__, ["tools/verify_proofs.py"],
         "임계각 닫힌 식 대 0~90° 전수 탐색(0.001° 간격): 무작위 법선 3,000개, 저장소 코드와 독립인 numpy 구현",
         f"비교 {n_used}면, 최대 |차| {md:.2e}° (< 격자 {STEP}°), 0°에서 이미 지지 {int(already.sum())}, "
         f"0~90° 불가 {n_never}",
         extra={"numbers": {"n": N, "compared": n_used, "already": int(already.sum()),
                            "never": n_never, "max_abs_diff_deg": md,
                            "mean_diff_deg": float(diff.mean())}})
    print(n_used, md, diff.mean())


if __name__ == "__main__":
    main()
