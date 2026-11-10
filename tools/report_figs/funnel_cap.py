"""funnel_cap — funnel 이 베드 상한 아래에서 0° 를 고르는 이유와 S³ 모델의 k 스케일.

(a) funnel 해석식 S(θ) 와 J(θ)=ΔS−0.2θ — 오버행 면 전부 θ*=25.26° 에서 한꺼번에 풀린다
(b) funnel 툴패스 미지지 mm(T1) — 이것도 계단이지만 계단 위치가 층고에 따라 다르다
(c) ΔS(θ) 와 k·θ 선 (ring · topopt · armadillo · funnel)

    python3 tools/report_figs/funnel_cap.py [--json k_funnel_results.json]
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from _style import FULL_W, ROOT, TAB10, panel_label, plt, save, setup  # noqa: E402

CAP = 22.79


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "k_funnel_results.json"))
    args = ap.parse_args()
    setup()
    d = json.load(open(args.json))
    f = d["funnel"]
    th = np.array(f["S_fine"]["theta"])
    S = np.array(f["S_fine"]["S"])
    J = np.array(f["S_fine"]["J_k0.2"])
    fig, axes = plt.subplots(1, 3, figsize=(FULL_W, 5.6 / 2.54))
    ax = axes[0]
    ax.plot(th, S, color=TAB10[0], label="S(θ) 해석식")
    ax.plot(th, J, color=TAB10[3], ls="--", label="J(θ), k=0.2")
    ax.axvspan(CAP, 44, color="0.85", alpha=0.6, lw=0)
    ax.axvline(f["theta_star"]["min"], color="0.3", lw=0.7, ls=":")
    ax.text(f["theta_star"]["min"] + 0.8, 34, f"θ*={f['theta_star']['min']:.2f}°", fontsize=7)
    ax.text(34, 6, "상한 밖", fontsize=7, color="0.4", ha="center")
    ax.set_xlabel("균일 θ (°)")
    ax.set_ylabel("%p")
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.42), frameon=False, fontsize=7)
    panel_label(ax, "(a) funnel 해석식")
    ax = axes[1]
    for i, (lh, mm) in enumerate(sorted(f["toolpath_mm"].items())):
        pts = sorted((float(a), v) for a, v in mm.items() if float(a) >= 0)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", ms=2.5, color=TAB10[i + 1],
                label=f"층고 {lh}")
    ax.axvspan(CAP, 45, color="0.85", alpha=0.6, lw=0)
    ax.axvline(f["theta_star"]["min"], color="0.3", lw=0.7, ls=":")
    steps = f.get("toolpath_step_posthoc", {}).get("by_layer_height", {})
    for i, (lh, st) in enumerate(sorted(steps.items())):
        lo, hi = st["implied_threshold_deg"]
        ax.text(0.03, 0.62 - 0.09 * i, f"{lh}: 실효 임계 ≈{(lo + hi) / 2:.0f}°", fontsize=6.5,
                color=TAB10[i + 1], ha="left", transform=ax.transAxes)
    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_ylim(0, 3000)
    ax.set_xlabel("균일 θ (°)")
    ax.set_ylabel("미지지 (mm)")
    ax.legend(frameon=False, fontsize=7)
    panel_label(ax, "(b) funnel 툴패스 (검사기 A)")
    ax = axes[2]
    xs = np.arange(0, 45, 2.0)
    curves = [("funnel", f["S_fine"]["theta"], (S[0] - S).tolist(), TAB10[0])]
    for i, name in enumerate(("ring", "topopt_new4", "armadillo4")):
        r = d.get("s3", {}).get(name)
        if r and r["available"]:
            curves.append((name, xs.tolist(), [r["S0"] - r["S"][f"{x:g}"] for x in xs],
                           TAB10[i + 4]))
    for name, x, y, col in curves:
        ax.plot(x, y, color=col, label=name)
    for k, ls in ((0.2, "--"), (0.1, ":"), (0.05, "-.")):
        ax.plot(xs, k * xs, color="0.3", ls=ls, lw=0.8, label=f"k·θ, k={k:g}")
    ax.set_ylim(-1, 12)
    ax.set_xlabel("균일 θ (°, outward)")
    ax.set_ylabel("ΔS (%p)")
    ax.legend(frameon=False, fontsize=6.5, ncol=2, loc="upper left")
    panel_label(ax, "(c) ΔS(θ) 와 각도 비용")
    fig.tight_layout()
    kn = {"funnel:theta_star_deg": round(f["theta_star"]["min"], 2),
          "funnel:overhang_area_pct": round(f["overhang_area_pct_0deg"], 2),
          "funnel:toolpath_drop_0_to_22_mm": {k: round(v, 1) for k, v in
                                              f["checks"]["3_toolpath_drop_0_to_22_mm"].items()}}
    for name in ("ring", "topopt_new4", "armadillo4"):
        r = d.get("s3", {}).get(name)
        if r and r["available"]:
            kn[f"{name}:k_star"] = round(r["k_star"], 4)
            kn[f"{name}:max_dS_pct"] = round(r["max_dS_pct"], 2)
    save(fig, "funnel_cap", __file__, [os.path.relpath(args.json, ROOT), "t1_conventional_results.json",
                                       "docs/test_k_sweep.md"],
         "funnel 은 오버행 면 전부가 θ*=25.26° 에서 한꺼번에 풀려 상한 22.79° 아래 ΔS=0 → J 가 0° 를 고른다; "
         "툴패스 미지지도 계단이나 위치가 층고별(0.3: 17°, 0.4: 29°)로 다르다; S³ 모델은 ΔS 가 k·θ 선 아래(k 스케일)", kn)


if __name__ == "__main__":
    main()
