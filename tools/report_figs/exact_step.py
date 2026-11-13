"""exact_step — 한 모델(허리 r=2 = 램프)의 S(θ) 계단함수와 J(θ), 정확 최적 대 2° 격자 최적.

데이터는 전부 이 스크립트가 저장소 코드로 다시 계산한다(지어낸 값 없음):
  · S(θ) 계단: conical.exact_angle.support_step (outward)
  · 2° 격자 점: conical.analytic.support_fraction
  · 정확 최적: conical.exact_angle.select_uniform_exact
  · 격자 최적: conical.selector.select_cone(method="grid")
두 최적 모두 outward 라 outward 만 그린다(inward 는 최적이 아님 — 표 docs/exact_angle.md §4.2).

실행 (저장소 루트):  PYTHONPATH=. python3 tools/report_figs/exact_step.py
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from compare_waist import waisted_model  # noqa: E402
from conical.analytic import support_fraction  # noqa: E402
from conical.config import DEFAULT_K, MAX_ANGLE_DEG  # noqa: E402
from conical.exact_angle import select_uniform_exact, support_step  # noqa: E402
from conical.selector import select_cone  # noqa: E402
from conical.varangle import angle_candidates  # noqa: E402

SLUG = "exact_step"
CM = 1 / 2.54
OUT_DIR = "docs/report/figures"


def style():
    path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    if os.path.exists(path):
        font_manager.fontManager.addfont(path)
    plt.rcParams.update({"font.family": "NanumGothic", "font.size": 9,
                         "axes.unicode_minus": False, "savefig.dpi": 300})


def upsert_manifest(entry):
    p = os.path.join(OUT_DIR, "manifest.json")
    items = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            items = json.load(f)
    items = [e for e in items if e.get("slug") != entry["slug"]] + [entry]
    items.sort(key=lambda e: e["slug"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    style()
    k = DEFAULT_K
    mesh = waisted_model(2.0)
    st = support_step(mesh, "outward")
    best, info = select_uniform_exact(mesh, k)
    grid, _ = select_cone(mesh, k, verbose=False, method="grid")
    base = info["baseline"]
    assert best["direction"] == grid["direction"] == "outward"

    th = np.linspace(0.0, MAX_ANGLE_DEG, 44001)          # 0.001° — 계단 모양 표시용
    S = st["eval"](th)
    J = (base - S) - k * th
    ga = np.array(angle_candidates(MAX_ANGLE_DEG, 2))
    gS = np.array([support_fraction(mesh, a, "outward") for a in ga])
    gJ = (base - gS) - k * ga
    roots = st["roots_deg"]
    rising = st["rising"]

    c = plt.get_cmap("tab10").colors
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16 * CM, 6.2 * CM),
                                   constrained_layout=True)
    # (a) S(θ)
    ax1.plot(th, S, color=c[0], lw=1.0, label="S(θ) 계단 (정확)")
    ax1.plot(ga, gS, "o", ms=2.8, color=c[1], label="2° 격자 점")
    ylo = min(S.min(), gS.min())
    tick_h = 0.06 * (S.max() - ylo)
    ax1.vlines(roots[rising], ylo - tick_h, ylo, color=c[2], lw=0.5,
               label=f"면이 고쳐지는 근 ({int(rising.sum())})")
    if (~rising).any():
        ax1.vlines(roots[~rising], ylo - tick_h, ylo, color=c[3], lw=0.5,
                   label=f"다시 실패하는 근 ({int((~rising).sum())})")
    ax1.set_xlabel("원뿔각 θ (°, outward)")
    ax1.set_ylabel("서포트 필요 넓이 S (%)")
    ax1.set_xlim(0, MAX_ANGLE_DEG)
    ax1.legend(fontsize=7, frameon=False)
    # (b) J(θ)
    ax2.plot(th, J, color=c[0], lw=1.0, label="J(θ) = S(0) - S(θ) - kθ")
    ax2.plot(ga, gJ, "o", ms=2.8, color=c[1], label="2° 격자 점")
    ax2.plot([best["angle"]], [best["J"]], "*", ms=9, color=c[3],
             label=f"정확 최적 {best['angle']:.2f}°, J={best['J']:.3f}")
    ax2.plot([grid["angle"]], [grid["J"]], "s", ms=5, mfc="none", mew=1.2, color=c[1],
             label=f"격자 최적 {grid['angle']:.0f}°, J={grid['J']:.3f}")
    ax2.set_xlabel("원뿔각 θ (°, outward)")
    ax2.set_ylabel(f"J (%p, k={k})")
    ax2.set_xlim(0, MAX_ANGLE_DEG)
    ax2.set_ylim(J.min() - 1.6, J.max() + 0.4)
    ax2.legend(fontsize=7, frameon=False, loc="lower center", ncol=2,
               columnspacing=1.0, handletextpad=0.4)
    for ax, lab in ((ax1, "(a)"), (ax2, "(b)")):
        ax.text(-0.10, 1.02, lab, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=9, fontweight="bold")

    os.makedirs(OUT_DIR, exist_ok=True)
    png = os.path.join(OUT_DIR, f"{SLUG}.png")
    fig.savefig(png)
    upsert_manifest({
        "slug": SLUG, "png": png, "script": f"tools/report_figs/{SLUG}.py",
        "data_sources": ["compare_waist.waisted_model(2.0) (허리 r=2 = 램프, 9856 면)",
                         "conical.exact_angle.support_step / select_uniform_exact",
                         "conical.analytic.support_fraction (2° 격자 점)",
                         "conical.selector.select_cone(method='grid')"],
        "description": "허리 r=2 모델의 S(θ) 계단함수와 J(θ): 판정이 바뀌는 근에서만 S 가 변하고, "
                       "정확 최적은 근 바로 위, 2° 격자 최적은 그보다 낮은 J",
        "key_numbers": {"exact_angle_deg": round(best["angle"], 3),
                        "exact_J": round(best["J"], 4),
                        "grid_angle_deg": float(grid["angle"]),
                        "grid_J": round(float(grid["J"]), 4),
                        "rising_roots": int(rising.sum()),
                        "falling_roots": int((~rising).sum()),
                        "S0_pct": round(base, 4), "k": k},
    })
    print(png, best["angle"], best["J"], grid["angle"], grid["J"],
          int(rising.sum()), int((~rising).sum()))


if __name__ == "__main__":
    main()
