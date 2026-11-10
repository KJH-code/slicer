"""t5_pred_vs_meas — (a) 해석식 서포트 대 툴패스 미지지 (균일 outward 0~44°, 층고 0.3),
(b) 모델별 스피어만 ρ (층고 0.3·0.4). 데이터: t5_prediction_results.json."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from _style import FULL, ROOT, TAB10, family, panel_label, plt, save, setup


def main():
    setup()
    src = ROOT / "t5_prediction_results.json"
    s = json.loads(src.read_text())
    ms = s["per_model"]
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 7.0 / 2.54),
                             gridspec_kw={"width_ratios": [1, 1.5]})
    seen = set()
    for m in ms:
        fi, fname = family(m["model"])
        rows = m["rows"]["outward"]
        x = [r["pred_pct"] for r in rows]
        y = [r["0.3"]["mm"] for r in rows]
        axes[0].scatter(x, y, s=6, color=TAB10[fi], alpha=0.7,
                        label=fname if fname not in seen else None, lw=0)
        seen.add(fname)
    axes[0].set_xlabel("메시 해석식 서포트 넓이 (%)")
    axes[0].set_ylabel("툴패스 미지지 길이 (mm, 층고 0.3)")
    axes[0].set_yscale("symlog", linthresh=1.0)
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.3)
    x = np.arange(len(ms))
    for i, lh in enumerate(("0.3", "0.4")):
        v = [m["rho"][f"outward_{lh}"] for m in ms]
        axes[1].bar(x + (i - 0.5) * 0.4, [np.nan if r is None else r for r in v], 0.4,
                    color=TAB10[i], label=f"층고 {lh} mm")
        for j, r in enumerate(v):
            if r is None:
                axes[1].text(x[j] + (i - 0.5) * 0.4, 0.03, "정의 안 됨", rotation=90,
                             ha="center", va="bottom", fontsize=5)
    axes[1].axhline(0.8, color="k", lw=0.7, ls="--", label="기준 0.8")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([m["model"] for m in ms], rotation=70, ha="right", fontsize=6)
    axes[1].set_ylabel("스피어만 ρ (무차원)")
    axes[1].set_ylim(-1.0, 1.05)
    axes[1].legend(frameon=False, ncol=3)
    axes[1].grid(axis="y", alpha=0.3)
    panel_label(axes[0], "(a)")
    panel_label(axes[1], "(b)")
    fig.tight_layout()
    save(fig, "t5_pred_vs_meas", __file__, [str(src.relative_to(ROOT)), "t5_results/"],
         "균일 원뿔 0~44° 에서 메시 해석식 예측과 G-code 툴패스 미지지의 순위 일치",
         {"ρ_중앙값": {k: v["median_rho"] for k, v in s["by_layer_height"].items()},
          "ρ_정의안됨": {k: v["undefined"] for k, v in s["by_layer_height"].items()},
          "기준통과": s["pass"]})


if __name__ == "__main__":
    main()
