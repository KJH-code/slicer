"""
analyze_blend_k.py — J의 '블렌드 비용' 가중치 k_blend 는 얼마여야 하나.

배경: 각도를 바꾸려면 블렌드가 필요하고 그 구간은 층이 벌어진다. 그런데 해석식
판정(analytic)은 면을 '그 높이의 국소 원뿔각'과만 비교해서 이 팽창을 못 본다 —
구 밴드2를 서포트 0.5%로 예측하지만 툴패스로는 균일각에 진다. 그래서 J 에
    blend_cost = Σ (블렌드 구간 표면적 %) × (m−1)/(limit−1)
를 넣고 k_blend 로 무게를 준다. 이 가중은 유도된 물리가 아니라 휴리스틱이므로,
**판단이 뒤집히는 창(window)** 을 실측해서 기본값을 정한다 (analyze_k.py 와 같은 방식).

정답지(툴패스 실측, 페리미터 미지지 %):
  · 구  (허리 없음): 균일 28° 1.08%  <  밴드 4.93%  → 균일이 정답
  · 램프(허리 있음): 균일 24° 3.01%  >  밴드 0.84%  → 부위별이 정답
따라서 올바른 k_blend 는 "구에서는 균일로 수렴, 램프에서는 부위별 유지" 하는 값.

    python3 analyze_blend_k.py

⚠ 두 모델 표본으로 고른 값이다 — 모델이 늘면 재검토 대상.
"""

import sys

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from conical.meshio import center_on_axis, RadiusProfile
from conical.varangle import select_banded_j
from conical.config import (MAX_SPACING_FACTOR, BLEND_SHIFT_RATIO, DEFAULT_K,
                            BLEND_COST_K)
from compare_waist import waisted_model

K_BLENDS = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]


def analyze(mesh, k=DEFAULT_K, n_bands=2):
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    h = mesh.bounds[1][2] - mesh.bounds[0][2]
    out = []
    for kb in K_BLENDS:
        r = select_banded_j(mesh, k, n_bands, r_max, rp, MAX_SPACING_FACTOR,
                            BLEND_SHIFT_RATIO * h / n_bands, k_blend=kb)
        uniform = len(set(r["thetas"])) == 1
        out.append({"k_blend": kb, "thetas": r["thetas"], "uniform": uniform,
                    "J": r["J"], "gain": r["J"] - r["uniform_J"],
                    "blend_penalty": r["blend_penalty"]})
    return out


def main():
    models = [("구 (허리 없음) — 정답: 균일",
               center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=10.0)),
               True),
              ("램프 (허리 있음) — 정답: 부위별", waisted_model(), False)]

    table = {}
    for name, mesh, want_uniform in models:
        rows = analyze(mesh)
        table[name] = (rows, want_uniform)
        print("=" * 78)
        print(f"[{name}]")
        print(f"  {'k_blend':>8} | {'선택 각도':<16} | {'균일?':<5} | "
              f"{'J':>6} | {'균일 대비':>8} | {'블렌드비용':>9} | 판정")
        for r in rows:
            ok = "○" if r["uniform"] == want_uniform else "✗"
            print(f"  {r['k_blend']:8.1f} | {str(r['thetas']):<16} | "
                  f"{'예' if r['uniform'] else '아니오':<5} | {r['J']:6.2f} | "
                  f"{r['gain']:+8.2f} | {r['blend_penalty']:9.1f} |  {ok}")

    # 두 모델이 동시에 맞는 k_blend 창
    good = [kb for kb in K_BLENDS
            if all(next(r for r in rows if r["k_blend"] == kb)["uniform"] == want
                   for rows, want in table.values())]
    print("=" * 78)
    if good:
        print(f"두 모델이 동시에 맞는 k_blend: {good}")
        print(f"  → 기본값 config.BLEND_COST_K = {BLEND_COST_K} "
              f"({'창 안' if BLEND_COST_K in good else '⚠ 창 밖 — 재검토 필요'})")
    else:
        print("⚠ 두 모델을 동시에 맞히는 k_blend 가 없다 — 비용 모형 재설계 필요")
    print("⚠ 표본 2개로 고른 값 — 모델이 늘면 재검토 대상.")

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for (name, (rows, want)), mark in zip(table.items(), ["o", "s"]):
        xs = [r["k_blend"] for r in rows]
        ys = [r["gain"] for r in rows]
        lbl = "sphere (no waist)" if "구" in name else "lamp (with waist)"
        ax.plot(xs, ys, marker=mark, label=lbl)
    ax.axhline(0, color="#888", lw=1, ls="--")
    ax.axvline(BLEND_COST_K, color="#d9534f", lw=1,
               label=f"default k_blend={BLEND_COST_K}")
    ax.set_xlabel("k_blend (blend-cost weight in J)")
    ax.set_ylabel("J(banded) − J(best uniform)")
    ax.set_title("above 0 = banding chosen;  below 0 = falls back to uniform")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig("analyze_blend_k.png", dpi=130)
    print("그림 저장: analyze_blend_k.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
