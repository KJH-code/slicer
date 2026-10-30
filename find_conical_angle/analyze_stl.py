"""Standalone command entry point; reusable logic lives in conical_slicing."""

from conical_slicing import analyze_stl
from conical_slicing.cli import main

__all__ = ["analyze_stl"]


if __name__ == "__main__":
    raise SystemExit(main())

