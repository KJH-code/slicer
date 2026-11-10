"""band_vs_radius — 그림 D: 밴드 경계를 반경이 작은 곳(허리)으로 옮기는 이유 (식 (5)).

패널마다 모델 반경 R(z)(왼쪽 축, 회색 채움), 고른 θ(Z′)(오른쪽 축, 선), 블렌드 구간(음영),
r* = (m_max − 1)/|s| (블렌드 안 기울기 s 의 층간격 한계 반경, 점선), 등분 경계(옮기기 전, 세로 점선).
데이터: band_boundary_results.json 의 "figd" (`analyze_band_boundary.py --part figd`).

    python3 tools/report_figs/band_vs_radius.py
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

ORDER = ("램프", "허리 r=3", "torus", "구")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "band_boundary_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))["figd"]
    fig, axes = plt.subplots(1, 4, figsize=(FULL_W, 6.4 / 2.54))
    key_numbers = {}
    for ax, name, lab in zip(axes, ORDER, "abcd", strict=True):
        m = d[name]
        z, r = (np.asarray(a) for a in m["R_z"])
        ax.fill_between(z, 0, r, color="0.85", linewidth=0, step="mid")
        ax.plot(z, r, color="0.45", linewidth=0.8, drawstyle="steps-mid", label="반경 R(z)")
        ax.axvline(m["edges"][1], color="0.3", linestyle=":", linewidth=0.8, label="등분 경계")
        ax2 = ax.twinx()
        zq, th = (np.asarray(a) for a in m["theta_z"])
        ax2.plot(zq, th, color=TAB10[3], linewidth=1.3, label="θ(Z′)")
        ax2.set_ylim(-2, 46)
        ax2.spines["right"].set_visible(True)
        ax2.grid(False)
        if name == ORDER[-1]:
            ax2.set_ylabel("θ (°)", color=TAB10[3])
        else:
            ax2.set_yticklabels([])
        kn = {"thetas": m["thetas"], "edge_mm": round(m["edges"][1], 2)}
        for b in m["blends"]:
            ax.axvspan(b["lo"], b["hi"], color=TAB10[0], alpha=0.18, linewidth=0)
            ax.hlines(b["r_star"], b["lo"] - 1.5, b["hi"] + 1.5, color=TAB10[0],
                      linestyle="--", linewidth=1.0)
            ax.annotate(f"r*={b['r_star']:.1f}\nw={b['w']:.1f}mm",
                        (b["hi"] + 0.5, b["r_star"]), fontsize=7, color=TAB10[0],
                        va="bottom")
            kn.update({"blend_mm": [round(b["lo"], 2), round(b["hi"], 2)],
                       "w_mm": round(b["w"], 2), "r_star_mm": round(b["r_star"], 2),
                       "r_at_edge_mm": round(b["r_at_edge"], 2),
                       "w_at_edge_lb_mm": round(b["w_needed_at_edge_lower_bound"], 2)})
        if not m["blends"]:
            ax.text(0.5, 0.95, f"밴드 안 씀\n(균일 {m['thetas'][0]:.0f}°)",
                    transform=ax.transAxes, ha="center", va="top", fontsize=7)
        th_s = "→".join(f"{t:.0f}°" for t in m["thetas"])
        ax.set_title(f"{name}  [{th_s}]")
        ax.set_xlabel("z (mm)")
        ax.set_xlim(m["z0"], m["z1"])
        ax.set_ylim(0, max(r.max() * 1.15, 1))
        if name == ORDER[0]:
            ax.set_ylabel("반경 R (mm)")
        panel_label(ax, f"({lab})")
        key_numbers[name] = kn
    h1, l1 = axes[0].get_legend_handles_labels()
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    h1 += [Line2D([], [], color=TAB10[3], linewidth=1.3),
           Patch(color=TAB10[0], alpha=0.25),
           Line2D([], [], color=TAB10[0], linestyle="--")]
    l1 += ["θ(Z′)", "블렌드", "r* = (m_max−1)/|s|"]
    fig.legend(h1, l1, loc="lower center", ncol=5, frameon=False,
               bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    mode = d[ORDER[0]]["mode"]
    save(fig, "band_vs_radius", __file__, ["band_boundary_results.json#figd"],
         f"그림 D: 모델 반경 R(z), 고른 θ(Z′), 블렌드 위치·폭, r*. 경계 판 = {mode}. "
         "블렌드 폭 w ≥ r_b·|Δtanθ|/(m_max−1) (식 (5)) 라 반경이 작은 높이에 둘수록 좁다.",
         key_numbers)


if __name__ == "__main__":
    sys.exit(main())
