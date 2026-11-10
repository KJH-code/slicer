"""analyze_k_time.py — k 를 '1° 당 출력 시간' 으로 번역해 본다 (사전 등록 `docs/test_k_sweep.md` §1.3 암시 k).

근거: 브랜치 `claude/serene-cray-u07dzk` 의 `report/exp5_angle_cost.json` (REP5X G-code, 층고 0.3,
`motion.plan_motion` 의 되감기 제외 출력 시간). 그 브랜치를 **읽기만** 한다(`git show`).

균일 4~44° 의 시간을 각도에 선형 맞춤해 기울기(분/°)를 얻는다. 0° → 4° 의 점프는 3축 → 5축 전환
고정비라 기울기에서 뺀다. 그리고 J 의 k (%p/°) 를 "서포트 1 %p = 1/k 도 = (1/k)·기울기 분" 으로 적는다.
이것은 해석이지 판정이 아니다.

    python3 analyze_k_time.py
"""

import json
import subprocess
import sys

import numpy as np

from analyze_k_sweep import KS

SRC = "origin/claude/serene-cray-u07dzk:report/exp5_angle_cost.json"


def main():
    raw = subprocess.run(["git", "show", SRC], capture_output=True, text=True, check=True).stdout
    rows = json.loads(raw)
    models = {}
    for r in rows:
        prof = r["profile"]
        if r["label"].startswith("균일") and len(prof) == 1:
            models.setdefault(r["model"], []).append((float(prof[0][1]), float(r["minutes"])))
    out = {"source": SRC, "models": {}}
    slopes = []
    for m, pts in models.items():
        pts.sort()
        a = np.array([p[0] for p in pts])
        t = np.array([p[1] for p in pts])
        sel = a >= 4
        slope, icpt = np.polyfit(a[sel], t[sel], 1)
        t0 = float(t[a == 0][0])
        out["models"][m] = {"angles": a.tolist(), "minutes": t.tolist(),
                            "slope_min_per_deg": float(slope), "intercept_min": float(icpt),
                            "t0_planar_min": t0, "jump_0_to_4_min": float(t[a == 4][0] - t0),
                            "pct_per_deg_of_t4": float(slope / t[a == 4][0] * 100)}
        slopes.append(slope)
    s = float(np.mean(slopes))
    out["slope_mean_min_per_deg"] = s
    out["k_as_minutes_per_pct"] = {f"{k:g}": (None if k == 0 else s / k) for k in KS}
    with open("k_time_results.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    for m, v in out["models"].items():
        print(f"{m}: 기울기 {v['slope_min_per_deg']:.3f} 분/° (4° 시간의 {v['pct_per_deg_of_t4']:.1f}%/°), "
              f"0→4° 점프 {v['jump_0_to_4_min']:.1f} 분")
    print(f"평균 기울기 {s:.3f} 분/° → k 별 '서포트 1 %p 의 값(분)':",
          {k: (None if v is None else round(v, 1)) for k, v in out["k_as_minutes_per_pct"].items()})
    print("저장: k_time_results.json")


if __name__ == "__main__":
    sys.exit(main())
