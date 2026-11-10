"""analyze_angle_cost.py — **왜 그냥 균일 44° 로 뽑지 않나** — 왜곡의 비용을 잰다.

## 왜 (2026-11-10)

보고서 실험 1 (report_experiments.py) 에서 균일각을 0~44° 로 훑자 **40° 이상에서
오버행이 낙관·비관 모두 ~0** 으로 나왔다(구 44°: 0.007%p). 오버행만 보면 '최대각
균일' 이 언제나 이긴다. 그러면 밴드(평균 왜곡 ~18°)는 무엇을 사는가?

답은 왜곡의 **비용**에 있어야 한다. 이 스크립트는 같은 모델을 균일 0~44° 와 밴드2 로
**실제 REP5X G-code 까지** 뽑아서 비용 축을 잰다:

| 비용 | 어떻게 | 왜 |
|---|---|---|
| 출력 시간 | `motion.plan_motion`, REP5X 실측 축 한계 (C 가속 500 deg/s²) | 회전축 가속이 병목이라는 것이 이미 나왔다 |
| 레이어 수·압출 경로 | G-code 에서 | 시간의 원인 분해 |
| 계단 자국 (표면) | 면별 `|n̂·b̂|` 면적가중 평균, 평면 대비 비 | 서포트를 없애는 각도가 계단을 키운다 (`quality.py`) |
| 회전축 부담 | `check_rep5x`: C 총 회전량, C 최대 한 걸음, 축 통과 | 축 근처 급회전 = 출력물 흔들림·감속 |

⚠ 시간의 절대값은 펌웨어 플래너 근사다. **각도 사이의 비** 만 본다.
⚠ 밴드의 계단은 블렌드 구간의 층간격 변화를 무시한 근사 (면별 θ 만 반영).
⚠ B(틸트) 축 한계는 시간 모델에 없다 — 레이어마다 한 번 움직여 영향이 작다.

    python3 analyze_angle_cost.py                 # 램프 + 허리 r=3 + 구
    python3 analyze_angle_cost.py --models lamp   # 실물 실험 모델만
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time

import numpy as np
import trimesh

from analyze_motion import REP5X_SPEC
from conical import gcode as gc
from conical.meshio import center_on_axis
from conical.motion import limits_from_spec, plan_motion
from conical.profile import AngleProfile
from conical.rep5x import check_rep5x

ANGLES = tuple(range(0, 45, 4))
LH = 0.3


def models(which):
    from analyze_blend_ratio import _sphere
    from compare_waist import waisted_model
    table = {
        "lamp": ("램프 (examples/lamp.stl)",
                 lambda: center_on_axis(trimesh.load("examples/lamp.stl", force="mesh"))),
        "waist3": ("허리 r=3", lambda: waisted_model(3.0)),
        "sphere": ("구", _sphere),
    }
    return [(k,) + table[k] for k in which]


def slice_rep5x(stl, args, out):
    cmd = [sys.executable, "conical_slice.py", stl, "--layer-height", str(LH),
           "--mode", "rep5x", "-o", out] + args
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    lines = open(out).readlines()
    meta = json.loads(lines[0].split("CONICAL_META", 1)[1])
    return gc.parse(lines), meta


def face_layer_normals(mesh, prof):
    """면 중심에서 그 높이의 θ 로 원뿔 레이어 법선 (outward)."""
    cen = np.asarray(mesh.triangles_center)
    r = np.hypot(cen[:, 0], cen[:, 1])
    th = np.radians(prof.theta_at(prof.solve_forward(cen[:, 2], r)))
    out = np.zeros_like(cen)
    ok = r > 1e-12
    out[:, 0] = np.where(ok, np.sin(th) * cen[:, 0] / np.where(ok, r, 1), 0)
    out[:, 1] = np.where(ok, np.sin(th) * cen[:, 1] / np.where(ok, r, 1), 0)
    out[:, 2] = np.where(ok, np.cos(th), 1.0)
    return out, th


def surface(mesh, prof):
    """계단 자국: 정렬 |n̂·b̂| (간격 이득 뺀 순수 기하) 와 같은 층고 계단 d·|n̂·b̂|."""
    n = np.asarray(mesh.face_normals)
    a = np.asarray(mesh.area_faces)
    b, th = face_layer_normals(mesh, prof)
    align = np.abs(np.einsum("ij,ij->i", n, b))
    cusp = LH * np.cos(th) * align
    flat = np.abs(n[:, 2])
    return dict(align=float((align * a).sum() / a.sum()),
                align_ratio=float((align * a).sum() / (flat * a).sum()),
                cusp_mean=float((cusp * a).sum() / a.sum()),
                worse_area_pct=float(a[align > flat + 1e-12].sum() / a.sum() * 100))


def gcode_stats(items):
    path = 0.0
    layers = 0
    last = None
    for kind, p in items:
        if kind != "move":
            if isinstance(p, str) and p.lstrip(";").strip().upper().startswith("LAYER"):
                layers += 1
            continue
        cur = (p.x, p.y, p.z)
        if last is not None and p.e is not None and None not in cur and None not in last:
            path += math.dist(cur, last)
        if None not in cur:
            last = cur
    return dict(path_mm=path, layer_comments=layers,
                moves=sum(1 for k, _ in items if k == "move"))


def measure(stl, args, label, mesh):
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.time()
        items, meta = slice_rep5x(stl, args, os.path.join(tmp, "o.gcode"))
        prof = AngleProfile([tuple(bp) for bp in meta["profile"]]) \
            if len(meta["profile"]) > 1 else AngleProfile.constant(meta["profile"][0][1])
        limits = limits_from_spec("REP5X", rot_axis="C", rot_in_feed_norm=False,
                                  **REP5X_SPEC)
        mot = plan_motion(items, limits, rot_axis="C", tilt_axis="B")
        findings, st = check_rep5x(items)
        row = dict(label=label, profile=meta["profile"],
                   minutes=mot["print_seconds"] / 60,
                   c_bound_min=mot["binding_time"].get("C", 0.0) / 60,
                   c_turns=st["c_span_turns"], c_max_step=st["c_max_step_deg"],
                   rewinds=st["rewinds"],
                   fatal=sum(1 for s, _ in findings if s == "치명"),
                   warn=sum(1 for s, _ in findings if s == "경고"),
                   **surface(mesh, prof), **gcode_stats(items),
                   seconds=round(time.time() - t0, 1))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="lamp,waist3,sphere")
    ap.add_argument("--json", default="report/exp5_angle_cost.json")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)

    out = []
    for key, name, build in models(args.models.split(",")):
        mesh = build()
        with tempfile.TemporaryDirectory() as tmp:
            stl = "examples/lamp.stl" if key == "lamp" else os.path.join(tmp, f"{key}.stl")
            if key != "lamp":
                mesh.export(stl)
            print(f"\n[{name}]")
            print(f"{'조건':>10}{'시간(분)':>9}{'C병목':>7}{'경로m':>7}{'정렬비':>7}"
                  f"{'나빠진면적%':>11}{'C회전':>7}{'C걸음°':>7}{'치명':>5}")
            conds = [(f"균일 {a}°", ["--angle", str(a), "--direction", "outward"])
                     for a in ANGLES] + [("밴드2", ["--auto-bands", "2"])]
            for label, cargs in conds:
                r = measure(stl, cargs, label, mesh)
                r["model"] = name
                out.append(r)
                print(f"{label:>10}{r['minutes']:>9.1f}{r['c_bound_min']:>7.1f}"
                      f"{r['path_mm'] / 1000:>7.2f}{r['align_ratio']:>7.2f}"
                      f"{r['worse_area_pct']:>11.1f}{r['c_turns']:>7.1f}"
                      f"{r['c_max_step']:>7.1f}{r['fatal']:>5}", flush=True)
            json.dump(out, open(args.json, "w"), ensure_ascii=False, indent=1)
    print(f"\n저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
