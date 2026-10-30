"""
sweep_quantile.py — 수정 ① (면적 가중 분위수 p) 의 손잡이 스윕. 예측은 NOTES.md §4.

    python3 find_conical_angle/sweep_quantile.py --s3-dir <S³ 데이터>
    python3 find_conical_angle/sweep_quantile.py --reanalyze find_conical_angle/quantile_results.json

p ∈ {None(원본 평균), 0.5, 0.75, 0.9, 1.0} × κ ∈ {adaptive, fixed} × 모델 11개.
열은 evaluate.py 와 같다 (해석식 자·기울기, 우리 모델은 툴패스 진짜 오버행).
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

QUANTILES = (None, 0.5, 0.75, 0.9, 1.0)


def _q(q):
    return "mean" if q is None else f"p{q:g}"


def measure(models, s3_dir, toolpath, bed_tolerance=None):
    out = {"meta": {"quantiles": [_q(q) for q in QUANTILES], "bed_tolerance": bed_tolerance},
           "models": {}}
    for spec in models:
        mesh = build_model(spec, s3_dir)
        row = {}
        t0 = time.time()
        for q in QUANTILES:
            row[_q(q)] = measure_model(spec, mesh, toolpath=toolpath, quantile=q,
                                       bed_tolerance=bed_tolerance)
        row["t_sec"] = time.time() - t0
        out["models"][spec] = row
        print(f"[{spec}] {row['t_sec']:.0f}s " + " | ".join(
            f"{_q(q)}: {row[_q(q)]['adaptive']['uniform']['angle']:.0f}°→"
            f"{row[_q(q)]['adaptive']['uniform']['support']:.2f}"
            + (f"/tp {row[_q(q)]['adaptive']['bands']['toolpath_overhang']:.2f}"
               if "toolpath_overhang" in row[_q(q)]["adaptive"]["bands"] else "")
            for q in QUANTILES), flush=True)
    return out


def report(res, ladder_path="dof_ladder_results.json"):
    ladder = json.load(open(ladder_path))["models"] if os.path.exists(ladder_path) else {}
    qs = res["meta"]["quantiles"]
    for rule in ("adaptive", "fixed"):
        print(f"\n=== κ={rule}: 해석식 자 남은 서포트 % (바닥 제외), 괄호 평균|θ|. 밴드 프로필 기준 ===")
        print("모델 | " + " | ".join(qs) + " | 우리 균일 J | 우리 균일 최소")
        for n, row in res["models"].items():
            cells = []
            for q in qs:
                b = row[q][rule]["bands"]
                cells.append(f"{b['support']:.2f} ({b['mean_abs_theta']:.0f}°)"
                             + ("†" if b.get("profile_failed") else ""))
            L = ladder.get(n, {})
            lj = L.get("uniform_J")
            lm = L.get("uniform_min")
            cells.append(f"{lj['support']:.2f} ({lj['mean_abs_theta']:.0f}°)" if lj else "—")
            cells.append(f"{lm['support']:.2f} ({lm['mean_abs_theta']:.0f}°)" if lm else "—")
            print(f"{n} | " + " | ".join(cells))
    tp = [(n, r) for n, r in res["models"].items()
          if "toolpath_overhang" in r[qs[0]]["adaptive"]["bands"]]
    if tp:
        for rule in ("adaptive", "fixed"):
            print(f"\n=== κ={rule}: 툴패스 진짜 오버행 %p (밴드 프로필, 층고 0.4, 낙관) ===")
            print("모델 | " + " | ".join(qs))
            for n, r in tp:
                print(f"{n} | " + " | ".join(
                    f"{r[q][rule]['bands']['toolpath_overhang']:.2f}" for q in qs))
    print("\n† = 층간격 제약으로 프로필 실패 → 균일로 대체")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--s3-dir", default=None)
    ap.add_argument("--no-toolpath", action="store_true")
    ap.add_argument("--out", default=os.path.join(_HERE, "quantile_results.json"))
    ap.add_argument("--reanalyze", default=None)
    ap.add_argument("--bed-tol", type=float, default=None,
                    help="팀메 바닥 판정 높이 (원본 1e-6; 우리 마스크와 맞추려면 0.3)")
    a = ap.parse_args()
    if a.reanalyze:
        report(json.load(open(a.reanalyze)))
        return
    models = a.models or (OUR_MODELS + (S3_MODELS if a.s3_dir else []))
    res = measure(models, a.s3_dir, toolpath=not a.no_toolpath, bed_tolerance=a.bed_tol)
    json.dump(res, open(a.out, "w"), indent=1, default=float)
    print(f"→ {a.out}")
    report(res)


if __name__ == "__main__":
    main()
