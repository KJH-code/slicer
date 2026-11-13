"""증명 B(층간격 식)를 **실제 출력 G-code** 에서 고정한다 (docs/test_t2_t6.md, T2).

    간격(r) = h − r·(tanθₖ₊₁ − tanθₖ)        (c = +1, 부호 각도 규약)

① 상수각이면 모든 이웃 층 간격이 h  ② 블렌드가 있는 프로필에서는 위 식.
작은 원기둥을 CLI(내장 슬라이서)로 자르고, 예측의 θ 는 파일의 ;CONICAL_META 에서 다시 읽는다.
측정 코드는 tools/check_layer_spacing.py 의 것을 그대로 쓴다.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_layer_spacing import measure  # noqa: E402


def _slice(tmp, extra, lh=0.4):
    stl = Path(tmp) / "cyl.stl"
    trimesh.creation.cylinder(radius=6.0, height=8.0, sections=48) \
        .apply_translation([0, 0, 4.0]).export(stl)
    out = Path(tmp) / "out.gcode"
    r = subprocess.run([sys.executable, str(ROOT / "conical_slice.py"), str(stl),
                        "--layer-height", str(lh), "-o", str(out), *extra],
                       cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    return out


def _ratios(path):
    m = measure(path, np.random.default_rng(0))
    a = m["rows"]
    assert len(a) > 200
    return a, a[:, 5] / a[:, 6], m["h"]


def test_constant_angle_spacing_is_h():
    with tempfile.TemporaryDirectory() as tmp:
        a, rho, h = _ratios(_slice(tmp, ["--angle", "25", "--direction", "outward"]))
    assert np.all(np.abs(a[:, 4]) < 1e-12)                 # Δtan ≡ 0
    assert np.allclose(a[:, 6], h)                         # 예측 = h
    assert abs(np.median(rho) - 1.0) < 0.01
    assert np.percentile(np.abs(rho - 1.0), 95) < 0.02


def test_blend_spacing_matches_h_minus_r_dtan():
    # 0→3mm 는 30°, 3→6mm 블렌드에서 tanθ 가 10° 쪽으로 줄어든다 (팽창: 간격 > h)
    with tempfile.TemporaryDirectory() as tmp:
        a, rho, h = _ratios(_slice(tmp, ["--profile", "0:30,3:30,6:10,20:10"]))
    blend = np.abs(a[:, 4]) > 1e-9
    assert blend.sum() > 50
    assert a[blend, 6].max() > 1.2 * h                     # 블렌드에서 예측이 h 와 확실히 다르다
    assert abs(np.median(rho[blend]) - 1.0) < 0.01
    assert np.percentile(np.abs(rho[blend] - 1.0), 95) < 0.02
    assert np.allclose(a[~blend, 6], h)
