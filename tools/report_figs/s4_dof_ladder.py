"""s4_dof_ladder — 모델별 평면/균일/밴드/원뿔족 천장/곡면(S4) 서포트 면적 (같은 판정식).

데이터: s4_comparison_results.json (tools/s4_compare.py 출력). 막대 = 대표 실행
(R2·P1, 없으면 R1·P1). S4 막대의 수염 = R1/R2 × P1/P2 네 실행의 최소~최대.
(a) 1차 지표(저장소 규칙, 바닥면 포함)  (b) 베드 접촉면 제외(모든 열 같은 규칙).
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import _style as st  # noqa: E402

MODELS = ["sphere", "funnel", "torus", "mushroom", "lamp"]
NAMES = {"sphere": "구", "funnel": "깔때기", "torus": "토러스", "mushroom": "버섯",
         "lamp": "램프"}
COLS = [("planar", "평면"), ("uniform", "균일 원뿔"), ("banded", "밴드"),
        ("ceiling", "원뿔족 천장"), ("s4", "곡면 (S4)")]


def pick(rows, model):
    for res in ("R2", "R1"):
        for r in rows:
            if r["model"] == model and r["res"] == res and r["params"] == "P1" and r["ok"]:
                return r
    return None


def values(r, nobed):
    c = r["cone_nobed"] if nobed else r["cone"]
    v = {k: c[k] for k, _ in COLS[:4]}
    v["s4"] = r["s4_nobed"] if nobed else r["s4"]
    return v


def main():
    st.setup()
    path = os.path.join(st.ROOT, "s4_comparison_results.json")
    rows = json.load(open(path, encoding="utf-8"))
    models = [m for m in MODELS if pick(rows, m)]
    fig, axes = st.plt.subplots(1, 2, figsize=(st.FULL, 6.2 * st.CM), sharey=True)
    key = {}
    for ax, nobed, lab in ((axes[0], False, "a"), (axes[1], True, "b")):
        x = np.arange(len(models))
        w = 0.16
        for i, (k, name) in enumerate(COLS):
            vals = [values(pick(rows, m), nobed)[k] for m in models]
            ax.bar(x + (i - 2) * w, vals, w, label=name, color=st.TAB10[i])
            if k == "s4":
                lo, hi = [], []
                for m in models:
                    rr = [r for r in rows if r["model"] == m and r["ok"]
                          and r["params"] in ("P1", "P2")]
                    s = [r["s4_nobed"] if nobed else r["s4"] for r in rr]
                    lo.append(min(s))
                    hi.append(max(s))
                vals = np.array(vals)
                ax.errorbar(x + (i - 2) * w, vals, yerr=[vals - np.array(lo), np.array(hi) - vals],
                            fmt="none", ecolor="k", elinewidth=0.7, capsize=1.5)
            if not nobed:
                for m, v in zip(models, vals, strict=True):
                    key[f"{m}.{k}_pct"] = round(float(v), 1)
        ax.set_xticks(x)
        ax.set_xticklabels([NAMES[m] for m in models])
        ax.set_ylabel("서포트가 필요한 표면 넓이 (%)" if not nobed else "")
        ax.set_xlabel("모델")
        ax.grid(axis="y", alpha=0.3, linewidth=0.5)
        ax.set_axisbelow(True)
        st.panel(ax, lab)
    axes[0].legend(ncol=1, frameon=False, loc="upper right")
    fig.tight_layout()
    st.save(fig, "s4_dof_ladder", __file__, ["s4_comparison_results.json"],
            "모델별 평면→균일 원뿔→밴드→원뿔족 천장→곡면(S4) 서포트 넓이, g=n·d<−sin45° 같은 판정식;"
            " (a) 바닥면 포함 (b) 베드 접촉면 제외; S4 수염=해상도·파라미터 4실행 범위", key)


if __name__ == "__main__":
    main()
