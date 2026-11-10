"""s4_runtime — 모델별 실행 시간 (로그축): 원뿔 각도 결정 vs S4 단계별.

데이터: s4_comparison_results.json 의 대표 실행(R2·P1, 없으면 R1·P1).
원뿔 쪽 = 같은 사면체 표면에서 균일 최선 탐색·밴드 계획·천장 계산 시간(conical 함수).
S4 쪽 = 사면체화(tetgen) · 속성 계산(이웃·경로 — 셀 2 의 나머지) · 회전장 최적화 · 변형 최적화.
같은 컨테이너에서 한 번씩 잰 벽시계 시간이라 자릿수 비교용이다.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import _style as st  # noqa: E402
from s4_dof_ladder import MODELS, NAMES, pick  # noqa: E402

BARS = [("cone", "원뿔 각도 결정 (균일+밴드+천장)"),
        ("tetgen", "S4: 사면체화"),
        ("attr", "S4: 속성·이웃 계산"),
        ("rot", "S4: 회전장 최적화"),
        ("def", "S4: 변형 최적화")]


def times(r):
    c, t = r["cone"], r["times_s"]
    return {"cone": c["t_uniform_s"] + c["t_banded_s"] + c["t_ceiling_s"],
            "tetgen": t["tetgen"],
            "attr": t["tet_and_attributes"] - t["tetgen"],
            "rot": t["rotation_field"], "def": t["deformation"]}


def main():
    st.setup()
    rows = json.load(open(os.path.join(st.ROOT, "s4_comparison_results.json"), encoding="utf-8"))
    models = [m for m in MODELS if pick(rows, m)]
    fig, ax = st.plt.subplots(figsize=(st.FULL, 6.0 * st.CM))
    x = np.arange(len(models))
    w = 0.16
    key = {}
    for i, (k, name) in enumerate(BARS):
        vals = [times(pick(rows, m))[k] for m in models]
        ax.bar(x + (i - 2) * w, vals, w, label=name, color=st.TAB10[i])
        for m, v in zip(models, vals, strict=True):
            key[f"{m}.{k}_s"] = round(float(v), 2)
    for m in models:
        r = pick(rows, m)
        tt = times(r)
        key[f"{m}.s4_total_s"] = round(sum(v for k, v in tt.items() if k != "cone"), 1)
        key[f"{m}.n_tets"] = r["n_tets"]
        key[f"{m}.res"] = r["res"]
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(st.plt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xticks(x)
    ax.set_xticklabels([f"{NAMES[m]}\n({pick(rows, m)['n_tets']:,} 사면체)" for m in models])
    ax.set_ylabel("실행 시간 (s, 로그축)")
    ax.set_xlabel("모델 (대표 해상도)")
    ax.grid(axis="y", which="both", alpha=0.3, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(ncol=3, frameon=False, loc="upper left", bbox_to_anchor=(0, 1.22))
    fig.tight_layout()
    st.save(fig, "s4_runtime", __file__, ["s4_comparison_results.json"],
            "모델별 실행 시간(로그축): 원뿔 각도 결정(conical, 같은 표면) vs S4 단계별"
            "(사면체화/속성/회전장/변형), 같은 컨테이너 벽시계", key)


if __name__ == "__main__":
    main()
