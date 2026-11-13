"""bed_cap_cost — 베드 안전각 상한(22.79°) 전후의 고른 각도와 미지지 길이 비용 (보고서 그림 E).

데이터: report_fig_bed_cap_results.json (python3 report_fig_bed_cap.py ← t1_conventional_results.json)

    python3 tools/report_figs/bed_cap_cost.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

NAME = {"sphere": "구(ico)", "funnel": "깔때기", "torus": "토러스", "mushroom": "버섯"}


def main():
    setup()
    d = json.load(open(os.path.join(ROOT, "report_fig_bed_cap_results.json")))
    cap = d["meta"]["bed_cap_deg"]
    rows = {(r["model"], r["layer_height"]): r for r in d["rows"]}
    models = [r["model"] for r in d["rows"] if r["layer_height"] == 0.4]
    y = np.arange(len(models))[::-1]
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL_W, 10.2 / 2.54), sharey=True,
                               gridspec_kw={"width_ratios": [1, 1.25]})

    # (a) 고른 각도: 상한 없음 → 상한
    for yi, m in zip(y, models, strict=True):
        r = rows[(m, 0.4)]
        u0, u1 = r["uniform"]["theta"], r["uniform"]["theta_cap"]
        b0, b1 = r["band2"]["theta"][0], r["band2"]["theta_cap"][0]
        a.plot([u0, u1], [yi + 0.12] * 2, color=TAB10[0], lw=0.8, alpha=0.7)
        a.plot([b0, b1], [yi - 0.12] * 2, color=TAB10[1], lw=0.8, alpha=0.7)
        a.plot(u0, yi + 0.12, "o", mfc="white", mec=TAB10[0], ms=4, mew=0.9)
        a.plot(u1, yi + 0.12, "o", color=TAB10[0], ms=4)
        a.plot(b0, yi - 0.12, "s", mfc="white", mec=TAB10[1], ms=3.6, mew=0.9)
        a.plot(b1, yi - 0.12, "s", color=TAB10[1], ms=3.6)
    a.axvline(cap, color=TAB10[3], ls="--", lw=0.8)
    a.text(cap + 0.6, -0.55, f"B_safe {cap:g}°", color=TAB10[3], fontsize=7, va="bottom")
    a.set_yticks(y)
    a.set_yticklabels([NAME.get(m, m) for m in models], fontsize=7)
    a.set_xlabel("고른 각도 θ (°) — 밴드2 는 아랫밴드 θ1")
    a.set_xlim(-8, 46)
    a.set_ylim(-0.7, len(models) - 0.1)
    h = [plt.Line2D([], [], marker="o", ls="", mfc="white", mec=TAB10[0], label="균일(J) 상한 없음"),
         plt.Line2D([], [], marker="o", ls="", color=TAB10[0], label="균일 상한"),
         plt.Line2D([], [], marker="s", ls="", mfc="white", mec=TAB10[1], label="밴드2 θ1 상한 없음"),
         plt.Line2D([], [], marker="s", ls="", color=TAB10[1], label="밴드2 θ1 상한")]
    a.legend(handles=h, fontsize=6.5, loc="lower left", bbox_to_anchor=(0.08, 1.0), ncol=2,
             handletextpad=0.2, columnspacing=0.8, borderaxespad=0.2)
    panel_label(a, "(a)")

    # (b) 비용 Δmm (균일), 층고 0.3 / 0.4
    for lh, col, off, mk in ((0.3, TAB10[2], 0.12, "o"), (0.4, TAB10[4], -0.12, "D")):
        for yi, m in zip(y, models, strict=True):
            r = rows[(m, lh)]
            dv = r["uniform"]["delta_mm"]
            if not r["uniform"]["changed"]:
                continue
            b.plot([0, dv], [yi + off] * 2, color=col, lw=1.0)
            b.plot(dv, yi + off, mk, color=col, ms=3.6)
        b.plot([], [], mk, color=col, ms=3.6, label=f"층고 {lh:g} mm")
    for yi, m in zip(y, models, strict=True):
        if not rows[(m, 0.4)]["uniform"]["changed"]:
            b.text(0.6, yi, "상한 아래 — 그대로", fontsize=6.3, color="0.5", va="center")
    b.set_xscale("symlog", linthresh=10)
    b.set_xlim(0, 1500)
    b.set_xticks([0, 10, 100, 1000])
    b.set_xticklabels(["0", "10", "100", "1000"])
    b.set_xlabel("균일 원뿔 미지지 증가 Δ (mm, 상한 - 상한 없음)")
    b.legend(fontsize=7, loc="lower left", bbox_to_anchor=(0.08, 1.0), ncol=2, borderaxespad=0.2)
    panel_label(b, "(b)")
    fig.tight_layout()

    st = d["stats"]
    key = {}
    for lh in ("0.3", "0.4"):
        for k in ("uniform", "band2", "oracle"):
            v = st[lh][k]
            key[f"{lh}:{k}:n_changed"] = v["n_changed"]
            key[f"{lh}:{k}:median_delta_mm"] = round(v["delta_changed"]["median"], 1)
            key[f"{lh}:{k}:max_delta_mm"] = round(v["delta_changed"]["max"], 1)
            key[f"{lh}:{k}:top"] = f"{v['top_model']} ({v['top_share_of_total'] * 100:.0f}%)"
    save(fig, "bed_cap_cost", __file__, ["report_fig_bed_cap_results.json",
                                          "t1_conventional_results.json"],
         "E: 베드 상한 22.79° 전후 고른 각도(균일·밴드2 아랫각, 층고 0.4 선택)와 균일 원뿔 미지지 증가(층고 0.3/0.4)",
         key)


if __name__ == "__main__":
    main()
