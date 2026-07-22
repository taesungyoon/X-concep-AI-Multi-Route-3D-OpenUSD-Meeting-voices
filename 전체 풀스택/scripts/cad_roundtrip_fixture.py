from __future__ import annotations

from typing import Any

from build123d import Box, Compound, Cylinder, Part, Pos


CASE_COUNT = 60


def case_spec(index: int) -> dict[str, Any]:
    if not 0 <= index < CASE_COUNT:
        raise ValueError(f"case index must be 0..{CASE_COUNT - 1}")
    family_index = index % 4
    variant = index // 4
    return {"index": index, "family": ("plate", "bracket", "spacer", "assembly")[family_index], "variant": variant}


def _plate(variant: int) -> Part:
    width = 50.0 + variant * 2.0
    depth = 36.0 + variant
    thickness = 4.0 + variant % 4
    hole_radius = 2.0 + (variant % 3) * 0.25
    hole_count = 1 + variant % 4
    part = Box(width, depth, thickness)
    spacing = width / (hole_count + 1)
    for hole_index in range(hole_count):
        x = -width / 2.0 + spacing * (hole_index + 1)
        tool = Pos(x, 0, 0) * Cylinder(hole_radius, thickness + 2.0)
        part = part - tool
    part.label = f"plate_{variant:02d}"
    return part


def _bracket(variant: int) -> Part:
    width = 55.0 + variant * 2.0
    depth = 30.0 + variant
    thickness = 4.0 + variant % 3
    height = 28.0 + variant * 1.5
    base = Box(width, depth, thickness)
    wall = Pos(-width / 2.0 + thickness / 2.0, 0, (height - thickness) / 2.0) * Box(thickness, depth, height)
    part = base + wall
    hole = Pos(width / 5.0, 0, 0) * Cylinder(2.25, thickness + 2.0)
    part = part - hole
    part.label = f"bracket_{variant:02d}"
    return part


def _spacer(variant: int) -> Part:
    outer_radius = 8.0 + variant * 0.35
    inner_radius = 2.0 + (variant % 4) * 0.25
    height = 10.0 + variant
    part = Cylinder(outer_radius, height) - Cylinder(inner_radius, height + 2.0)
    part.label = f"spacer_{variant:02d}"
    return part


def _assembly(variant: int) -> Compound:
    width_a = 18.0 + variant
    width_b = 12.0 + variant * 0.5
    depth = 16.0 + variant * 0.3
    height = 8.0 + variant * 0.2
    signed_clearance = (0.5 + (variant % 3) * 0.5) if variant % 2 == 0 else -(1.0 + (variant % 3) * 0.5)
    part_a = Box(width_a, depth, height)
    part_a.label = "fixed_block"
    centre_x = width_a / 2.0 + width_b / 2.0 + signed_clearance
    part_b = Pos(centre_x, 0, 0) * Box(width_b, depth, height)
    part_b.label = "moving_block"
    assembly = Compound(children=[part_a, part_b])
    assembly.label = f"clearance_assembly_{variant:02d}"
    return assembly


def build_case(index: int):
    spec = case_spec(index)
    builders = {"plate": _plate, "bracket": _bracket, "spacer": _spacer, "assembly": _assembly}
    return builders[spec["family"]](spec["variant"])


def gen_step():
    """Default artifact used by the CAD skill CLI; the benchmark calls build_case for all 60 variants."""
    return build_case(0)
