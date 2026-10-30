"""Public API for STL conical slicing analysis."""

from .analysis import analyze_stl
from .config import ConfigError, load_config, validate_config

__all__ = ["ConfigError", "analyze_stl", "load_config", "validate_config"]

