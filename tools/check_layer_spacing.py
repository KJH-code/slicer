"""check_layer_spacing.py — T2: 증명 B 의 층간격 식을 **실제로 내보낸 G-code** 에서 잰다.

    간격(r) = (Z′ₖ₊₁ − Z′ₖ) − r·(tanθₖ₊₁ − tanθₖ)        ( = h − r·Δtan, c = +1 )

사전 등록·판정 기준: `docs/test_t2_t6.md` §1. 이 스크립트는 그 절차를 그대로 따른다.

    python3 tools/check_layer_spacing.py                 # 생성 + 측정, 약 수 분
    python3 tools/check_layer_spacing.py --reuse         # 이미 만든 G-code 로 측정만

G-code 는 `conical_slice.py`(내장 슬라이서, --mode xyz)를 **CLI 로** 돌려 만든다 — 실제 출력 파일을
재는 것이 목적이라 내부 함수를 거치지 않는다. 예측의 θₖ 는 생성 쪽 객체가 아니라 파일의
`;CONICAL_META` 프로필을 다시 읽어 계산한다. 결과: `results/t2_layer_spacing.json`.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conical.profile import AngleProfile  # noqa: E402

PAIR_WINDOW = 0.1          # |r₂ − r₁| 창 (mm) — 사전 등록 값
PAIRS_PER_LAYER = 300      # 층 쌍마다 뽑는 점 수 — 사전 등록 값
SLOPE_MIN_SPAN = 1.0       # 기울기 진단에 쓰는 층의 최소 r 폭 (mm) — 결과 본 뒤 추가한 진단
SEED = 0
LAYER_HEIGHTS = (0.3, 0.4)

_LAYER = re.compile(r"^;\s*layer\s+(\d+)\s+z=([-\d.]+)")
_WORD = re.compile(r"([XYZEF])([-+]?\d*\.?\d+)")


# ─────────────────────────────────────────────────────────────
# 표본 생성
# ─────────────────────────────────────────────────────────────
def _models():
    """이름 → (메시 만드는 함수 또는 STL 경로, 프로필 지정)."""
    from analyze_blend_ratio import _sphere, widen
    from compare_waist import waisted_model
    lamp = str(ROOT / "examples" / "lamp.stl")
    return {
        "lamp_band2": (lamp, ("auto", 2)),
        "sphere_28_20": (_sphere, ("bands", [28.0, 20.0])),
        "waist3x2_42_36": (lambda: widen(waisted_model(3.0), 2.0), ("bands", [42.0, 36.0])),
        "sphere_10_30": (_sphere, ("bands", [10.0, 30.0])),
        "ctrl_sphere_20": (_sphere, ("const", 20.0)),
        "ctrl_lamp_25": (lamp, ("const", 25.0)),
    }


def _band_profile_text(mesh, thetas):
    """analyze_gap_sample.profile_from 과 같은 프로필 → CLI 의 --profile 문자열 (전 정밀도)."""
    from analyze_gap_sample import profile_from
    from conical.meshio import RadiusProfile
    rp = RadiusProfile(mesh)
    r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
    prof = profile_from(mesh, thetas, rp, r_max)
    return ",".join(f"{float(z)!r}:{float(t)!r}"
                    for z, t in zip(prof.zs, prof.thetas_deg, strict=True))


def generate(outdir, names):
    import trimesh
    outdir.mkdir(parents=True, exist_ok=True)
    made = {}
    for name, (src, (kind, val)) in _models().items():
        if names and name not in names:
            continue
        if isinstance(src, str):
            stl = src
            mesh = None
        else:
            mesh = src()
            stl = str(outdir / f"{name}.stl")
            mesh.export(stl)
        for lh in LAYER_HEIGHTS:
            out = outdir / f"{name}_h{lh}.gcode"
            cmd = [sys.executable, str(ROOT / "conical_slice.py"), stl,
                   "--layer-height", str(lh), "-o", str(out)]
            if kind == "auto":
                cmd += ["--auto-bands", str(val)]
            elif kind == "bands":
                if mesh is None:
                    mesh = trimesh.load(stl, force="mesh")
                cmd += ["--profile", _band_profile_text(mesh, val)]
            else:
                cmd += ["--angle", str(val), "--direction", "outward"]
            env = dict(os.environ, PYTHONPATH=str(ROOT), MPLBACKEND="Agg")
            res = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"{name} h={lh}: {res.stderr[-2000:]}")
            made[(name, lh)] = out
            print(f"  생성 {out.name}")
    return made


# ─────────────────────────────────────────────────────────────
# G-code 읽기 (저장소 파서를 쓰지 않는 독립 구현)
# ─────────────────────────────────────────────────────────────
def read_gcode(path):
    """→ meta(dict), layers {k: (Z′ₖ, pts (N,3))} — 압출 끝점만."""
    meta = None
    layers = {}
    cur = None
    x = y = z = None
    e = 0.0
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if s.startswith(";CONICAL_META"):
            meta = json.loads(s.split(";CONICAL_META", 1)[1])
            continue
        mo = _LAYER.match(s)
        if mo:
            cur = int(mo.group(1))
            layers[cur] = (float(mo.group(2)), [])
            continue
        code = s.split(";", 1)[0].strip()
        if not (code.startswith("G1 ") or code.startswith("G0 ")):
            if code.startswith("G92"):
                for k, v in _WORD.findall(code):
                    if k == "E":
                        e = float(v)
            continue
        w = dict(_WORD.findall(code))
        x = float(w["X"]) if "X" in w else x
        y = float(w["Y"]) if "Y" in w else y
        z = float(w["Z"]) if "Z" in w else z
        e_new = float(w["E"]) if "E" in w else e
        extr = e_new > e + 1e-9 and ("X" in w or "Y" in w or "Z" in w)
        e = e_new
        if extr and cur is not None and None not in (x, y, z):
            layers[cur][1].append((x, y, z))
    if meta is None:
        raise ValueError(f"{path}: ;CONICAL_META 없음")
    return meta, {k: (zp, np.array(p)) for k, (zp, p) in layers.items() if p}


def meta_profile(meta):
    if meta["direction"] != "outward":
        raise ValueError("부호 각도 규약(outward)만 다룬다")
    return AngleProfile([(z, t) for z, t in meta["profile"]])


# ─────────────────────────────────────────────────────────────
# 측정
# ─────────────────────────────────────────────────────────────
def measure(path, rng):
    meta, layers = read_gcode(path)
    prof = meta_profile(meta)
    h = float(meta["layer_height"])
    blends = prof.blend_intervals()
    ks = sorted(layers)

    # 층마다 직선 맞춤 z = a + b·r (측정 기울기)
    fits = {}
    for k in ks:
        zp, p = layers[k]
        r = np.hypot(p[:, 0], p[:, 1])
        if np.ptp(r) < 1e-6:
            fits[k] = None
            continue
        A = np.column_stack([np.ones_like(r), r])
        coef, *_ = np.linalg.lstsq(A, p[:, 2], rcond=None)
        res = p[:, 2] - A @ coef
        fits[k] = (float(coef[0]), float(coef[1]), float(np.abs(res).max()), float(np.ptp(r)))

    # 기울기 확인은 r 폭이 1mm 이상인 층만 — 폭이 좁으면 z 반올림(0.001mm)만으로도
    # 기울기가 크게 흔들린다 (진단용, 판정 아님)
    slope_err = []
    n_narrow = 0
    for k in ks:
        if fits[k] is not None and fits[k][3] < SLOPE_MIN_SPAN:
            n_narrow += 1
        if fits[k] is not None and fits[k][3] >= SLOPE_MIN_SPAN:
            tan_k = float(prof.tan_at(layers[k][0]))
            slope_err.append(abs(fits[k][1] + tan_k))

    rows = []
    skipped_gap = 0
    for k0, k1 in zip(ks[:-1], ks[1:], strict=True):
        z0p, p0 = layers[k0]
        z1p, p1 = layers[k1]
        if abs((z1p - z0p) - h) > 1e-6 or fits[k0] is None:
            skipped_gap += 1
            continue
        r0 = np.hypot(p0[:, 0], p0[:, 1])
        r1 = np.hypot(p1[:, 0], p1[:, 1])
        order = np.argsort(r0)
        r0s, z0s = r0[order], p0[order, 2]
        pick = rng.choice(len(p1), size=min(PAIRS_PER_LAYER, len(p1)), replace=False)
        t0, t1 = float(prof.tan_at(z0p)), float(prof.tan_at(z1p))
        b0 = fits[k0][1]
        for i in pick:
            rq = r1[i]
            j = int(np.searchsorted(r0s, rq))
            cand = [c for c in (j - 1, j) if 0 <= c < len(r0s)]
            jj = min(cand, key=lambda c: abs(r0s[c] - rq))
            dr = rq - r0s[jj]
            if abs(dr) > PAIR_WINDOW:
                continue
            m1 = p1[i, 2] - (z0s[jj] + b0 * dr)
            pred = (z1p - z0p) - rq * (t1 - t0)
            m2 = p1[i, 2] - z0s[jj]
            pred2 = (z1p - z0p) - (rq - dr / 2) * (t1 - t0)
            rows.append((k0, z0p, rq, dr, t1 - t0, m1, pred, m2, pred2, fits[k0][3]))
    a = np.array(rows) if rows else np.zeros((0, 10))
    return {
        "meta": meta, "profile": prof, "blends": blends, "h": h, "rows": a,
        "n_layers": len(ks), "skipped_pairs": skipped_gap, "n_narrow_layers": n_narrow,
        "slope_err_max": float(max(slope_err)) if slope_err else float("nan"),
        "fit_resid_max": float(max(f[2] for f in fits.values() if f is not None)),
    }


def summarize(ratios):
    if len(ratios) == 0:
        return {"n": 0}
    q = np.percentile(ratios, [0, 2.5, 50, 97.5, 100])
    return {"n": int(len(ratios)), "min": q[0], "p2.5": q[1], "median": q[2],
            "p97.5": q[3], "max": q[4]}


def passes(s):
    if s.get("n", 0) == 0:
        return None
    return bool(0.98 <= s["median"] <= 1.02 and s["p2.5"] >= 0.95 and s["p97.5"] <= 1.05)


def _dist_to_blend(zp, blends):
    if not blends:
        return float("inf")
    return min(0.0 if a <= zp <= b else min(abs(zp - a), abs(zp - b)) for a, b in blends)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--outdir", default=None, help="G-code 를 둘 곳 (기본: 임시 폴더)")
    ap.add_argument("--reuse", action="store_true", help="--outdir 의 G-code 를 그대로 잰다")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--json", default=str(ROOT / "results" / "t2_layer_spacing.json"))
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else Path(tempfile.mkdtemp(prefix="t2_"))
    if args.reuse:
        files = {(p.stem.rsplit("_h", 1)[0], float(p.stem.rsplit("_h", 1)[1])): p
                 for p in sorted(outdir.glob("*.gcode"))}
    else:
        print(f"G-code 생성 → {outdir}")
        files = generate(outdir, args.only)

    rng = np.random.default_rng(SEED)
    out = {"criteria": "docs/test_t2_t6.md §1.4", "pair_window_mm": PAIR_WINDOW,
           "pairs_per_layer": PAIRS_PER_LAYER, "seed": SEED, "cases": [], "pooled": {}}
    pooled = {"band_all": [], "band_blend": [], "ctrl_all": []}
    pairs = {"meas": [], "pred": [], "h": [], "r": [], "dtan": [], "ctrl": [], "case": []}
    case_names = []
    print("\n표본 | 층고 | 프로필 | 쌍 | 블렌드 쌍 | ρ 중앙값 [2.5, 97.5] (M1) | 블렌드만 | M2 | "
          "기울기 오차 | 맞춤 잔차")
    for (name, lh), path in sorted(files.items()):
        m = measure(path, rng)
        a = m["rows"]
        rho = a[:, 5] / a[:, 6]
        rho2 = a[:, 7] / a[:, 8]
        blend_mask = np.abs(a[:, 4]) > 1e-9
        s_all, s_bl, s_m2 = summarize(rho), summarize(rho[blend_mask]), summarize(rho2)
        ctrl = name.startswith("ctrl_")
        case_names.append(f"{name}_h{lh}")
        for key, col in (("meas", a[:, 5]), ("pred", a[:, 6]), ("r", a[:, 2]), ("dtan", a[:, 4])):
            pairs[key].append(col.astype(np.float32))
        pairs["h"].append(np.full(len(a), lh, np.float32))
        pairs["ctrl"].append(np.full(len(a), ctrl))
        pairs["case"].append(np.full(len(a), len(case_names) - 1, np.int16))
        if ctrl:
            pooled["ctrl_all"].append(rho)
        else:
            pooled["band_all"].append(rho)
            pooled["band_blend"].append(rho[blend_mask])
        bad = np.abs(rho - 1.0) > 0.05
        worst = []
        for idx in np.argsort(-np.abs(rho - 1.0))[:10]:
            if not bad[idx]:
                break
            k0, zp, rq, dr, dtan, m1, pred, _m2, _p2, span = a[idx]
            worst.append({"layer": int(k0), "Zp": zp, "r": rq, "dr": dr, "dtan": dtan,
                          "meas": m1, "pred": pred, "rho": float(rho[idx]),
                          "dist_to_blend": _dist_to_blend(zp, m["blends"]),
                          "layer_k_r_span": span})
        case = {
            "name": name, "layer_height": lh, "file": path.name,
            "profile": m["meta"]["profile"], "blends": m["blends"],
            "n_layers": m["n_layers"], "skipped_layer_pairs": m["skipped_pairs"],
            "n_pairs": int(len(a)), "n_blend_pairs": int(blend_mask.sum()),
            "dtan_max_abs": float(np.abs(a[:, 4]).max()) if len(a) else 0.0,
            "pred_range": [float(a[:, 6].min()), float(a[:, 6].max())] if len(a) else None,
            "M1_all": s_all, "M1_blend": s_bl, "M2_all_uncorrected": s_m2,
            "M1_abs_err_mm_max": float(np.abs(a[:, 5] - a[:, 6]).max()) if len(a) else None,
            "pass_all": passes(s_all), "pass_blend": passes(s_bl),
            "slope_vs_meta_tan_max_span_ge_1mm": m["slope_err_max"],
            "n_layers_r_span_lt_1mm": m["n_narrow_layers"],
            "n_pairs_from_narrow_layer": int((a[:, 9] < SLOPE_MIN_SPAN).sum()) if len(a) else 0,
            "layer_line_fit_resid_max_mm": m["fit_resid_max"],
            "n_outside_5pct": int(bad.sum()), "worst": worst,
        }
        out["cases"].append(case)
        bl = (f"{s_bl['median']:.4f} [{s_bl['p2.5']:.4f}, {s_bl['p97.5']:.4f}]"
              if s_bl["n"] else "—")
        print(f"{name} | {lh} | {m['meta']['profile']} | {len(a)} | {blend_mask.sum()} | "
              f"{s_all['median']:.4f} [{s_all['p2.5']:.4f}, {s_all['p97.5']:.4f}] | {bl} | "
              f"{s_m2['median']:.3f} [{s_m2['p2.5']:.3f}, {s_m2['p97.5']:.3f}] | "
              f"{m['slope_err_max']:.1e} | {m['fit_resid_max']:.1e}")
    for key, lst in pooled.items():
        s = summarize(np.concatenate(lst)) if lst else {"n": 0}
        out["pooled"][key] = {**s, "pass": passes(s)}
        if s.get("n"):
            print(f"합산 {key}: n={s['n']} 중앙값 {s['median']:.4f} "
                  f"[{s['p2.5']:.4f}, {s['p97.5']:.4f}] 범위 [{s['min']:.4f}, {s['max']:.4f}] "
                  f"→ {'통과' if passes(s) else '실패'}")
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)

    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return None if not math.isfinite(float(o)) else round(float(o), 6)
        if isinstance(o, np.integer):
            return int(o)
        return o
    Path(args.json).write_text(json.dumps(_clean(out), ensure_ascii=False, indent=1),
                               encoding="utf-8")
    # 쌍별 원자료 (보고서 그림 tools/report_figs/t2_spacing.py 가 읽는다)
    npz = Path(args.json).with_name("t2_layer_spacing_pairs.npz")
    np.savez_compressed(npz, case_names=np.array(case_names),
                        **{k: np.concatenate(v) for k, v in pairs.items()})
    print(f"\n→ {args.json}\n→ {npz}")


if __name__ == "__main__":
    main()
