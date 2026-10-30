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
