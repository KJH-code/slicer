"""
test_bridge.py — 팀메 탐색 ↔ 우리 프로필 다리의 정답 아는 시험.

    PYTHONPATH=. python3 -m pytest find_conical_angle/tests_bridge -q

바깥 `pytest tests/` 기준선(141개)과 따로 돈다 — 팀메 패키지 import 가 필요해서다.
"""

import math
import os
import sys

import numpy as np
import pytest
import trimesh

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from conical import analytic
from conical.meshio import center_on_axis
from conical.s3io import cone_dirs, profile_dirs, support_fraction_dirs
from find_conical_angle import bridge


@pytest.fixture
def sphere():
    return center_on_axis(trimesh.creation.icosphere(subdivisions=2, radius=10.0))


def test_bands_to_intervals_fills_gaps_and_merges():
    plan = {"bands": [
        {"h_min": 0.0, "h_max": 10.0, "signed_angle": 20.0},
        {"h_min": 20.0, "h_max": 31.0, "signed_angle": 9.0},
        {"h_min": 35.0, "h_max": 40.0, "signed_angle": 9.0},      # 같은 각 → 합침
    ]}
    iv = bridge.bands_to_intervals(plan, 0.0, 50.0)
    assert iv == [(0.0, 15.0, 20.0), (15.0, 50.0, 9.0)]


def test_bands_to_intervals_no_bands_is_planar():
    assert bridge.bands_to_intervals({"bands": []}, 0.0, 30.0) == [(0.0, 30.0, 0.0)]


def test_single_component_profile_equals_uniform(sphere):
    r = bridge.analyze(sphere, kappa_rule="adaptive")
    assert len(r["bands"]) == 1
    assert r["profile"].is_constant()
    u = r["uniform"]
    assert abs(float(r["profile"].theta_at(5.0)) - u["signed"]) < 1e-9
    assert u["direction"] == "outward"


def test_fixed_kappa_matches_our_threshold(sphere):
    """κ 고정 규칙이면 성분 κ 가 −sin45° 이고, 면 최소각은 우리 critical_angle 과 같다."""
    r = bridge.analyze(sphere, kappa_rule="fixed")
    k = -math.sin(math.radians(45.0))
    for c in r["raw"]["components"]:
        assert abs(c.kappa - k) < 1e-12
    ours = analytic.critical_angle(sphere, "outward", 45.0, 44.0)
    ev = r["raw"]["evaluations"]
    for c in r["raw"]["components"]:
        for item in ev[c.component_id]["outward"]["face_minimum_angles"]:
            if item["feasible"] and not np.isnan(ours[item["face_index"]]):
                assert abs(item["angle"] - ours[item["face_index"]]) < 1e-6


def test_profile_support_is_measured_with_same_ruler(sphere):
    r = bridge.analyze(sphere, kappa_rule="adaptive")
    a = support_fraction_dirs(sphere, profile_dirs(sphere, r["profile"]))
    b = support_fraction_dirs(sphere, cone_dirs(sphere, r["uniform"]["angle"],
                                                 r["uniform"]["direction"]))
    assert abs(a - b) < 1e-9          # 단일 밴드 = 균일


def test_mean_of_minima_leaves_violations(sphere):
    """P1: 면적가중 평균 각도에서는 평균보다 큰 최소각의 면이 위반으로 남는다."""
    r = bridge.analyze(sphere, kappa_rule="adaptive")
    c = r["components"][0]
    assert c["outward"]["allows_all"] is False
    assert c["outward"]["violating_area"] > 0.2 * c["area"]


# ── 수정 ② ─────────────────────────────────────────────────
def test_sweep_fixed_kappa_matches_our_uniform_min(sphere):
    """R2: 손실 최소 전수(κ 45°)는 우리 자의 전수 최소와 같은 각을 골라야 한다.

    팀메 손실은 Σ A·max(0, κ−g) 이고 우리 자는 Σ A·[g<κ] 라 **같은 양이 아니다** —
    하지만 구처럼 매끈한 모델에서는 최소점이 같다(둘 다 0 이 되는 각 중 최소)."""
    r = bridge.analyze(sphere, kappa_rule="fixed", method="sweep", outward_only=True)
    ours = min((support_fraction_dirs(sphere, cone_dirs(sphere, a), exclude=None), a)
               for a in range(0, 45, 2))
    assert r["uniform"]["direction"] == "outward"
    assert support_fraction_dirs(sphere, cone_dirs(sphere, r["uniform"]["angle"])) <= ours[0] + 1e-9


def test_outward_only_never_returns_inward(sphere):
    r = bridge.analyze(sphere, kappa_rule="adaptive", outward_only=True)
    assert r["uniform"]["direction"] == "outward"
    assert all("inward" not in c or c["inward"]["angle"] is None for c in r["components"])
    assert all(b["direction"] == "outward" for b in r["bands"])


def test_sweep_grid_includes_both_ends():
    from conical_slicing.evaluation import sweep_grid
    assert sweep_grid(0.0, 44.0, 2.0)[0] == 0.0
    assert sweep_grid(0.0, 44.0, 2.0)[-1] == 44.0
    assert sweep_grid(0.0, 45.0, 2.0)[-1] == 45.0


# ── 수정 ③ ─────────────────────────────────────────────────
def test_reselect_all_single_band_equals_our_uniform_min(sphere):
    """경계가 하나뿐이면 재선택은 우리 자의 전수 최소(바닥 제외)와 정확히 같아야 한다."""
    from conical.s3io import bed_contact_mask
    r = bridge.analyze(sphere, kappa_rule="adaptive", outward_only=True, reselect="all")
    assert len(r["band_intervals"]) == 1
    bed = bed_contact_mask(sphere)
    sup = {a: support_fraction_dirs(sphere, cone_dirs(sphere, a), exclude=bed)
           for a in range(0, 45, 2)}
    best = min(sup.values())
    expect = min(a for a in sup if sup[a] <= best + 1e-12)
    assert abs(r["band_intervals"][0][2] - expect) < 1e-9
    assert abs(r["reselect_info"][0]["support_at"] - best) < 1e-9


def test_reselect_tolerance_picks_smaller_angle(sphere):
    r0 = bridge.analyze(sphere, outward_only=True, reselect="all", tol_pct=0.0)
    r5 = bridge.analyze(sphere, outward_only=True, reselect="all", tol_pct=5.0)
    assert r5["band_intervals"][0][2] <= r0["band_intervals"][0][2]
    assert r5["reselect_info"][0]["support_at"] <= r5["reselect_info"][0]["support_min"] + 5.0 + 1e-9
