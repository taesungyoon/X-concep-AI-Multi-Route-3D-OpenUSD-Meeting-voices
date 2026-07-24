from pathlib import Path
import sys

from PIL import Image, ImageDraw


RENDER_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "render"
FILES = sorted(RENDER_DIR.glob("page-*.png"))

for sheet_index in range(0, len(FILES), 12):
    group = FILES[sheet_index : sheet_index + 12]
    thumb_w, thumb_h = 255, 330
    sheet = Image.new("RGB", (thumb_w * 4, thumb_h * 3), "white")
    draw = ImageDraw.Draw(sheet)
    for offset, path in enumerate(group):
        page = Image.open(path).convert("RGB")
        page.thumbnail((thumb_w - 12, thumb_h - 28))
        x = (offset % 4) * thumb_w + (thumb_w - page.width) // 2
        y = (offset // 4) * thumb_h + 20
        sheet.paste(page, (x, y))
        draw.text((x, 3 + (offset // 4) * thumb_h), path.stem, fill="black")
    sheet.save(RENDER_DIR / f"contact-{sheet_index // 12 + 1}.png")
