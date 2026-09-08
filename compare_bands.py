"""
compare_bands.py — 복잡도(밴드 수) vs 성능 곡선, 툴패스 실측판.

기존 compare_complexity.py 는 '이상적 추정'(각 밴드를 상수각으로 독립 평가)으로
곡선을 그렸다. 그 추정은 각도를 바꾸는 값(블렌드)을 모른다. 여기서는

  · 밴드 각도를 프로필 단위 J 로 고르고 (블렌드 비용 포함, select_banded_j)
  · 실제로 파이프라인을 돌려 G-code 를 만들고
  · 툴패스 검사기의 **페리미터 미지지 %** 로 잰다

두 축을 같이 본다 — 서포트만 보면 항상 큰 각도가 이기기 때문에, 면적가중
평균 왜곡각 ⟨|θ|⟩ 를 나란히 기록한다.

    python3 compare_bands.py [model.stl]

⚠ 시뮬레이션 경향이며 실물 출력 검증 전 — '증명'이 아니다.
"""

import sys
import time

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from conical.config import (MAX_SPACING_FACTOR, BLEND_SHIFT_RATIO, DEFAULT_K)
from conical.meshio import center_on_axis, RadiusProfile
from conical.varangle import select_banded_j
from compare_waist import waisted_model, run_pipeline, mean_abs_angle

N_BANDS = [1, 2, 3, 4]


def sweep(mesh, k=DEFAULT_K):
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    h = mesh.bounds[1][2] - mesh.bounds[0][2]
    rows = []
    for n in N_BANDS:
        t0 = time.time()
        r = select_banded_j(mesh, k, n, r_max, rp, MAX_SPACING_FACTOR,
)
        t_sel = time.time() - t0
        prof = r["profile_obj"]
        peri, total, fill = run_pipeline(mesh, prof)
        blends = prof.blend_intervals()
        rows.append({
            "n": n, "thetas": r["thetas"], "J": r["J"],
            "uniform_J": r["uniform_J"], "blend_penalty": r["blend_penalty"],
            "n_blends": len(blends),
            "blend_mm": sum(b - a for a, b in blends),
            "peri": peri, "total": total,
            "angle": mean_abs_angle(mesh, prof), "t_sel": t_sel,
        })
    return rows


def main():
    if len(sys.argv) > 1:
        models = [(sys.argv[1],
                   center_on_axis(trimesh.load(sys.argv[1], force="mesh")))]
    else:
        models = [
            ("구 (허리 없음)",
             center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=10.0))),
            ("램프 (허리 있음)", waisted_model()),
        ]

    results = {}
    for name, mesh in models:
        rows = sweep(mesh)
        results[name] = rows
        print("=" * 84)
        print(f"[{name}]  면 {len(mesh.faces):,}  높이 {mesh.bounds[1][2]:.1f}mm")
        print(f"  {'N':>2} | {'선택 각도':<22} | {'페리미터':>8} | {'⟨|θ|⟩':>6} | "
              f"{'J':>6} | {'블렌드':>10} | {'선택':>5}")
        for r in rows:
            th = ",".join(f"{t:.0f}" for t in r["thetas"])
            bl = f"{r['n_blends']}개 {r['blend_mm']:.1f}mm" if r["n_blends"] else "없음"
            print(f"  {r['n']:>2} | [{th:<20}] | {r['peri']:7.2f}% | "
                  f"{r['angle']:5.1f}° | {r['J']:6.2f} | {bl:>10} | {r['t_sel']:4.0f}s")
        best = min(rows, key=lambda r: r["peri"])
        jbest = max(rows, key=lambda r: r["J"])
        print(f"  → 페리미터 최소 N={best['n']} ({best['peri']:.2f}%), "
              f"J 최대 N={jbest['n']} (J={jbest['J']:.2f})")
        # 단조성 점검: N개 밴드는 이웃 밴드를 같은 각도로 두면 N-1개를 흉내낼 수 있으므로
        # J 는 N 에 대해 비감소여야 한다. 다만 밴드 경계(linspace)가 N 마다 달라서
        # 전이 위치가 미세하게 달라지므로, 0.01 미만 차이는 그 잡음으로 본다.
        drops = [(rows[i - 1]["n"], rows[i]["n"],
                  rows[i - 1]["J"] - rows[i]["J"])
                 for i in range(1, len(rows))
                 if rows[i]["J"] < rows[i - 1]["J"] - 0.01]
        if drops:
            print("  ⚠ J가 N에 대해 단조증가하지 않는다 — 밴드를 늘렸는데 손해인 구간:")
            for a, b, d in drops:
                print(f"      N={a} → N={b}: J가 {d:.2f} 감소")
        else:
            gaps = [rows[i]["J"] - rows[i - 1]["J"] for i in range(1, len(rows))]
            print(f"  ✓ J가 N에 대해 비감소 (증분 "
                  f"{', '.join(f'{g:+.3f}' for g in gaps)})")

    fig, axes = plt.subplots(1, len(results), figsize=(6.4 * len(results), 4.4),
                             squeeze=False)
    for ax, (name, rows) in zip(axes[0], results.items()):
        ns = [r["n"] for r in rows]
        ax.plot(ns, [r["peri"] for r in rows], "o-", color="#2e7d32",
                label="unsupported perimeter (%)")
        for r in rows:
            ax.annotate(f"⟨|θ|⟩={r['angle']:.0f}°", (r["n"], r["peri"]),
                        textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=7)
        ax2 = ax.twinx()
        ax2.plot(ns, [r["J"] for r in rows], "s--", color="#4a7ebb", alpha=.75,
                 label="J (objective)")
        ax2.set_ylabel("J", color="#4a7ebb")
        ax.set_xlabel("number of bands N")
        ax.set_ylabel("unsupported perimeter (%)", color="#2e7d32")
        ax.set_xticks(ns)
        ax.set_title("sphere (no waist)" if "구" in name else "lamp (with waist)",
                     fontsize=10)
        ax.margins(y=.22)
    fig.suptitle("complexity (bands) vs performance — measured on the toolpath, "
                 "not the ideal estimate", fontsize=11)
    fig.tight_layout()
    fig.savefig("compare_bands.png", dpi=130)
    print("\n그림 저장: compare_bands.png")
    print("⚠ 시뮬레이션 경향이며 실물 출력 검증 전 — '증명'이 아니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
