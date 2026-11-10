"""t3_band_curve — 밴드 수 N 의 최선해(목적 ①) 곡선: (a) 툴패스 미지지 mm, (b) 평균|θ|.

데이터: t3_band_optimum_results.json (analyze_t3_band_optimum.py --report).
N=4 는 제한 탐색(N=3 최선해 이웃)이라 점선으로 잇는다. 별표 = 포화 N*.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from _style import FULL, ROOT, TAB10, family, panel_label, plt, save, setup

LH = "0.3"
TAG = "obj1"


def main():
    setup()
    src = ROOT / "t3_band_optimum_results.json"
    s = json.loads(src.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 6.2 / 2.54))
    seen = set()
    rng = np.random.default_rng(0)
    for r in s["rows"]:
        fi, fname = family(r["model"])
        best = r["best"][TAG]
        ns = [n for n in (1, 2, 3, 4) if best.get(str(n))]
        mm = [best[str(n)]["mm"][LH] for n in ns]
        ang = [best[str(n)]["mean_abs_deg"] for n in ns]
        jit = rng.uniform(-0.06, 0.06)
        x = np.array(ns, dtype=float) + jit
        lab = fname if fname not in seen else None
        seen.add(fname)
        for ax, y in ((axes[0], mm), (axes[1], ang)):
            k = min(3, len(ns))
            ax.plot(x[:k], y[:k], color=TAB10[fi], lw=0.9, alpha=0.8, marker="o",
                    ms=2.5, label=lab if ax is axes[0] else None)
            if len(ns) == 4:
                ax.plot(x[2:], y[2:], color=TAB10[fi], lw=0.9, alpha=0.8, ls=":",
                        marker="o", ms=2.5)
            ns_star = r["nstar"].get(f"{TAG}_{LH}")
            if isinstance(ns_star, int) and ns_star in ns:
                i = ns.index(ns_star)
                ax.plot(x[i], y[i], marker="*", ms=7, color=TAB10[fi],
                        markeredgecolor="k", markeredgewidth=0.4, ls="none")
    axes[0].set_yscale("symlog", linthresh=1.0)
    axes[0].set_ylabel(f"툴패스 미지지 길이 (mm, 층고 {LH})")
    axes[1].set_ylabel("면적가중 평균 |θ| (°)")
    for ax, lab in zip(axes, ("(a)", "(b)"), strict=True):
        ax.set_xlabel("밴드 수 N (4 = 제한 탐색)")
        ax.set_xticks([1, 2, 3, 4])
        ax.grid(alpha=0.3)
        panel_label(ax, lab)
    axes[0].plot([], [], marker="*", ms=7, color="0.5", markeredgecolor="k",
                 markeredgewidth=0.4, ls="none", label="포화 N*")
    fig.tight_layout()
    fig.legend(*axes[0].get_legend_handles_labels(), ncol=6, frameon=False,
               loc="lower center", bbox_to_anchor=(0.5, 1.0))
    tally = s["nstar_tally"][f"{TAG}_{LH}"]
    a1 = [r["best"][TAG]["1"]["mean_abs_deg"] for r in s["rows"]]
    a3 = [r["best"][TAG]["3"]["mean_abs_deg"] for r in s["rows"] if r["best"][TAG].get("3")]
    save(fig, "t3_band_curve", __file__, [str(src.relative_to(ROOT)), "t3_search/", "t3_measure/"],
         "밴드 수 N 별 전수 탐색 최선해(서포트 최소, 동점 평균|θ|): 툴패스 미지지와 평균|θ|, 21 모델",
         {"N*_분포_층고0.3": tally,
          "평균|θ|_중앙값_N1": float(np.median(a1)), "평균|θ|_중앙값_N3": float(np.median(a3)),
          "단조성_위반": len(s["monotonic_violations"])})


if __name__ == "__main__":
    main()
