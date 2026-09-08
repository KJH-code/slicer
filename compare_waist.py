"""
compare_waist.py — 핵심 실험: 부위별 각도(밴드)가 균일 원뿔을 언제 이기는가.

우리 연구 논지는 "모델을 높이 구간으로 나눠 구간마다 최적 각도를 주면 균일
원뿔(RotBot식)보다 낫다"였다. 툴패스 검사기로 실제로 재보니 **조건부로만 참**이다.

    각도를 바꾸려면 블렌드(전이 구간)가 필요하고, 층간격 제약 때문에 그 폭은
        w ≥ r_b · |Δtanθ| / (limit − 1)          (conical/profile.py 유도)
    로 '그 높이의 반경 r_b' 에 비례한다. 즉 **각도 변경의 가격은 그 높이가
    얼마나 뚱뚱한가로 정해진다.** 어디나 뚱뚱한 모델(구)은 블렌드가 모델 높이의
    70% 이상을 잡아먹어 밴드가 손해고, '허리'가 있는 모델(램프)은 목에서 싸게
    각도를 바꿀 수 있어 밴드가 이긴다.

이 스크립트는 두 모델 × 여러 전략을 돌려 그 표를 만든다.

    python3 compare_waist.py            # 구(허리 없음) + 램프(허리 있음)

⚠ 보고 지표는 '페리미터 미지지 %' 다. 전체 미지지 %는 희소 인필(레이어마다
  0/90° 교차 → 원래 브리징)에 지배당해 표면 지지를 가린다 — 이 사실 자체가
  검사기가 잡아낸 측정 결함이었다(docs/verification.md).
"""

import math
import sys
import time

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from conical.meshio import center_on_axis, RadiusProfile
from conical.transform import transform_cone, transform_cone_profile
from conical.planar_slicer import slice_mesh
from conical.backtransform import backtransform
from conical.profile import AngleProfile
from conical.varangle import select_banded, select_banded_j
from conical.selector import select_cone
from conical.toolpath import sample_extrusions, check_support
from conical.config import MAX_SPACING_FACTOR, BLEND_SHIFT_RATIO, DEFAULT_K

LAYER_H = 0.4


def waisted_model():
    """구 + 가는 목(r=2) + 위로 벌어지는 형상. '허리가 있는' 대조 모델."""
    R, ZC = 8.0, 8.0
    t_end = math.pi - math.asin(2.0 / R)          # 구를 r=2 되는 윗지점까지
    pts = [(R * math.sin(t), ZC - R * math.cos(t))
           for t in np.linspace(0, t_end, 60)]
    z_neck = pts[-1][1]
    pts += [(2.0, z) for z in np.linspace(z_neck, 20.0, 8)[1:]]
    pts += [(r, z) for r, z in zip(np.linspace(2.0, 7.0, 12)[1:],
                                   np.linspace(20.0, 30.0, 12)[1:])]
    pts += [(0.0, 30.0)]
    m = trimesh.creation.revolve(np.array(pts), sections=64)
    m.merge_vertices()
    m.fix_normals()
    return center_on_axis(m)


def mean_abs_angle(mesh, spec):
    """면적가중 평균 |θ| (왜곡 비용 축). 고정각이면 그 각도 그대로."""
    if not isinstance(spec, AngleProfile):
        return abs(float(spec))
    areas = mesh.area_faces
    fz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    return float((np.abs(spec.theta_at(fz)) * areas).sum() / areas.sum())


def run_pipeline(mesh, angle_or_profile, direction="outward"):
    """파이프라인 1회 → (페리미터 미지지 %, 전체 미지지 %, 인필 미지지 %)."""
    if isinstance(angle_or_profile, AngleProfile):
        v = transform_cone_profile(mesh.vertices, angle_or_profile, direction)
    elif angle_or_profile > 0:
        v = transform_cone(mesh.vertices, angle_or_profile, direction)
    else:
        v = mesh.vertices
    warped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    items = slice_mesh(warped, layer_height=LAYER_H)
    real, _ = backtransform(items, angle_or_profile, direction)
    pts, mid, w, kinds = sample_extrusions(real, return_types=True)
    sup, st = check_support(pts, mid, w, layer_height=LAYER_H)

    def pct(mask):
        tot = w[mask].sum()
        return (w[mask & ~sup].sum() / tot * 100.0) if tot > 0 else float("nan")

    return pct(kinds == 0), st["unsupported_pct"], pct(kinds == 1)


def strategies(mesh, k=DEFAULT_K):
    """이 모델에 대해 비교할 전략들 → [(이름, 각도 or 프로필, 메모)]."""
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    rp = RadiusProfile(mesh)
    h = mesh.bounds[1][2] - mesh.bounds[0][2]

    best, _ = select_cone(mesh, k, verbose=False)
    banded = select_banded(mesh, k, 2)

    old = AngleProfile.from_banded_result(banded, r_max)            # 층간격 제약 없음
    new = AngleProfile.from_banded_result(
        banded, r_max, radius_profile=rp, spacing_limit=MAX_SPACING_FACTOR,
        max_shift=BLEND_SHIFT_RATIO * h / 2)
    jr = select_banded_j(mesh, k, 2, r_max, rp, MAX_SPACING_FACTOR,
                         BLEND_SHIFT_RATIO * h / 2)

    def blend_note(p):
        iv = p.blend_intervals()
        if not iv:
            return "블렌드 없음(균일로 수렴)"
        (a, b), = iv
        return (f"블렌드 {b-a:.1f}mm, 배율 "
                f"{p.max_spacing_factor(r_max, 'outward', rp):.2f}배")

    return [
        ("평면 (0°)", 0.0, "기준선"),
        (f"균일 {best['angle']:.0f}° (J 자동)", float(best["angle"]),
         f"RotBot식 균일 원뿔, k={k}"),
        ("밴드2 (층간격 제약 없음)", old,
         f"블렌드 {old.blend_intervals()[0][1]-old.blend_intervals()[0][0]:.1f}mm, "
         f"배율 {old.max_spacing_factor(r_max, 'outward', rp):.1f}배"),
        ("밴드2 (층간격 제약)", new,
         blend_note(new) + (f"; {new.notes[0]}" if new.notes else "")),
        ("밴드2 (제약 + J에 블렌드비용)", jr["profile_obj"],
         f"각도 {jr['thetas']}, " + blend_note(jr["profile_obj"])),
    ], rp


def main():
    models = [("구 (허리 없음)",
               center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=10.0))),
              ("램프 (허리 있음)", waisted_model())]
    if len(sys.argv) > 1:
        models = [(sys.argv[1], center_on_axis(trimesh.load(sys.argv[1], force="mesh")))]

    results = {}
    for name, mesh in models:
        rp = RadiusProfile(mesh)
        print("=" * 74)
        print(f"[{name}]  면 {len(mesh.faces):,}  높이 {mesh.bounds[1][2]:.1f}mm  "
              f"최대반경 {rp.global_max:.1f}mm")
        rows = []
        strats, _ = strategies(mesh)
        for label, spec, note in strats:
            t0 = time.time()
            peri, total, fill = run_pipeline(mesh, spec)
            ma = mean_abs_angle(mesh, spec)
            rows.append((label, peri, total, fill, note, ma))
            print(f"  {label:<28} 페리미터 {peri:6.2f}%   평균|θ| {ma:5.1f}°   "
                  f"전체 {total:6.2f}%   ({time.time()-t0:.0f}s)")
            print(f"  {'':<28} └ {note}")
        results[name] = rows

    # 그림: 모델별 페리미터 미지지 막대 (시스템에 한글 폰트가 없어 라벨은 영문 —
    # 저장소의 다른 PNG 들과 같은 관례)
    en = ["planar 0°", "uniform (J)", "banded-2\n(no spacing limit)",
          "banded-2\n(spacing limit)", "banded-2\n(+ blend cost in J)"]
    fig, axes = plt.subplots(1, len(results), figsize=(6.6 * len(results), 4.4))
    axes = np.atleast_1d(axes)
    for ax, (name, rows) in zip(axes, results.items()):
        vals = [r[1] for r in rows]
        angs = [r[5] for r in rows]
        colors = ["#9aa7c4", "#4a7ebb", "#d9534f", "#8bc34a", "#2e7d32"][:len(rows)]
        ax.bar(range(len(vals)), vals, color=colors)
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(en[:len(vals)], fontsize=7)
        ax.set_ylabel("unsupported perimeter (%)")
        ax.set_title("sphere (no waist)" if "구" in name else "lamp (with waist)",
                     fontsize=10)
        for i, (v, a) in enumerate(zip(vals, angs)):
            ax.text(i, v, f"{v:.2f}\n⟨|θ|⟩={a:.0f}°", ha="center", va="bottom",
                    fontsize=7)
        ax.set_ylim(0, max(vals) * 1.25)
    fig.suptitle("per-band angles vs uniform cone — banding wins only where the "
                 "model has a waist  (⟨|θ|⟩ = mean distortion angle)", fontsize=11)
    fig.tight_layout()
    fig.savefig("compare_waist.png", dpi=130)
    print("\n그림 저장: compare_waist.png")
    print("⚠ 시뮬레이션 경향이며 실물 출력 검증 전 — '증명'이 아니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
