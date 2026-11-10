"""report_experiments.py — 최종 보고서 실험 1 (형상 의존성) 계산.

docs/report_experiment_design.md 의 실험 1 을 한 번에 돌린다. 기존 스크립트와 다른 점:

* **균일 기준선을 두 개** 쓴다 — J 가 고른 균일각, 그리고 같은 지표로 각도를 훑어
  찾은 **최선 균일각**(사후 최선, 낙관/비관 각각). 밴드가 이겨야 하는 것은 뒤쪽이다.
  약한 기준선을 이기는 것은 의미가 없다 (CLAUDE.md 규칙 2).
* 모든 수치는 **실제 툴패스**를 낙관·비관 두 지지 모델로 판정한 진짜 오버행 %p.
* 층고 0.3 / 0.4 두 점 — 두 지지 모델이 같은 답을 내는 쪽과 갈리는 쪽.

결과는 report/exp1_raw.jsonl 에 한 줄씩 쌓인다(중단돼도 이어 돌릴 수 있다).
표·그림은 report_figures.py 가 만든다.

    python3 report_experiments.py              # 전체 (4 코어 약 30~40분)
    python3 report_experiments.py --quick      # 대표 3 모델 × 층고 0.3
    python3 report_experiments.py --jobs 2
    python3 report_experiments.py --heldout    # 실험 3 보류 모델

⚠ 시뮬레이션 경향이다. 물리(브리징·수축·냉각)는 없다.
"""

import argparse
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np
import trimesh

from analyze_blend_ratio import build_specs, lobe, widen
from analyze_layer_height import measure
from compare_waist import mean_abs_angle, waisted_model
from conical.config import DEFAULT_K, MAX_ANGLE_DEG, MAX_SPACING_FACTOR
from conical.meshio import RadiusProfile, center_on_axis
from conical.profile import AngleProfile
from conical.varangle import select_banded_j

OUT = os.path.join("report", "exp1_raw.jsonl")
OUT_HELDOUT = os.path.join("report", "exp3_raw.jsonl")
HELDOUT_SEED = 20261110      # 결과 보기 전에 고정 (docs/report_experiment_design.md)
HELDOUT_COUNT = 20
SWEEP = tuple(range(0, MAX_ANGLE_DEG + 1, 4))      # 0,4,...,44 (0 = 평면)
HEIGHTS = (0.3, 0.4)
QUICK = ("구", "허리 r=2", "허리 r=5")

_SPECS = None
_CACHE = {}


def random_model(seed, model_id):
    """보류(held-out) 무작위 모델. 팀 저장소 wjd 의 conical/test_models.py
    generate_random_model 과 같은 규칙(SeedSequence([seed, id, 0]), 다섯 계열).
    튜닝에 쓴 17 모델과 겹치지 않는 형상(원기둥·상자·나팔)이 섞인다."""
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(model_id), 0]))
    family = ("sphere", "cylinder", "box", "flaring_cone", "waisted_lobe")[
        int(rng.integers(0, 5))]
    if family == "sphere":
        p = {"radius": float(rng.uniform(4.0, 9.0))}
        m = trimesh.creation.icosphere(subdivisions=2, radius=p["radius"])
    elif family == "cylinder":
        p = {"radius": float(rng.uniform(4.0, 9.0)), "height": float(rng.uniform(8.0, 18.0))}
        m = trimesh.creation.cylinder(radius=p["radius"], height=p["height"], sections=48)
    elif family == "box":
        p = {"width": float(rng.uniform(7.0, 17.0)), "depth": float(rng.uniform(7.0, 17.0)),
             "height": float(rng.uniform(8.0, 18.0))}
        m = trimesh.creation.box(extents=(p["width"], p["depth"], p["height"]))
    elif family == "flaring_cone":
        p = {"bottom_radius": float(rng.uniform(3.5, 7.0)),
             "top_radius": float(rng.uniform(7.0, 11.0)),
             "height": float(rng.uniform(10.0, 20.0))}
        prof = np.array([[0, 0], [p["bottom_radius"], 0],
                         [p["top_radius"], p["height"]], [0, p["height"]]])
        m = trimesh.creation.revolve(prof, sections=48)
        m.merge_vertices()
        m.fix_normals()
    else:
        p = {"r_neck": float(rng.uniform(1.5, 5.5)), "xy_scale": float(rng.uniform(0.7, 1.3)),
             "lobe_amplitude": float(rng.uniform(0.0, 0.18))}
        m = lobe(widen(waisted_model(p["r_neck"]), p["xy_scale"]), p["lobe_amplitude"])
    return center_on_axis(m), family, p


def build_mesh(name):
    global _SPECS
    if name.startswith("rand:"):
        return random_model(HELDOUT_SEED, int(name[5:]))[0]
    if name.endswith(".stl"):
        return center_on_axis(trimesh.load(name, force="mesh"))
    if _SPECS is None:
        _SPECS = dict(build_specs(asym=True))
    return _SPECS[name]()


def _model(name):
    if name not in _CACHE:
        mesh = build_mesh(name)
        rp = RadiusProfile(mesh)
        r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
        sel = {n: select_banded_j(mesh, DEFAULT_K, n, r_max, rp, MAX_SPACING_FACTOR)
               for n in (1, 2)}
        _CACHE[name] = (mesh, sel)
    return _CACHE[name]


def run_task(task):
    name, kind, angle, lh = task
    mesh, sel = _model(name)
    if kind == "sweep":
        prof, thetas = AngleProfile.constant(angle), [float(angle)]
    else:
        n = 1 if kind == "uniform_J" else 2
        prof, thetas = sel[n]["profile_obj"], [round(t, 2) for t in sel[n]["thetas"]]
    t0 = time.time()
    r = measure(mesh, prof, lh)
    blends = []
    mean_abs = float(angle) if kind == "sweep" else float(mean_abs_angle(mesh, prof))
    if kind == "band2":
        blends = [[round(a, 3), round(b, 3)] for a, b in prof.blend_intervals()]
    return dict(model=name, kind=kind, angle=angle, layer_height=lh, thetas=thetas,
                blends=blends, mean_abs=mean_abs, opt=r["낙관"], pes=r["비관"],
                seconds=round(time.time() - t0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--heldout", action="store_true",
                    help="실험 3: 보류 모델(funnel + 무작위 20개), 층고 0.3")
    args = ap.parse_args()

    out = OUT
    if args.heldout:
        out = OUT_HELDOUT
        names = ["examples/funnel.stl"] + [f"rand:{i}" for i in range(HELDOUT_COUNT)]
        heights = HEIGHTS[:1]
    else:
        names = [n for n, _ in build_specs(asym=True) if not args.quick or n in QUICK]
        heights = HEIGHTS[:1] if args.quick else HEIGHTS

    os.makedirs("report", exist_ok=True)
    done = set()
    if os.path.exists(out):
        for line in open(out, encoding="utf-8"):
            d = json.loads(line)
            done.add((d["model"], d["kind"], d["angle"], d["layer_height"]))

    tasks = []
    for lh in heights:
        for name in names:
            tasks.append((name, "uniform_J", None, lh))
            tasks.append((name, "band2", None, lh))
            tasks += [(name, "sweep", a, lh) for a in SWEEP]
    # 같은 모델끼리 한 프로세스에 몰리도록(선택 캐시) 모델 순으로 정렬
    tasks = sorted((t for t in tasks if t not in done), key=lambda t: (t[0], t[3]))
    print(f"작업 {len(tasks)} 개 (이미 끝난 것 {len(done)} 개), jobs={args.jobs}", flush=True)

    t0 = time.time()
    with mp.get_context("fork").Pool(args.jobs) as pool, \
            open(out, "a", encoding="utf-8") as f:
        for i, r in enumerate(pool.imap_unordered(run_task, tasks, chunksize=1), 1):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(tasks)} {time.time() - t0:6.0f}s] {r['model']:<13} "
                  f"{r['kind']:<9} {str(r['angle']):>4} lh={r['layer_height']} "
                  f"낙관 {r['opt']:.3f} 비관 {r['pes']:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
