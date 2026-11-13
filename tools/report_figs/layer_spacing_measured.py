"""layer_spacing_measured — L3b G-code 에서 같은 반경(±0.1mm) 이웃 층의 z 간격 측정 대 예측 h − c·r·Δtanθ.

측정 절차는 tools/check_layer_spacing.measure 그대로(T2 사전 등록, docs/test_t2_t6.md §1.3 의 M1):
층 k+1 의 압출 끝점마다 층 k 의 가장 가까운 반경 점을 찾고(|Δr| ≤ 0.1mm), 층 k 의 측정 기울기로
반경 차를 보정한 z 차. 예측의 θ 는 파일의 ;CONICAL_META 에서 다시 읽는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.check_layer_spacing import measure  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    COLORS,
    ROOT,
    figure,
    panel_label,
    save,
    setup,
)

G = "examples/rep5x_ladder/L3b_lamp_band22to0.gcode"


def main():
    setup()
    res = measure(ROOT / G, np.random.default_rng(0))
    a = res["rows"]
    dtan, m1, pred = a[:, 4], a[:, 5], a[:, 6]
    inb = np.abs(dtan) > 1e-9
    rho = m1 / pred
    fig, (a1, a2) = figure("full", 7.0, ncols=2)
    lo, hi = 0.25, 0.48
    a1.plot([lo, hi], [lo, hi], color="0.6", lw=0.8, label="y = x")
    a1.plot(pred[~inb], m1[~inb], ".", ms=2, color=COLORS[0], alpha=0.5,
            label=f"블렌드 밖 ({int((~inb).sum())}쌍)")
    a1.plot(pred[inb], m1[inb], ".", ms=3, color=COLORS[3], label=f"블렌드 안 ({int(inb.sum())}쌍)")
    a1.set_xlabel("예측 h - r·Δtanθ (mm)")
    a1.set_ylabel("측정 z 간격 (mm)")
    a1.set_xlim(lo, hi)
    a1.set_ylim(lo, hi)
    a1.set_aspect("equal")
    a1.legend(loc="upper left", fontsize=7.5)
    panel_label(a1, "a")
    a2.plot(a[~inb, 2], rho[~inb], ".", ms=2, color=COLORS[0], alpha=0.5)
    a2.plot(a[inb, 2], rho[inb], ".", ms=3, color=COLORS[3])
    a2.axhspan(0.95, 1.05, color="0.9", lw=0, zorder=0)
    a2.set_xlabel("반경 r (mm)")
    a2.set_ylabel("측정 / 예측")
    a2.set_ylim(0.9, 1.1)
    panel_label(a2, "b")
    q = lambda x: np.percentile(x, [2.5, 50, 97.5])  # noqa: E731
    qa, qb = q(rho), q(rho[inb])
    a2.text(0.03, 0.04, f"전체 중앙 {qa[1]:.4f} (2.5~97.5%: {qa[0]:.3f}~{qa[2]:.3f})\n"
            f"블렌드 안 중앙 {qb[1]:.4f} ({qb[0]:.3f}~{qb[2]:.3f})", transform=a2.transAxes,
            fontsize=7.5, bbox={"fc": "white", "ec": "0.7", "lw": 0.5, "pad": 3})
    save(fig, "layer_spacing_measured", __file__, [G, "tools/check_layer_spacing.py"],
         "L3b G-code 의 이웃 층 z 간격(같은 반경 ±0.1mm, 기울기 보정) 측정 대 예측 h − r·Δtanθ, (b) 비 대 반경 "
         "(회색 띠 = T2 사전 기준 0.95~1.05)",
         f"{len(a)}쌍 (블렌드 안 {int(inb.sum())}); 비 중앙 {qa[1]:.4f} [{qa[0]:.3f}, {qa[2]:.3f}], "
         f"블렌드 안 {qb[1]:.4f} [{qb[0]:.3f}, {qb[2]:.3f}]; 예측 간격 범위 {pred.min():.3f}~{pred.max():.3f} mm",
         extra={"numbers": {"pairs": int(len(a)), "blend_pairs": int(inb.sum()),
                            "rho_all": qa.tolist(), "rho_blend": qb.tolist(),
                            "pred_min": float(pred.min()), "pred_max": float(pred.max())}})
    print(len(a), inb.sum(), qa, qb, pred.min(), pred.max())


if __name__ == "__main__":
    main()
