"""analyze_t7_scaling.py — T7: 메시 면 수에 따른 각도 결정 시간·메모리 (경량성).

사전 등록: docs/test_t3_t5_t7.md §1.3. 기준 없음 — 측정만 한다.

  ⓐ 균일각 결정  = CLI 기본 경로 `conical_slice.auto_select(mesh, k=0.2)`
  ⓑ 밴드2 계획   = `RadiusProfile(mesh)` + `select_banded_j(N=2)` (CLI `--auto-bands 2`)

모델 둘: 구(`icosphere`, subdiv 3~8 → 1.3k ~ 1.3M 면), 허리 r=3(기본 9.9k 면을 `subdivide`
0~3 회 → 9.9k ~ 631k 면). 측정마다 **새 프로세스**를 띄워 그 프로세스의 최대 RSS(`ru_maxrss`)를
잰다. 같은 메시를 만들기만 하고 끝나는 프로세스의 값도 따로 재서 '계산이 더한 메모리' 를 뺀다.
시간은 한 프로세스 안에서 3 회 중앙값(면 50 만 이상은 1 회).

    python3 analyze_t7_scaling.py            # → t7_scaling_results.json, t7_scaling.png
"""

import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "t7_scaling_results.json"
FIG = ROOT / "t7_scaling.png"
K = 0.2
SIZES = {"sphere": [3, 4, 5, 6, 7, 8], "waist_r3": [0, 1, 2, 3]}


def build(model, level):
    import trimesh

    from compare_waist import waisted_model
    from conical.meshio import center_on_axis

    if model == "sphere":
        return center_on_axis(trimesh.creation.icosphere(subdivisions=level, radius=10.0))
    m = waisted_model(3.0)
    for _ in range(level):
        v, f = trimesh.remesh.subdivide(m.vertices, m.faces)
        m = trimesh.Trimesh(vertices=v, faces=f, process=False)
    return center_on_axis(m)


def worker(model, level, task):
    """자식 프로세스: 메시 생성 → task 실행 → 시간·RSS 를 JSON 한 줄로."""
    import numpy as np

    mesh = build(model, level)
    _ = mesh.face_normals, mesh.area_faces          # 캐시 채우기 (적재 비용에 넣는다)
    n_faces = int(len(mesh.faces))
    reps = 1 if n_faces >= 500_000 else 3
    from conical.config import MAX_SPACING_FACTOR
    from conical.meshio import RadiusProfile
    from conical.varangle import select_banded_j
    from conical_slice import auto_select

    times, result = [], None
    for _ in range(reps if task != "load" else 0):
        # trimesh 캐시는 메시마다 남으므로 반복 간 차이는 그 캐시뿐이다 (같은 조건)
        t0 = time.perf_counter()
        if task == "uniform":
            sup, ang, d, _j = auto_select(mesh, K)
            result = {"angle": float(ang), "direction": d, "support_pct": float(sup)}
        elif task == "band2":
            rp = RadiusProfile(mesh)
            r_max = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1]).max())
            r = select_banded_j(mesh, K, 2, r_max, rp, MAX_SPACING_FACTOR)
            result = {"thetas": [float(t) for t in r["thetas"]],
                      "support_pct": float(r["support_pct"])}
        times.append(time.perf_counter() - t0)
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"model": model, "level": level, "task": task, "faces": n_faces,
                      "times_s": times,
                      "median_s": statistics.median(times) if times else None,
                      "maxrss_mb": rss_kb / 1024.0, "result": result}))


def machine():
    import numpy
    import scipy
    import trimesh

    cpu = ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem = ""
    try:
        mem = Path("/proc/meminfo").read_text().splitlines()[0].split(":", 1)[1].strip()
    except OSError:
        pass
    return {"cores": os.cpu_count(), "cpu": cpu, "mem_total": mem,
            "python": platform.python_version(), "numpy": numpy.__version__,
            "scipy": scipy.__version__, "trimesh": trimesh.__version__,
            "platform": platform.platform(),
            "note": "단일 프로세스 측정 (병렬 없음), 다른 무거운 작업이 없을 때 실행"}


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--worker":
        worker(sys.argv[2], int(sys.argv[3]), sys.argv[4])
        return 0
    env = dict(os.environ, PYTHONPATH=str(ROOT), MPLBACKEND="Agg",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    rows = []
    if OUT_JSON.exists():
        rows = json.loads(OUT_JSON.read_text()).get("rows", [])
    done = {(r["model"], r["level"], r["task"]) for r in rows}
    for model, levels in SIZES.items():
        for level in levels:
            for task in ("load", "uniform", "band2"):
                if (model, level, task) in done:
                    continue
                p = subprocess.run([sys.executable, __file__, "--worker", model,
                                    str(level), task], env=env, capture_output=True,
                                   text=True, check=True)
                row = json.loads(p.stdout.strip().splitlines()[-1])
                rows.append(row)
                print(f"{model:9s} L{level} {task:7s} faces={row['faces']:>8d} "
                      f"t={row['median_s']} rss={row['maxrss_mb']:.0f}MB", flush=True)
                OUT_JSON.write_text(json.dumps({"machine": machine(), "rows": rows},
                                               ensure_ascii=False, indent=1))
    report(rows)
    return 0


def report(rows):
    load = {(r["model"], r["level"]): r["maxrss_mb"] for r in rows if r["task"] == "load"}
    table = []
    for r in rows:
        if r["task"] == "load":
            continue
        table.append({**r, "extra_rss_mb": r["maxrss_mb"] - load[(r["model"], r["level"])]})
    table.sort(key=lambda r: (r["model"], r["faces"], r["task"]))
    print("| 모델 | 면 수 | 작업 | 시간 (s) | 최대 RSS (MB) | 적재 대비 추가 (MB) |")
    print("|---|---|---|---|---|---|")
    for r in table:
        print(f"| {r['model']} | {r['faces']:,} | {r['task']} | {r['median_s']:.3f} | "
              f"{r['maxrss_mb']:.0f} | {r['extra_rss_mb']:.0f} |")
    data = json.loads(OUT_JSON.read_text())
    data["table"] = table
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from conical.plotstyle import L

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    styles = {("sphere", "uniform"): ("#4c72b0", "o", "-"),
              ("sphere", "band2"): ("#4c72b0", "s", "--"),
              ("waist_r3", "uniform"): ("#dd8452", "o", "-"),
              ("waist_r3", "band2"): ("#dd8452", "s", "--")}
    for (model, task), (c, mk, ls) in styles.items():
        rs = [r for r in table if r["model"] == model and r["task"] == task]
        if not rs:
            continue
        f = [r["faces"] for r in rs]
        axes[0].plot(f, [r["median_s"] for r in rs], color=c, marker=mk, ls=ls,
                     label=f"{model} {task}")
        axes[1].plot(f, [r["maxrss_mb"] for r in rs], color=c, marker=mk, ls=ls,
                     label=f"{model} {task}")
    for ax, yl in ((axes[0], L("time (s)", "시간 (s)")),
                   (axes[1], L("peak RSS (MB)", "최대 RSS (MB)"))):
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(L("mesh faces", "메시 면 수"))
        ax.set_ylabel(yl)
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG, dpi=130)
    print(f"저장: {FIG.name}")


if __name__ == "__main__":
    sys.exit(main())
