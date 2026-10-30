"""Batch runner for repeated conical-slicing STL analyses.

The runner deliberately depends only on the public ``analyze_stl`` API.  It can
scan one model directory, expand a Cartesian parameter grid, repeat identical
runs for timing experiments, and save resilient CSV/JSONL summaries plus the
full result JSON for each successful execution.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import re
import sys
import time
import traceback
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from decimal import Decimal, InvalidOperation

from conical_slicing import analyze_stl
from conical_slicing.analysis import write_json
from conical_slicing.config import DEFAULT_CONFIG, ConfigError, load_config
from conical_slicing.mesh import MeshAnalysisError


BATCH_DEFAULTS: dict[str, Any] = {
    "models_dir": "models",
    "recursive": False,
    "output_dir": "batch_results",
    "run_name": None,
    "repeats": 1,
    "continue_on_error": True,
    "save_detailed_json": True,
    "base_config_file": "config.json",
    "base_overrides": {},
    "parameter_grid": {
        "angle_min": [-89.0],
        "angle_max": [89.0],
        "kappa_max": [0.3],
        "q0": [1.0],
    },
    "parameter_sets": [],
}

SUMMARY_FIXED_FIELDS = [
    "timestamp_utc",
    "status",
    "run_name",
    "experiment_index",
    "configuration_index",
    "repeat",
    "model",
    "model_path",
    "detail_json",
    "runtime_seconds",
    "wall_runtime_seconds",
    "face_count",
    "bed_face_count",
    "non_overhang_face_count",
    "overhang_face_count",
    "degenerate_face_count",
    "overhang_component_count",
    "open_boundary_edge_count",
    "non_manifold_edge_count",
    "inconsistent_winding_edge_count",
    "warning_count",
    "axis_source",
    "resolved_axis_x",
    "resolved_axis_y",
    "inward_angle",
    "inward_loss",
    "outward_angle",
    "outward_loss",
    "selected_direction",
    "selected_angle",
    "selected_loss",
    "selected_angle_allows_all",
    "selected_passed_area",
    "selected_violating_area",
    "selected_feasible_face_count",
    "selected_infeasible_face_count",
    "error_type",
    "error_message",
    "traceback",
]
CONFIG_FIELDS = [f"config_{key}" for key in DEFAULT_CONFIG]
SUMMARY_FIELDS = SUMMARY_FIXED_FIELDS + CONFIG_FIELDS


class BatchConfigError(ValueError):
    """Raised when the batch configuration is malformed."""


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except OSError as exc:
        raise BatchConfigError(f"배치 설정 파일을 읽을 수 없습니다: {path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise BatchConfigError(
            f"배치 설정 파일이 올바른 JSON이 아닙니다: {path} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(value, dict):
        raise BatchConfigError("배치 설정 JSON의 최상위 값은 객체여야 합니다.")
    return value


def _resolve_path(value: str | os.PathLike[str], base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def load_batch_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    """Load and validate a batch configuration.

    Relative paths are interpreted from the directory containing the batch
    configuration, not from the process working directory.
    """

    config_path = Path(path).expanduser().resolve()
    raw = _read_json_object(config_path)
    unknown = sorted(set(raw) - set(BATCH_DEFAULTS))
    if unknown:
        raise BatchConfigError(f"알 수 없는 배치 설정 항목: {', '.join(unknown)}")

    config = dict(BATCH_DEFAULTS)
    config.update(raw)

    for key in ("recursive", "continue_on_error", "save_detailed_json"):
        if not isinstance(config[key], bool):
            raise BatchConfigError(f"{key}는 true 또는 false여야 합니다.")

    repeats = config["repeats"]
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats <= 0:
        raise BatchConfigError("repeats는 1 이상의 정수여야 합니다.")

    run_name = config["run_name"]
    if run_name is not None and (not isinstance(run_name, str) or not run_name.strip()):
        raise BatchConfigError("run_name은 null 또는 비어 있지 않은 문자열이어야 합니다.")

    for key in ("models_dir", "output_dir", "base_config_file"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise BatchConfigError(f"{key}는 비어 있지 않은 문자열이어야 합니다.")

    if not isinstance(config["base_overrides"], dict):
        raise BatchConfigError("base_overrides는 JSON 객체여야 합니다.")
    if not isinstance(config["parameter_grid"], dict):
        raise BatchConfigError("parameter_grid는 JSON 객체여야 합니다.")
    if not isinstance(config["parameter_sets"], list) or any(
        not isinstance(item, dict) for item in config["parameter_sets"]
    ):
        raise BatchConfigError("parameter_sets는 JSON 객체들의 배열이어야 합니다.")

    for key, specification in config["parameter_grid"].items():
        if key not in DEFAULT_CONFIG:
            raise BatchConfigError(
                f"parameter_grid의 알 수 없는 설정 항목: {key}"
            )

        # 여기서 형식과 범위를 미리 검증합니다.
        _expand_grid_values(key, specification)

    for index, parameter_set in enumerate(config["parameter_sets"], start=1):
        unknown_keys = sorted(set(parameter_set) - set(DEFAULT_CONFIG))
        if unknown_keys:
            raise BatchConfigError(
                f"parameter_sets[{index}]의 알 수 없는 설정 항목: "
                f"{', '.join(unknown_keys)}"
            )

    base_dir = config_path.parent
    config["models_dir"] = _resolve_path(config["models_dir"], base_dir)
    config["output_dir"] = _resolve_path(config["output_dir"], base_dir)
    config["base_config_file"] = _resolve_path(config["base_config_file"], base_dir)
    return config, config_path


def discover_stl_files(models_dir: Path, recursive: bool) -> list[Path]:
    if not models_dir.exists():
        raise BatchConfigError(f"모델 폴더가 존재하지 않습니다: {models_dir}")
    if not models_dir.is_dir():
        raise BatchConfigError(f"models_dir는 폴더여야 합니다: {models_dir}")
    candidates = models_dir.rglob("*") if recursive else models_dir.iterdir()
    files = sorted(
        (
            path
            for path in candidates
            if path.is_file() and path.suffix.casefold() == ".stl"
        ),
        key=lambda path: str(path).casefold(),
    )
    if not files:
        raise BatchConfigError(f"STL 파일을 찾지 못했습니다: {models_dir}")
    return files

def _cartesian_grid(
    parameter_grid: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not parameter_grid:
        return [{}]

    keys = list(parameter_grid)

    expanded_values = [
        _expand_grid_values(key, parameter_grid[key])
        for key in keys
    ]

    return [
        dict(zip(keys, values, strict=True))
        for values in itertools.product(*expanded_values)
    ]

def _expand_grid_values(name: str, specification: Any) -> list[Any]:
        """배열 또는 start/stop/step 범위 설정을 실제 값 배열로 변환합니다."""

        if isinstance(specification, list):
            if not specification:
                raise BatchConfigError(
                    f"parameter_grid.{name}은 비어 있지 않은 배열이어야 합니다."
                )
            return specification

        if not isinstance(specification, dict):
            raise BatchConfigError(
                f"parameter_grid.{name}은 배열 또는 "
                '{"start": ..., "stop": ..., "step": ...} 형식이어야 합니다.'
            )

        required_keys = {"start", "stop", "step"}
        unknown_keys = set(specification) - required_keys
        missing_keys = required_keys - set(specification)

        if missing_keys:
            raise BatchConfigError(
                f"parameter_grid.{name}에 누락된 항목: "
                f"{', '.join(sorted(missing_keys))}"
            )

        if unknown_keys:
            raise BatchConfigError(
                f"parameter_grid.{name}의 알 수 없는 항목: "
                f"{', '.join(sorted(unknown_keys))}"
            )

        try:
            start = Decimal(str(specification["start"]))
            stop = Decimal(str(specification["stop"]))
            step = Decimal(str(specification["step"]))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise BatchConfigError(
                f"parameter_grid.{name}의 start, stop, step은 숫자여야 합니다."
            ) from exc

        if not start.is_finite() or not stop.is_finite() or not step.is_finite():
            raise BatchConfigError(
                f"parameter_grid.{name}의 범위 값은 유한한 숫자여야 합니다."
            )

        if step <= 0:
            raise BatchConfigError(
                f"parameter_grid.{name}.step은 0보다 커야 합니다."
            )

        if start > stop:
            raise BatchConfigError(
                f"parameter_grid.{name}에서 start는 stop 이하여야 합니다."
            )

        values: list[float] = []
        current = start

        # stop을 포함하는 범위
        while current <= stop:
            values.append(float(current))
            current += step

        if not values:
            raise BatchConfigError(
                f"parameter_grid.{name}에서 생성된 값이 없습니다."
            )

        return values

def expand_experiment_configs(
    base_config_file: Path,
    base_overrides: Mapping[str, Any],
    parameter_grid: Mapping[str, Any],
    parameter_sets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return validated, deduplicated full analysis configurations.

    Every parameter-set object is overlaid on every Cartesian grid combination.
    An empty ``parameter_sets`` array behaves as one empty overlay.
    """

    grid_items = _cartesian_grid(parameter_grid)
    overlays: Sequence[Mapping[str, Any]] = parameter_sets or ({},)
    configurations: list[dict[str, Any]] = []
    seen: set[str] = set()

    for grid_item in grid_items:
        for overlay in overlays:
            overrides = dict(base_overrides)
            overrides.update(grid_item)
            overrides.update(overlay)
            validated = load_config(base_config_file, overrides)
            signature = json.dumps(validated, sort_keys=True, ensure_ascii=False)
            if signature not in seen:
                seen.add(signature)
                configurations.append(validated)

    if not configurations:
        raise BatchConfigError("실행할 분석 설정 조합이 없습니다.")
    return configurations


def _safe_filename(value: str, max_length: int = 90) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("._")
    return (cleaned or "model")[:max_length]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_run_name() -> str:
    return datetime.now().strftime("run_%Y%m%d_%H%M%S")


def _selected_component_totals(result: Mapping[str, Any]) -> dict[str, Any]:
    direction = str(result["selected_result"]["direction"])
    evaluations = [
        component["direction_evaluations"][direction]
        for component in result["components"]
        if component["direction_evaluations"][direction]["status"] == "ok"
    ]
    if not evaluations:
        return {
            "selected_angle_allows_all": True,
            "selected_passed_area": 0.0,
            "selected_violating_area": 0.0,
            "selected_feasible_face_count": 0,
            "selected_infeasible_face_count": 0,
        }
    return {
        "selected_angle_allows_all": all(
            bool(item["selected_angle_allows_all"]) for item in evaluations
        ),
        "selected_passed_area": sum(float(item["passed_area"]) for item in evaluations),
        "selected_violating_area": sum(
            float(item["violating_area"]) for item in evaluations
        ),
        "selected_feasible_face_count": sum(
            int(item["feasible_face_count"]) for item in evaluations
        ),
        "selected_infeasible_face_count": sum(
            int(item["infeasible_face_count"]) for item in evaluations
        ),
    }


def result_to_summary(
    result: Mapping[str, Any],
    *,
    run_name: str,
    experiment_index: int,
    configuration_index: int,
    repeat: int,
    model_path: Path,
    detail_json: Path | None,
    wall_runtime_seconds: float,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    mesh = result["mesh_summary"]
    inward = result["direction_results"]["inward"]
    outward = result["direction_results"]["outward"]
    selected = result["selected_result"]
    axis = result["axis"]
    row: dict[str, Any] = {
        "timestamp_utc": _utc_now(),
        "status": "ok",
        "run_name": run_name,
        "experiment_index": experiment_index,
        "configuration_index": configuration_index,
        "repeat": repeat,
        "model": model_path.name,
        "model_path": str(model_path.resolve()),
        "detail_json": "" if detail_json is None else str(detail_json.resolve()),
        "runtime_seconds": float(result["runtime_seconds"]),
        "wall_runtime_seconds": wall_runtime_seconds,
        "face_count": int(mesh["face_count"]),
        "bed_face_count": int(mesh["bed_face_count"]),
        "non_overhang_face_count": int(mesh["non_overhang_face_count"]),
        "overhang_face_count": int(mesh["overhang_face_count"]),
        "degenerate_face_count": int(mesh["degenerate_face_count"]),
        "overhang_component_count": int(mesh["overhang_component_count"]),
        "open_boundary_edge_count": int(mesh["open_boundary_edge_count"]),
        "non_manifold_edge_count": int(mesh["non_manifold_edge_count"]),
        "inconsistent_winding_edge_count": int(mesh["inconsistent_winding_edge_count"]),
        "warning_count": int(mesh["warning_count"]),
        "axis_source": str(axis["source"]),
        "resolved_axis_x": float(axis["x"]),
        "resolved_axis_y": float(axis["y"]),
        "inward_angle": float(inward["final_angle"]),
        "inward_loss": float(inward["model_loss"]),
        "outward_angle": float(outward["final_angle"]),
        "outward_loss": float(outward["model_loss"]),
        "selected_direction": str(selected["direction"]),
        "selected_angle": float(selected["angle"]),
        "selected_loss": float(selected["model_loss"]),
        "error_type": "",
        "error_message": "",
        "traceback": "",
    }
    row.update(_selected_component_totals(result))
    row.update({f"config_{key}": config[key] for key in DEFAULT_CONFIG})
    return row


def error_to_summary(
    exc: Exception,
    *,
    run_name: str,
    experiment_index: int,
    configuration_index: int,
    repeat: int,
    model_path: Path,
    wall_runtime_seconds: float,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    row = {field: "" for field in SUMMARY_FIELDS}
    row.update(
        {
            "timestamp_utc": _utc_now(),
            "status": "error",
            "run_name": run_name,
            "experiment_index": experiment_index,
            "configuration_index": configuration_index,
            "repeat": repeat,
            "model": model_path.name,
            "model_path": str(model_path.resolve()),
            "wall_runtime_seconds": wall_runtime_seconds,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }
    )
    row.update({f"config_{key}": config[key] for key in DEFAULT_CONFIG})
    return row


def _write_jsonl_row(stream: Any, row: Mapping[str, Any]) -> None:
    json.dump(dict(row), stream, ensure_ascii=False, allow_nan=False)
    stream.write("\n")
    stream.flush()


def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(dict(manifest), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run_batch(batch_config_path: str | Path, cli_overrides: Mapping[str, Any] | None = None) -> int:
    batch, resolved_batch_path = load_batch_config(batch_config_path)
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None:
                batch[key] = value

    models = discover_stl_files(Path(batch["models_dir"]), bool(batch["recursive"]))
    configurations = expand_experiment_configs(
        Path(batch["base_config_file"]),
        batch["base_overrides"],
        batch["parameter_grid"],
        batch["parameter_sets"],
    )

    run_name = str(batch["run_name"] or _default_run_name())
    run_dir = Path(batch["output_dir"]) / _safe_filename(run_name)
    details_dir = run_dir / "details"
    run_dir.mkdir(parents=True, exist_ok=False)
    if batch["save_detailed_json"]:
        details_dir.mkdir(parents=True, exist_ok=True)

    csv_path = run_dir / "summary.csv"
    jsonl_path = run_dir / "summary.jsonl"
    manifest_path = run_dir / "manifest.json"
    total_planned = len(models) * len(configurations) * int(batch["repeats"])
    manifest: dict[str, Any] = {
        "status": "running",
        "started_utc": _utc_now(),
        "finished_utc": None,
        "batch_config_path": str(resolved_batch_path),
        "run_name": run_name,
        "models_dir": str(Path(batch["models_dir"]).resolve()),
        "models": [str(path.resolve()) for path in models],
        "configuration_count": len(configurations),
        "configurations": configurations,
        "repeats": int(batch["repeats"]),
        "planned_execution_count": total_planned,
        "completed_execution_count": 0,
        "success_count": 0,
        "error_count": 0,
        "summary_csv": str(csv_path.resolve()),
        "summary_jsonl": str(jsonl_path.resolve()),
    }
    _write_manifest(manifest_path, manifest)

    print(f"모델 {len(models)}개 × 설정 {len(configurations)}개 × 반복 {batch['repeats']}회")
    print(f"총 실행 예정: {total_planned}회")
    print(f"결과 폴더: {run_dir}")

    interrupted = False
    experiment_index = 0
    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_stream, jsonl_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as jsonl_stream:
        writer = csv.DictWriter(csv_stream, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        csv_stream.flush()

        try:
            for model_path in models:
                for configuration_index, config in enumerate(configurations, start=1):
                    for repeat in range(1, int(batch["repeats"]) + 1):
                        experiment_index += 1
                        label = (
                            f"[{experiment_index}/{total_planned}] {model_path.name} "
                            f"config={configuration_index}/{len(configurations)} repeat={repeat}"
                        )
                        print(label)
                        started = time.perf_counter()
                        detail_path: Path | None = None
                        try:
                            result = analyze_stl(model_path, config)
                            wall_runtime = time.perf_counter() - started
                            if batch["save_detailed_json"]:
                                stem = _safe_filename(model_path.stem)
                                detail_path = details_dir / (
                                    f"{experiment_index:06d}_{stem}_"
                                    f"c{configuration_index:04d}_r{repeat:03d}.json"
                                )
                                write_json(result, detail_path)
                            row = result_to_summary(
                                result,
                                run_name=run_name,
                                experiment_index=experiment_index,
                                configuration_index=configuration_index,
                                repeat=repeat,
                                model_path=model_path,
                                detail_json=detail_path,
                                wall_runtime_seconds=wall_runtime,
                                config=config,
                            )
                            manifest["success_count"] += 1
                            print(
                                f"  -> {row['selected_direction']} "
                                f"{float(row['selected_angle']):.6g} deg, "
                                f"loss={float(row['selected_loss']):.6g}"
                            )
                        except (ConfigError, MeshAnalysisError, OSError, ValueError) as exc:
                            wall_runtime = time.perf_counter() - started
                            row = error_to_summary(
                                exc,
                                run_name=run_name,
                                experiment_index=experiment_index,
                                configuration_index=configuration_index,
                                repeat=repeat,
                                model_path=model_path,
                                wall_runtime_seconds=wall_runtime,
                                config=config,
                            )
                            manifest["error_count"] += 1
                            print(f"  -> 오류: {type(exc).__name__}: {exc}", file=sys.stderr)
                            if not batch["continue_on_error"]:
                                writer.writerow(row)
                                csv_stream.flush()
                                _write_jsonl_row(jsonl_stream, row)
                                manifest["completed_execution_count"] = experiment_index
                                raise

                        writer.writerow(row)
                        csv_stream.flush()
                        _write_jsonl_row(jsonl_stream, row)
                        manifest["completed_execution_count"] = experiment_index
                        _write_manifest(manifest_path, manifest)
        except KeyboardInterrupt:
            interrupted = True
            print("\n사용자 요청으로 중단했습니다. 완료된 결과는 그대로 보존됩니다.", file=sys.stderr)

    manifest["status"] = "interrupted" if interrupted else "completed"
    manifest["finished_utc"] = _utc_now()
    _write_manifest(manifest_path, manifest)

    print(f"완료: 성공 {manifest['success_count']}회, 오류 {manifest['error_count']}회")
    print(f"CSV: {csv_path}")
    print(f"JSONL: {jsonl_path}")
    return 130 if interrupted else (1 if manifest["error_count"] else 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="폴더의 STL 파일을 설정 조합별로 반복 분석합니다."
    )
    parser.add_argument(
        "--config",
        default="batch_config.json",
        help="배치 설정 JSON 경로 (기본: batch_config.json)",
    )
    parser.add_argument("--models-dir", help="배치 설정의 models_dir 덮어쓰기")
    parser.add_argument("--output-dir", help="배치 설정의 output_dir 덮어쓰기")
    parser.add_argument("--run-name", help="결과 하위 폴더 이름")
    parser.add_argument("--repeats", type=int, help="동일 설정 반복 횟수")
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="하위 폴더의 STL까지 검색",
    )
    parser.add_argument(
        "--save-detailed-json",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="실행별 전체 JSON 저장",
    )
    parser.add_argument(
        "--continue-on-error",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="한 모델이 실패해도 다음 실행 계속",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    overrides: dict[str, Any] = {
        "models_dir": None if args.models_dir is None else Path(args.models_dir).resolve(),
        "output_dir": None if args.output_dir is None else Path(args.output_dir).resolve(),
        "run_name": args.run_name,
        "repeats": args.repeats,
        "recursive": args.recursive,
        "save_detailed_json": args.save_detailed_json,
        "continue_on_error": args.continue_on_error,
    }
    try:
        if args.repeats is not None and args.repeats <= 0:
            raise BatchConfigError("--repeats는 1 이상이어야 합니다.")
        return run_batch(args.config, overrides)
    except (BatchConfigError, ConfigError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
