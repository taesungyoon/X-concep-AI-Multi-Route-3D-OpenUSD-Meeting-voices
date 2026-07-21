import torch

from torchmcubes import marching_cubes


def test_marching_cubes_fallback_returns_mesh():
    axis = torch.linspace(-1.0, 1.0, 24)
    x, y, z = torch.meshgrid(axis, axis, axis, indexing="ij")
    field = x.square() + y.square() + z.square() - 0.45
    vertices, faces = marching_cubes(field, 0.0)
    assert vertices.ndim == 2 and vertices.shape[1] == 3
    assert faces.ndim == 2 and faces.shape[1] == 3
    assert vertices.shape[0] > 100
    assert faces.dtype == torch.int64
