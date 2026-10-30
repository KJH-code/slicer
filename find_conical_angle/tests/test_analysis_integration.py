from __future__ import annotations

import json

import pytest

from analyze_stl import analyze_stl
from conical_slicing.analysis import write_json
from conical_slicing.cli import main
from conftest import triangle_mesh


def test_full_stl_analysis_is_strict_json(tmp_path, base_config):
    mesh = triangle_mesh(
        [
            [0, 0, 0], [0, 1, 0], [1, 0, 1], [1, 0, 0],
            [3, 0, 1], [3, 1, 1], [4, 0, 1],
        ],
        [[0, 1, 2], [1, 0, 3], [4, 5, 6]],
    )
    stl_path = tmp_path / "synthetic.stl"
    mesh.export(stl_path)
    result = analyze_stl(stl_path, base_config)
    output = write_json(result, tmp_path / "result.json")
    reloaded = json.loads(output.read_text(encoding="utf-8"))

    assert reloaded["schema_version"] == "1.3"
    assert reloaded["mesh_summary"]["face_count"] == 3
    assert reloaded["mesh_summary"]["overhang_component_count"] == 2
    assert set(reloaded["direction_results"]) == {"inward", "outward"}
    assert reloaded["selected_result"]["angle"] >= 0.0
    assert len(reloaded["components"]) == 2

    supported = reloaded["components"][0]
    assert supported["downward_boundary_face_indices"] == [0]
    assert supported["downward_boundary_face_count"] == 1
    assert supported["downward_boundary_ratio"] == pytest.approx(1.0)
    assert supported["q_source"] == "downward_boundary_area_ratio"


def test_cli_reports_bad_file_without_traceback(capsys):
    exit_code = main(["does-not-exist.stl"])
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "오류:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_partial_axis(capsys, tmp_path):
    mesh = triangle_mesh([[0, 0, 1], [0, 1, 1], [1, 0, 1]])
    stl_path = tmp_path / "one.stl"
    mesh.export(stl_path)
    exit_code = main([str(stl_path), "--axis-x", "1"])
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "axis_x와 axis_y" in captured.err
