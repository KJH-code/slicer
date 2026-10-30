from __future__ import annotations

import numpy as np
import pytest
import trimesh

from conical_slicing.config import load_config


@pytest.fixture
def base_config() -> dict[str, float | None]:
    return load_config()


def triangle_mesh(vertices, faces=None) -> trimesh.Trimesh:
    vertices_array = np.asarray(vertices, dtype=np.float64)
    if faces is None:
        faces = np.arange(len(vertices_array), dtype=np.int64).reshape((-1, 3))
    return trimesh.Trimesh(
        vertices=vertices_array,
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
    )

