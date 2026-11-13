"""report_fig_bed_cap.py — 베드 안전각(B_safe = 22.79°) 상한의 비용 (보고서 그림 E).

사전 등록: `docs/test_report_figs_acefg.md` §1.3. 새 측정 없음 — `t1_conventional_results.json`
(지금 코드, 21 모델 × 층고 0.3/0.4, 검사기 A 낙관 진짜 오버행 mm) 을 다시 읽어 정리한다.

팔: 균일 (자동 균일 → 상한 균일), 밴드2 (자동 밴드2 → 상한 밴드2), 사후 최적 균일 (상한 없음 → |θ| ≤ 상한).
비용 Δmm = 상한 − 상한 없음. 0.5mm 안은 0 으로 센다.
교차 확인: 17 모델의 상한 없는 균일(J) mm 를 `docs/gap_audit.md` §9.3 모델별 표와 0.1mm 로 대조.

    python3 report_fig_bed_cap.py
"""

import argparse
import json
import re

import numpy as np

TIE = 0.5
CAP = 22.79


def gap_audit_uniform_mm(path="docs/gap_audit.md"):
    text = open(path, encoding="utf-8").read()
    sec = text.split("### 9.3", 1)[1].split("### 9.4", 1)[0]
    out = {}
    for lh, head in (("0.4", "**층고 0.4mm**"), ("0.3", "**층고 0.3mm**")):
        part = sec.split(head, 1)[1]
        rows = {}
        for line in part.splitlines()[1:]:
            if not line.startswith("|"):
                if rows:
                    break
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells[0] == "모델" or set(cells[0]) <= set("-"):
                continue
            m = re.match(r"([\d.]+)\s*/\s*([\d.]+)", cells[3])
            if m:
                rows[cells[0]] = float(m.group(2))
        out[lh] = rows
    return out


def summarize(vals):
    v = np.asarray(vals, dtype=float)
    return {"n": int(len(v)), "median": float(np.median(v)) if len(v) else None,
            "max": float(v.max()) if len(v) else None, "sum": float(v.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t1", default="t1_conventional_results.json")
    ap.add_argument("--json", default="report_fig_bed_cap_results.json")
    args = ap.parse_args()
    t1 = json.load(open(args.t1))
    summ = t1["summary"]
    rows = []
    for r in t1["rows"]:
        lh = r["layer_height"]
        u = r["uniform"]
        pm_none = {p["model"]: p for p in summ[f"{lh:g}|none"]["per_model"]}[r["model"]]
        pm_cap = {p["model"]: p for p in summ[f"{lh:g}|cap"]["per_model"]}[r["model"]]
        row = {"model": r["model"], "layer_height": lh,
               "uniform": {"theta": r["auto_uniform"], "mm": u[f"{r['auto_uniform']:g}"]["mm"],
                           "theta_cap": r["cap_uniform"], "mm_cap": u[f"{r['cap_uniform']:g}"]["mm"]},
               "band2": {"theta": r["auto_band2"], "mm": r["arms"]["band2"]["mm"],
                         "mean_abs": r["arms"]["band2"]["angle"],
                         "theta_cap": r["cap_band2"], "mm_cap": r["arms"]["cap_band2"]["mm"],
                         "mean_abs_cap": r["arms"]["cap_band2"]["angle"]},
               "oracle": {"theta": float(pm_none["arms"]["oracle"]["theta"]),
                          "mm": pm_none["arms"]["oracle"]["mm"],
                          "theta_cap": float(pm_cap["arms"]["oracle"]["theta"]),
                          "mm_cap": pm_cap["arms"]["oracle"]["mm"]}}
        for k in ("uniform", "band2", "oracle"):
            a = row[k]
            a["delta_mm"] = a["mm_cap"] - a["mm"]
            th, tc = np.atleast_1d(a["theta"]), np.atleast_1d(a["theta_cap"])
            a["changed"] = bool(len(th) != len(tc) or np.any(np.abs(th - tc) > 1e-9))
        rows.append(row)

    stats = {}
    for lh in (0.3, 0.4):
        sub = [r for r in rows if r["layer_height"] == lh]
        st = {}
        for k in ("uniform", "band2", "oracle"):
            ch = [r for r in sub if r[k]["changed"]]
            d = [r[k]["delta_mm"] for r in ch]
            cost = [x for x in d if x > TIE]
            tot = sum(max(x, 0.0) for x in d)
            top = max(ch, key=lambda r: r[k]["delta_mm"]) if ch else None
            st[k] = {"n_changed": len(ch), "changed_models": [r["model"] for r in ch],
                     "n_cost_gt_tie": len(cost), "n_gain_gt_tie": sum(x < -TIE for x in d),
                     "delta_changed": summarize(d),
                     "top_model": top["model"] if top else None,
                     "top_share_of_total": (top[k]["delta_mm"] / tot) if top and tot > 0 else None,
                     "concentrated": bool(top and tot > 0 and top[k]["delta_mm"] / tot > 0.5)}
            st[k]["sum_mm_capped_vs_free"] = [float(sum(r[k]["mm_cap"] for r in sub)),
                                              float(sum(r[k]["mm"] for r in sub))]
        stats[f"{lh:g}"] = st

    ga = gap_audit_uniform_mm()
    cross = {}
    for lh in ("0.4", "0.3"):
        diffs = {}
        for r in rows:
            if f"{r['layer_height']:g}" == lh and r["model"] in ga[lh]:
                diffs[r["model"]] = r["uniform"]["mm"] - ga[lh][r["model"]]
        cross[lh] = {"n": len(diffs), "max_abs_diff": max(abs(v) for v in diffs.values()),
                     "all_within_0p1": all(abs(v) <= 0.1 for v in diffs.values())}

    out = {"rows": rows, "stats": stats, "crosscheck_gap_audit_9_3": cross,
           "meta": {"source": args.t1, "bed_cap_deg": CAP, "tie_mm": TIE,
                    "prereg": "docs/test_report_figs_acefg.md §1.3"}}
    with open(args.json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    for lh, st in stats.items():
        for k, v in st.items():
            print(f"[{lh}] {k:8s} 바뀜 {v['n_changed']:2d}  비용>0.5 {v['n_cost_gt_tie']:2d}  "
                  f"이득>0.5 {v['n_gain_gt_tie']}  Δ중앙 {v['delta_changed']['median']}  "
                  f"Δ최대 {v['delta_changed']['max']}  최대 모델 {v['top_model']} "
                  f"몫 {v['top_share_of_total']}  총 mm 상한/없음 {v['sum_mm_capped_vs_free']}")
    print("교차 확인:", cross)
    print("저장:", args.json)


if __name__ == "__main__":
    main()
