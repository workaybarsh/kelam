"""Build English promo images for Kelam from a real wizard screenshot.

Output: docs/promo-hero.png, docs/promo-flow.png, docs/promo-features.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "AppData/Local/Temp/kelam_welcome.png"

BG = (11, 17, 29)
CARD = (21, 29, 44)
CARD2 = (32, 42, 60)
BORDER = (48, 60, 80)
FG = (233, 238, 245)
MUTED = (141, 154, 174)
ACCENT = (59, 130, 246)
GREEN = (52, 211, 153)
AMBER = (245, 158, 11)

W, H = 1200, 630
FONT_DIR = Path(r"C:\Windows\Fonts")
BOLD = "segoeuib.ttf"
SEMI = "seguisb.ttf"
REG = "segoeui.ttf"
MONO = "consola.ttf"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def rounded(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.size[0], image.size[1]), radius, fill=255)
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    return out


def framed(image: Image.Image, color=BORDER, width: int = 2) -> Image.Image:
    canvas = Image.new("RGBA", (image.size[0] + width * 2, image.size[1] + width * 2), color)
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, canvas.size[0], canvas.size[1]), 14, fill=255)
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    out.paste(canvas, (0, 0), mask)
    out.paste(image, (width, width), image)
    return out


def crop_client(path: Path) -> Image.Image:
    shot = Image.open(path).convert("RGB")
    # window borders + title bar are not part of the UI
    return shot.crop((6, 32, shot.width - 6, shot.height - 6))


def paste_shot(base: Image.Image, box: tuple[int, int, int, int]) -> None:
    if not SHOT.is_file():
        return
    shot = crop_client(SHOT)
    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    scale = min(max_w / shot.width, max_h / shot.height)
    shot = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS)
    card = framed(rounded(shot, 12))
    x = box[0] + (max_w - card.width) // 2
    y = box[1] + (max_h - card.height) // 2
    base.alpha_composite(card, (x, y))


def hero() -> None:
    image = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(image)

    head = Image.open(ROOT / "assets" / "head-256.png").convert("RGBA")
    head.thumbnail((92, 92), Image.LANCZOS)
    image.alpha_composite(head, (60, 48))

    draw.text((60, 158), "Kelam", font=font(BOLD, 52), fill=FG)
    draw.text((60, 220), "Your remote's mic button,", font=font(REG, 21), fill=MUTED)
    draw.text((60, 248), "connected to Windows voice typing.", font=font(REG, 21), fill=MUTED)

    draw.text((60, 300), "Press the button. Speak.", font=font(SEMI, 22), fill=FG)
    draw.text((60, 332), "The text appears where the cursor is.", font=font(SEMI, 22), fill=ACCENT)

    chips = [("Any remote", ACCENT), ("Any app", ACCENT), ("No cloud, no extra keys", GREEN)]
    y = 396
    for label, color in chips:
        width = draw.textlength(label, font=font(SEMI, 15)) + 26
        draw.rounded_rectangle((60, y, 60 + width, y + 34), 17, fill=CARD2, outline=BORDER)
        draw.text((73, y + 8), label, font=font(SEMI, 15), fill=color)
        y += 44

    draw.text((60, 566), "github.com/workaybarsh", font=font(MONO, 13), fill=MUTED)
    draw.text((60, 586), "/kelam", font=font(MONO, 13), fill=MUTED)

    paste_shot(image, (470, 56, 1146, 574))
    image.convert("RGB").save(DOCS / "promo-hero.png")


def flow() -> None:
    image = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((60, 56), "One button, five steps", font=font(BOLD, 42), fill=FG)
    draw.text(
        (60, 112),
        "Kelam only relays the button; Windows does the typing.",
        font=font(REG, 19),
        fill=MUTED,
    )

    steps = [
        ("1", "Mic button", "A consumer-control or\nkeyboard event"),
        ("2", "Kelam bridge", "Runs in the tray,\nno window"),
        ("3", "Win+H", "Windows voice typing\nopens"),
        ("4", "You speak", "Text is typed into\nthe focused field"),
        ("5", "Any app", "Browser, Notepad,\nchat, search"),
    ]

    box_w, gap = 192, 28
    x = 64
    y = 210
    for index, (number, title, body) in enumerate(steps):
        card = Image.new("RGBA", (box_w, 190), CARD)
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, box_w - 1, 189), 14, outline=BORDER, width=2)
        cd.ellipse((16, 16, 44, 44), fill=(22, 58, 104), outline=ACCENT)
        cd.text((26, 22), number, font=font(SEMI, 15), fill=(190, 215, 255))
        cd.text((16, 62), title, font=font(SEMI, 19), fill=FG)
        cd.multiline_text((16, 96), body, font=font(REG, 14), fill=MUTED, spacing=5)
        image.alpha_composite(card, (x, y))
        if index < len(steps) - 1:
            ax = x + box_w + 6
            draw.line((ax, y + 95, ax + gap - 12, y + 95), fill=BORDER, width=3)
            draw.polygon(
                [(ax + gap - 12, y + 88), (ax + gap - 12, y + 102), (ax + gap, y + 95)],
                fill=ACCENT,
            )
        x += box_w + gap

    draw.rounded_rectangle((60, 452, 1140, 552), 14, fill=CARD, outline=BORDER)
    draw.text((84, 474), "Nothing leaves your PC.", font=font(SEMI, 19), fill=GREEN)
    draw.text(
        (84, 506),
        "Kelam has no account, no cloud and no telemetry: it translates one button "
        "into one keystroke.",
        font=font(REG, 15),
        fill=MUTED,
    )

    image.convert("RGB").save(DOCS / "promo-flow.png")


def features() -> None:
    image = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((60, 56), "Small app, no surprises", font=font(BOLD, 40), fill=FG)
    draw.text((60, 110), "What you get with the wizard.", font=font(REG, 19), fill=MUTED)

    cards = [
        ("Teach any key", "Press the mic button once;\nKelam remembers that event."),
        ("Pick the action", "Windows voice typing by default,\nor your own hotkey."),
        ("Runs quietly", "A small background bridge,\noptional start with Windows."),
        ("Two languages", "English and Turkish, switch\nany time, remembered."),
        ("Clean folder", "Settings and logs live in\n%APPDATA%, never next to the exe."),
        ("Clean uninstall", "Removes files, startup entry\nand shortcuts in one step."),
    ]

    for index, (title, body) in enumerate(cards):
        col = index % 3
        row = index // 3
        x = 60 + col * 366
        y = 176 + row * 210
        card = Image.new("RGBA", (346, 190), CARD)
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 345, 189), 14, outline=BORDER, width=2)
        cd.rounded_rectangle((22, 22, 46, 46), 7, fill=(22, 58, 104))
        cd.text((29, 25), str(index + 1), font=font(SEMI, 14), fill=(190, 215, 255))
        cd.text((22, 62), title, font=font(SEMI, 20), fill=FG)
        cd.multiline_text((22, 98), body, font=font(REG, 15), fill=MUTED, spacing=5)
        image.alpha_composite(card, (x, y))

    image.convert("RGB").save(DOCS / "promo-features.png")


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    if not SHOT.is_file():
        print(f"screenshot not found: {SHOT}")
        return 1
    hero()
    flow()
    features()
    for name in ("promo-hero.png", "promo-flow.png", "promo-features.png"):
        path = DOCS / name
        print(f"{path}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
