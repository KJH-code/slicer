"""t6_effective_overhang — 증명 A 검산: 실제 원뿔 층 법선으로 잰 유효 오버행 대 '원래 − θ'.

원자료: results/t6_proofs_ae_points.npz (tools/check_proofs_ae.py, 무작위 회전체 10 개).
    python3 tools/report_figs/t6_effective_overhang.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import FULL, ROOT, TAB, panel, plt, save, setup  # noqa: E402

SLUG = "t6_effective_overhang"


def main():
    setup()
    d = np.load(ROOT / "results" / "t6_proofs_ae_points.npz")
    pred = d["a1_w0"] - d["a1_theta"]
    weff = d["a1_weff"]
    diff1 = weff - pred
    diff2 = d["a2_weff"] - d["a2_wg"]
    rng = np.random.default_rng(0)
    show = rng.choice(len(pred), size=min(6000, len(pred)), replace=False)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FULL, 7.0 / 2.54),
                                   gridspec_kw={"wspace": 0.35})
    lim = (min(pred.min(), weff.min()) - 3, max(pred.max(), weff.max()) + 3)
    ax1.plot(lim, lim, color="0.3", lw=0.8, ls="--", label="y = x")
    ax1.scatter(pred[show], weff[show], s=3, lw=0, alpha=0.5, color=TAB[0],
                label=f"표본 {len(show):,}/{len(pred):,}")
    ax1.set_xlim(lim)
    ax1.set_ylim(lim)
    ax1.set_aspect("equal")
    ax1.set_xlabel("원래 오버행 − θ (°)")
    ax1.set_ylabel("실제 층 법선으로 잰 유효 오버행 (°)")
    ax1.legend(loc="upper left", frameon=False, markerscale=3)
    panel(ax1, "(a)")

    ax2.scatter(pred[show], diff1[show] * 1e7, s=3, lw=0, alpha=0.5, color=TAB[0],
                label="경선 법선: 측정 − (원래 − θ)")
    sh2 = rng.choice(len(diff2), size=min(6000, len(diff2)), replace=False)
    ax2.scatter(d["a2_wg"][sh2], diff2[sh2] * 1e7, s=3, lw=0, alpha=0.5, color=TAB[1],
                label="메시 전 면: 측정 − g(θ) 식")
    ax2.axhline(0, color="0.3", lw=0.6)
    ax2.set_ylim(-1.9, 2.1)
    ax2.set_xlabel("예측 유효 오버행 (°)")
    ax2.set_ylabel("차이 (×10⁻⁷ °)")
    mx = float(max(np.abs(diff1).max(), np.abs(diff2).max()))
    ax2.text(0.98, 0.03, f"최대 |차이| {mx:.1e}°\n(사전 기준 0.01°)",
             transform=ax2.transAxes, ha="right", va="bottom", fontsize=7.5)
    ax2.legend(loc="upper left", frameon=False, markerscale=3, fontsize=7.5)
    panel(ax2, "(b)")
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.17, top=0.92)
    print(save(fig, SLUG))
    return {"n_meridian": int(len(pred)), "n_mesh_faces": int(len(diff2)),
            "max_abs_diff_deg": mx}


if __name__ == "__main__":
    print(main())
