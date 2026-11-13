"""t6_cone_approx — 증명 E(iii): 곡면 층 z = Z′ − a·r − b·r² 와 접하는 원뿔의 높이 오차.

원자료: results/t6_proofs_ae_points.npz 의 E_* 배열 (tools/check_proofs_ae.py, a = tan20°).
    python3 tools/report_figs/t6_cone_approx.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import FULL, ROOT, TAB, log_ticks, panel, plt, save, setup  # noqa: E402

SLUG = "t6_cone_approx"
BS = (0.002, 0.01, 0.05)


def main():
    setup()
    d = np.load(ROOT / "results" / "t6_proofs_ae_points.npz")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FULL, 7.0 / 2.54),
                                   gridspec_kw={"wspace": 0.3})
    r = d["E_sec_r"]
    rr = np.concatenate([-r[::-1], r])

    def mirror(v):
        return np.concatenate([v[::-1], v])
    b = float(d["E_sec_b"])
    ax1.plot(rr, mirror(d["E_sec_layer"]), color="k", lw=1.6, label=f"곡면 층 (b = {b:g} /mm)")
    ax1.plot(rr, mirror(d["E_sec_cone_axis"]), color=TAB[0], lw=1.2, ls="--",
             label="축에서 접하는 원뿔")
    ax1.plot(rr, mirror(d["E_sec_cone_r8"]), color=TAB[1], lw=1.2, ls="--",
             label="r = 8 mm 에서 접하는 원뿔")
    z8 = np.interp(8.0, r, d["E_sec_layer"])
    ax1.plot([-8, 8], [z8, z8], "o", ms=3.5, color=TAB[1])
    ax1.set_xlabel("r (mm)")
    ax1.set_ylabel("z (mm)")
    ax1.legend(loc="lower center", frameon=False)
    panel(ax1, "(a)")

    x = d["E_e1_r"]
    slopes = {}
    for bb, c in zip(BS, TAB[:3], strict=True):
        e = d[f"E_e1_err_b{bb}"]
        slopes[bb] = float(np.polyfit(np.log(x), np.log(e), 1)[0])
        ax2.plot(x, e, "o-", ms=2.5, lw=0.9, color=c,
                 label=f"{bb:g} (기울기 {slopes[bb]:.3f})")
    ref = 1e-5 * (x / x[0]) ** 2
    ax2.plot(x, ref, color="0.4", lw=0.9, ls="--", label="기울기 2 기준")
    ax2.axhline(0.3, color="0.4", lw=0.7, ls=":")
    ax2.text(0.11, 0.38, "층고 0.3 mm", fontsize=7.5, color="0.3")
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    log_ticks(ax2)
    ax2.set_xlabel("접점(축)에서의 거리 r (mm)")
    ax2.set_ylabel("높이 오차 |z층 − z원뿔| (mm)")
    ax2.legend(loc="lower right", frameon=False, fontsize=7, title="b (/mm)",
               title_fontsize=7, handlelength=1.4, borderaxespad=0.2)
    panel(ax2, "(b)")
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.17, top=0.92)
    print(save(fig, SLUG))
    return {"loglog_slopes": slopes,
            "r_where_err_eq_0.3mm": {bb: float(np.sqrt(0.3 / bb)) for bb in BS}}


if __name__ == "__main__":
    print(main())
