"""t3_nstar_hist — 포화 N* 분포 (목적 ①·② × 층고 0.3·0.4). 데이터: t3_band_optimum_results.json."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from _style import HALF, ROOT, TAB10, plt, save, setup

KEYS = [("obj1_0.3", "① 서포트 최소, 0.3mm"), ("obj1_0.4", "① 서포트 최소, 0.4mm"),
        ("obj2_0.3", "② 같은 서포트·각 최소, 0.3mm"), ("obj2_0.4", "② 같은 서포트·각 최소, 0.4mm")]
CATS = ["1", "2", "3", ">=4"]


def main():
    setup()
    src = ROOT / "t3_band_optimum_results.json"
    s = json.loads(src.read_text())
    fig, ax = plt.subplots(figsize=(HALF, 6.0 / 2.54))
    w = 0.2
    for i, (k, lab) in enumerate(KEYS):
        t = s["nstar_tally"][k]
        ax.bar(np.arange(4) + (i - 1.5) * w, [t.get(c, 0) for c in CATS], w,
               color=TAB10[i], label=lab)
    ax.set_xticks(range(4))
    ax.set_xticklabels(["1", "2", "3", "≥4"])
    ax.set_xlabel("포화 밴드 수 N*")
    ax.set_ylabel(f"모델 수 (총 {s['models']}개)")
    ax.legend(frameon=False, fontsize=6)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    save(fig, "t3_nstar_hist", __file__, [str(src.relative_to(ROOT))],
         "포화 N* (N→N+1 에서 미지지 감소<0.5mm 그리고 평균|θ| 감소<1° 인 첫 N) 의 분포",
         {k: s["nstar_tally"][k] for k, _ in KEYS})


if __name__ == "__main__":
    main()
