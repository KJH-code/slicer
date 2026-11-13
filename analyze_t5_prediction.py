"""analyze_t5_prediction.py — T5: 메시 예측(해석식) 대 G-code 측정(툴패스) 의 순위 일치.

사전 등록: docs/test_t3_t5_t7.md §1.2 (결과 보기 전에 커밋).

`compare_prediction_vs_toolpath.py`(데모 구 하나, 6 각, 전체 미지지 %) 를 최신 코드·21 모델로 넓힌다.
모델마다 균일 outward 0, 4, …, 44° 에서

  예측  = `analytic.support_fraction` (메시 해석식 서포트 %)
  측정  = 내장 슬라이서 → 역변환 → 검사기 A(낙관) → 진짜 오버행 미지지 길이 mm
          (`analyze_gap_sample.measure` — T1·T3·gap_audit 와 같은 경로)

의 스피어만 ρ 를 층고 0.3·0.4 따로 낸다. 기준: 두 층고 모두 모델별 ρ 중앙값 ≥ 0.8.
한쪽이 상수면 ρ 정의 안 됨 → 중앙값에서 빼고 따로 센다. torus 는 inward 줄을 따로 더 적는다.

    python3 analyze_t5_prediction.py [--jobs 4] [--models 0,1]    # 측정 (모델별 JSON, 재개 가능)
    python3 analyze_t5_prediction.py --report                     # 표·그림·요약
"""

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

import analyze_gap_sample
from analyze_t3_band_optimum import LAYER_HEIGHTS, load_model, model_specs
from conical.analytic import critical_angle, support_fraction
from conical.profile import AngleProfile

ANGLES = list(range(0, 45, 4))          # 0, 4, …, 44
RHO_PASS = 0.8
NEAR = 1.0                              # 원인 기록용: 바닥 1mm 안
ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "t5_results"
SUMMARY_JSON = ROOT / "t5_prediction_results.json"
FIG = ROOT / "t5_prediction.png"


def run_model(idx):
    path = OUT_DIR / f"{idx:02d}.json"
    if path.exists():
        return str(path)
    analyze_gap_sample.NEAR_BED = NEAR          # near_mm 를 바닥 1mm 안으로
    name, mesh = load_model(idx)
    dirs = ["outward"]
    th = critical_angle(mesh, "inward")
    if np.any(np.nan_to_num(th, nan=0.0) > 0):
        dirs.append("inward")
    t0 = time.perf_counter()
    rows = {}
    for d in dirs:
        sgn = 1.0 if d == "outward" else -1.0
        rows[d] = []
        for a in ANGLES:
            pred = float(support_fraction(mesh, float(a), d))
            rec = {"angle": a, "pred_pct": pred}
            for lh in LAYER_HEIGHTS:
                m = analyze_gap_sample.measure(mesh, AngleProfile.constant(sgn * a), lh)
                rec[str(lh)] = {"mm": m["mm"], "pct": m["pct"], "near1_mm": m["near_mm"],
                                "mm_pes": m["mm_pes"], "over_z": m["over_z"]}
            rows[d].append(rec)
    out = {"model": name, "index": idx, "faces": int(len(mesh.faces)), "rows": rows,
           "seconds": time.perf_counter() - t0}
    OUT_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    os.replace(tmp, path)
    print(f"[{idx:02d} {name}] {out['seconds']:.0f}s", flush=True)
    return str(path)


def rho_of(pred, meas):
    if np.ptp(pred) == 0 or np.ptp(meas) == 0:
        return None
    return float(spearmanr(pred, meas)[0])


def diagnose(rows, lh):
    """ρ 가 낮을 때 원인 후보를 숫자로."""
    pred = np.array([r["pred_pct"] for r in rows])
    meas = np.array([r[str(lh)]["mm"] for r in rows])
    near = np.array([r[str(lh)]["near1_mm"] for r in rows])
    tot = meas.sum()
    inv = []
    for i in range(len(rows) - 1):
        dp, dm = pred[i + 1] - pred[i], meas[i + 1] - meas[i]
        if dp < -1e-9 and dm > 0.5:
            inv.append([rows[i]["angle"], rows[i + 1]["angle"]])
    return {"near1_share": float(near.sum() / tot) if tot > 0 else None,
            "pred_zero_meas_pos": [r["angle"] for r in rows
                                   if r["pred_pct"] < 1e-9 and r[str(lh)]["mm"] > 0.5],
            "pred_down_meas_up": inv,
            "pred_constant": bool(np.ptp(pred) == 0),
            "meas_constant": bool(np.ptp(meas) == 0)}


def run_report():
    models = []
    for idx in range(len(model_specs())):
        p = OUT_DIR / f"{idx:02d}.json"
        if not p.exists():
            print(f"[{idx:02d}] 결과 없음 — 건너뜀")
            continue
        d = json.loads(p.read_text())
        rec = {"model": d["model"], "index": idx, "rho": {}, "diag": {}}
        for direction, rows in d["rows"].items():
            for lh in LAYER_HEIGHTS:
                pred = [r["pred_pct"] for r in rows]
                meas = [r[str(lh)]["mm"] for r in rows]
                key = f"{direction}_{lh}"
                rec["rho"][key] = rho_of(pred, meas)
                rec["diag"][key] = diagnose(rows, lh)
        rec["rows"] = d["rows"]
        models.append(rec)
    summary = {"models": len(models), "criterion": RHO_PASS, "by_layer_height": {}}
    for lh in LAYER_HEIGHTS:
        rs = [m["rho"][f"outward_{lh}"] for m in models]
        ok = [r for r in rs if r is not None]
        summary["by_layer_height"][str(lh)] = {
            "median_rho": float(np.median(ok)) if ok else None,
            "defined": len(ok), "undefined": len(rs) - len(ok),
            "below_0.8": [m["model"] for m in models
                          if m["rho"][f"outward_{lh}"] is not None
                          and m["rho"][f"outward_{lh}"] < RHO_PASS],
            "min_rho": float(min(ok)) if ok else None}
    summary["pass"] = all(v["median_rho"] is not None and v["median_rho"] >= RHO_PASS
                          for v in summary["by_layer_height"].values())
    summary["per_model"] = models
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print_table(summary)
    plot(summary)
    return summary


def print_table(summary):
    print("| 모델 | ρ 0.3 | ρ 0.4 | 바닥 1mm 몫 0.3 / 0.4 | 예측 0 인데 측정>0.5mm (0.3) | 예측↓ 측정↑ (0.3) |")
    print("|---|---|---|---|---|---|")
    for m in summary["per_model"]:
        for d in ("outward", "inward"):
            if f"{d}_0.3" not in m["rho"]:
                continue

            def f(x):
                return "—" if x is None else f"{x:.2f}"
            g3, g4 = m["diag"][f"{d}_0.3"], m["diag"][f"{d}_0.4"]
            name = m["model"] + (" (inward)" if d == "inward" else "")
            print(f"| {name} | {f(m['rho'][d + '_0.3'])} | {f(m['rho'][d + '_0.4'])} | "
                  f"{f(g3['near1_share'])} / {f(g4['near1_share'])} | "
                  f"{g3['pred_zero_meas_pos']} | {g3['pred_down_meas_up']} |")
    print(json.dumps(summary["by_layer_height"], ensure_ascii=False, indent=1))
    print("통과" if summary["pass"] else "불통과")


def plot(summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from conical.plotstyle import L

    ms = summary["per_model"]
    x = np.arange(len(ms))
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for i, (lh, c) in enumerate(((0.3, "#4c72b0"), (0.4, "#dd8452"))):
        v = [m["rho"][f"outward_{lh}"] for m in ms]
        ax.bar(x + (i - 0.5) * 0.38, [np.nan if r is None else r for r in v], 0.38,
               color=c, label=L(f"layer {lh}", f"층고 {lh}"))
        for j, r in enumerate(v):
            if r is None:
                ax.text(x[j] + (i - 0.5) * 0.38, 0.02, "n/a", ha="center",
                        fontsize=6, rotation=90)
    ax.axhline(RHO_PASS, color="k", lw=0.8, ls="--")
    ax.set_xticks(x)
    ax.set_xticklabels([m["model"] for m in ms], rotation=60, ha="right", fontsize=7)
    ax.set_ylabel(L("Spearman ρ (prediction vs toolpath)", "스피어만 ρ (예측 대 툴패스)"))
    ax.set_ylim(-1, 1.05)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG, dpi=130)
    print(f"저장: {FIG.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--models", default="")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.report:
        run_report()
        return 0
    idxs = ([int(x) for x in args.models.split(",")] if args.models
            else list(range(len(model_specs()))))
    with Pool(args.jobs) as pool:
        for p in pool.imap_unordered(run_model, idxs):
            print("완료:", p, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
