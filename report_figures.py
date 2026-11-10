"""report_figures.py — report_experiments.py 결과를 보고서용 표·그림으로.

    python3 report_figures.py            # report/ 에 표(md/csv)와 그림(png)

판정 규칙은 docs/report_experiment_design.md 에 **결과 전에** 고정한 것을 그대로 쓴다:

* 주 비교: 밴드2 vs **등왜곡 균일** — 균일각 스윕(0~44°, 4°) 곡선을 밴드2 의
  평균 왜곡각 ⟨|θ|⟩ 에서 선형 보간한 값
* 보조 비교: 밴드2 vs J 가 고른 균일각
* tie: |Δ| < 0.10 %p (0.05·0.20 도 같이 센다)
* 밴드2 의 두 각도가 같으면(선택기가 균일로 수렴) 승패에서 빼고 '밴드 안 씀' 으로 센다
"""

import csv
import json
import os
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from conical.plotstyle import L

TIE = 0.10
TIES = (0.05, 0.10, 0.20)
SUPPORT = (("opt", "낙관"), ("pes", "비관"))
# 범주색 (dataviz 기본 팔레트 1~3 슬롯 — 세 개까지 전 쌍 CVD 검증됨)
C_UNI, C_BAND, C_J = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def load(path):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    need = [r for r in rows if "mean_abs" not in r]
    if need:   # 초기 실행분에는 ⟨|θ|⟩ 이 없다 — 프로필을 다시 골라 계산(결정적)
        from compare_waist import mean_abs_angle
        from report_experiments import _model
        for r in need:
            if r["kind"] == "sweep":
                r["mean_abs"] = float(r["angle"])
            else:
                mesh, sel = _model(r["model"])
                n = 1 if r["kind"] == "uniform_J" else 2
                r["mean_abs"] = float(mean_abs_angle(mesh, sel[n]["profile_obj"]))
    return rows


def group(rows):
    g = defaultdict(lambda: {"sweep": {}})
    for r in rows:
        key = (r["model"], r["layer_height"])
        if r["kind"] == "sweep":
            g[key]["sweep"][r["angle"]] = r
        else:
            g[key][r["kind"]] = r
    return g


def eq_uniform(sweep, theta, key):
    a = np.array(sorted(sweep))
    v = np.array([sweep[x][key] for x in a])
    return float(np.interp(theta, a, v))


def verdict(delta, converged, tie=TIE):
    if converged:
        return "밴드 안 씀"
    if delta < -tie:
        return "승"
    if delta > tie:
        return "패"
    return "무"


def analyze(rows, order):
    g = group(rows)
    out = []
    for (model, lh), d in sorted(g.items(), key=lambda kv: (kv[0][1], order(kv[0][0]))):
        if "band2" not in d or "uniform_J" not in d or len(d["sweep"]) < 3:
            continue
        b, u = d["band2"], d["uniform_J"]
        conv = len({round(t, 3) for t in b["thetas"]}) == 1
        row = dict(model=model, layer_height=lh, band_thetas=b["thetas"],
                   band_mean_abs=b["mean_abs"], uniJ_theta=u["thetas"][0],
                   blend_mm=(b["blends"][0][1] - b["blends"][0][0]) if b["blends"] else 0.0,
                   converged=conv)
        for key, _ in SUPPORT:
            row[f"planar_{key}"] = d["sweep"][0][key] if 0 in d["sweep"] else float("nan")
            row[f"uniJ_{key}"] = u[key]
            row[f"band_{key}"] = b[key]
            row[f"equni_{key}"] = eq_uniform(d["sweep"], b["mean_abs"], key)
            row[f"d_eq_{key}"] = b[key] - row[f"equni_{key}"]
            row[f"d_J_{key}"] = b[key] - u[key]
            row[f"v_eq_{key}"] = verdict(row[f"d_eq_{key}"], conv)
            row[f"v_J_{key}"] = verdict(row[f"d_J_{key}"], conv)
        out.append(row)
    return out, g


def tally(res, lh, key, kind="eq", tie=TIE):
    c = defaultdict(int)
    for r in res:
        if r["layer_height"] == lh:
            c[verdict(r[f"d_{kind}_{key}"], r["converged"], tie)] += 1
    return c


def fmt_tally(c):
    s = f"{c['승']}승 {c['무']}무 {c['패']}패"
    return s + (f" (밴드 안 씀 {c['밴드 안 씀']})" if c["밴드 안 씀"] else "")


def write_tables(res, prefix, title):
    with open(f"report/{prefix}_table.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
        w.writeheader()
        w.writerows(res)
    lines = [f"# {title}", "",
             "진짜 오버행 %p (툴패스 실측). Δ = 밴드2 − 등왜곡 균일, 음수면 밴드 승. "
             f"tie |Δ|<{TIE}. 낙관 / 비관 지지 모델.", ""]
    for lh in sorted({r["layer_height"] for r in res}):
        sub = [r for r in res if r["layer_height"] == lh]
        lines += [f"## 층고 {lh} mm", "",
                  "| 모델 | 평면(참고) | J 균일 | 밴드2 (θ₁→θ₂, ⟨\\|θ\\|⟩) | 등왜곡 균일 | Δ 낙관 | Δ 비관 | 판정 낙관 / 비관 |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in sub:
            th = "→".join(f"{t:g}°" for t in r["band_thetas"])
            lines.append(
                f"| {r['model']} | {r['planar_opt']:.2f} / {r['planar_pes']:.2f} "
                f"| {r['uniJ_theta']:g}°: {r['uniJ_opt']:.2f} / {r['uniJ_pes']:.2f} "
                f"| {th}, {r['band_mean_abs']:.1f}°: {r['band_opt']:.2f} / {r['band_pes']:.2f} "
                f"| {r['equni_opt']:.2f} / {r['equni_pes']:.2f} "
                f"| {r['d_eq_opt']:+.2f} | {r['d_eq_pes']:+.2f} "
                f"| {r['v_eq_opt']} / {r['v_eq_pes']} |")
        lines += ["", "**집계 (등왜곡 균일 대비)**", "",
                  "| 지지 모델 | " + " | ".join(f"tie {t}" for t in TIES) + " | J 균일 대비 (tie 0.1) |",
                  "|---|" + "---|" * (len(TIES) + 1)]
        for key, nm in SUPPORT:
            cells = [fmt_tally(tally(res, lh, key, "eq", t)) for t in TIES]
            cells.append(fmt_tally(tally(res, lh, key, "J")))
            lines.append(f"| {nm} | " + " | ".join(cells) + " |")
        d = np.array([r["d_eq_opt"] for r in sub if not r["converged"]])
        p = np.array([r["d_eq_pes"] for r in sub if not r["converged"]])
        if len(d):
            lines += ["", f"Δ 중앙값 (밴드를 쓴 {len(d)} 모델): 낙관 {np.median(d):+.3f} "
                      f"[{d.min():+.2f}, {d.max():+.2f}], 비관 {np.median(p):+.3f} "
                      f"[{p.min():+.2f}, {p.max():+.2f}] %p", ""]
    open(f"report/{prefix}_table.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


def style(ax):
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)


def fig_pareto(g, models, lh, path):
    """핵심 그림: 오버행 vs 평균 왜곡각. 균일 곡선 아래에 밴드 점이 있으면 밴드 승."""
    fig, axes = plt.subplots(2, len(models), figsize=(3.1 * len(models), 5.6),
                             squeeze=False, sharex=True)
    for j, m in enumerate(models):
        d = g.get((m, lh))
        if not d or "band2" not in d:
            continue
        a = sorted(d["sweep"])
        for i, (key, nm) in enumerate(SUPPORT):
            ax = axes[i][j]
            style(ax)
            ax.plot(a, [d["sweep"][x][key] for x in a], color=C_UNI, lw=2,
                    marker="o", ms=4, label=L("uniform cone (sweep)", "균일 원뿔 (각도 스윕)"))
            u, b = d["uniform_J"], d["band2"]
            ax.plot([u["mean_abs"]], [u[key]], "s", color=C_J, ms=8, mec="white", mew=1.5,
                    label=L("uniform, J choice", "균일 (J 선택)"))
            ax.plot([b["mean_abs"]], [b[key]], "D", color=C_BAND, ms=9, mec="white", mew=1.5,
                    label=L("band2", "밴드2"))
            th = "→".join(f"{t:g}" for t in b["thetas"])
            ax.annotate(f"{th}°", (b["mean_abs"], b[key]), xytext=(6, 6),
                        textcoords="offset points", fontsize=8, color=INK)
            if i == 0:
                ax.set_title(m, fontsize=10, color=INK)
            if j == 0:
                ax.set_ylabel(L(f"overhang %p ({key})", f"진짜 오버행 %p ({nm})"),
                              fontsize=9, color=INK)
            if i == 1:
                ax.set_xlabel(L("mean |θ| (°)", "평균 왜곡각 ⟨|θ|⟩ (°)"), fontsize=9, color=INK)
    h, lab = axes[0][0].get_legend_handles_labels()
    fig.suptitle(L(f"Band vs uniform at equal distortion — layer {lh} mm",
                   f"같은 왜곡량에서 밴드 vs 균일 — 층고 {lh} mm"),
                 y=0.985, fontsize=11, color=INK, x=0.5, va="top")
    fig.legend(h, lab, loc="upper center", bbox_to_anchor=(0.5, 0.935), ncol=3,
               frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def fig_delta(res, path, title):
    """모델별 Δ (등왜곡 균일 대비) — 낙관/비관 나란히, 층고별 패널."""
    lhs = sorted({r["layer_height"] for r in res})
    models = []
    for r in res:
        if r["model"] not in models:
            models.append(r["model"])
    fig, axes = plt.subplots(len(lhs), 1, figsize=(max(7, 0.5 * len(models) + 2), 3.0 * len(lhs)),
                             squeeze=False, sharex=True)
    x = np.arange(len(models))
    for i, lh in enumerate(lhs):
        ax = axes[i][0]
        style(ax)
        by = {r["model"]: r for r in res if r["layer_height"] == lh}
        for k, (key, nm), col in ((0, SUPPORT[0], C_UNI), (1, SUPPORT[1], C_BAND)):
            vals = [by[m][f"d_eq_{key}"] if m in by and not by[m]["converged"] else np.nan
                    for m in models]
            ax.bar(x + (k - 0.5) * 0.38, vals, 0.36, color=col,
                   label=L(f"{key} support", f"{nm} 지지"))
        for xi, m in enumerate(models):
            if m in by and by[m]["converged"]:
                ax.text(xi, 0, L("no band", "밴드\n안 씀"), ha="center", va="bottom",
                        fontsize=6.5, color=MUTED)
        ax.axhspan(-TIE, TIE, color=GRID, alpha=0.6, lw=0)
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_ylabel(L("Δ overhang %p", "Δ 오버행 %p\n(음수 = 밴드 승)"), fontsize=9, color=INK)
        ax.set_title(L(f"layer {lh} mm", f"층고 {lh} mm"), fontsize=10, color=INK, loc="left")
    h, lab = axes[0][0].get_legend_handles_labels()
    axes[-1][0].set_xticks(x)
    axes[-1][0].set_xticklabels(models, rotation=45, ha="right", fontsize=8)
    fig.suptitle(title, fontsize=11, color=INK, y=0.99, va="top")
    fig.legend(h, lab, loc="upper center", bbox_to_anchor=(0.5, 0.955), ncol=2,
               frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def fig_layer_height(path, src="layer_height_results.json"):
    if not os.path.exists(src):
        return
    rows = json.load(open(src, encoding="utf-8"))
    models = []
    for r in rows:
        if r["model"] not in models:
            models.append(r["model"])
    fig, axes = plt.subplots(1, len(models), figsize=(3.4 * len(models), 3.4), squeeze=False)
    for j, m in enumerate(models):
        ax = axes[0][j]
        style(ax)
        sub = sorted((r for r in rows if r["model"] == m), key=lambda r: r["layer_height"])
        h = [r["layer_height"] for r in sub]
        for key, nm, col in (("opt", "낙관", C_UNI), ("pes", "비관", C_BAND)):
            ax.plot(h, [r[f"band2_{key}"] - r[f"uniform_{key}"] for r in sub], color=col,
                    lw=2, marker="o", ms=5, label=L(f"{key} support", f"{nm} 지지"))
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_title(m, fontsize=10, color=INK)
        ax.set_xlabel(L("layer height (mm)", "층고 (mm)"), fontsize=9, color=INK)
        if j == 0:
            ax.set_ylabel(L("band2 − uniform(J) %p", "밴드2 − 균일(J) %p\n(음수 = 밴드 승)"),
                          fontsize=9, color=INK)
            ax.legend(frameon=False, fontsize=8)
    fig.suptitle(L("Verdict vs layer height", "층고에 따른 판정 — 두 지지 모델이 갈리는 경계"),
                 fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main():
    os.makedirs("report", exist_ok=True)
    from analyze_blend_ratio import build_specs
    names = [n for n, _ in build_specs(asym=True)]

    def order(m):
        return names.index(m) if m in names else len(names) + (int(m[5:]) if m.startswith("rand:") else -1)

    if os.path.exists("report/exp1_raw.jsonl"):
        rows = load("report/exp1_raw.jsonl")
        res, g = analyze(rows, order)
        if res:
            write_tables(res, "exp1", "실험 1 — 형상 의존성 (17 모델)")
            for lh in sorted({r["layer_height"] for r in res}):
                fig_pareto(g, ["구", "허리 r=5", "허리 r=2", "허리 r=1"], lh,
                           f"report/fig1_pareto_lh{str(lh).replace('.', '')}.png")
            fig_delta(res, "report/fig2_delta_exp1.png",
                      L("Exp 1: band2 − equal-distortion uniform",
                        "실험 1 — 밴드2 − 등왜곡 균일 (진짜 오버행 %p)"))
    src = "report/exp2_layer_height.json"
    fig_layer_height("report/fig3_layer_height.png",
                     src if os.path.exists(src) else "layer_height_results.json")
    if os.path.exists("report/exp3_raw.jsonl"):
        rows = load("report/exp3_raw.jsonl")
        res, g = analyze(rows, order)
        if res:
            write_tables(res, "exp3", "실험 3 — 보류 모델 (funnel + 무작위 20, 시드 20261110)")
            fig_delta(res, "report/fig4_delta_exp3.png",
                      L("Exp 3: held-out models", "실험 3 — 보류 모델, 밴드2 − 등왜곡 균일"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
