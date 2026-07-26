"""
toolpath_check.py — 출력 G-code 의 툴패스 가상 검증 (하드웨어 없이).

검사기 A(기본): 압출 세그먼트 지지 검사 — 미지지 압출 길이 비율(%), 층별 통계,
미지지 지점 산점 PNG(위+옆 2뷰).
검사기 B(--nozzle): 3축 노즐 간섭 검사 (HotendProfile 추정 기하).

    python3 toolpath_check.py out.gcode
    python3 toolpath_check.py out.gcode --nozzle
    python3 toolpath_check.py out.gcode --layer-height 0.4 --width 0.45

⚠ 이 검사는 브리징·수축·유변학을 무시한 기하 판정이며, 메시 기반 예측과 측정
  대상이 다르다(툴패스에는 인필·트래블·시임이 있음) — 절대값이 아니라 각도 간
  순위·경향 비교가 목적이다.
"""

import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from conical import gcode as gc
from conical.toolpath import (sample_extrusions, check_support, check_nozzle,
                              HotendProfile)


def detect_layer_height(lines, fallback=0.3):
    for ln in lines[:20]:
        m = re.search(r"layer_h=([\d.]+)", ln)
        if m:
            return float(m.group(1))
    return fallback


def main():
    ap = argparse.ArgumentParser(description="toolpath virtual checker")
    ap.add_argument("gcode")
    ap.add_argument("--width", type=float, default=0.45)
    ap.add_argument("--layer-height", type=float, default=None)
    ap.add_argument("--nozzle", action="store_true", help="노즐 간섭 검사도 수행")
    ap.add_argument("--png", default=None)
    args = ap.parse_args()

    lines = open(args.gcode).readlines()
    lh = args.layer_height or detect_layer_height(lines)
    items = gc.parse(lines)
    pts, mid, w = sample_extrusions(items, width=args.width)
    if len(pts) == 0:
        raise SystemExit("압출 세그먼트 없음")

    sup, st = check_support(pts, mid, w, layer_height=lh, width=args.width)
    print("=" * 62)
    print(f"[toolpath_check] {args.gcode}  (layer_h={lh}, width={args.width})")
    print(f"  샘플점        : {len(pts):,}  (압출 경로 {w.sum()/1000:.2f} m)")
    print(f"  미지지 압출   : {st['unsupported_pct']:.2f} %  (길이 가중)")
    worst = sorted(st["layers"].items(), key=lambda kv: -kv[1])[:5]
    if worst and worst[0][1] > 0:
        print("  최악 층(z bin → 미지지%): " +
              ", ".join(f"z≈{k * lh:.1f}:{v:.0f}%" for k, v in worst if v > 0))

    if args.nozzle:
        col, ns = check_nozzle(pts, mid, HotendProfile())
        print(f"  노즐 간섭     : {ns['collision_pct']:.2f} % "
              f"(첫 간섭 z={ns['first_collision_z']})"
              "  [HotendProfile은 실측 전 추정값]")

    png = args.png or (Path(args.gcode).stem + "_check.png")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    ok = sup
    for ax, (a, b), name in zip(axes, [(0, 1), (0, 2)], ["top (XY)", "side (XZ)"]):
        ax.scatter(pts[ok][::5, a], pts[ok][::5, b], s=1, c="#9aa7c4", label="supported")
        if (~ok).any():
            ax.scatter(pts[~ok][:, a], pts[~ok][:, b], s=2, c="#d9534f", label="unsupported")
        ax.set_title(name); ax.set_aspect("equal"); ax.legend(fontsize=7)
    fig.suptitle(f"unsupported {st['unsupported_pct']:.2f}%")
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    print(f"  산점 저장     : {png}")
    print("  ⚠ 기하 판정(브리징·수축 무시) — 절대값 아닌 각도 간 경향 비교용")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
