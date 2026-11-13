"""exact_lambda — λ 축(허리3 widen, λ 1.16~1.30, 간격 0.002, 71 점)에서 2° 격자와 정확 탐색이
고른 균일각, 그리고 격자가 잃는 J.

데이터는 전부 이 스크립트가 저장소 코드로 다시 계산한다(지어낸 값 없음):
  · 모델: analyze_blend_ratio.widen(compare_waist.waisted_model(3.0), λ)  (analyze_angle_grid 와 같은 축)
  · 격자: conical.selector.select_cone(method="grid")  — select_banded_j(n=1) 의 균일 후보와
    같은 각도·J 임을 analyze_exact_angle.py 가 10/10 점에서 확인
  · 정확: conical.exact_angle.select_uniform_exact
점선 세로선 = docs/verification.md 2026-09-28 이 인용한 λ 1.22 / 1.24.

실행 (저장소 루트):  PYTHONPATH=. python3 tools/report_figs/exact_lambda.py
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from analyze_blend_ratio import widen  # noqa: E402
from compare_waist import waisted_model  # noqa: E402
from conical.config import DEFAULT_K  # noqa: E402
from conical.exact_angle import select_uniform_exact  # noqa: E402
from conical.selector import select_cone  # noqa: E402

SLUG = "exact_lambda"
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


def signed(a, d):
    return a if d == "outward" else -a


def jumps(lams, A, thr=1.0):
    j = np.nonzero(np.abs(np.diff(A)) > thr)[0]
    return [[round(float(lams[i]), 3), round(float(lams[i + 1]), 3),
             round(float(A[i]), 3), round(float(A[i + 1]), 3)] for i in j]


def main():
    style()
    k = DEFAULT_K
    base = waisted_model(3.0)
    lams = np.round(np.arange(1.16, 1.30 + 1e-9, 0.002), 6)
    E, G, JE, JG = [], [], [], []
    for lam in lams:
        m = widen(base, float(lam))
        e, _ = select_uniform_exact(m, k)
        g, _ = select_cone(m, k, verbose=False, method="grid")
        E.append(signed(e["angle"], e["direction"]))
        G.append(signed(float(g["angle"]), g["direction"]))
        JE.append(e["J"])
        JG.append(float(g["J"]))
    E, G, JE, JG = map(np.array, (E, G, JE, JG))
    loss = JE - JG

    c = plt.get_cmap("tab10").colors
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16 * CM, 6.2 * CM),
                                   constrained_layout=True)
    ax1.step(lams, G, where="mid", color=c[1], lw=1.0, label="2° 격자")
    ax1.plot(lams, G, "o", ms=2.0, color=c[1])
    ax1.plot(lams, E, ".", ms=3.0, color=c[0], label="정확 탐색")
    jg, je = jumps(lams, G), jumps(lams, E)
    for a, b, _, _ in je:
        ax1.axvspan(a, b, color=c[0], alpha=0.25, lw=0)
    ax1.set_xlabel("XY 배율 λ (무차원)")
    ax1.set_ylabel("고른 균일각 θ (°, outward)")
    ax1.set_ylim(23.5, 38.5)
    ax1.legend(fontsize=7, frameon=False, loc="upper left", ncol=2,
               title=f"1° 넘는 점프: 격자 {len(jg)}회, 정확 {len(je)}회",
               title_fontsize=7)
    ax2.plot(lams, loss, color=c[1], lw=1.0, label="J(정확) - J(격자)")
    ax2.axhline(k * 2.0, color="0.4", lw=0.8, ls=":", label=f"격자 최대 손실 k·2° = {k * 2:.1f}")
    ax2.set_xlabel("XY 배율 λ (무차원)")
    ax2.set_ylabel(f"J 차 (%p, k={k})")
    ax2.set_ylim(0, k * 2.0 * 1.25)
    ax2.legend(fontsize=7, frameon=False, loc="upper left")
    for ax, lab in ((ax1, "(a)"), (ax2, "(b)")):
        for x in (1.22, 1.24):
            ax.axvline(x, color="0.6", lw=0.6, ls="--")
        ax.set_xlim(lams[0], lams[-1])
        ax.text(-0.10, 1.02, lab, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=9, fontweight="bold")

    os.makedirs(OUT_DIR, exist_ok=True)
    png = os.path.join(OUT_DIR, f"{SLUG}.png")
    fig.savefig(png)
    upsert_manifest({
        "slug": SLUG, "png": png, "script": f"tools/report_figs/{SLUG}.py",
        "data_sources": ["analyze_blend_ratio.widen(compare_waist.waisted_model(3.0), λ), "
                         "λ 1.16~1.30 간격 0.002 (71 점)",
                         "conical.selector.select_cone(method='grid')",
                         "conical.exact_angle.select_uniform_exact"],
        "description": "λ 축에서 고른 균일각: 2° 격자는 점프 5회(인용된 24→32° 포함), 정확 탐색은 "
                       "1회만 남는다(구조적 점프). (b) 격자가 잃는 J 가 경쟁 계단 차보다 크다",
        "key_numbers": {"grid_jumps": jg, "exact_jumps": je,
                        "grid_jump_count": len(jg), "exact_jump_count": len(je),
                        "exact_angle_range_deg": [round(float(E.min()), 3),
                                                  round(float(E.max()), 3)],
                        "J_loss_median": round(float(np.median(loss)), 4),
                        "J_loss_max": round(float(loss.max()), 4), "k": k},
    })
    print(png, len(jg), len(je), je, round(float(np.median(loss)), 4), round(float(loss.max()), 4))


if __name__ == "__main__":
    main()
