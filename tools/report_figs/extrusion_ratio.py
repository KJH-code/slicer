"""extrusion_ratio — 단벽 원기둥의 '벽 1mm 당 E' 비 (θ / θ=0) 측정 대 예측.

conical_slice.py 를 CLI 로 돌려 examples/rep5x_ladder/cylinder.stl (r10 × 8) 을 θ = 0, 5, …, 30° 로
실제 생성한다. 조건은 사다리 L4 와 같다(--perimeters 1 --infill-spacing 0 --layer-height 0.3
--min-layer-time 8, outward). 단 25°·30° 는 REP5X 의 B_safe(≈22.8°) 를 넘어 --mode rep5x --strict 로
뽑을 수 없으므로 전부 --mode xyz 로 뽑고, 같은 측정을 실제 사다리 파일 L4a(B0)·L4b(22°, rep5x) 에도
해서 두 모드의 비가 같은지 대조한다.

측정: 반경 r > 9 mm 인 압출 선분(벽)만, Σ ΔE / Σ 실제 3D 길이. 예측: 야코비안 배율 cos²θ·m(m=1) 을
변환공간 길이 대비 실길이 cosθ 로 나눈 cosθ. 대안 '길이 비' 모형은 1.0.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.report_figs import gcodeio  # noqa: E402
from tools.report_figs.style import COLORS, ROOT, figure, save, setup  # noqa: E402

D = "examples/rep5x_ladder"
STL = f"{D}/cylinder.stl"
ANGLES = [0, 5, 10, 15, 20, 22, 25, 30]


def e_per_mm(path):
    _, L = gcodeio.read(path)
    de, ln = 0.0, 0.0
    for d in L.values():
        seg = d["seg"]
        r = np.hypot(seg[:, :, 0], seg[:, :, 1]).min(axis=1)
        keep = r > 9.0
        de += d["de"][keep].sum()
        ln += np.linalg.norm(seg[keep, 1] - seg[keep, 0], axis=1).sum()
    return de / ln, ln


def generate(tmp, theta):
    out = Path(tmp) / f"wall_{theta}.gcode"
    cmd = [sys.executable, str(ROOT / "conical_slice.py"), str(ROOT / STL),
           "--angle", str(theta), "--direction", "outward", "--perimeters", "1",
           "--infill-spacing", "0", "--min-layer-time", "8", "--mode", "xyz",
           "--layer-height", "0.3", "-o", str(out)]
    subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
    return out


def main():
    setup()
    with tempfile.TemporaryDirectory() as tmp:
        meas = {}
        for t in ANGLES:
            meas[t] = e_per_mm(generate(tmp, t))
    base = meas[0][0]
    ratio = {t: meas[t][0] / base for t in ANGLES}
    l4a = e_per_mm(ROOT / f"{D}/L4a_wall_b0.gcode")[0]
    l4b = e_per_mm(ROOT / f"{D}/L4b_wall_u22.gcode")[0]
    lad = l4b / l4a

    fig, ax = figure("half", 6.2)
    tt = np.linspace(0, 32, 200)
    ax.plot(tt, np.cos(np.radians(tt)), color=COLORS[0], label="예측 cosθ (야코비안)")
    ax.axhline(1.0, color=COLORS[7], ls="--", lw=1.0, label="길이 비 모형 1.0")
    ax.plot(ANGLES, [ratio[t] for t in ANGLES], "o", color=COLORS[3], ms=4,
            label="측정 (생성 G-code, xyz)")
    ax.plot([22], [lad], "x", color="k", ms=6, mew=1.2, label="사다리 L4b/L4a (rep5x)")
    ax.annotate(f"22°: {ratio[22]:.4f}", xy=(22, ratio[22]), xytext=(23.5, 0.958), fontsize=8,
                arrowprops={"arrowstyle": "-", "lw": 0.6})
    ax.set_xlabel("원뿔각 θ (°)")
    ax.set_ylabel("벽 1mm 당 E 비 (θ / 0°)")
    ax.set_xlim(-1, 32)
    ax.set_ylim(0.84, 1.02)
    ax.legend(fontsize=6.5, loc="lower left")
    dev = max(abs(ratio[t] - np.cos(np.radians(t))) for t in ANGLES)
    save(fig, "extrusion_ratio", __file__,
         [STL, f"{D}/L4a_wall_b0.gcode", f"{D}/L4b_wall_u22.gcode", "conical_slice.py"],
         "단벽 원기둥(r10×8, 둘레 1줄)을 θ=0~30° 로 실제 생성해 잰 벽 1mm 당 E 비 대 예측 cosθ 와 길이 비 모형 1.0",
         f"22°: 측정 {ratio[22]:.4f} (cos22° = {np.cos(np.radians(22)):.4f}), 사다리 L4b/L4a {lad:.4f}; "
         f"전 각도 |측정 − cosθ| 최대 {dev:.1e}",
         extra={"numbers": {"ratio": {str(t): ratio[t] for t in ANGLES},
                            "e_per_mm_0": base, "ladder_L4b_over_L4a": lad,
                            "generation": "conical_slice.py --mode xyz (스크립트가 임시 폴더에 생성)"}})
    for t in ANGLES:
        print(t, round(ratio[t], 5), round(float(np.cos(np.radians(t))), 5))
    print("ladder", lad)


if __name__ == "__main__":
    main()
