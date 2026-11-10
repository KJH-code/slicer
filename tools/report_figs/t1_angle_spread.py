"""t1_angle_spread — 모델별 사후 최적 균일각 분포 + 관례 각도 세로선. (a) 층고 0.3 (b) 층고 0.4.

    python3 tools/report_figs/t1_angle_spread.py [--json t1_conventional_results.json]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

CONVENTIONAL = (15, 20, 25, 45)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "t1_conventional_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    lhs = [f"{lh:g}" for lh in d["meta"]["layer_heights"]]
    fig, axes = plt.subplots(1, len(lhs), figsize=(FULL_W, 5.5 / 2.54), sharey=True)
    key_numbers = {}
    bins = np.arange(-46, 48, 2) - 1
    for ax, lh, lab in zip(axes, lhs, "(a) (b)".split(), strict=True):
        ang = np.array(d["summary"][f"{lh}|none"]["oracle_angles"])
        auto = np.array([float(p["arms"]["auto_uniform"]["theta"])
                         for p in d["summary"][f"{lh}|none"]["per_model"]])
        lo = min(-2, ang.min() - 2, auto.min() - 2)
        b = bins[(bins >= lo - 2)]
        ax.hist(ang, bins=b, color=TAB10[0], alpha=0.8, label="사후 최적 균일각",
                edgecolor="white", linewidth=0.5)
        ax.hist(auto, bins=b, histtype="step", color=TAB10[1], linewidth=1.2,
                label="자동 균일(J)")
        for i, c in enumerate(CONVENTIONAL):
            ax.axvline(c, color="0.3", linestyle=(0, (3, 2)), linewidth=0.8)
            ax.text(c, 1.0, f"{c}°", transform=ax.get_xaxis_transform(), ha="center",
                    va="bottom", fontsize=6.5, color="0.3")
            del i
        ax.axvline(22.79, color=TAB10[3], linewidth=0.8)
        ax.text(22.79, 0.6, "B_safe ", rotation=90, transform=ax.get_xaxis_transform(), fontsize=7,
                color=TAB10[3], ha="right", va="center")
        ax.set_xlabel("균일 원뿔각 θ (°)")
        ax.yaxis.get_major_locator().set_params(integer=True)
        panel_label(ax, f"{lab} 층고 {lh} mm")
        key_numbers[f"{lh}:oracle_median_deg"] = float(np.median(ang))
        key_numbers[f"{lh}:oracle_range_deg"] = [float(ang.min()), float(ang.max())]
        key_numbers[f"{lh}:n_models"] = int(len(ang))
    axes[0].set_ylabel("모델 수")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2,
               frameon=False, bbox_to_anchor=(0.5, 0.0))
    save(fig, "t1_angle_spread", __file__,
         [os.path.relpath(args.json, ROOT), "docs/test_t1_t4.md"],
         "T1: 모델별 사후 최적 균일각(미지지 mm 최소, 베드 상한 없음) 분포와 관례 고정각(15·20·25·45°)",
         key_numbers)


if __name__ == "__main__":
    main()
