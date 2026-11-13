"""baseline_bars — 축대칭 17 모델의 미지지 길이(mm, 툴패스 검사기 A, 낙관):
균일(J 최선) · 밴드2 · 균일(밴드2 아랫각) 3막대, 층고 0.3 / 0.4 두 패널.

데이터: gap_sample_results.json 의 by_layer_height (docs/gap_audit.md §9.3 '베드 상한 없음' 표와
gapdata.check 로 대조 — 다르면 멈춘다).
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

TIE = 0.5   # meta.mm_tie_tolerance


def tally(rows, a, b):
    w = sum(r[b] < r[a] - TIE for r in rows)      # b 가 더 짧으면 b 우세
    lo = sum(r[b] > r[a] + TIE for r in rows)
    return w, lo, len(rows) - w - lo


def main():
    setup()
    data = gapdata.load()
    n_checked = gapdata.check(data)
    fig, axs = figure("full", 13.0, ncols=2, sharey=True)
    keys = [("uJ_mm", "균일 (J 최선)", COLORS[0]), ("b2_mm", "밴드2", COLORS[3]),
            ("ub_mm", "균일 (밴드2 아랫각)", COLORS[2])]
    summary = {}
    for ax, lh, letter in ((axs[0], "0.3", "a"), (axs[1], "0.4", "b")):
        rows = data[lh]
        y = np.arange(len(rows))[::-1]
        h = 0.27
        for i, (k, lab, c) in enumerate(keys):
            vals = [r[k] for r in rows]
            ax.barh(y + (1 - i) * h, vals, h, color=c, label=lab if letter == "a" else None, lw=0)
            for yy, v in zip(y + (1 - i) * h, vals, strict=True):
                if v < 0.05:
                    ax.text(0, yy, " 0", color=c, fontsize=6, va="center", ha="left")
        ax.set_yticks(y)
        ax.set_yticklabels([r["model"] for r in rows], fontsize=7.5)
        ax.set_xlabel(f"미지지 길이 (mm), 층고 {lh} mm")
        ax.grid(axis="y", visible=False)
        panel_label(ax, letter)
        a = tally(rows, "uJ_mm", "b2_mm")
        b = tally(rows, "ub_mm", "b2_mm")
        summary[lh] = {"band2_vs_uniformJ": a, "band2_vs_uniform_bottom": b}
        ax.set_xlim(0, {"0.3": 72, "0.4": 480}[lh])
        ax.text(0.97, {"0.3": 0.39, "0.4": 0.5}[lh], f"밴드2 대 균일(J): {a[0]}승 {a[1]}패 {a[2]}무\n"
                f"밴드2 대 균일(아랫각): {b[0]}승 {b[1]}패 {b[2]}무\n(무승부 = 0.5mm 안)",
                transform=ax.transAxes, ha="right", va="center", fontsize=7.5,
                bbox={"fc": "white", "ec": "0.7", "lw": 0.5, "pad": 3})
    fig.legend(loc="outside lower center", ncols=3, fontsize=8)
    s3, s4 = summary["0.3"], summary["0.4"]
    save(fig, "baseline_bars", __file__, [gapdata.JSON, gapdata.DOC],
         "축대칭 17 모델의 미지지 길이(툴패스 검사기 A, 낙관): 균일(J 최선)·밴드2·균일(밴드2 아랫각), 층고 0.3/0.4",
         f"밴드2 대 균일(J) 승·패·무: 0.3 {s3['band2_vs_uniformJ']} / 0.4 {s4['band2_vs_uniformJ']}; "
         f"밴드2 대 균일(아랫각): 0.3 {s3['band2_vs_uniform_bottom']} / 0.4 {s4['band2_vs_uniform_bottom']} "
         f"(gap_audit §9.3 표 {n_checked}행과 대조 일치)",
         extra={"numbers": summary})
    print(summary)


if __name__ == "__main__":
    main()
