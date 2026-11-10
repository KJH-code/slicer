"""report_fig_checker.py — 툴패스 검사기 A 의 '지지됨' 정의를 합성 시험으로 확인 (보고서 그림 G).

사전 등록: `docs/test_report_figs_acefg.md` §1.5.

코드에서 읽은 기본값(`conical/toolpath.py`):
  * 샘플 간격 = 압출폭/2 (`sample_extrusions(width=0.45)`)
  * 지지 = 베드(z ≤ 층고 × bed_factor, 기본 1.0) 이거나,
    G-code 순서상 먼저 퇴적된 점이 수평 ≤ 압출폭(0.45mm), 수직 (0, 층고 × vwin_factor(1.5)] 아래에 있음
  * 프레임은 연직(수평 = XY 거리, 수직 = Δz), 낙관(미지지로 퇴적된 재료도 지지 후보), 층 구분 없음
  * '진짜 오버행' = 미지지 페리미터 중 아랫층 단면(페리미터 선 ± 폭/2) 밖 (`classify_unsupported`)

합성 시험: 평면 고리를 층마다 Δr 씩 밖으로, 수직 gap 간격으로 쌓아 `check_support` 를 직접 부른다.
모든 고리를 같은 각도에서 샘플링하므로 이웃 고리의 가장 가까운 점은 정확히 Δr 떨어져 있다.

    python3 report_fig_checker.py
"""

import argparse
import inspect
import json
import math

import numpy as np

from conical import toolpath
from conical.toolpath import check_support

H = 0.3
R0 = 5.0
N_LAYERS = 4


def rings(dr, gap, z0, h=H, n_layers=N_LAYERS, width=0.45):
    """층 k: 반경 R0 + k·dr, 높이 z0 + k·gap. 둘레를 압출폭/2 간격으로 샘플링."""
    n = int(math.ceil(2 * math.pi * (R0 + n_layers * max(dr, 0)) / (width / 2)))
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts, mid, lay = [], [], []
    for k in range(n_layers):
        r = R0 + k * dr
        z = z0 + k * gap
        pts.append(np.c_[r * np.cos(ang), r * np.sin(ang), np.full(n, z)])
        mid.append(np.arange(n) + k * n)
        lay.append(np.full(n, k))
    pts = np.vstack(pts)
    return pts, np.concatenate(mid), np.full(len(pts), width / 2), np.concatenate(lay)


def frac_supported(dr, gap, z0, h=H):
    pts, mid, w, lay = rings(dr, gap, z0, h)
    sup, _ = check_support(pts, mid, w, layer_height=h)
    out = []
    for k in range(N_LAYERS):
        out.append(float(sup[lay == k].mean()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="report_fig_checker_results.json")
    args = ap.parse_args()
    sig = inspect.signature(check_support).parameters
    defaults = {k: sig[k].default for k in ("width", "vwin_factor", "bed_factor",
                                            "require_supported_below", "tool_up", "layer")}
    samp = inspect.signature(toolpath.sample_extrusions).parameters["width"].default
    w = defaults["width"]
    vf = defaults["vwin_factor"]

    # 사전 등록한 여섯 경우 (층 1 = 둘째 고리의 지지 비율; 첫 층 경우는 층 0)
    cases = [
        ("Δr=0.44 (수평 창 안)", dict(dr=0.44, gap=H, z0=H), 1, 1.0),
        ("Δr=0.46 (수평 창 밖)", dict(dr=0.46, gap=H, z0=H), 1, 0.0),
        ("수직 간격 1.49h", dict(dr=0.0, gap=1.49 * H, z0=H), 1, 1.0),
        ("수직 간격 1.51h", dict(dr=0.0, gap=1.51 * H, z0=H), 1, 0.0),
        ("첫 층 z=h (베드)", dict(dr=0.0, gap=H, z0=H), 0, 1.0),
        ("첫 층 z=1.01h", dict(dr=0.0, gap=H, z0=1.01 * H), 0, 0.0),
    ]
    res = []
    for name, kw, layer, expect in cases:
        f = frac_supported(**kw)[layer]
        res.append({"case": name, "params": kw, "layer": layer, "supported_frac": f,
                    "expected": expect, "match": abs(f - expect) < 1e-9})
        print(f"{name:22s} 지지 비율 {f:.3f} (예상 {expect:.0f}) "
              f"{'일치' if abs(f - expect) < 1e-9 else '불일치'}")

    # 그림용 스윕: Δr (gap = h) 와 gap (Δr = 0)
    drs = np.round(np.arange(0.30, 0.601, 0.01), 3)
    gaps = np.round(np.arange(1.20, 1.801, 0.02), 3)
    sweep_dr = [frac_supported(float(d), H, H)[1] for d in drs]
    sweep_gap = [frac_supported(0.0, float(g) * H, H)[1] for g in gaps]

    # 평면 층에서 함의되는 자기지지 오버행각 (연직 기준): tanφ = w / h
    implied = {f"{h:g}": math.degrees(math.atan(w / h)) for h in (0.2, 0.25, 0.3, 0.35, 0.4, 0.5)}
    out = {"defaults": {**{k: (None if v is None else v) for k, v in defaults.items()},
                        "sample_spacing": samp / 2.0, "bed_height_factor": defaults["bed_factor"]},
           "cases": res, "all_match": all(r["match"] for r in res),
           "sweep": {"layer_height": H, "dr": drs.tolist(), "dr_supported": sweep_dr,
                     "gap_over_h": gaps.tolist(), "gap_supported": sweep_gap},
           "implied_planar_overhang_deg": implied,
           "meta": {"prereg": "docs/test_report_figs_acefg.md §1.5", "width": w,
                    "vwin_factor": vf}}
    with open(args.json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("기본값:", out["defaults"])
    print("평면 함의 임계각:", {k: round(v, 1) for k, v in implied.items()})
    print("저장:", args.json, "| 여섯 경우 모두 일치" if out["all_match"] else "| 불일치 있음")


if __name__ == "__main__":
    main()
