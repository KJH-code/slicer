"""dof_ladder — 자유도 사다리: 평면 → 균일 원뿔 → 밴드 → 원뿔족 천장 → 곡면(S4, 추가 예정).

값: compare_ceiling.run_model (해석식 서포트 면적 %, k 없음 = 순수 성능). 모델: compare_ceiling.demo_models().
S4 칸은 비워 둔다(docs/s4_comparison.md 실행 전).
"""

import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from compare_ceiling import demo_models, run_model  # noqa: E402
from tools.report_figs.style import COLORS, figure, save, setup  # noqa: E402

KO = {"sphere": "구", "funnel": "깔때기", "sphere+stalk": "구+줄기", "mushroom": "버섯",
      "two-spheres": "구 두 개", "torus": "토러스"}
STEPS = [("baseline", "평면 (0°)", "0.6"), ("uniform", "균일 원뿔", COLORS[0]),
         ("banded", "밴드 계획", COLORS[2]), ("ceiling", "원뿔족 천장", COLORS[3])]


def main():
    setup()
    with contextlib.redirect_stdout(io.StringIO()):
        rows = [run_model(n, m) for n, m in demo_models().items()]
    fig, ax = figure("full", 7.0)
    x = np.arange(len(rows))
    w = 0.16
    for i, (k, lab, c) in enumerate(STEPS):
        vals = [r[k] for r in rows]
        ax.bar(x + (i - 2) * w, vals, w, color=c, label=lab, lw=0)
        for xi, v in zip(x + (i - 2) * w, vals, strict=True):
            ax.text(xi, v + 0.4, f"{v:.1f}" if v >= 0.05 else "0", ha="center", va="bottom",
                    fontsize=5.5, rotation=90)
    # S4 빈 칸
    ymax = max(r["baseline"] for r in rows)
    for xi in x:
        ax.bar(xi + 2 * w, ymax * 0.06, w, fill=False, ec="0.5", ls=":", lw=0.8,
               label="곡면 S4 (추가 예정)" if xi == 0 else None)
        ax.text(xi + 2 * w, ymax * 0.07, "?", ha="center", va="bottom", fontsize=7, color="0.4")
    ax.set_xticks(x)
    ax.set_xticklabels([KO[r["name"]] for r in rows])
    ax.set_ylabel("남은 서포트 면적 (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(ncols=5, loc="upper center", fontsize=7.5, bbox_to_anchor=(0.5, 1.13))
    ax.set_ylim(0, ymax * 1.15)
    txt = "; ".join(f"{KO[r['name']]} {r['baseline']:.1f}→{r['uniform']:.1f}→{r['banded']:.1f}→"
                    f"{r['ceiling']:.1f}%" for r in rows)
    save(fig, "dof_ladder", __file__, ["compare_ceiling.py", "conical/bandplan.py",
                                       "conical/clusters.py", "conical/analytic.py"],
         "데모 6 모델의 남은 서포트 면적(해석식): 평면 → 균일 원뿔(최선) → 밴드 계획 → 원뿔족 천장(클러스터별 자유 각). "
         "곡면(S4) 칸은 빈 자리",
         txt + " (평면→균일→밴드→천장)",
         extra={"pending": "곡면(S4) 칸 추가 예정 — docs/s4_comparison.md",
                "numbers": {r["name"]: {k: r[k] for k in ("baseline", "uniform", "banded", "ceiling")}
                            for r in rows}})
    print(txt)


if __name__ == "__main__":
    main()
