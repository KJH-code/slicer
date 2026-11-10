"""k_sweep — k 별 자동 균일·밴드2 의 후회 중앙값(고정각 수평선과 함께)과 고른 균일각.

    python3 tools/report_figs/k_sweep.py [--json k_sweep_results.json]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

FIX_COL = {"15": TAB10[0], "20": TAB10[1], "25": TAB10[2], "45": TAB10[3]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "k_sweep_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    ks = [float(k) for k in d["meta"]["ks"]]
    xs = np.arange(len(ks))
    fig, axes = plt.subplots(2, 3, figsize=(FULL_W, 10.5 / 2.54))
    key_numbers = {}
    labels = "abcdef"
    for r, cap in enumerate(("none", "cap")):
        for c, lh in enumerate(("0.3", "0.4")):
            ax = axes[r, c]
            cell = d["cells"][f"{lh}|{cap}"]
            for a, v in cell["fixed_regret_median"].items():
                if v is None:
                    continue
                ax.axhline(v, color=FIX_COL[a], ls=":", lw=0.9)
                ax.text(len(ks) - 0.6, v, f"{a}°", color=FIX_COL[a], fontsize=7, va="center")
            yu = [cell["by_k"][f"{k:g}"]["uniform"]["regret_median"] for k in ks]
            yb = [cell["by_k"][f"{k:g}"]["band2"]["regret_median"] for k in ks]
            ax.plot(xs, yu, "o-", color=TAB10[4], ms=3, label="자동 균일(J)")
            ax.plot(xs, yb, "s--", color=TAB10[5], ms=3, label="자동 밴드2")
            for k, y in zip(ks, yu, strict=True):
                key_numbers[f"{lh}|{cap}:k{k:g}:uniform_regret_median"] = round(y, 1)
            ax.set_xticks(xs)
            ax.set_xticklabels([f"{k:g}" for k in ks], rotation=45, fontsize=7)
            ax.set_xlim(-0.4, len(ks) - 0.1)
            ax.set_yscale("symlog", linthresh=1.0)
            ax.set_ylim(bottom=0)
            ax.set_xlabel("k (%p/°)")
            ax.set_ylabel(f"후회 중앙값 (mm, 층고 {lh})")
            tag = "상한 없음" if cap == "none" else "상한 22.79°"
            panel_label(ax, f"({labels[r * 3 + c]}) 층고 {lh} · {tag}")
            if r == 0 and c == 0:
                ax.legend(loc="lower left", frameon=False)
        ax = axes[r, 2]
        cell = d["cells"][f"0.4|{cap}"]
        th = np.array([cell["by_k"][f"{k:g}"]["uniform_theta_list"] for k in ks])
        q1, med, q3 = np.percentile(th, [25, 50, 75], axis=1)
        ax.fill_between(xs, q1, q3, color=TAB10[4], alpha=0.2, lw=0)
        ax.plot(xs, med, "o-", color=TAB10[4], ms=3, label="자동 균일 각 (중앙·사분위)")
        for lh, ls in (("0.3", "--"), ("0.4", ":")):
            o = np.median(d["cells"][f"{lh}|{cap}"]["oracle_theta_list"])
            ax.axhline(o, color="0.3", ls=ls, lw=0.9, label=f"사후 최적 중앙 (층고 {lh})")
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{k:g}" for k in ks], rotation=45, fontsize=7)
        ax.set_xlabel("k (%p/°)")
        ax.set_ylabel("각도 (°)")
        ax.set_ylim(-46, 46)
        panel_label(ax, f"({labels[r * 3 + 2]}) 고른 균일각 · "
                    + ("상한 없음" if cap == "none" else "상한 22.79°"))
        if r == 0:
            ax.legend(loc="lower left", frameon=False, fontsize=7)
        for k, m in zip(ks, med, strict=True):
            key_numbers[f"{cap}:k{k:g}:uniform_theta_median"] = float(m)
    fig.tight_layout()
    save(fig, "k_sweep", __file__, [os.path.relpath(args.json, ROOT), "docs/test_k_sweep.md"],
         "k 스윕: 자동 균일·밴드2 후회 중앙값(점선 = 고정 15·20·25·45° 후회 중앙값)과 고른 균일각, "
         "21 모델, 층고 0.3/0.4, 베드 상한 유무", key_numbers)


if __name__ == "__main__":
    main()
