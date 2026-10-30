"""
sweep_rules.py — 선택 규칙 비교 (수정 ①·②). 예측은 NOTES.md §5.

    python3 find_conical_angle/sweep_rules.py --s3-dir <S³ 데이터>
    python3 find_conical_angle/sweep_rules.py --reanalyze find_conical_angle/rules_results.json

규칙 × κ(adaptive/fixed) × 모델 11개. 열은 evaluate.py 와 같다.
"""

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from compare_dof_ladder import OUR_MODELS, S3_MODELS, build_model
from find_conical_angle.evaluate import measure_model

RULE_SETS = {
    "rules": {
        "mean": {},                                             # 원본
        "mean_out": {"outward_only": True},
        "p0.9": {"quantile": 0.9},                              # 수정 ①
        "sweep": {"method": "sweep"},                           # 수정 ②
        "sweep_out": {"method": "sweep", "outward_only": True},  # 수정 ②
    },
    "margin": {                                                 # 수정 ④
        "all_m0": {"outward_only": True, "reselect": "all", "threshold_deg": 45.0},
        "all_m5": {"outward_only": True, "reselect": "all", "threshold_deg": 40.0},
        "all_m10": {"outward_only": True, "reselect": "all", "threshold_deg": 35.0},
    },
    "reselect": {                                               # 수정 ③
        "mean": {},
        "all_t0": {"outward_only": True, "reselect": "all", "tol_pct": 0.0},
        "all_t0.5": {"outward_only": True, "reselect": "all", "tol_pct": 0.5},
        "all_t1": {"outward_only": True, "reselect": "all", "tol_pct": 1.0},
    },
}
RULES = RULE_SETS["rules"]


def measure(models, s3_dir, toolpath, bed_tolerance=None, rules=None):
    rules = rules or RULES
    out = {"meta": {"rules": list(rules), "bed_tolerance": bed_tolerance}, "models": {}}
    for spec in models:
        mesh = build_model(spec, s3_dir)
        row = {}
        t0 = time.time()
        for name, kw in rules.items():
            row[name] = measure_model(spec, mesh, toolpath=toolpath,
                                      bed_tolerance=bed_tolerance, **kw)
        row["t_sec"] = time.time() - t0
        out["models"][spec] = row
        print(f"[{spec}] {row['t_sec']:.0f}s " + " | ".join(
            f"{name}: {row[name]['adaptive']['uniform']['direction'][:3]} "
            f"{row[name]['adaptive']['uniform']['angle']:.0f}°→{row[name]['adaptive']['bands']['support']:.2f}"
            + (f"/tp {row[name]['adaptive']['bands']['toolpath_overhang']:.2f}"
               if "toolpath_overhang" in row[name]["adaptive"]["bands"] else "")
            for name in rules), flush=True)
    return out


def report(res, ladder_path="dof_ladder_results.json"):
    ladder = json.load(open(ladder_path))["models"] if os.path.exists(ladder_path) else {}
    rules = res["meta"]["rules"]
    for rule in ("adaptive", "fixed"):
        print(f"\n=== κ={rule}: 해석식 자 남은 서포트 % (바닥 제외), 괄호 평균|θ|, 밴드 프로필 ===")
        print("모델 | " + " | ".join(rules) + " | 우리 균일 J | 우리 균일 최소")
        for n, row in res["models"].items():
            cells = []
            for r in rules:
                b = row[r][rule]["bands"]
                d = row[r][rule]["uniform"]["direction"][:3]
                cells.append(f"{b['support']:.2f} ({b['mean_abs_theta']:.0f}° {d})"
                             + ("†" if b.get("profile_failed") else ""))
            L = ladder.get(n, {})
            for k in ("uniform_J", "uniform_min"):
                d = L.get(k)
                cells.append(f"{d['support']:.2f} ({d['mean_abs_theta']:.0f}°)" if d else "—")
            print(f"{n} | " + " | ".join(cells))
    tp = [(n, r) for n, r in res["models"].items()
          if "toolpath_overhang" in r[rules[0]]["adaptive"]["bands"]]
    if tp:
        for rule in ("adaptive", "fixed"):
            print(f"\n=== κ={rule}: 툴패스 진짜 오버행 %p (밴드 프로필, 층고 0.4, 낙관) ===")
            print("모델 | " + " | ".join(rules))
            for n, r in tp:
                print(f"{n} | " + " | ".join(
                    f"{r[k][rule]['bands']['toolpath_overhang']:.2f}" for k in rules))
    print(f"\n† = 층간격 제약으로 프로필 실패 → 균일로 대체  (bed_tolerance={res['meta'].get('bed_tolerance')})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--s3-dir", default=None)
    ap.add_argument("--no-toolpath", action="store_true")
    ap.add_argument("--bed-tol", type=float, default=None)
    ap.add_argument("--set", default="rules", choices=list(RULE_SETS),
                    help="규칙 묶음: rules(수정 ①②) / reselect(수정 ③)")
    ap.add_argument("--out", default=os.path.join(_HERE, "rules_results.json"))
    ap.add_argument("--reanalyze", default=None)
    a = ap.parse_args()
    if a.reanalyze:
        report(json.load(open(a.reanalyze)))
        return
    models = a.models or (OUR_MODELS + (S3_MODELS if a.s3_dir else []))
    res = measure(models, a.s3_dir, toolpath=not a.no_toolpath, bed_tolerance=a.bed_tol,
                  rules=RULE_SETS[a.set])
    json.dump(res, open(a.out, "w"), indent=1, default=float)
    print(f"→ {a.out}")
    report(res)


if __name__ == "__main__":
    main()
