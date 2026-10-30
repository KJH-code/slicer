"""
evaluate.py — 팀메 탐색(bridge.analyze)을 우리 검증 도구로 잰다. 예측은 NOTES.md.

    python3 find_conical_angle/evaluate.py                       # 우리 5 모델, 해석식 자 + 툴패스
    python3 find_conical_angle/evaluate.py --s3-dir <S³ 데이터>   # + S³ 모델 6개 (해석식 자만)
    python3 find_conical_angle/evaluate.py --no-toolpath          # 빠르게 해석식만
    python3 find_conical_angle/evaluate.py --reanalyze find_conical_angle/results.json

열 (모두 바깥 저장소의 자):
  · 해석식 자 — `conical/s3io.support_fraction_dirs`, 45°, 바닥 제외. 사다리와 같은 자.
  · 툴패스 — `compare_waist.run_pipeline` 의 진짜 오버행 %p (층고 0.4, 낙관 지지 모델).
    우리 모델에서만 (S³ 모델은 크고 비축대칭이라 내장 슬라이서가 느리다 — 다음 단계).
  · 기울기 — 면적가중 평균 |θ|.
사다리 칸(`dof_ladder_results.json`)이 있으면 같은 표에 나란히 놓는다.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from compare_dof_ladder import OUR_MODELS, S3_MODELS, build_model
from compare_waist import run_pipeline
from conical.s3io import (
    bed_contact_mask,
    cone_dirs,
    profile_dirs,
    support_fraction_dirs,
)
from find_conical_angle import bridge

LAYER_H_NOTE = "툴패스는 compare_waist.LAYER_H (0.4mm), 낙관 지지 모델"


def _tilt(mesh, profile):
    cz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    th = np.abs(np.asarray(profile.theta_at(cz), dtype=float))
    return float((th * mesh.area_faces).sum() / mesh.area_faces.sum())


def measure_model(spec, mesh, rules=("adaptive", "fixed"), toolpath=True, quantile=None,
                  bed_tolerance=None):
    bed = bed_contact_mask(mesh)
    row = {"faces": int(len(mesh.faces)),
           "planar": support_fraction_dirs(mesh, cone_dirs(mesh, 0.0), exclude=bed)}
    for rule in rules:
        t0 = time.time()
        r = bridge.analyze(mesh, kappa_rule=rule, quantile=quantile, bed_tolerance=bed_tolerance)
        u = r["uniform"]
        prof = r["profile"]
        if prof is None:                       # 블렌드 겹침 → 균일로 대체하고 사유를 남긴다
            from conical.profile import AngleProfile
            prof = AngleProfile.constant(u["signed"])
            prof.notes = [f"프로필 실패 → 균일로 대체: {r['profile_error']}"]
        raw = r["profile_raw"] if r["profile_raw"] is not None else prof
        entry = {
            "uniform": {"direction": u["direction"], "angle": u["angle"],
                        "support": support_fraction_dirs(
                            mesh, cone_dirs(mesh, u["angle"], u["direction"]), exclude=bed),
                        "mean_abs_theta": u["angle"]},
            "bands": {"intervals": r["band_intervals"],
                      "support": support_fraction_dirs(mesh, profile_dirs(mesh, prof), exclude=bed),
                      "support_raw": support_fraction_dirs(mesh, profile_dirs(mesh, raw),
                                                           exclude=bed),
                      "profile_failed": r["profile"] is None,
                      "mean_abs_theta": _tilt(mesh, prof),
                      "blend_mm": float(sum(b - a for a, b in prof.blend_intervals())),
                      "notes": list(getattr(prof, "notes", []))},
            "components": [{k: v for k, v in c.items() if k in
                            ("id", "faces", "area", "q", "kappa", "bed_supported")}
                           | {"outward_allows_all": c["outward"]["allows_all"],
                              "outward_violating_area": c["outward"]["violating_area"]}
                           for c in r["components"]],
            "n_bands": len(r["bands"]), "t_sec": time.time() - t0,
        }
        if toolpath and spec in OUR_MODELS:
            t1 = time.time()
            ang = u["angle"] if u["direction"] == "outward" else -u["angle"]
            if abs(ang) < 1e-9:
                tp_u = run_pipeline(mesh, 0.0, breakdown=True)
            else:
                tp_u = run_pipeline(mesh, abs(ang), u["direction"], breakdown=True)
            tp_b = run_pipeline(mesh, prof, breakdown=True)
            entry["uniform"]["toolpath_overhang"] = float(tp_u[3])
            entry["bands"]["toolpath_overhang"] = float(tp_b[3])
            entry["toolpath_sec"] = time.time() - t1
        row[rule] = entry
    return row


def measure(models, s3_dir, toolpath):
    out = {"meta": {"ruler": "n·b < -sin45, bed excluded", "toolpath": LAYER_H_NOTE}, "models": {}}
    for spec in models:
        mesh = build_model(spec, s3_dir)
        t0 = time.time()
        row = measure_model(spec, mesh, toolpath=toolpath)
        row["t_sec"] = time.time() - t0
        out["models"][spec] = row
        a, f = row["adaptive"], row["fixed"]
        print(f"[{spec}] {row['t_sec']:.0f}s planar {row['planar']:.2f} | adaptive 균일 "
              f"{a['uniform']['direction'][:3]} {a['uniform']['angle']:.1f}°→{a['uniform']['support']:.2f} "
              f"밴드{a['n_bands']}→{a['bands']['support']:.2f} | fixed 균일 {f['uniform']['angle']:.1f}°→"
              f"{f['uniform']['support']:.2f} 밴드→{f['bands']['support']:.2f}"
              + (f" | 툴패스 adaptive 균일 {a['uniform']['toolpath_overhang']:.2f} 밴드 "
                 f"{a['bands']['toolpath_overhang']:.2f}" if "toolpath_overhang" in a["uniform"] else ""),
              flush=True)
    return out


def report(res, ladder_path="dof_ladder_results.json"):
    ladder = json.load(open(ladder_path))["models"] if os.path.exists(ladder_path) else {}
    print("\n=== 해석식 자 (남은 서포트 %, 바닥 제외) · 괄호는 평균|θ| ===")
    print("모델 | 평면 | 팀메 균일(adaptive) | 팀메 밴드(adaptive) | 팀메 균일(fixed45) | "
          "팀메 밴드(fixed45) | 우리 균일 J | 우리 밴드2 J | 우리 균일 최소 | S³/S4")
    for n, row in res["models"].items():
        a, f = row["adaptive"], row["fixed"]
        L = ladder.get(n, {})

        def c(d):
            return f"{d['support']:.2f} ({d['mean_abs_theta']:.0f}°)"

        def lc(k, L=L):
            d = L.get(k)
            return f"{d['support']:.2f} ({d['mean_abs_theta']:.0f}°)" if d else "—"

        ceil = "—"
        if L.get("s3", {}).get("valid"):
            ceil = f"{L['s3']['support']:.2f} (S³)"
        elif "s4" in L:
            ceil = f"{L['s4']['support']:.2f} (S4)"
        print(f"{n} | {row['planar']:.2f} | {c(a['uniform'])} {a['uniform']['direction'][:3]} | "
              f"{c(a['bands'])} N={a['n_bands']} | {c(f['uniform'])} | {c(f['bands'])} | "
              f"{lc('uniform_J')} | {lc('band2_J')} | {lc('uniform_min')} | {ceil}")
    tp = [(n, r) for n, r in res["models"].items() if "toolpath_overhang" in r["adaptive"]["uniform"]]
    if tp:
        print("\n=== 툴패스 진짜 오버행 %p (층고 0.4, 낙관) ===")
        print("모델 | 팀메 균일 adaptive | 팀메 밴드 adaptive | 팀메 균일 fixed | 팀메 밴드 fixed")
        for n, r in tp:
            print(f"{n} | {r['adaptive']['uniform']['toolpath_overhang']:.2f} | "
                  f"{r['adaptive']['bands']['toolpath_overhang']:.2f} | "
                  f"{r['fixed']['uniform']['toolpath_overhang']:.2f} | "
                  f"{r['fixed']['bands']['toolpath_overhang']:.2f}")
    print("\n=== P1: 성분별 '전부 통과' (adaptive, outward) ===")
    for n, row in res["models"].items():
        cs = row["adaptive"]["components"]
        if not cs:
            print(f"{n}: 성분 없음")
            continue
        tot = sum(c["area"] for c in cs)
        viol = sum(c["outward_violating_area"] or 0 for c in cs)
        print(f"{n}: 성분 {len(cs)}, 전부 통과 {sum(1 for c in cs if c['outward_allows_all'])}/{len(cs)}, "
              f"위반 면적 {viol / tot * 100:.0f}% of 오버행 면적")
    print("\n=== 밴드 구간 (adaptive) ===")
    for n, row in res["models"].items():
        iv = row["adaptive"]["bands"]["intervals"]
        print(f"{n}: " + ", ".join(f"[{a:.1f}, {b:.1f}] {t:+.1f}°" for a, b, t in iv)
              + (f"  블렌드 {row['adaptive']['bands']['blend_mm']:.1f}mm" )
              + ("".join(f"\n    ⚠ {m}" for m in row["adaptive"]["bands"]["notes"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--s3-dir", default=None)
    ap.add_argument("--no-toolpath", action="store_true")
    ap.add_argument("--out", default=os.path.join(_HERE, "results.json"))
    ap.add_argument("--reanalyze", default=None)
    a = ap.parse_args()
    if a.reanalyze:
        report(json.load(open(a.reanalyze)))
        return
    models = a.models or (OUR_MODELS + (S3_MODELS if a.s3_dir else []))
    res = measure(models, a.s3_dir, toolpath=not a.no_toolpath)
    json.dump(res, open(a.out, "w"), indent=1, default=float)
    print(f"→ {a.out}")
    report(res)


if __name__ == "__main__":
    main()
