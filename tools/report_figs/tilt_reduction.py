"""tilt_reduction — 17 모델의 평균|θ|: 균일 → 밴드2 짝 점 그림 (층고 0.3, 사다리와 같은 층고).

(a) 균일(J 최선) → 밴드2, (b) 균일(밴드2 아랫각) → 밴드2. 미지지 길이가 0.5mm 안에서 같은
모델만 진하게(그 모델들의 감소량 중앙·범위를 표기). 평균|θ| 는 툴패스 검사기가 잰 값
(gap_sample_results.json 의 *.angle). docs/gap_audit.md §9.6 의 '중앙 8.4° (1.0 ~ 11.1°)' 는 (b) 기준.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.report_figs import gapdata  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    COLORS,
    figure,
    panel_label,
    save,
    setup,
)

TIE = 0.5
LH = "0.3"


def stats(rows, ref):
    tie = [abs(r["b2_mm"] - r[ref + "_mm"]) <= TIE for r in rows]
    red = np.array([r[ref + "_mean"] - r["b2_mean"] for r, t in zip(rows, tie, strict=True) if t])
    return tie, red


def main():
    setup()
    data = gapdata.load()
    gapdata.check(data)
    rows = data[LH]
    fig, axs = figure("full", 11.5, ncols=2, sharey=True)
    y = np.arange(len(rows))[::-1]
    nums = {}
    for ax, ref, lab, letter in ((axs[0], "uJ", "균일 (J 최선)", "a"),
                                 (axs[1], "ub", "균일 (밴드2 아랫각)", "b")):
        tie, red = stats(rows, ref)
        for yy, r, t in zip(y, rows, tie, strict=True):
            al = 1.0 if t else 0.3
            ax.plot([r[ref + "_mean"], r["b2_mean"]], [yy, yy], color="0.5", lw=1.0, alpha=al)
            ax.plot(r[ref + "_mean"], yy, "o", color=COLORS[0], ms=4, alpha=al)
            ax.plot(r["b2_mean"], yy, "o", color=COLORS[3], ms=4, alpha=al)
        ax.set_yticks(y)
        ax.set_yticklabels([r["model"] for r in rows], fontsize=7.5)
        ax.set_xlabel("평균 |θ| (°)")
        ax.set_xlim(8, 46)
        ax.grid(axis="y", visible=False)
        ax.text(0.98, 0.02, f"미지지 길이 같은 모델 {len(red)}/17\n감소 중앙 {np.median(red):.1f}° "
                f"({red.min():.1f}~{red.max():.1f}°)", transform=ax.transAxes, ha="right",
                va="bottom", fontsize=7.5, bbox={"fc": "white", "ec": "0.7", "lw": 0.5, "pad": 3})
        ax.plot([], [], "o", color=COLORS[0], ms=4, label=lab)
        ax.plot([], [], "o", color=COLORS[3], ms=4, label="밴드2")
        ax.legend(loc="center right", fontsize=7.5, bbox_to_anchor=(1.0, 0.47))
        panel_label(ax, letter)
        nums[ref] = {"n_tie": len(red), "median": float(np.median(red)),
                     "min": float(red.min()), "max": float(red.max())}
    # 층고 0.4 도 같이 기록
    for ref in ("uJ", "ub"):
        _, red = stats(data["0.4"], ref)
        nums[ref + "_lh0.4"] = {"n_tie": len(red), "median": float(np.median(red)),
                                "min": float(red.min()), "max": float(red.max())}
    a, b = nums["uJ"], nums["ub"]
    save(fig, "tilt_reduction", __file__, [gapdata.JSON, gapdata.DOC],
         "17 모델 평균|θ| 짝 점(층고 0.3): (a) 균일(J)→밴드2, (b) 균일(밴드2 아랫각)→밴드2. "
         "진한 점 = 미지지 길이가 0.5mm 안에서 같은 모델, 흐린 점 = 다른 모델",
         f"(a) 같은 미지지 {a['n_tie']}/17, 감소 중앙 {a['median']:.1f}° ({a['min']:.1f}~{a['max']:.1f}°); "
         f"(b) {b['n_tie']}/17, 중앙 {b['median']:.1f}° ({b['min']:.1f}~{b['max']:.1f}°) — 문서 8.4°(1.0~11.1°) 와 일치는 (b)",
         extra={"numbers": nums})
    print(nums)


if __name__ == "__main__":
    main()
