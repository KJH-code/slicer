"""iou_angle — 퇴적 복원 IoU 대 원뿔각 (mushroom_03, 46 후보: outward/inward × 0~44°).

데이터는 팀 저장소 26037-arch/R-E-second-presentation 의 assets/data/angle-iou.csv,
재실행 3회는 deposition-repeats.csv. 이 저장소에 복사하지 않고 클론한 경로를 인자로 받는다.

    git clone https://github.com/26037-arch/R-E-second-presentation.git ../R-E-second-presentation
    python3 tools/report_figs/iou_angle.py --ext ../R-E-second-presentation
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.report_figs.style import (  # noqa: E402
    COLORS,
    ROOT,
    figure,
    panel_label,
    save,
    setup,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ext", default=str(ROOT.parent / "R-E-second-presentation"))
    ext = Path(ap.parse_args().ext)
    rows = list(csv.DictReader(open(ext / "assets/data/angle-iou.csv", encoding="utf-8")))
    reps = list(csv.DictReader(open(ext / "assets/data/deposition-repeats.csv", encoding="utf-8")))
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ext,
                                     text=True).strip()
    setup()
    fig, (ax, az) = figure("full", 6.8, ncols=2, gridspec_kw={"width_ratios": [1.2, 1]})
    best = None
    for d, c, lab in (("outward", COLORS[0], "outward (+)"), ("inward", COLORS[1], "inward (-)")):
        rr = sorted((float(r["angle_deg"]), float(r["iou"])) for r in rows if r["direction"] == d)
        a, v = np.array(rr).T
        for axx in (ax, az):
            axx.plot(a, v, "-o", color=c, ms=2.5, lw=1.0, label=lab if axx is ax else None)
        i = int(np.argmax(v))
        if best is None or v[i] > best[2]:
            best = (d, a[i], v[i])
    out = {float(r["angle_deg"]): float(r["iou"]) for r in rows if r["direction"] == "outward"}
    ax.axvspan(-0.5, 16.5, color="0.9", lw=0, zorder=0)
    ax.set_xlabel("원뿔각 θ (°)")
    ax.set_ylabel("퇴적 복원 IoU")
    ax.legend(fontsize=7.5, loc="lower left")
    panel_label(ax, "a")
    # (b) 확대 + 재실행 3회를 점 3개로 (가로로 조금씩 벌려 겹침을 보이게)
    for t in sorted({float(r["angle_deg"]) for r in reps}):
        vs = [float(r["iou"]) for r in reps if float(r["angle_deg"]) == t]
        az.plot(t + np.array([-0.3, 0.0, 0.3])[:len(vs)], vs, "D", color="k", ms=3.2,
                mfc="white", mew=0.8, label="재실행 3회" if t == 0.0 else None, zorder=6)
    for t, txt, pos in ((0.0, "0°", (0.4, 0.9276)), (10.0, "10° (최대)", (6.2, 0.9330)),
                        (12.0, "12°", (12.5, 0.9278))):
        az.text(*pos, f"{txt} {out[t]:.4f}", fontsize=7.5)
    az.set_xlim(-1, 16.5)
    az.set_ylim(0.910, 0.936)
    az.set_xticks([0, 2, 4, 6, 8, 10, 12, 14, 16])
    az.set_xlabel("원뿔각 θ (°)")
    az.legend(fontsize=7.5, loc="lower left")
    panel_label(az, "b")
    spread = {}
    for t in sorted({r["angle_deg"] for r in reps}, key=float):
        v = [float(r["iou"]) for r in reps if r["angle_deg"] == t]
        spread[t] = {"n": len(v), "range": max(v) - min(v), "iou": v[0]}
    n_total = len(rows)
    save(fig, "iou_angle", __file__,
         [{"path": "26037-arch/R-E-second-presentation:assets/data/angle-iou.csv", "commit": commit},
          {"path": "26037-arch/R-E-second-presentation:assets/data/deposition-repeats.csv",
           "commit": commit}],
         f"mushroom_03 퇴적 복원 IoU 대 원뿔각 ({n_total} 후보, outward/inward). (b) 0~16° 확대, ◇ = 0·10·12° 재실행 3회(가로로 ±0.3° 벌려 그림)",
         f"최대 {best[0]} {best[1]:.0f}° IoU {best[2]:.4f}; 0° {out[0.0]:.4f}, 12° {out[12.0]:.4f}, "
         f"44° {out[44.0]:.4f}; 재실행 3회 범위 " + ", ".join(f"{k}°: {v['range']:.1e}" for k, v in spread.items()),
         extra={"numbers": {"best": list(map(str, best)), "repeats": spread}})
    print(best, spread)


if __name__ == "__main__":
    main()
