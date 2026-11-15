"""Builds image assets: assets/source-* -> icon, side panel, logo.

Run this when the source files change:

    python tools/make_assets.py

Outputs:
    assets/kelam.ico      multi-size application icon (16-256)
    assets/side.png       wizard side panel (190x540)
    assets/logo.png       small logo (96x96)
    assets/head-256.png   icon source (transparent)
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

SIDE_SOURCE = os.path.join(ASSETS, "source-side.jpg")
HEAD_SOURCE = os.path.join(ASSETS, "source-head.png")

SIDE_SIZE = (190, 500)
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BRAND = (0x10, 0x24, 0x3A)


def build_icon_master():
    """Fits the cat head into a square canvas and writes a 256x256 transparent PNG."""
    head = Image.open(HEAD_SOURCE).convert("RGBA")
    bbox = head.getbbox()
    if bbox:
        head = head.crop(bbox)

    side = max(head.size)
    margin = int(side * 0.06)
    canvas = Image.new("RGBA", (side + margin * 2, side + margin * 2), (0, 0, 0, 0))
    canvas.paste(
        head,
        ((canvas.width - head.width) // 2, (canvas.height - head.height) // 2),
        head,
    )
    master = canvas.resize((256, 256), Image.LANCZOS)
    master.save(os.path.join(ASSETS, "head-256.png"))

    ico_path = os.path.join(ASSETS, "kelam.ico")
    master.save(ico_path, format="ICO", sizes=ICO_SIZES)
    master.resize((96, 96), Image.LANCZOS).save(os.path.join(ASSETS, "logo.png"))
    return ico_path


def build_side():
    """Crops the portrait into the panel and darkens it so text stays readable."""
    photo = Image.open(SIDE_SOURCE).convert("RGB")

    target_ratio = SIDE_SIZE[0] / SIDE_SIZE[1]
    width, height = photo.size
    if width / height > target_ratio:
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        photo = photo.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / target_ratio)
        top = int((height - new_height) * 0.35)
        photo = photo.crop((0, top, width, top + new_height))

    photo = photo.resize(SIDE_SIZE, Image.LANCZOS)

    tint = Image.new("RGB", SIDE_SIZE, BRAND)
    photo = Image.blend(photo, tint, 0.45)

    # Slight top-to-bottom darkening so the title and steps read well
    overlay = Image.new("RGBA", SIDE_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(SIDE_SIZE[1]):
        alpha = int(70 + 85 * y / (SIDE_SIZE[1] - 1))
        draw.line([(0, y), (SIDE_SIZE[0], y)], fill=(0, 0, 0, alpha))
    photo = Image.alpha_composite(photo.convert("RGBA"), overlay).convert("RGB")

    path = os.path.join(ASSETS, "side.png")
    photo.save(path, optimize=True)
    return path


def main():
    if not os.path.isfile(SIDE_SOURCE) or not os.path.isfile(HEAD_SOURCE):
        raise SystemExit("assets/source-side.jpg veya assets/source-head.png yok")
    print("ikon :", build_icon_master())
    print("panel:", build_side())


if __name__ == "__main__":
    main()

