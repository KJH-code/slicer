"""Command-line interface for one-file STL analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from .analysis import analyze_stl, write_json
from .config import ConfigError, load_config
from .mesh import MeshAnalysisError


CONFIG_OPTIONS = {
    "axis_x": "--axis-x",
    "axis_y": "--axis-y",
    "angle_min": "--angle-min",
    "angle_max": "--angle-max",
    "angle_step": "--angle-step",
    "kappa_max": "--kappa-max",
    "q0": "--q0",
    "bed_z": "--bed-z",
    "bed_tolerance": "--bed-tolerance",
    "vertex_tolerance": "--vertex-tolerance",
    "cross_z_epsilon": "--cross-z-epsilon",
    "radial_epsilon": "--radial-epsilon",
    "height_overlap_tolerance": "--height-overlap-tolerance",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "STL의 아래쪽 삼각형 연결 성분과 지지 경계를 분석해 "
            "원뿔 방향 및 각도를 선택합니다."
        )
    )
    parser.add_argument("stl_path", help="분석할 ASCII 또는 binary STL 파일")
    parser.add_argument("--config", help="기본값을 대체할 JSON 설정 파일")
    parser.add_argument("--output", help="결과 JSON 경로 (기본: <STL명>_analysis.json)")
    for destination, option in CONFIG_OPTIONS.items():
        parser.add_argument(option, dest=destination, type=float, default=None)
    return parser


def _default_output(stl_path: str | Path) -> Path:
    source = Path(stl_path)
    return source.with_name(f"{source.stem}_analysis.json")


def _print_summary(result: dict[str, Any], output_path: Path) -> None:
    summary = result["mesh_summary"]
    axis = result["axis"]
    inward = result["direction_results"]["inward"]
    outward = result["direction_results"]["outward"]
    selected = result["selected_result"]
    slice_plan = result["slice_plan"]
    lines = [
        f"입력 STL: {result['input']['stl_path']}",
        f"전체 면: {summary['face_count']}",
        f"바닥면: {summary['bed_face_count']}",
        f"비오버행 면: {summary['non_overhang_face_count']}",
        f"오버행 면: {summary['overhang_face_count']}",
        f"오버행 성분: {summary['overhang_component_count']}",
        f"원뿔축: ({axis['x']:.9g}, {axis['y']:.9g}) [{axis['source']}]",
        f"inward: {inward['final_angle']:.9g} deg, loss={inward['model_loss']:.9g}",
        f"outward: {outward['final_angle']:.9g} deg, loss={outward['model_loss']:.9g}",
        f"최종 선택: {selected['direction']} / {selected['angle']:.9g} deg",
        f"변환 높이 슬라이싱 밴드: {len(slice_plan['bands'])}",
        f"메시 경고: {summary['warning_count']}",
        f"JSON 저장: {output_path}",
    ]
    if slice_plan["bands"]:
        lines.append("밴드별 선택:")
        for band in slice_plan["bands"]:
            component_ids = ", ".join(
                str(component_id) for component_id in band["component_ids"]
            )
            lines.append(
                f"  밴드 {band['band_id']}: "
                f"성분 [{component_ids}], "
                f"{band['direction']} / {band['angle']:.9g} deg, "
                f"signed={band['signed_angle']:.9g} deg, "
                f"h={band['h_min']:.9g}..{band['h_max']:.9g}, "
                f"loss={band['model_loss']:.9g}"
            )
    print("\n".join(lines))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    overrides = {
        key: getattr(args, key)
        for key in CONFIG_OPTIONS
        if getattr(args, key) is not None
    }
    try:
        config = load_config(args.config, overrides)
        result = analyze_stl(args.stl_path, config)
        output_path = Path(args.output) if args.output else _default_output(args.stl_path)
        write_json(result, output_path)
    except (ConfigError, MeshAnalysisError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    _print_summary(result, output_path)
    return 0

