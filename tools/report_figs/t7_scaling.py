"""t7_scaling — 면 수 대 각도 결정 시간 (로그-로그), 최대 RSS 보조축. 데이터: t7_scaling_results.json."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import FULL, ROOT, TAB10, plt, save, setup
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

LABEL = {"sphere": "구", "waist_r3": "허리 r=3", "uniform": "균일각 결정", "band2": "밴드2 계획"}


def main():
    setup()
    src = ROOT / "t7_scaling_results.json"
    d = json.loads(src.read_text())
    t = d["table"]
    fig, ax = plt.subplots(figsize=(FULL, 7.0 / 2.54))
    ax2 = ax.twinx()
    for ci, (model, task) in enumerate([("sphere", "uniform"), ("sphere", "band2"),
                                        ("waist_r3", "uniform"), ("waist_r3", "band2")]):
        rs = sorted([r for r in t if r["model"] == model and r["task"] == task],
                    key=lambda r: r["faces"])
        f = [r["faces"] for r in rs]
        ax.plot(f, [r["median_s"] for r in rs], color=TAB10[ci], marker="o", ms=3,
                label=f"{LABEL[model]} · {LABEL[task]} 시간")
        ax2.plot(f, [r["maxrss_mb"] for r in rs], color=TAB10[ci], marker="s", ms=2.5,
                 ls=":", lw=0.8, label=f"{LABEL[model]} · {LABEL[task]} 메모리")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax2.set_yscale("log")
    fmt = FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}")
    for a in (ax.xaxis, ax.yaxis, ax2.yaxis):
        a.set_major_formatter(fmt)
        a.set_minor_formatter(NullFormatter())
    ax2.yaxis.set_major_locator(FixedLocator([150, 200, 300, 400, 600, 800]))
    ax.set_xlabel("메시 면 수 (개)")
    ax.set_ylabel("계산 시간 (s)")
    ax2.set_ylabel("프로세스 최대 RSS (MB, 점선)")
    ax.grid(alpha=0.3, which="both")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, ncol=2, fontsize=6, loc="upper left")
    fig.tight_layout()
    big = {f"{r['model']}_{r['task']}_{r['faces']}": round(r["median_s"], 3) for r in t}
    save(fig, "t7_scaling", __file__, [str(src.relative_to(ROOT))],
         f"면 수 1k~1.3M 에서 균일각 결정·밴드2 계획 시간과 메모리 (단일 프로세스, "
         f"{d['machine']['cores']} 코어 머신)", {"시간_s": big})


if __name__ == "__main__":
    main()
