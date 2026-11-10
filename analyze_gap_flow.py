"""analyze_gap_flow.py — 역변환 뒤 압출량(E)이 실공간 층 두께와 맞는가.

## 왜

`backtransform.py` 는 ΔE 에 `(실길이 / 변환길이)` 만 곱한다. 그런데 평면 슬라이서가
변환공간에서 채운 체적 `w·h·L′` 이 실공간에서 차지하는 체적은 **변환의 야코비안**
만큼 달라진다. 역변환 `(X, Y, Z′) → (x, y, z)`:

    x = X·cosθ(Z′),  y = Y·cosθ(Z′),  z = Z′ − c·R·sinθ(Z′)        (R = √(X²+Y²))

원통좌표로 풀면  det = cos²θ · (1 − c·r·s) = **cos²θ · m**  (s = d tanθ/dZ′).
즉 실공간에서 비드가 채워야 할 체적은 `w·h·L′·cos²θ·m` 이고, 방향과 무관하다.
코드가 실제로 내는 것은 `w·h·L′·(L/L′)` 이며 `L/L′` 는 둘레 방향 cosθ, 반경 방향 1 이다.

    과압출 배율 = (L/L′) / (cos²θ·m)      둘레: 1/(cosθ·m)   반경: 1/(cos²θ·m)

같은 식의 다른 얼굴이 **실공간 층 두께**다 — 층 법선 방향 간격 `t_n = h·m·cosθ`.
균일 원뿔이면 얇아지고(cosθ), 블렌드(m=1.5)에서는 두꺼워진다.

## 무엇을 재나 (출력 파일 그대로 — 다시 슬라이싱하지 않는다)

`examples/*.gcode` 의 `;CONICAL_META` 에서 프로필·층고를 읽고, 압출 이동마다
끝점을 정변환해 변환길이 L′ 를 되찾는다(재분할이 변환공간 선형보간이라 정확).

* 야코비안 수치 검산 (유한차분 vs cos²θ·m)
* 파일별 압출 배율 `E_낸것 / E_필요` — 페리미터/인필, 상수 구간/블렌드 구간
* 낸 E 가 슬라이서 입력 E 와 얼마나 같은가 (보정이 실제로 걸렸는지)
* 실공간 층 두께 `t_n = h·m·cosθ` 의 분포와 노즐 지름 대비 비율

판정은 하지 않는다 — 이 스크립트는 **흐름(유량) 오차의 크기**만 낸다.
노즐 지름 0.4mm 는 **가정**이다(압출폭 0.45 에서 역산, 실기 확인 전).

    python3 analyze_gap_flow.py
"""

import json
import math
import sys

import numpy as np

from conical import gcode as gc
from conical.backtransform import _inv_point
from conical.planar_slicer import FILAMENT_D
from conical.profile import AngleProfile

FILES = [
    ("funnel 균일 26° (lh0.3)", "examples/funnel_conical.gcode"),
    ("funnel 밴드 26→10 (lh0.3)", "examples/funnel_profile2band.gcode"),
    ("lamp 균일 24° (lh0.3)", "examples/lamp_expA_uniform24_lh03.gcode"),
    ("lamp 밴드2 30→0 (lh0.3)", "examples/lamp_expA_band2_lh03.gcode"),
    ("lamp 균일 24° (lh0.4)", "examples/lamp_expA_uniform24_lh04.gcode"),
    ("lamp 밴드2 30→0 (lh0.4)", "examples/lamp_expA_band2_lh04.gcode"),
]
NOZZLE_D = 0.4          # ⚠ 가정 (압출폭 0.45 → 0.4 노즐). 실기 확인 전
A_FIL = math.pi * (FILAMENT_D / 2) ** 2


def jacobian_check(n=2000, seed=0):
    """역변환의 체적 야코비안을 유한차분으로 구해 cos²θ·m 과 대조한다."""
    rng = np.random.default_rng(seed)
    prof = AngleProfile([(0.0, 30.0), (10.0, 30.0), (14.0, 5.0), (30.0, 5.0)])
    worst = 0.0
    eps = 1e-5
    for _ in range(n):
        X, Y = rng.uniform(-12, 12, 2)
        Zw = rng.uniform(1.0, 25.0)
        if min(abs(Zw - 10.0), abs(Zw - 14.0)) < 1e-3:
            continue
        cols = []
        for d in ((eps, 0, 0), (0, eps, 0), (0, 0, eps)):
            a = np.array(_inv_point(X + d[0], Y + d[1], Zw + d[2], prof, 1.0))
            b = np.array(_inv_point(X - d[0], Y - d[1], Zw - d[2], prof, 1.0))
            cols.append((a - b) / (2 * eps))
        det = float(np.linalg.det(np.array(cols).T))
        th = math.radians(float(prof.theta_at(Zw)))
        r = math.hypot(X, Y) * math.cos(th)
        m = float(prof.spacing_factor(np.array([Zw]), np.array([r]))[0])
        worst = max(worst, abs(det - math.cos(th) ** 2 * m) / abs(det))
    return worst


def load(path):
    """G-code → (메타, 본문 아이템). 시작 G-code(프라임 선)는 뺀다."""
    with open(path) as fh:
        lines = fh.readlines()
    meta = None
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith(";CONICAL_META"):
            meta = json.loads(ln.split(" ", 1)[1])
        if ln.startswith("; conical built-in planar slicer"):
            start = i
            break
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("; end"):
            end = i
            break
    return meta, gc.parse(lines[start:end])


def segments(meta, items):
    """압출 이동마다 (종류, r, z, θ, m, L, L′, ΔE, 블렌드 안인가)."""
    prof = AngleProfile([tuple(b) for b in meta["profile"]])
    c = 1.0 if meta["direction"] == "outward" else -1.0
    blends = prof.blend_intervals()
    rows = []
    x = y = z = None
    e_prev = 0.0
    kind = 2
    for k, p in items:
        if k != "move":
            if isinstance(p, str) and p.upper().startswith(";TYPE:"):
                kind = 0 if "PERIMETER" in p.upper() else 1
            continue
        nx = p.x if p.x is not None else x
        ny = p.y if p.y is not None else y
        nz = p.z if p.z is not None else z
        if p.e is not None and p.e > e_prev + 1e-12 and None not in (x, y, z):
            L = math.dist((x, y, z), (nx, ny, nz))
            if L > 1e-9:
                pts = np.array([[x, y, z], [nx, ny, nz]])
                rr = np.hypot(pts[:, 0], pts[:, 1])
                zw = prof.solve_forward(pts[:, 2], rr, meta["direction"])
                th = np.radians(prof.theta_at(zw))
                W = np.column_stack([pts[:, 0] / np.cos(th),
                                     pts[:, 1] / np.cos(th), zw])
                Lw = float(np.linalg.norm(W[1] - W[0]))
                zm, rm = float(zw.mean()), float(rr.mean())
                thm = math.radians(float(prof.theta_at(zm)))
                m = float(1.0 - c * rm * _slope(prof, zm))
                rows.append((kind, rm, float(pts[:, 2].mean()), thm, m, L, Lw,
                             p.e - e_prev,
                             any(a < zm < b for a, b in blends)))
        if p.e is not None:
            e_prev = p.e
        x, y, z = nx, ny, nz
    return np.array(rows, dtype=float)


def _slope(prof, zw):
    for i in range(len(prof.zs) - 1):
        if prof.zs[i] <= zw <= prof.zs[i + 1]:
            return (prof.tans[i + 1] - prof.tans[i]) / (prof.zs[i + 1] - prof.zs[i])
    return 0.0


def wq(v, w, q):
    """가중 분위수."""
    o = np.argsort(v)
    cw = np.cumsum(w[o])
    return float(v[o][np.searchsorted(cw, q * cw[-1])])


def analyze(name, path):
    meta, items = load(path)
    h, w = meta["layer_height"], meta["extrusion_width"]
    s = segments(meta, items)
    kind, th, m, L, Lw, dE, inb = (s[:, 0], s[:, 3], s[:, 4], s[:, 5],
                                   s[:, 6], s[:, 7], s[:, 8] > 0.5)
    e_mm = h * w / A_FIL
    e_req = e_mm * Lw * np.cos(th) ** 2 * m           # 야코비안이 요구하는 양
    # 문서가 말한 보정대로라면 ΔE = e_mm·L′·(L/L′) = e_mm·L 이어야 한다.
    # 실제로는 그렇지 않다 — 원인은 analyze_gap_pipeline.py ① (e_prev 혼용).
    resid = float(np.abs(dE - e_mm * L).max() / (e_mm * L).max())
    tn = h * m * np.cos(th)                           # 실공간 층 두께(법선 방향)
    out = {"file": path, "layer_height": h, "e_accounting_residual": resid,
           "profile": meta["profile"]}

    def block(mask):
        if not mask.any():
            return None
        ratio = dE[mask] / e_req[mask]
        vs_in = dE[mask] / (e_mm * Lw[mask])          # 슬라이서가 준 양 대비
        return {"length_mm": float(L[mask].sum()),
                "vs_input_total": float(dE[mask].sum() / (e_mm * Lw[mask]).sum()),
                "vs_input_p99": float(np.percentile(vs_in, 99)),
                "vs_input_max": float(vs_in.max()),
                "flow_total": float(dE[mask].sum() / e_req[mask].sum()),
                "flow_p05": wq(ratio, L[mask], 0.05),
                "flow_p50": wq(ratio, L[mask], 0.50),
                "flow_p95": wq(ratio, L[mask], 0.95),
                "tn_min": float(tn[mask].min()),
                "tn_p50": wq(tn[mask], L[mask], 0.50),
                "tn_max": float(tn[mask].max()),
                "m_min": float(m[mask].min()), "m_max": float(m[mask].max()),
                "share_tn_over_0.8d": float(L[mask & (tn > 0.8 * NOZZLE_D)].sum()
                                            / L[mask].sum()),
                "share_tn_over_d": float(L[mask & (tn > NOZZLE_D)].sum()
                                         / L[mask].sum())}

    peri = kind == 0
    out["perimeter_all"] = block(peri)
    out["perimeter_const"] = block(peri & ~inb)
    out["perimeter_blend"] = block(peri & inb)
    out["infill_all"] = block(kind == 1)
    print(f"\n[{name}]  {path}")
    pa = out["perimeter_all"]
    print(f"  의도한 보정(ΔE = e_mm·L)과의 최대 잔차 {resid:.2f} (0 이어야 한다).  "
          f"페리미터: 낸 E / 슬라이서 입력 E = {pa['vs_input_total']:.3f} "
          f"(이동별 p99 {pa['vs_input_p99']:.2f} 배, 최대 {pa['vs_input_max']:.2f} 배)")
    print(f"  {'구간':<16}{'길이mm':>9}{'배율(합)':>9}{'p05':>7}{'p50':>7}{'p95':>7}"
          f"{'t_n 최소':>9}{'중앙':>7}{'최대':>7}{'>0.8d':>7}{'>d':>6}")
    for label, key in (("페리미터 전체", "perimeter_all"),
                       ("  상수각 구간", "perimeter_const"),
                       ("  블렌드 구간", "perimeter_blend"),
                       ("인필 전체", "infill_all")):
        b = out[key]
        if b is None:
            continue
        print(f"  {label:<16}{b['length_mm']:>9.0f}{b['flow_total']:>9.3f}"
              f"{b['flow_p05']:>7.3f}{b['flow_p50']:>7.3f}{b['flow_p95']:>7.3f}"
              f"{b['tn_min']:>9.3f}{b['tn_p50']:>7.3f}{b['tn_max']:>7.3f}"
              f"{b['share_tn_over_0.8d'] * 100:>6.1f}%{b['share_tn_over_d'] * 100:>5.1f}%")
    return name, out


def main():
    print("야코비안 검산: 유한차분 det vs cos²θ·m, 최대 상대오차 "
          f"{jacobian_check():.2e}")
    print("\n배율 = 낸 E / 야코비안이 요구하는 E  (1.000 = 정확, >1 과압출, <1 과소)")
    print(f"t_n = h·m·cosθ (mm, 층 법선 방향 두께).  d = 노즐 지름 {NOZZLE_D} (가정)")
    res = dict(analyze(n, p) for n, p in FILES)
    with open("gap_flow_results.json", "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print("\n저장: gap_flow_results.json")


if __name__ == "__main__":
    sys.exit(main())
