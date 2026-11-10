"""critical_angle_hist — 면별 임계각 θ* (analytic.critical_angle) 의 면적 가중 히스토그램.

모델: compare_ceiling.demo_models() 의 sphere, funnel, torus, mushroom + examples/lamp.stl.
각 면은 outward(+)/inward(−) 중 θ*(≤44°) 가 작은 쪽의 부호 있는 각도로 센다. 0°에서 이미 자기지지인 면은 뺀다.
마지막 패널: 0°에서 서포트가 필요한 면 가운데 (i) 0~44°(config.MAX_ANGLE_DEG) 로 풀림,
(ii) 44~90° 에서야 풀림, (iii) 0~90° 어떤 θ 로도 못 풂 — (ii)(iii) 은 g 를 0.05° 격자로 직접 훑어 가름 — 의 면적 비율(모델 전체 면적 %).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from compare_ceiling import demo_models  # noqa: E402
from conical import analytic  # noqa: E402
from conical.config import MAX_ANGLE_DEG  # noqa: E402
from conical.meshio import center_on_axis  # noqa: E402
from tools.report_figs.style import (  # noqa: E402
    COLORS,
    ROOT,
    figure,
    panel_label,
    save,
    setup,
)

NAMES = {"sphere": "구", "funnel": "깔때기(funnel)", "torus": "토러스",
         "mushroom": "버섯", "lamp": "램프(lamp.stl)"}


def models():
    d = demo_models()
    out = {k: d[k] for k in ("sphere", "funnel", "torus", "mushroom")}
    out["lamp"] = trimesh.load(ROOT / "examples/lamp.stl", force="mesh")
    return {k: center_on_axis(m.copy()) for k, m in out.items()}


def signed_theta_star(mesh, amax):
    to = analytic.critical_angle(mesh, "outward", angle_max=amax)
    ti = analytic.critical_angle(mesh, "inward", angle_max=amax)
    need = ~(to == 0.0)                          # 0° 에서 이미 지지되면 두 방향 모두 0
    o = np.where(np.isnan(to), np.inf, to)
    i = np.where(np.isnan(ti), np.inf, ti)
    s = np.where(o <= i, o, -i)
    s[~np.isfinite(o) & ~np.isfinite(i)] = np.nan
    return need, s


def solvable_beyond(mesh, faces, lo, hi=90.0, step=0.05):
    """θ* 가 lo 를 넘는 면이 (lo, hi] 안의 어떤 θ(두 방향)로든 g ≥ κ 가 되는가 — 전수 격자.

    analytic.critical_angle 은 n_r = 0 인 면(평평한 아랫면)을 '도달 불가'로 둔다.
    그 면은 g = n_z·cosθ 라 θ ≥ 45° 에서 풀리는데, 기본 범위 ≤ 44° 안에서는 결론이
    같으므로 함수가 틀린 것은 아니다. 44° 너머는 여기서 직접 g 를 훑어 가른다.
    """
    kappa = -np.sin(np.radians(45.0))
    ok = np.zeros(int(faces.sum()), dtype=bool)
    for d in ("outward", "inward"):
        for t in np.arange(lo, hi + 1e-9, step):
            g = analytic.overhang_score(mesh, float(t), d)[faces]
            ok |= g >= kappa
    return ok


def main():
    setup()
    ms = models()
    fig, axs = figure("full", 11.0, nrows=2, ncols=3)
    axs = axs.ravel()
    bins = np.arange(-90, 90.01, 1.0)
    shares = {}
    for ax, (key, mesh), letter in zip(axs[:5], ms.items(), "abcde", strict=True):
        A = mesh.area_faces
        tot = A.sum()
        need, s44 = signed_theta_star(mesh, float(MAX_ANGLE_DEG))
        ok = need & np.isfinite(s44)
        h, _ = np.histogram(s44[ok], bins=bins, weights=A[ok] / tot * 100)
        ax.bar(bins[:-1], h, width=1.0, align="edge", color=COLORS[0], lw=0)
        for x in (-MAX_ANGLE_DEG, MAX_ANGLE_DEG):
            ax.axvline(x, color="k", ls="--", lw=0.7)
        ax.set_xlim(-50, 50)
        ax.set_xticks([-44, -20, 0, 20, 44])
        ax.text(0.11, 1.02, " " + NAMES[key], transform=ax.transAxes, ha="left", va="bottom")
        ax.set_xlabel("θ* (°, + 바깥 / - 안쪽)")
        ax.set_ylabel("면적 (%)")
        panel_label(ax, letter)
        if not ok.any():
            ax.set_yticks([])
            ax.text(0.5, 0.5, f"0~{MAX_ANGLE_DEG}° 에서 풀리는 면 없음\n"
                    f"(0°에서 필요한 {A[need].sum() / tot * 100:.1f}% 는\n평평한 아랫면 — (f) 참고)",
                    transform=ax.transAxes, ha="center", va="center", fontsize=8)
        rest = need & ~np.isfinite(s44)
        late = np.zeros_like(rest)
        late[rest] = solvable_beyond(mesh, rest, float(MAX_ANGLE_DEG))
        shares[key] = {
            "need0": float(A[need].sum() / tot * 100),
            "in44": float(A[ok].sum() / tot * 100),
            "beyond44": float(A[late].sum() / tot * 100),
            "never": float(A[rest & ~late].sum() / tot * 100),
        }
    ax = axs[5]
    x = np.arange(len(shares))
    b0 = np.array([v["in44"] for v in shares.values()])
    b1 = np.array([v["beyond44"] for v in shares.values()])
    b2 = np.array([v["never"] for v in shares.values()])
    ax.bar(x, b0, color=COLORS[0], label=f"0~{MAX_ANGLE_DEG}° 로 풀림")
    ax.bar(x, b1, bottom=b0, color=COLORS[1], label=f"{MAX_ANGLE_DEG}~90° 에서야 풀림")
    ax.bar(x, b2, bottom=b0 + b1, color=COLORS[3], label="0~90° 어떤 θ 로도 못 풂")
    ax.set_xticks(x)
    ax.set_xticklabels([NAMES[k].split("(")[0] for k in shares], fontsize=6.8)
    ax.set_ylabel("0° 에서 서포트 필요 면적 (%)")
    ax.set_ylim(0, 75)
    ax.legend(fontsize=6.5, loc="upper left")
    ax.grid(axis="x", visible=False)
    panel_label(ax, "f")
    key_txt = "; ".join(f"{NAMES[k]}: 0°필요 {v['need0']:.1f}%, ≤44° {v['in44']:.1f}%, "
                        f"44~90° {v['beyond44']:.1f}%, 불가 {v['never']:.1f}%"
                        for k, v in shares.items())
    save(fig, "critical_angle_hist", __file__,
         ["compare_ceiling.py", "conical/analytic.py", "examples/lamp.stl"],
         "면별 임계각 θ* 면적 가중 히스토그램(부호: + outward, − inward, 0°에서 이미 지지된 면 제외)과 "
         "해결 가능/불가 면적 비율 (모델 전체 면적 %)",
         key_txt, extra={"numbers": shares})
    for k, v in shares.items():
        print(k, {a: round(b, 2) for a, b in v.items()})


if __name__ == "__main__":
    main()
