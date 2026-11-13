"""t2_spacing — 증명 B 검산: G-code 에서 잰 층간격 대 예측 h − c·r·Δtanθ.

원자료: results/t2_layer_spacing_pairs.npz (tools/check_layer_spacing.py 가 만든 쌍별 값).
    python3 tools/report_figs/t2_spacing.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import FULL, ROOT, TAB, panel, plt, save, setup  # noqa: E402

SLUG = "t2_spacing"


def main():
    setup()
    d = np.load(ROOT / "results" / "t2_layer_spacing_pairs.npz")
    meas, pred, ctrl = d["meas"].astype(float), d["pred"].astype(float), d["ctrl"]
    rho = meas / pred
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FULL, 6.4 / 2.54 * 1.25),
                                   gridspec_kw={"wspace": 0.32})

    lo, hi = 0.18, 0.62
    ax1.plot([lo, hi], [lo, hi], color="0.3", lw=0.8, ls="--", zorder=1, label="y = x")
    ax1.scatter(pred[ctrl], meas[ctrl], s=14, color=TAB[1], alpha=0.8, lw=0, zorder=4,
                label=f"상수각 대조군 (n={int(ctrl.sum()):,})")
    ax1.scatter(pred[~ctrl], meas[~ctrl], s=2, color=TAB[0], alpha=0.35, lw=0, zorder=3,
                label=f"블렌드 프로필 (n={int((~ctrl).sum()):,})")
    ax1.set_xlim(lo, hi)
    ax1.set_ylim(lo, hi)
    ax1.set_aspect("equal")
    ax1.set_xlabel("예측 층간격 h − c·r·Δtanθ (mm)")
    ax1.set_ylabel("G-code 측정 층간격 (mm)")
    ax1.legend(loc="upper left", frameon=False, markerscale=3)
    panel(ax1, "(a)")

    edges = np.arange(0.975, 1.0251, 0.0005)
    ax2.axvspan(0.98, 1.02, color="0.9", zorder=0, label="기준 1±0.02")
    for mask, c, name in ((~ctrl, TAB[0], "블렌드"), (ctrl, TAB[1], "상수각")):
        ax2.hist(np.clip(rho[mask], edges[0], edges[-1]), bins=edges, density=True,
                 histtype="step", lw=1.2, color=c, label=name)
    ax2.set_xlim(edges[0], edges[-1])
    ax2.set_xlabel("측정 / 예측 (무차원)")
    ax2.set_ylabel("확률 밀도 (1/단위비)")
    out = int(((rho < 0.95) | (rho > 1.05)).sum())
    med = float(np.median(rho[~ctrl]))
    lo95, hi95 = np.percentile(rho[~ctrl], [2.5, 97.5])
    ax2.text(0.03, 0.62, f"블렌드\n중앙값 {med:.4f}\n95% [{lo95:.4f},\n         {hi95:.4f}]\n"
             f"±5% 밖 {out}쌍\n(양 끝 칸에 합침)", transform=ax2.transAxes, ha="left",
             va="top", fontsize=7.5)
    ax2.legend(loc="upper left", frameon=False, fontsize=7.5, handlelength=1.2)
    panel(ax2, "(b)")
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.17, top=0.93)
    print(save(fig, SLUG))
    return {"n_band": int((~ctrl).sum()), "n_ctrl": int(ctrl.sum()), "median_band": med,
            "p2_5_band": float(lo95), "p97_5_band": float(hi95), "n_outside_5pct": out}


if __name__ == "__main__":
    print(main())
