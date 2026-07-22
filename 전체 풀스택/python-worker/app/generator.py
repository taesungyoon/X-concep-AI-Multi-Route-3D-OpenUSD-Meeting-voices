from __future__ import annotations

import math
import os
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFilter, ImageFont

STORAGE_PATH = Path(os.getenv("STORAGE_PATH", Path(__file__).resolve().parents[2] / "storage"))
FONT_REGULAR = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
FONT_BOLD = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        FONT_BOLD if bold else FONT_REGULAR,
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        FONT_REGULAR,
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def project_dir(project_id: str) -> Path:
    path = STORAGE_PATH / "projects" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_url(project_id: str, filename: str) -> str:
    return f"/storage/projects/{project_id}/{filename}"


def generate_2d(project_id: str, prompt: str, category: str, image_paths: list[str]) -> list[dict]:
    output_dir = project_dir(project_id) / "concepts"
    output_dir.mkdir(parents=True, exist_ok=True)
    styles = [
        ("Compact Line", "공간 효율 중심의 컴팩트 구성", "#23c9e8", "compact"),
        ("Open Frame", "구조와 작업부가 잘 보이는 개방형", "#48dfa7", "open"),
        ("Safety Cover", "투명 안전커버를 적용한 현장형", "#ffc55d", "cover"),
        ("Premium Cell", "제어반과 상태표시를 통합한 셀형", "#9e86ff", "premium"),
    ]
    results: list[dict] = []
    reference = _find_reference_image(project_id, image_paths)
    for index, (title, description, accent, variant) in enumerate(styles, start=1):
        filename = f"concept-{index}.png"
        path = output_dir / filename
        _draw_concept(path, prompt, category, title, accent, variant, reference)
        results.append({
            "id": f"CONCEPT-{index}",
            "title": title,
            "description": description,
            "url": public_url(project_id, f"concepts/{filename}"),
            "absolute_path": str(path),
        })
    return results


def _find_reference_image(project_id: str, paths: list[str]) -> Path | None:
    upload_dir = project_dir(project_id) / "uploads"
    candidates = list(upload_dir.glob("*")) if upload_dir.exists() else []
    if candidates:
        return candidates[0]
    for value in paths:
        candidate = Path(value)
        if candidate.exists():
            return candidate
    return None


def _draw_concept(path: Path, prompt: str, category: str, title: str, accent: str, variant: str, reference: Path | None) -> None:
    width, height = 1120, 840
    image = Image.new("RGB", (width, height), "#071421")
    draw = ImageDraw.Draw(image)
    _gradient_background(image, accent)
    draw.rounded_rectangle((34, 32, width - 34, height - 32), radius=24, outline="#284a62", width=2, fill="#091b2b")
    draw.text((62, 58), "X CONCEP AI · 2D CONCEPT", font=font(18, True), fill=accent)
    draw.text((62, 92), title, font=font(34, True), fill="#f3f8fb")
    category_text = {"equipment": "AUTOMATION EQUIPMENT", "module": "INDUSTRIAL MODULE", "part": "MECHANICAL PART"}[category]
    draw.rounded_rectangle((width - 305, 60, width - 62, 101), radius=10, fill="#0d2b3f", outline="#24536f")
    draw.text((width - 284, 73), category_text, font=font(14, True), fill="#8fbed5")

    scene_box = (74, 148, width - 74, height - 174)
    draw.rounded_rectangle(scene_box, radius=19, fill="#06131f", outline="#15384f", width=2)
    _draw_floor_grid(draw, scene_box, accent)
    _draw_machine(draw, scene_box, accent, variant, category)

    if reference:
        try:
            ref = Image.open(reference).convert("RGB")
            ref.thumbnail((190, 128))
            ref = ref.filter(ImageFilter.GaussianBlur(radius=0.15))
            x, y = width - ref.width - 94, height - ref.height - 197
            image.paste(ref, (x, y))
            draw.rounded_rectangle((x - 5, y - 5, x + ref.width + 5, y + ref.height + 5), radius=9, outline=accent, width=2)
            draw.text((x, y - 26), "REFERENCE", font=font(11, True), fill=accent)
        except OSError:
            pass

    footer_y = height - 145
    draw.line((62, footer_y, width - 62, footer_y), fill="#1b3c52", width=2)
    prompt_short = textwrap.shorten(prompt.replace("\n", " "), width=86, placeholder=" …")
    draw.text((62, footer_y + 22), prompt_short, font=font(16), fill="#b5c7d4")
    draw.text((62, footer_y + 64), "2D 비교 후 선택한 이미지를 기준으로 3D 모델을 생성함", font=font(13), fill="#617e91")
    draw.text((width - 157, footer_y + 62), "01 / 04", font=font(14, True), fill=accent)
    image.save(path, quality=94)


def _gradient_background(image: Image.Image, accent: str) -> None:
    base = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    accent_rgb = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))
    for radius in range(420, 40, -18):
        alpha = int(2 + 22 * (1 - radius / 420))
        box = (image.width * .63 - radius, -radius * .6, image.width * .63 + radius, radius * 1.4)
        draw.ellipse(box, fill=(*accent_rgb, alpha))
    image.alpha_composite(base) if image.mode == "RGBA" else image.paste(Image.alpha_composite(image.convert("RGBA"), base).convert("RGB"))


def _draw_floor_grid(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], accent: str) -> None:
    left, top, right, bottom = box
    horizon = top + int((bottom - top) * .64)
    draw.line((left + 35, horizon, right - 35, horizon), fill="#174158", width=2)
    for i in range(1, 10):
        y = horizon + int((bottom - horizon) * (i / 10) ** .72)
        draw.line((left + 30, y, right - 30, y), fill="#102f43", width=1)
    center = (left + right) // 2
    for dx in range(-420, 421, 70):
        draw.line((center + dx // 5, horizon, center + dx, bottom - 26), fill="#12354a", width=1)
    draw.line((left + 35, top + 38, left + 35, bottom - 28), fill="#12354a", width=1)


def _draw_machine(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], accent: str, variant: str, category: str) -> None:
    left, top, right, bottom = box
    cx = (left + right) // 2
    base_y = bottom - 105
    if category == "part":
        _draw_bracket(draw, cx, base_y, accent, variant)
        return
    scale = 1.0 if category == "equipment" else .83
    base_w = int(600 * scale)
    base_h = int(72 * scale)
    x0, x1 = cx - base_w // 2, cx + base_w // 2
    draw.polygon([(x0, base_y), (x1, base_y), (x1 - 70, base_y + base_h), (x0 + 70, base_y + base_h)], fill="#29495c", outline=accent)
    draw.polygon([(x0, base_y), (x0 + 70, base_y + base_h), (x0 + 70, base_y + base_h + 18), (x0, base_y + 18)], fill="#163247")
    post_top = top + 150
    for px in (x0 + 84, x1 - 84):
        draw.polygon([(px, base_y), (px + 36, base_y - 14), (px + 36, post_top), (px, post_top + 14)], fill="#31556a", outline="#6dc8e0")
    draw.polygon([(x0 + 80, post_top + 12), (x1 - 48, post_top - 12), (x1 - 48, post_top + 35), (x0 + 80, post_top + 56)], fill="#375e73", outline=accent)
    conveyor_y = base_y - 78
    draw.polygon([(x0 + 70, conveyor_y), (x1 - 120, conveyor_y - 24), (x1 - 88, conveyor_y + 16), (x0 + 98, conveyor_y + 41)], fill="#1f6a80", outline="#78d9ee")
    for i in range(7):
        rx = x0 + 120 + i * int((base_w - 260) / 6)
        draw.ellipse((rx - 16, conveyor_y - 1, rx + 17, conveyor_y + 26), fill="#0b2332", outline="#63b8ce")
    panel_x = x1 - 55 if variant in {"premium", "cover"} else x1 - 110
    draw.polygon([(panel_x, base_y - 225), (panel_x + 125, base_y - 250), (panel_x + 125, base_y - 55), (panel_x, base_y - 38)], fill="#214257", outline=accent)
    draw.rounded_rectangle((panel_x + 26, base_y - 202, panel_x + 98, base_y - 143), radius=7, fill="#071927", outline="#49c5df")
    draw.ellipse((panel_x + 39, base_y - 118, panel_x + 54, base_y - 103), fill="#42e0a9")
    draw.ellipse((panel_x + 68, base_y - 118, panel_x + 83, base_y - 103), fill="#ffbc55")
    if variant == "cover":
        cover = [(x0 + 62, post_top + 32), (x1 - 70, post_top + 12), (x1 - 70, base_y - 38), (x0 + 62, base_y - 4)]
        draw.polygon(cover, fill="#1f799077", outline="#77dff2")
    if variant == "open":
        draw.line((cx, post_top + 55, cx, conveyor_y - 16), fill=accent, width=5)
        draw.ellipse((cx - 36, conveyor_y - 68, cx + 36, conveyor_y + 4), outline=accent, width=4)
    if variant == "compact":
        draw.rounded_rectangle((cx - 74, conveyor_y - 128, cx + 74, conveyor_y - 23), radius=12, fill="#153d51", outline=accent, width=3)
    if variant == "premium":
        draw.rounded_rectangle((x0 + 110, post_top + 82, x0 + 235, post_top + 132), radius=11, fill="#112d42", outline=accent)
        draw.text((x0 + 133, post_top + 96), "STATUS", font=font(12, True), fill=accent)


def _draw_bracket(draw: ImageDraw.ImageDraw, cx: int, base_y: int, accent: str, variant: str) -> None:
    draw.polygon([(cx - 280, base_y), (cx + 230, base_y - 55), (cx + 325, base_y + 18), (cx - 190, base_y + 77)], fill="#33566b", outline=accent)
    draw.polygon([(cx - 50, base_y - 15), (cx + 105, base_y - 37), (cx + 105, base_y - 355), (cx - 50, base_y - 316)], fill="#294a60", outline=accent)
    draw.ellipse((cx - 4, base_y - 245, cx + 62, base_y - 176), fill="#081a28", outline="#7adeef", width=4)
    for px, py in [(cx - 200, base_y + 10), (cx + 190, base_y - 25), (cx - 120, base_y + 48)]:
        draw.ellipse((px - 15, py - 9, px + 15, py + 10), fill="#071622", outline=accent)
    if variant in {"cover", "premium"}:
        draw.line((cx + 105, base_y - 350, cx + 230, base_y - 250), fill=accent, width=7)


@dataclass
class Part:
    name: str
    size: tuple[float, float, float]
    center: tuple[float, float, float]
    color: tuple[int, int, int, int]


def build_parts(category: str, variant: int) -> list[Part]:
    cyan = (37, 186, 218, 255)
    steel = (83, 116, 133, 255)
    dark = (27, 52, 67, 255)
    green = (54, 218, 159, 255)
    parts: list[Part] = []
    if category == "part":
        parts.extend([
            Part("base", (4.8, 3.2, .25), (0, 0, .125), steel),
            Part("upright", (.35, 2.8, 3.2), (0, .2, 1.75), cyan),
            Part("rib_left", (.18, 1.3, 1.55), (-.95, .2, .9), dark),
            Part("rib_right", (.18, 1.3, 1.55), (.95, .2, .9), dark),
        ])
        return parts
    width = 5.6 if category == "equipment" else 4.5
    depth = 3.6 if category == "equipment" else 2.8
    height = 4.2 if category == "equipment" else 3.3
    parts.append(Part("base", (width, depth, .32), (0, 0, .16), steel))
    for x in (-width / 2 + .28, width / 2 - .28):
        for y in (-depth / 2 + .28, depth / 2 - .28):
            parts.append(Part("post", (.24, .24, height), (x, y, height / 2 + .3), cyan))
    parts += [
        Part("top_front", (width, .24, .24), (0, -depth / 2 + .28, height + .3), steel),
        Part("top_back", (width, .24, .24), (0, depth / 2 - .28, height + .3), steel),
        Part("conveyor", (width - .9, 1.35, .28), (-.15, -.15, 1.5), dark),
        Part("work_unit", (1.6, 1.5, 1.15), (-.15, -.1, 2.35), cyan if variant % 2 else green),
        Part("control_box", (1.05, .65, 2.05), (width / 2 + .32, .45, 1.65), steel),
    ]
    if variant in (3, 4):
        parts.append(Part("safety_cover", (width - .65, .12, 2.6), (0, -depth / 2 + .12, 2.5), (67, 171, 205, 125)))
    if variant == 4:
        parts.append(Part("status_bar", (2.0, .25, .35), (0, -depth / 2, height - .1), green))
    return parts


def generate_3d(project_id: str, prompt: str, category: str, selected_2d_id: str) -> dict:
    output_dir = project_dir(project_id) / "result"
    output_dir.mkdir(parents=True, exist_ok=True)
    variant = max(1, min(4, int(selected_2d_id.rsplit("-", 1)[-1]) if selected_2d_id.rsplit("-", 1)[-1].isdigit() else 1))
    parts = build_parts(category, variant)
    scene = trimesh.Scene()
    meshes: list[trimesh.Trimesh] = []
    for index, part in enumerate(parts):
        mesh = trimesh.creation.box(extents=part.size)
        mesh.apply_translation(part.center)
        mesh.visual.face_colors = np.array(part.color, dtype=np.uint8)
        scene.add_geometry(mesh, node_name=f"{part.name}_{index}", geom_name=f"{part.name}_{index}")
        meshes.append(mesh.copy())

    glb_path = output_dir / "model.glb"
    stl_path = output_dir / "model.stl"
    preview_path = output_dir / "render.png"
    glb_path.write_bytes(scene.export(file_type="glb"))
    merged = trimesh.util.concatenate(meshes)
    merged.export(stl_path, file_type="stl")
    _render_isometric(preview_path, parts, prompt)
    tags = [
        {"equipment": "자동화 설비", "module": "산업용 모듈", "part": "기계 부품"}[category],
        "GLB", "STL", "3D 렌더링", f"Option {variant}",
    ]
    return {
        "title": {"equipment": "산업용 자동화 설비 3D", "module": "독립형 작업 모듈 3D", "part": "기계 부품 3D"}[category],
        "glb_url": public_url(project_id, "result/model.glb"),
        "stl_url": public_url(project_id, "result/model.stl"),
        "preview_url": public_url(project_id, "result/render.png"),
        "tags": tags,
        "absolute_paths": {"glb": str(glb_path), "stl": str(stl_path), "preview": str(preview_path)},
    }


def _render_isometric(path: Path, parts: Iterable[Part], prompt: str) -> None:
    width, height = 1280, 860
    image = Image.new("RGB", (width, height), "#07131f")
    draw = ImageDraw.Draw(image)
    # radial background
    for r in range(520, 40, -20):
        alpha = int(2 + 17 * (1 - r / 520))
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse((width // 2 - r, 30 - r // 2, width // 2 + r, 30 + r * 1.5), fill=(34, 199, 232, alpha))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((36, 32, width - 36, height - 32), radius=28, fill="#091a29", outline="#20465f", width=2)
    draw.text((65, 58), "X CONCEP AI · 3D RENDERING", font=font(18, True), fill="#25c8e8")
    draw.text((65, 92), "Generated Industrial Concept", font=font(34, True), fill="#f4f8fb")
    draw.text((width - 220, 70), "GLB · STL", font=font(15, True), fill="#8eb7ca")
    scene_rect = (68, 145, width - 68, height - 155)
    draw.rounded_rectangle(scene_rect, radius=20, fill="#06131e", outline="#17394e")
    _draw_iso_grid(draw, scene_rect)

    render_parts = _fit_parts_for_preview(list(parts))
    polygons = []
    for part in render_parts:
        polygons.extend(_box_polygons(part, scene_rect))
    polygons.sort(key=lambda item: item[0])
    for _, points, fill, outline in polygons:
        draw.polygon(points, fill=fill, outline=outline)
    draw.text((76, height - 127), textwrap.shorten(prompt.replace("\n", " "), width=98, placeholder=" …"), font=font(15), fill="#a9becb")
    draw.text((76, height - 89), "실제 서비스 연결 시 선택된 2D 이미지와 생성 모델 API 결과를 표시함", font=font(12), fill="#607d90")
    image.save(path, quality=95)


def _fit_parts_for_preview(parts: list[Part]) -> list[Part]:
    if not parts:
        return []
    minimum = [min(part.center[axis] - part.size[axis] / 2 for part in parts) for axis in range(3)]
    maximum = [max(part.center[axis] + part.size[axis] / 2 for part in parts) for axis in range(3)]
    span = [maximum[axis] - minimum[axis] for axis in range(3)]
    fit_scale = 5.4 / max(max(span), 1e-9)
    center_x = (minimum[0] + maximum[0]) / 2
    center_y = (minimum[1] + maximum[1]) / 2
    base_z = minimum[2]
    return [
        Part(
            part.name,
            tuple(value * fit_scale for value in part.size),
            (
                (part.center[0] - center_x) * fit_scale,
                (part.center[1] - center_y) * fit_scale,
                (part.center[2] - base_z) * fit_scale,
            ),
            part.color,
        )
        for part in parts
    ]


def _iso(point: tuple[float, float, float], rect: tuple[int, int, int, int]) -> tuple[int, int]:
    x, y, z = point
    left, top, right, bottom = rect
    scale = min((right - left) / 10.5, (bottom - top) / 7.6)
    px = (left + right) / 2 + (x - y) * scale * .72
    py = bottom - 95 - (x + y) * scale * .28 - z * scale * .78
    return int(px), int(py)


def _box_polygons(part: Part, rect: tuple[int, int, int, int]) -> list[tuple[float, list[tuple[int, int]], str, str]]:
    sx, sy, sz = part.size
    cx, cy, cz = part.center
    corners = [(cx + dx * sx / 2, cy + dy * sy / 2, cz + dz * sz / 2) for dx, dy, dz in [
        (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    ]]
    faces = [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6)]
    base = part.color[:3]
    colors = [_shade(base, 1.08, part.color[3]), _shade(base, .78, part.color[3]), _shade(base, .94, part.color[3]), _shade(base, .67, part.color[3])]
    result = []
    for face, color in zip(faces, colors):
        points3d = [corners[i] for i in face]
        depth = sum(p[0] + p[1] + p[2] * .1 for p in points3d) / 4
        result.append((depth, [_iso(p, rect) for p in points3d], color, "#6ed5e7"))
    return result


def _shade(rgb: tuple[int, int, int], factor: float, alpha: int) -> str:
    r, g, b = [max(0, min(255, int(value * factor))) for value in rgb]
    # Pillow RGB output; translucent covers are represented by brighter dark color
    if alpha < 255:
        r, g, b = int((r + 7) / 2), int((g + 25) / 2), int((b + 38) / 2)
    return f"#{r:02x}{g:02x}{b:02x}"


def _draw_iso_grid(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = rect
    horizon = bottom - 94
    for i in range(-9, 10):
        draw.line(((left + right) // 2 + i * 34, horizon, (left + right) // 2 + i * 93, top + 160), fill="#103248", width=1)
    for i in range(10):
        y = horizon - int((i / 10) ** .72 * 370)
        draw.line((left + 38, y, right - 38, y), fill="#0f3045", width=1)
