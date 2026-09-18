"""
compare_bands.py — 복잡도(밴드 수) vs 성능 곡선, 툴패스 실측판.

기존 compare_complexity.py 는 '이상적 추정'(각 밴드를 상수각으로 독립 평가)으로
곡선을 그렸다. 그 추정은 각도를 바꾸는 값(블렌드)을 모른다. 여기서는

  · 밴드 각도를 프로필 단위 J 로 고르고 (블렌드 비용 포함, select_banded_j)
  · 실제로 파이프라인을 돌려 G-code 를 만들고
  · 툴패스 검사기의 **페리미터 미지지 %** 로 잰다

두 축을 같이 본다 — 서포트만 보면 항상 큰 각도가 이기기 때문에, 면적가중
평균 왜곡각 ⟨|θ|⟩ 를 나란히 기록한다.

    python3 compare_bands.py                       # 기본: 구 + 램프, N=1..6
    python3 compare_bands.py --n-max 4             # 곡선을 N=4 까지만
    python3 compare_bands.py model.stl             # 임의 STL
    python3 compare_bands.py sphere waist:4 waist:1    # 절차 생성 모델 섞기
    python3 compare_bands.py --waist-sweep         # 허리 깊이 축으로 표본 확대
    python3 compare_bands.py --replay compare_bands_results.json   # 그림만 다시 그리기

모델 지정자:
    sphere          구 (허리 없음, icosphere r=10)
    waist:<r>       목 반경 r 인 램프형 (r=7 이면 허리 없음, 1 이면 아주 깊은 목)
    lamp            waist:2 의 별칭 (기존 '램프' 모델)
    <경로>.stl      STL 파일

⚠ 시뮬레이션 경향이며 실물 출력 검증 전 — '증명'이 아니다.
"""

import argparse
import json
import math
import os
import time

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from conical.plotstyle import L

from conical.config import (MAX_SPACING_FACTOR, BLEND_SHIFT_RATIO, DEFAULT_K)
from conical.meshio import center_on_axis, RadiusProfile, waist_prominence
from conical.varangle import select_banded_j
from compare_waist import waisted_model, run_pipeline, mean_abs_angle

DEFAULT_N_MAX = 6

# 허리 깊이 축을 훑을 때 쓰는 목 반경들 (7 = 허리 없음 → 1 = 아주 깊은 목).
WAIST_SWEEP = [7.0, 5.0, 3.0, 2.0, 1.0]


def build_model(spec):
    """모델 지정자 → (표시 이름, 메시). 지정자 문법은 모듈 docstring 참조."""
    if spec == "sphere":
        return (L("sphere", "구"),
                center_on_axis(trimesh.creation.icosphere(subdivisions=3,
                                                          radius=10.0)))
    if spec == "lamp":
        spec = "waist:2"
    if spec.startswith("waist:"):
        r_neck = float(spec.split(":", 1)[1])
        return (L(f"waist r={r_neck:g}", f"허리 r={r_neck:g}"),
                waisted_model(r_neck))
    mesh = center_on_axis(trimesh.load(spec, force="mesh"))
    return (os.path.basename(spec), mesh)


def sweep(mesh, n_max, k=DEFAULT_K):
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    rows = []
    for n in range(1, n_max + 1):
        t0 = time.time()
        r = select_banded_j(mesh, k, n, r_max, rp, MAX_SPACING_FACTOR)
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


def print_monotonicity(rows, tol=0.01):
    """J 가 N 에 대해 비감소인지 — 단, **경계가 겹치는 짝에서만** 점검한다.

    원래 논거는 "N개 밴드는 이웃을 같은 각도로 두면 N−1개를 흉내낼 수 있으므로
    J 는 N 에 대해 비감소여야 한다" 였다. 그 논거는 **틀렸다**: 밴드 경계가
    `linspace` 라 N=3 의 경계(33.3%, 66.7%)는 N=4 의 경계(25%, 50%, 75%)에
    하나도 들어 있지 않다. N=4 는 66.7% 에 전이를 놓을 수 없으므로 N=3 의 해를
    **원리적으로 흉내낼 수 없다.**

    실측(허리 r=7 모델): N=3 이 J=1.2826, N=4 는 한 번 꺾는 해를 전수 조사해도
    최대 1.1356 이다(좌표하강이 찾은 값과 동일 — 탐색이 아니라 격자의 문제다).
    같은 해를 N=6 으로 흉내내면(경계가 겹친다) J 차이가 정확히 0.00e+00 이다.

    그래서 흉내내기가 보장되는 짝은 **n 이 m 을 나눌 때뿐**이다(1→2, 2→4, 3→6 …).
    그 짝에서 J 가 줄면 그때는 진짜 결함이다 — 이 점검이 지금까지 계획기 결함
    셋을 잡아낸 방식이 그것이다. 이웃한 N 사이의 감소는 결함이 아니라 격자
    비정합이므로 참고로만 찍는다.
    """
    by_n = {r["n"]: r["J"] for r in rows}
    violations = [(n, m, by_n[n] - by_n[m])
                  for n in by_n for m in by_n
                  if m > n and m % n == 0 and by_n[m] < by_n[n] - tol]
    if violations:
        print("  ⚠ 경계가 겹치는 짝에서 J 가 감소했다 — 흉내내기가 보장되는 자리라 "
              "진짜 결함이다:")
        for a, b, d in sorted(violations):
            print(f"      N={a} → N={b} (N={a} 의 경계가 N={b} 에 포함): J가 {d:.3f} 감소")
    else:
        pairs = sorted((n, m) for n in by_n for m in by_n if m > n and m % n == 0)
        print(f"  ✓ 경계가 겹치는 짝 {len(pairs)}개 전부 비감소 "
              f"({', '.join(f'{a}→{b}' for a, b in pairs)})")

    gaps = [(rows[i - 1]["n"], rows[i]["n"], rows[i]["J"] - rows[i - 1]["J"])
            for i in range(1, len(rows))]
    dips = [(a, b, g) for a, b, g in gaps if g < -tol]
    print(f"    이웃 N 증분: {', '.join(f'{g:+.3f}' for _, _, g in gaps)}")
    if dips:
        print("    (이웃 감소는 결함이 아니라 경계 비정합 — "
              + ", ".join(f"N={a}→{b} {g:+.3f}" for a, b, g in dips) + ")")


def report(name, mesh, rows):
    """한 모델의 표를 찍고, 그 모델의 요약 dict 를 돌려준다."""
    prom, z_w, r_w = waist_prominence(mesh)
    waist_txt = (f"허리 {prom:.2f} (z={z_w:.1f}, r={r_w:.2f})" if prom > 0.01
                 else "허리 없음")
    print("=" * 92)
    print(f"[{name}]  면 {len(mesh.faces):,}  높이 {mesh.bounds[1][2]:.1f}mm  {waist_txt}")
    print(f"  {'N':>2} | {'선택 각도':<26} | {'페리미터':>8} | {'⟨|θ|⟩':>6} | "
          f"{'J':>6} | {'블렌드':>10} | {'선택':>5}")
    for r in rows:
        th = ",".join(f"{t:.0f}" for t in r["thetas"])
        bl = f"{r['n_blends']}개 {r['blend_mm']:.1f}mm" if r["n_blends"] else "없음"
        print(f"  {r['n']:>2} | [{th:<24}] | {r['peri']:7.2f}% | "
              f"{r['angle']:5.1f}° | {r['J']:6.2f} | {bl:>10} | {r['t_sel']:4.0f}s")

    best = min(rows, key=lambda r: r["peri"])
    jbest = max(rows, key=lambda r: r["J"])
    uni = rows[0]
    print(f"  → 페리미터 최소 N={best['n']} ({best['peri']:.2f}%), "
          f"J 최대 N={jbest['n']} (J={jbest['J']:.2f})")
    # 밴드가 균일각을 이겼는가 — J 기준(선택이 실제로 쓰는 축)과 툴패스 기준 둘 다.
    print(f"  → 균일(N=1) 대비: J {uni['J']:.2f}→{jbest['J']:.2f} "
          f"({jbest['J'] - uni['J']:+.2f}), "
          f"페리미터 {uni['peri']:.2f}%→{best['peri']:.2f}% "
          f"({uni['peri'] / best['peri'] if best['peri'] > 0 else float('inf'):.2f}배)")

    print_monotonicity(rows)

    return {"name": name, "prominence": prom, "rows": rows,
            "J_gain": jbest["J"] - uni["J"], "n_best": jbest["n"],
            "peri_uniform": uni["peri"], "peri_best": best["peri"]}


def plot(summaries, path="compare_bands.png"):
    # 축 범위는 모델 간 공유한다 — 값이 전부 같은 패널(구)에서 축이 확대되면
    # 평평한 선이 구조가 있는 것처럼 보인다.
    all_peri = [r["peri"] for s in summaries for r in s["rows"]]
    all_J = [r["J"] for s in summaries for r in s["rows"]]
    ylim_p = (0, max(all_peri) * 1.30)
    ylim_J = (min(0, min(all_J)) * 1.1, max(all_J) * 1.15)

    ncols = min(3, len(summaries))
    nrows = math.ceil(len(summaries) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.0 * ncols, 4.4 * nrows),
                             squeeze=False)
    flat = [ax for row in axes for ax in row]
    for ax in flat[len(summaries):]:
        ax.axis("off")

    for ax, s in zip(flat, summaries):
        rows = s["rows"]
        ns = [r["n"] for r in rows]
        l1, = ax.plot(ns, [r["peri"] for r in rows], "o-", color="#2e7d32",
                      label=L("unsupported perimeter (%)", "페리미터 미지지 (%)"))
        for r in rows:
            ax.annotate(f"{r['angle']:.0f}°", (r["n"], r["peri"]),
                        textcoords="offset points", xytext=(0, 10),
                        ha="center", fontsize=8)
        ax2 = ax.twinx()
        l2, = ax2.plot(ns, [r["J"] for r in rows], "s--", color="#4a7ebb",
                       alpha=.75,
                       label=L("J (objective, higher is better)",
                               "J (평가함수, 클수록 좋음)"))
        ax2.set_ylabel(L("J (objective)", "J (평가함수)"), color="#4a7ebb")
        ax2.set_ylim(*ylim_J)
        ax.set_xlabel(L("number of bands N", "밴드 수 N"))
        ax.set_ylabel(L("unsupported perimeter (%)", "페리미터 미지지 (%)"),
                      color="#2e7d32")
        ax.set_xticks(ns)
        ax.set_ylim(*ylim_p)
        ax.set_title(f"{s['name']}  ·  {L('prominence', '두드러짐')} "
                     f"{s['prominence']:.2f}", fontsize=10)
        ax.legend(handles=[l1, l2], loc="lower left", fontsize=8, framealpha=.9)

    fig.suptitle(L("complexity (bands) vs performance — measured on the toolpath, "
                   "not the ideal estimate",
                   "복잡도(밴드 수) vs 성능 — 이상적 추정이 아니라 툴패스 실측"),
                 fontsize=11)
    # 전체 제목이 첫 줄 패널 제목을 덮지 않게 위쪽을 비워 둔다.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.035 / nrows))
    fig.savefig(path, dpi=130)
    print(f"\n그림 저장: {path}")


def plot_waist_axis(summaries, path="bands_vs_waist.png"):
    """허리 두드러짐 ↔ 밴드의 이득. 표본이 3개 이상일 때만 의미가 있다."""
    order = sorted(summaries, key=lambda s: (s["prominence"], s["J_gain"]))
    x = [s["prominence"] for s in order]
    y = [s["J_gain"] for s in order]
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(x, y, "o-", color="#4a7ebb",
            label=L("J gain over uniform cone", "균일 원뿔 대비 J 이득"))
    ax.axhline(0, color="#999", lw=.8, ls=":")

    # 두드러짐 0.5 아래 구간은 '경향'이라고 부르지 않는다 — 이득이 J 지형의 평평한
    # 구간(0.005 차이로 해를 가른다)과 자릿수가 같고 부호도 뒤섞인다.
    shallow = max([s["J_gain"] for s in order if s["prominence"] < 0.5] or [0])
    ax.axvspan(-0.03, 0.5, color="#bbb", alpha=.18, lw=0)
    ax.annotate(L(f"shallow: gain ≤ {shallow:.2f} — not a trend",
                  f"얕은 구간: 이득 ≤ {shallow:.2f} — 경향이라 부르지 않음"),
                (0.235, max(y) * .92), ha="center", fontsize=8, color="#666")

    # 허리가 없는 모델은 전부 x=0 에 겹친다 — 그 묶음만 라벨을 부채꼴로 편다.
    groups = {}
    for s in order:
        groups.setdefault(round(s["prominence"], 3), []).append(s)
    for members in groups.values():
        n = len(members)
        for i, s in enumerate(members):
            dx = 0 if n == 1 else (i - (n - 1) / 2) * 86
            dy = 14 + (i % 2) * 26 if n > 1 else 12
            ax.annotate(f"{s['name']}\nN*={s['n_best']}",
                        (s["prominence"], s["J_gain"]),
                        textcoords="offset points", xytext=(dx, dy),
                        ha="center", fontsize=7.5,
                        arrowprops=dict(arrowstyle="-", lw=.5, color="#aaa",
                                        shrinkA=0, shrinkB=2))
    ax.set_xlim(-0.05, 0.95)
    ax.set_xlabel(L("waist prominence  1 − r(z*)/min(max below, max above)",
                    "허리 두드러짐  1 − r(z*)/min(아래 최대, 위 최대)"))
    ax.set_ylabel(L("J gain over uniform cone", "균일 원뿔 대비 J 이득"))
    ax.set_title(L("the deeper the waist, the more bands gain over a uniform cone",
                   "허리가 깊을수록 밴드가 균일 원뿔보다 얻는 것이 커진다"),
                 fontsize=11)
    ax.legend(fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"그림 저장: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*",
                    help="모델 지정자 (sphere / waist:<r> / lamp / *.stl)")
    ap.add_argument("--n-max", type=int, default=DEFAULT_N_MAX,
                    help=f"밴드 수 곡선의 끝 (기본 {DEFAULT_N_MAX})")
    ap.add_argument("--waist-sweep", action="store_true",
                    help=f"허리 깊이 축으로 표본 확대 (목 반경 {WAIST_SWEEP})")
    ap.add_argument("--out", default="compare_bands.png")
    ap.add_argument("--results", default="compare_bands_results.json",
                    help="측정 결과를 남길 JSON (그림만 다시 그릴 때 --replay 로 읽는다)")
    ap.add_argument("--replay", metavar="JSON",
                    help="측정을 다시 하지 않고 저장된 결과로 그림만 다시 그린다. "
                         "스윕이 수십 분 걸리므로 라벨·축을 손볼 때 쓴다")
    args = ap.parse_args()

    if args.replay:
        with open(args.replay, encoding="utf-8") as f:
            summaries = json.load(f)
        print(f"측정 없이 {args.replay} 로 다시 그린다 (모델 {len(summaries)}개)")
    else:
        specs = list(args.models)
        if args.waist_sweep:
            specs = ["sphere"] + [f"waist:{r:g}" for r in WAIST_SWEEP] + specs
        if not specs:
            specs = ["sphere", "lamp"]

        summaries = []
        for spec in specs:
            name, mesh = build_model(spec)
            summaries.append(report(name, mesh, sweep(mesh, args.n_max)))

        with open(args.results, "w", encoding="utf-8") as f:
            json.dump(summaries, f, ensure_ascii=False, indent=1, default=float)
        print(f"\n측정 결과 저장: {args.results}")

    plot(summaries, args.out)
    if len(summaries) >= 3:
        # 두 번째 그림은 --out 과 같은 폴더에 둔다 (스크래치로 뽑을 때 레포를 안 건드리게).
        root, ext = os.path.splitext(args.out)
        plot_waist_axis(summaries, f"{os.path.dirname(root) or '.'}/bands_vs_waist{ext}")

    print("\n" + "=" * 92)
    print(f"  {'모델':<18} | {'허리':>5} | {'N*':>3} | {'균일 J':>7} | {'최선 J':>7} "
          f"| {'J 이득':>7} | {'페리미터 균일→최선':>20}")
    for s in summaries:
        uni, best = s["rows"][0], max(s["rows"], key=lambda r: r["J"])
        print(f"  {s['name']:<18} | {s['prominence']:5.2f} | {s['n_best']:>3} | "
              f"{uni['J']:7.2f} | {best['J']:7.2f} | {s['J_gain']:+7.2f} | "
              f"{s['peri_uniform']:8.2f}% → {s['peri_best']:.2f}%")
    print("⚠ 시뮬레이션 경향이며 실물 출력 검증 전 — '증명'이 아니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
