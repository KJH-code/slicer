"""
compare_dof_ladder.py — 자유도 사다리: 평면(0) → 균일 원뿔(1) → θ(z) 밴드(N) →
축 위치(N+2) → 변형장 천장(S³ 결과물 / S4 실행). 같은 모델·같은 자로 남은 서포트 %.

판정 기준은 **결과를 보기 전에** docs/dof_ladder.md 에 적었다. 이 스크립트의
`judge()` 는 그 문서의 문턱을 그대로 코드로 옮긴 것이고, 문서를 안 고치면 여기도
안 고친다. 측정(`measure`)과 판정(`judge`/`report`)은 분리돼 있어 저장된 JSON 으로
다시 판정할 수 있다 — 지난 실험에서 판정 문구가 두 번 틀렸던 교훈
(docs/verification.md 2026-09-28).

    python3 compare_dof_ladder.py --s3-dir <S³ 데이터>            # 우리 모델 + S³ 모델 6개
    python3 compare_dof_ladder.py --s3-dir <S³ 데이터> --models teapot ring
    python3 compare_dof_ladder.py --s4 s4_results.json ...         # S4 천장(우리 모델) 합치기
    python3 compare_dof_ladder.py --reanalyze dof_ladder_results.json   # 판정·그림만

S³ 데이터는 `bash tools/fetch_s3_dataset.sh <dir>` 로 받는다 (저장소에 안 넣는다).

자 (docs/dof_ladder.md §2): g = n̂·b̂ < −sin45° 면 서포트, 면적 %. 바닥 접촉 면은
양쪽에서 뺀다. outward 만, 최대각 44°, k=0.2, k_blend=0.1, 층간격 상한 1.5.
"""

import argparse
import json
import os
import time

import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from compare_waist import waisted_model
from conical.config import DEFAULT_K, MAX_ANGLE_DEG, MAX_SPACING_FACTOR
from conical.meshio import RadiusProfile, center_on_axis
from conical.plotstyle import L
from conical.s3io import (
    bed_contact_mask,
    cone_dirs,
    face_build_dirs,
    load_s3_model,
    load_waypoints,
    profile_dirs,
    support_fraction_dirs,
)
from conical.varangle import select_banded_j, select_uniform

OUR_MODELS = ["sphere", "lamp", "waist:3", "waist:7", "funnel"]
S3_MODELS = ["ring", "teapot", "bunny_cut6", "topopt_new4", "armadillo4", "AnkleBaseV1"]
ANGLES = list(range(0, int(MAX_ANGLE_DEG) + 1, 2))
BANDS = (2, 3, 4)

# 천장 데이터 유효 조건 (docs/dof_ladder.md §4) — 수치를 보고 바꾸지 않는다
VALID_SIGN = 0.95
VALID_DIST_MEDIAN = 1.0
VALID_DIST_P95 = 3.0
# 축 위치 격자: 모델 최대 반경의 ±AXIS_RANGE 안 AXIS_GRID×AXIS_GRID
AXIS_RANGE = 0.30
AXIS_GRID = 5


# ─────────────────────────────────────────────────────────────
# 모델
# ─────────────────────────────────────────────────────────────
def build_model(spec, s3_dir):
    if spec == "sphere":
        return center_on_axis(trimesh.creation.icosphere(subdivisions=3, radius=10.0))
    if spec == "lamp":
        return waisted_model(2.0)
    if spec.startswith("waist:"):
        return waisted_model(float(spec.split(":", 1)[1]))
    if spec == "funnel":
        return center_on_axis(trimesh.load("examples/funnel.stl", force="mesh"))
    if spec in S3_MODELS:
        if not s3_dir:
            raise SystemExit(f"{spec}: --s3-dir 가 필요하다 (tools/fetch_s3_dataset.sh)")
        return center_on_axis(load_s3_model(os.path.join(s3_dir, f"{spec}.tet")))
    return center_on_axis(trimesh.load(spec, force="mesh"))


# ─────────────────────────────────────────────────────────────
# 측정
# ─────────────────────────────────────────────────────────────
def _pct(mesh, dirs, bed):
    return support_fraction_dirs(mesh, dirs, exclude=bed)


def _mean_abs_theta(mesh, profile):
    """면적가중 평균 |θ| (왜곡 축). 프로필은 축상 근사로 조회."""
    cz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    th = np.abs(np.asarray(profile.theta_at(cz), dtype=float))
    return float((th * mesh.area_faces).sum() / mesh.area_faces.sum())


def uniform_sweep(mesh, bed):
    return {a: _pct(mesh, cone_dirs(mesh, float(a)), bed) for a in ANGLES}


BAND2_BOUNDARIES = (0.2, 0.35, 0.5, 0.65, 0.8)     # 모델 높이 비율


def band2_min(mesh, bed, rp, r_max):
    """N=2 의 **능력** 칸: (θ₁, θ₂) 2° 격자 × 경계 5 위치 전수, 층간격 제약을
    만족하는 프로필 중 서포트 최소. J 가 고른 것(`band2_J`)과 달리 각도 비용이
    없다 — 균일 최소 칸의 밴드판이다. 블렌드 폭은 계획기 규칙 그대로
    (`AngleProfile.from_bands`, 반경 프로필·경계 이동 포함)."""
    from conical.config import BLEND_SHIFT_RATIO
    from conical.profile import AngleProfile
    z0, z1 = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    h = z1 - z0
    best = None
    for fb in BAND2_BOUNDARIES:
        zb = z0 + fb * h
        for t1 in ANGLES:
            for t2 in ANGLES:
                if t1 == t2:
                    continue        # 균일은 uniform_min 이 이미 잰다
                try:
                    prof = AngleProfile.from_bands(
                        [(z0, zb, float(t1)), (zb, z1, float(t2))], r_max,
                        radius_profile=rp, spacing_limit=MAX_SPACING_FACTOR,
                        max_shift=BLEND_SHIFT_RATIO * h)
                except ValueError:
                    continue
                s = _pct(mesh, profile_dirs(mesh, prof), bed)
                key = (s, abs(t1) + abs(t2))
                if best is None or key < best[0]:
                    best = (key, {"thetas": [float(t1), float(t2)], "boundary_frac": fb,
                                  "support": s, "mean_abs_theta": _mean_abs_theta(mesh, prof),
                                  "blend_mm": float(sum(b - a for a, b in prof.blend_intervals()))})
    return best[1] if best else None


def measure_rungs(mesh, bands=BANDS):
    """한 메시(축 고정)에서 우리 칸 전부."""
    bed = bed_contact_mask(mesh)
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    out = {"planar": _pct(mesh, cone_dirs(mesh, 0.0), bed)}
    t0 = time.time()
    out["band2_min"] = band2_min(mesh, bed, rp, r_max)
    out["band2_min"]["t_sec"] = time.time() - t0
    sw = uniform_sweep(mesh, bed)
    a_min = min(sw, key=lambda a: (sw[a], a))
    out["uniform_sweep"] = {str(a): v for a, v in sw.items()}
    out["uniform_min"] = {"theta": float(a_min), "support": sw[a_min],
                          "mean_abs_theta": float(a_min)}
    u = select_uniform(mesh, DEFAULT_K)
    a_j = float(u["profile"][0][0])
    out["uniform_J"] = {"theta": a_j, "support": _pct(mesh, cone_dirs(mesh, a_j), bed),
                        "mean_abs_theta": a_j}
    for n in bands:
        t0 = time.time()
        r = select_banded_j(mesh, DEFAULT_K, n, r_max, rp, MAX_SPACING_FACTOR)
        prof = r["profile_obj"]
        out[f"band{n}_J"] = {
            "thetas": [float(t) for t in r["thetas"]],
            "support": _pct(mesh, profile_dirs(mesh, prof), bed),
            "mean_abs_theta": _mean_abs_theta(mesh, prof),
            "blend_mm": float(sum(b - a for a, b in prof.blend_intervals())),
            "t_sec": time.time() - t0,
        }
    return out


def measure_axis_rung(mesh, band_n=2):
    """축 위치 칸: (x₀,y₀) 격자에서 균일 최소 칸이 가장 낮은 축을 고른 뒤,
    그 축에서 밴드 N 도 한 번 더 고른다. 격자 전체의 균일 최소값을 함께 남긴다."""
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    offs = np.linspace(-AXIS_RANGE * r_max, AXIS_RANGE * r_max, AXIS_GRID)
    grid = []
    best = None
    for x0 in offs:
        for y0 in offs:
            m = mesh.copy()
            m.apply_translation([-x0, -y0, 0.0])
            bed = bed_contact_mask(m)
            sw = uniform_sweep(m, bed)
            a = min(sw, key=lambda k: (sw[k], k))
            grid.append({"x0": float(x0), "y0": float(y0), "theta": float(a),
                         "support": sw[a]})
            if best is None or sw[a] < best["support"] - 1e-12:
                best = dict(grid[-1])
    m = mesh.copy()
    m.apply_translation([-best["x0"], -best["y0"], 0.0])
    bed = bed_contact_mask(m)
    rp = RadiusProfile(m)
    rm = float(np.hypot(m.vertices[:, 0], m.vertices[:, 1]).max())
    r = select_banded_j(m, DEFAULT_K, band_n, rm, rp, MAX_SPACING_FACTOR)
    prof = r["profile_obj"]
    b2 = band2_min(m, bed, rp, rm)
    b2.update({"x0": best["x0"], "y0": best["y0"]})
    return {
        "grid": grid, "best": best,
        "axis_band2_min": b2,
        "axis_uniform_min": {"x0": best["x0"], "y0": best["y0"],
                             "theta": best["theta"], "support": best["support"],
                             "mean_abs_theta": best["theta"]},
        f"axis_band{band_n}_J": {
            "x0": best["x0"], "y0": best["y0"],
            "thetas": [float(t) for t in r["thetas"]],
            "support": _pct(m, profile_dirs(m, prof), bed),
            "mean_abs_theta": _mean_abs_theta(m, prof),
        },
    }


def measure_s3_ceiling(mesh, s3_dir, name):
    """S³ 결과물(웨이포인트 법선)을 면에 최근접 매핑해 같은 자로 잰다.

    ⚠ `center_on_axis` 가 XY 를 옮겼으므로 웨이포인트도 같은 양만큼 옮겨야 한다.
      load_s3_model 은 바닥만 z=0 으로 옮기고 XY 는 그대로이므로, 여기서 원본
      경계 메시를 다시 읽어 그 바운딩박스 중심으로 웨이포인트를 옮긴다.
    """
    raw = load_s3_model(os.path.join(s3_dir, f"{name}.tet"))
    lo, hi = raw.bounds
    shift = np.array([-0.5 * (lo[0] + hi[0]), -0.5 * (lo[1] + hi[1]), -lo[2]])
    wp = load_waypoints(os.path.join(s3_dir, f"wp_{name}"))
    # load_s3_model 이 z 를 −lo[2] 만큼 옮겼으나 wp 는 아직 원본 Z-위 좌표다
    wp["points"] = wp["points"] + np.array([shift[0], shift[1], 0.0])
    dirs, dist = face_build_dirs(mesh, wp)
    bed = bed_contact_mask(mesh)
    med, p95 = float(np.median(dist)), float(np.percentile(dist, 95))
    sign = float(wp["sign_evidence"])
    valid = (abs(sign) >= VALID_SIGN and med <= VALID_DIST_MEDIAN
             and p95 <= VALID_DIST_P95)
    return {"support": _pct(mesh, dirs, bed), "dist_median": med, "dist_p95": p95,
            "sign_evidence": sign, "n_waypoints": int(len(wp["points"])),
            "n_layers": wp["n_layers"], "valid": bool(valid),
            # 둘째 축 재료: 면별 빌드 방향의 수직 기울기 (면적가중 평균, 도)
            "mean_tilt_deg": float((np.degrees(np.arccos(np.clip(dirs[:, 2], -1, 1)))
                                    * mesh.area_faces).sum() / mesh.area_faces.sum())}


def measure(models, s3_dir, s4_path, axis=True):
    res = {"meta": {"angles": ANGLES, "bands": list(BANDS), "k": DEFAULT_K,
                    "spacing_limit": MAX_SPACING_FACTOR, "axis_range": AXIS_RANGE,
                    "axis_grid": AXIS_GRID, "ruler": "n·b < -sin45, bed excluded"},
            "models": {}}
    s4 = json.load(open(s4_path)) if s4_path else {}
    for spec in models:
        t0 = time.time()
        mesh = build_model(spec, s3_dir)
        bed = bed_contact_mask(mesh)
        row = {"faces": int(len(mesh.faces)),
               "bed_pct": float(mesh.area_faces[bed].sum() / mesh.area_faces.sum() * 100),
               "extent": [float(x) for x in (mesh.bounds[1] - mesh.bounds[0])]}
        row.update(measure_rungs(mesh))
        if axis:
            row["axis"] = measure_axis_rung(mesh)
        if spec in S3_MODELS:
            row["s3"] = measure_s3_ceiling(mesh, s3_dir, spec)
        if spec in s4:
            row["s4"] = s4[spec]
        row["t_sec"] = time.time() - t0
        res["models"][spec] = row
        print(f"[{spec}] {time.time() - t0:.0f}s  planar {row['planar']:.2f}  "
              f"uniform_min {row['uniform_min']['theta']:.0f}°→{row['uniform_min']['support']:.2f}  "
              f"band2_min {row['band2_min']['support']:.2f} band2_J {row['band2_J']['support']:.2f}"
              + (f"  axis {row['axis']['axis_uniform_min']['support']:.2f}" if axis else "")
              + (f"  S³ {row['s3']['support']:.2f} (valid={row['s3']['valid']})" if "s3" in row else "")
              + (f"  S4 {row['s4']['support']:.2f}" if "s4" in row else ""),
              flush=True)
    return res


# ─────────────────────────────────────────────────────────────
# 판정 — docs/dof_ladder.md §4~§6 의 문턱을 그대로
# ─────────────────────────────────────────────────────────────
RUNG_ORDER = ["planar", "uniform_min", "band2_min", "uniform_J", "band2_J", "band3_J",
              "band4_J", "axis_uniform_min", "axis_band2_min", "axis_band2_J", "ceiling"]
# 능력 선(각도 비용 없음, 전수) 과 실제 선(J 가 고름)
CAPABILITY = ["planar", "uniform_min", "band2_min", "axis_uniform_min", "axis_band2_min", "ceiling"]
PRACTICE = ["planar", "uniform_J", "band2_J", "band3_J", "band4_J", "axis_band2_J"]


def rung_support(row, rung):
    if rung == "planar":
        return row["planar"]
    if rung.startswith("axis_"):
        return row["axis"][rung]["support"] if "axis" in row else None
    if rung == "ceiling":
        c = ceiling(row)
        return c["support"] if c else None
    return row[rung]["support"] if rung in row else None


def ceiling(row):
    """그 모델에서 쓸 수 있는 천장 중 낮은 쪽 (유효한 것만)."""
    cands = []
    if "s3" in row and row["s3"]["valid"]:
        cands.append(("S³", row["s3"]["support"]))
    if "s4" in row and row["s4"].get("valid", True):
        cands.append(("S4", row["s4"]["support"]))
    if not cands:
        return None
    src, s = min(cands, key=lambda c: c[1])
    return {"source": src, "support": s}


def achievement(row, rung):
    """A = (S_평면 − S_칸) / (S_평면 − S_천장)."""
    c = ceiling(row)
    s = rung_support(row, rung)
    if c is None or s is None:
        return None
    den = row["planar"] - c["support"]
    if den <= 1e-9:
        return None
    return (row["planar"] - s) / den


def judge(res):
    """문서 §5 의 H1~H6 과 §6 표를 코드로. 반환: 사람이 읽는 줄 목록 + 표."""
    rows = res["models"]
    lines, table = [], {}
    for name, row in rows.items():
        t = {r: rung_support(row, r) for r in RUNG_ORDER}
        t["A"] = {r: achievement(row, r) for r in RUNG_ORDER if r != "planar"}
        t["ceiling_info"] = ceiling(row)
        if "s3" in row:
            s3 = row["s3"]
            t["s3_valid"] = s3["valid"]
            why = []
            if abs(s3["sign_evidence"]) < VALID_SIGN:
                why.append(f"첫 층 법선 |{s3['sign_evidence']:.3f}| < {VALID_SIGN}")
            if s3["dist_median"] > VALID_DIST_MEDIAN:
                why.append(f"거리 중앙값 {s3['dist_median']:.2f} > {VALID_DIST_MEDIAN}")
            if s3["dist_p95"] > VALID_DIST_P95:
                why.append(f"거리 95% {s3['dist_p95']:.2f} > {VALID_DIST_P95}")
            if s3["support"] > row["planar"] + 1e-9:
                why.append("S³ 칸이 평면보다 높다 (매핑 오류)")
                t["s3_valid"] = False
            t["s3_invalid_why"] = why
        table[name] = t

    s3_rows = {n: t for n, t in table.items() if n in S3_MODELS and t.get("s3_valid")}
    n_s3 = len(s3_rows)
    lines.append(f"유효한 S³ 모델 {n_s3}/{sum(1 for n in rows if n in S3_MODELS)}"
                 + "".join(f"  ⚠ {n} 무효: {'; '.join(table[n]['s3_invalid_why'])}"
                           for n in rows if n in S3_MODELS and not table[n].get("s3_valid")))
    # H1
    h1 = [n for n, t in s3_rows.items() if t["ceiling_info"]["support"] > 2.0]
    h1_txt = ", ".join(f"{n} {s3_rows[n]['ceiling_info']['support']:.2f}%" for n in h1)
    lines.append("H1 (S³ 천장 ≤ 2%): " + ("성립" if not h1 else
                 f"**깨짐** — {h1_txt} → 다목적 결과물이거나 매핑 문제. "
                 "'S³ 의 한계' 로 읽지 않는다"))
    # H2
    pred = {"teapot": (0.5, 0.7), "bunny_cut6": (0.3, 0.5), "armadillo4": (0.3, 0.5),
            "topopt_new4": (0.2, 0.4), "ring": (0.2, 0.4), "AnkleBaseV1": (0.3, 0.5)}
    a_uni = {n: t["A"]["uniform_min"] for n, t in s3_rows.items()
             if t["A"]["uniform_min"] is not None}
    hits = [n for n, a in a_uni.items() if pred[n][0] <= a <= pred[n][1]]
    lines.append("H2 (균일 최소 달성률 예측 구간): "
                 + ", ".join(f"{n} {a:.2f}{'✓' if n in hits else '✗'}[{pred[n][0]}~{pred[n][1]}]"
                             for n, a in a_uni.items())
                 + f"  → {len(hits)}/{len(a_uni)} 적중")
    hi = sum(1 for a in a_uni.values() if a >= 0.7)
    lo = sum(1 for a in a_uni.values() if a <= 0.2)
    if hi >= 4:
        lines.append("  §6: H2 가 **위로** 틀림 (A≥0.7 이 4+ ) → 비축대칭에서도 경량으로 충분. "
                     "판별기 문턱을 올리고 'S³ 의 절반' 을 '대부분' 으로 고친다")
    if lo >= 4:
        lines.append("  §6: H2 가 **아래로** 틀림 (A≤0.2 이 4+) → 축 위치·θ(z,φ) 없이는 "
                     "이 부류를 적용 범위 밖으로 선언")
    # H3
    gains = {}
    for n, t in s3_rows.items():
        a1, a2 = t["A"]["uniform_min"], t["A"]["band2_min"]
        aj = t["A"]["uniform_J"]
        a4 = max(t["A"][f"band{k}_J"] or -1 for k in BANDS)
        if a1 is not None and a2 is not None and aj is not None:
            gains[n] = (a2 - a1, a4 - aj)
    bad = [n for n, (gc, _) in gains.items() if gc > (0.15 if n == "teapot" else 0.10)]
    lines.append("H3 (밴드 추가 달성률 — 능력선 band2_min−uniform_min / 실제선 bandN_J−uniform_J): "
                 + ", ".join(f"{n} {gc:+.2f}/{gj:+.2f}" for n, (gc, gj) in gains.items())
                 + ("  → 성립" if not bad else f"  → **깨짐** ({', '.join(bad)})"))
    if any(gc > 0.20 for gc, _ in gains.values()):
        lines.append("  §6: 어느 모델에서 밴드 추가 이득 > 0.20 → 높이 밴드가 비축대칭에서도 "
                     "값이 있다(놀라움). 밴드 경계와 오버행 높이 분포를 대조해 적을 것")
    # H4
    ax = {n: (t["A"]["axis_uniform_min"] or 0) - (t["A"]["uniform_min"] or 0)
          for n, t in s3_rows.items() if t["A"].get("axis_uniform_min") is not None}
    if ax:
        top = max(ax, key=ax.get)
        lines.append("H4 (축 위치 이득): " + ", ".join(f"{n} {g:+.2f}" for n, g in ax.items())
                     + f"  → 최대 {top} ({'예측 적중' if top in ('bunny_cut6', 'topopt_new4') else '예측 빗나감'})")
        if max(ax.values()) > 0.20:
            lines.append("  §6: 축 위치 이득 > 0.20 → 다음 자유도는 θ(z,φ) 보다 **축 선택**이 먼저")
        if all(g < 0.05 for g in ax.values()) and len(ax) == 6:
            lines.append("  §6: 축 위치 이득 < 0.05 가 6/6 → 사다리에서 그 칸을 뺀다")
    # H5
    ours = {n: t for n, t in table.items() if n in OUR_MODELS}
    s4s = {n: rows[n]["s4"]["support"] for n in ours if "s4" in rows[n]}
    lines.append("H5 (우리 모델 S4 천장 = 0.0%): "
                 + (", ".join(f"{n} {s:.2f}" for n, s in s4s.items()) if s4s else "S4 없음 (빈칸)"))
    # H6 / 철회 조건
    outside = [n for n, a in a_uni.items() if a < 0.2 or a > 0.8]
    if a_uni:
        med = float(np.median(list(a_uni.values())))
        lines.append(f"H6 (균일 달성률 중앙값 0.3~0.5, S³ 까지 격차 ≥ 0.3): 중앙값 {med:.2f}, "
                     f"밖(A<0.2 또는 >0.8) {len(outside)}/{len(a_uni)}"
                     + ("  → **'절반 안팎' 철회**, 모델별로 적는다" if len(outside) >= 4 else "  → 유지"))
    return lines, table


def report(res, png="dof_ladder.png"):
    lines, table = judge(res)
    print("\n=== 판정 (docs/dof_ladder.md §5~§6) ===")
    for ln in lines:
        print(ln)
    print("\n=== 남은 서포트 % (바닥 제외) ===")
    hdr = ["모델"] + RUNG_ORDER
    print(" | ".join(hdr))
    for n, t in table.items():
        cells = [n] + [("—" if t[r] is None else f"{t[r]:.2f}") for r in RUNG_ORDER]
        if t["ceiling_info"]:
            cells[-1] += f"({t['ceiling_info']['source']})"
        print(" | ".join(cells))
    print("\n=== 둘째 축: 빌드 방향의 면적가중 평균 기울기 (도) — 우리 칸은 평균|θ|, 천장은 arccos(b_z) ===")
    for n, t in table.items():
        row = res["models"][n]
        vals = []
        for r in RUNG_ORDER:
            if r in ("planar", "ceiling"):
                continue
            d = row["axis"].get(r) if r.startswith("axis_") else row.get(r)
            vals.append(f"{r}={d['mean_abs_theta']:.1f}" if d and d.get("mean_abs_theta") is not None else f"{r}=—")
        c = t["ceiling_info"]
        if c:
            src = row["s3"] if c["source"] == "S³" else row["s4"]
            vals.append(f"ceiling={src.get('mean_tilt_deg', float('nan')):.1f}({c['source']})")
        print(n, " ".join(vals))
    print("\n=== 달성률 A ===")
    for n, t in table.items():
        print(n, " ".join(f"{r}={t['A'][r]:.2f}" if t["A"].get(r) is not None else f"{r}=—"
                          for r in RUNG_ORDER if r != "planar"))
    plot(res, table, png)
    return lines, table


def plot(res, table, png):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    rungs = CAPABILITY
    labels = [L("planar", "평면"), L("uniform", "균일"), "N=2",
              L("axis", "축위치"), L("axis+N2", "축+N2"), L("ceiling", "천장")]
    x = np.arange(len(rungs))
    for n, t in table.items():
        ys = [t[r] if t[r] is not None else np.nan for r in rungs]
        line, = axes[0].plot(x, ys, marker="o", label=n)
        a = [t["A"].get(r) if r != "planar" else 0.0 for r in rungs]
        axes[1].plot(x, [np.nan if v is None else v for v in a], marker="o",
                     color=line.get_color(), label=n)
        # 실제 선(J): 균일 J, 밴드2 J 를 같은 색 점선으로
        pj = [t["planar"], t["uniform_J"], t["band2_J"], np.nan,
              t["axis_band2_J"] if t["axis_band2_J"] is not None else np.nan, np.nan]
        axes[0].plot(x, pj, ls=":", marker="x", color=line.get_color(), alpha=0.7)
    for ax, yl in ((axes[0], L("remaining support % (bed excluded)", "남은 서포트 % (바닥 제외)")),
                   (axes[1], L("achievement A", "달성률 A"))):
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=20)
        ax.set_ylabel(yl)
        ax.grid(alpha=0.3)
    axes[1].axhline(1.0, color="k", lw=0.8, ls="--")
    axes[0].legend(fontsize=8)
    axes[0].set_title(L("DOF ladder (solid: capability, dotted: J-chosen)",
                        "자유도 사다리 (실선: 능력, 점선: J 선택)"))
    fig.tight_layout()
    fig.savefig(png, dpi=130)
    print(f"→ {png}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=OUR_MODELS + S3_MODELS)
    ap.add_argument("--s3-dir", default=None)
    ap.add_argument("--s4", default=None, help="S4 실행 결과 JSON (tools/run_s4_ceiling.py)")
    ap.add_argument("--no-axis", action="store_true")
    ap.add_argument("--out", default="dof_ladder_results.json")
    ap.add_argument("--png", default="dof_ladder.png")
    ap.add_argument("--reanalyze", default=None)
    a = ap.parse_args()
    if a.reanalyze:
        res = json.load(open(a.reanalyze))
        if a.s4:
            for n, v in json.load(open(a.s4)).items():
                if n in res["models"]:
                    res["models"][n]["s4"] = v
        report(res, a.png)
        return
    models = [m for m in a.models if m in S3_MODELS and a.s3_dir or m not in S3_MODELS]
    res = measure(models, a.s3_dir, a.s4, axis=not a.no_axis)
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"→ {a.out}")
    report(res, a.png)


if __name__ == "__main__":
    main()
