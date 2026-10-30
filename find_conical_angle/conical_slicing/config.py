"""Configuration loading, merging, validation, and candidate-angle creation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_CONFIG: dict[str, Any] = {
    "angle_min": 0.0,
    "angle_max": 60.0,
    "angle_step": 1.0,
    "axis_x": 0.0,
    "axis_y": 0.0,
    "kappa_max": 0.3,
    "q0": 1.0,
    "bed_z": 0.0,
    "bed_tolerance": 1e-6,
    "vertex_tolerance": 1e-8,
    "cross_z_epsilon": 1e-12,
    "radial_epsilon": 1e-12,
    "height_overlap_tolerance": 1e-9,
}

NUMERIC_KEYS = set(DEFAULT_CONFIG) - {"axis_x", "axis_y"}
TOLERANCE_KEYS = {
    "bed_tolerance",
    "vertex_tolerance",
    "cross_z_epsilon",
    "radial_epsilon",
    "height_overlap_tolerance",
}


class ConfigError(ValueError):
    """Raised when analysis configuration is invalid."""


def _project_default_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config.json"


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except OSError as exc:
        raise ConfigError(f"설정 파일을 읽을 수 없습니다: {path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"설정 파일이 올바른 JSON이 아닙니다: {path} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(value, dict):
        raise ConfigError("설정 JSON의 최상위 값은 객체여야 합니다.")
    return value


def load_config(
    path: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load defaults (normally config.json), apply overrides, and validate."""

    config = dict(DEFAULT_CONFIG)
    default_path = _project_default_path() if path is None else Path(path)
    if default_path.exists():
        config.update(_read_json_object(default_path))
    elif path is not None:
        raise ConfigError(f"설정 파일이 존재하지 않습니다: {default_path}")
    if overrides:
        config.update(dict(overrides))
    return validate_config(config)


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized copy of *config* or raise ConfigError."""

    unknown = sorted(set(config) - set(DEFAULT_CONFIG))
    if unknown:
        raise ConfigError(f"알 수 없는 설정 항목: {', '.join(unknown)}")

    missing = sorted(set(DEFAULT_CONFIG) - set(config))
    if missing:
        raise ConfigError(f"누락된 설정 항목: {', '.join(missing)}")

    normalized: dict[str, Any] = {}
    for key in NUMERIC_KEYS:
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{key}는 유한한 숫자여야 합니다.")
        number = float(value)
        if not math.isfinite(number):
            raise ConfigError(f"{key}는 유한한 숫자여야 합니다.")
        normalized[key] = number

    for key in ("axis_x", "axis_y"):
        value = config[key]
        if value is None:
            normalized[key] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{key}는 null 또는 유한한 숫자여야 합니다.")
        else:
            number = float(value)
            if not math.isfinite(number):
                raise ConfigError(f"{key}는 null 또는 유한한 숫자여야 합니다.")
            normalized[key] = number

    if (normalized["axis_x"] is None) != (normalized["axis_y"] is None):
        raise ConfigError("axis_x와 axis_y는 둘 다 지정하거나 둘 다 null이어야 합니다.")
    if normalized["angle_step"] <= 0:
        raise ConfigError("angle_step은 0보다 커야 합니다.")
    if normalized["angle_min"] < 0:
        raise ConfigError("angle_min은 0 이상이어야 합니다.")
    if normalized["angle_max"] < normalized["angle_min"]:
        raise ConfigError("angle_max는 angle_min 이상이어야 합니다.")
    if normalized["kappa_max"] < 0:
        raise ConfigError("kappa_max는 0 이상이어야 합니다.")
    if normalized["q0"] <= 0:
        raise ConfigError("q0는 0보다 커야 합니다.")
    for key in TOLERANCE_KEYS:
        if normalized[key] < 0:
            raise ConfigError(f"{key}는 0 이상이어야 합니다.")
    return {key: normalized[key] for key in DEFAULT_CONFIG}


def candidate_angles(config: Mapping[str, Any]) -> np.ndarray:
    """Build sorted, unique degree candidates, including both ends when possible."""

    start = float(config["angle_min"])
    stop = float(config["angle_max"])
    step = float(config["angle_step"])
    if start == stop:
        return np.array([start], dtype=np.float64)

    count = int(math.floor((stop - start) / step))
    values = start + step * np.arange(count + 1, dtype=np.float64)
    scale = max(1.0, abs(start), abs(stop))
    tolerance = 16.0 * np.finfo(np.float64).eps * scale
    values = values[values <= stop + tolerance]
    if values.size == 0 or abs(float(values[0]) - start) > tolerance:
        values = np.insert(values, 0, start)
    else:
        values[0] = start
    if abs(float(values[-1]) - stop) <= tolerance:
        values[-1] = stop
    else:
        values = np.append(values, stop)

    unique = [float(values[0])]
    for value in values[1:]:
        if abs(float(value) - unique[-1]) > tolerance:
            unique.append(float(value))
    return np.asarray(unique, dtype=np.float64)

