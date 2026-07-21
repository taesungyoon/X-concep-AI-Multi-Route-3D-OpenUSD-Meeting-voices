from __future__ import annotations

import numpy as np
import torch
from skimage.measure import marching_cubes as _skimage_marching_cubes


def marching_cubes(volume: torch.Tensor, isovalue: float):
    """CPU fallback compatible with the torchmcubes API used by TripoSR."""
    source = volume.detach().to(device="cpu", dtype=torch.float32).numpy()
    vertices, faces, _normals, _values = _skimage_marching_cubes(
        source, level=float(isovalue), allow_degenerate=False
    )
    vertices_tensor = torch.from_numpy(np.ascontiguousarray(vertices)).to(
        device=volume.device, dtype=torch.float32
    )
    faces_tensor = torch.from_numpy(
        np.ascontiguousarray(faces.astype(np.int64, copy=False))
    ).to(device=volume.device)
    return vertices_tensor, faces_tensor
