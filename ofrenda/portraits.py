"""Painted portraits for the fictional sample family.

These are flat retablo-style illustrations, generated in code. They are not
photographs, and they are not of real people. A real photograph you add later
is what MediaPipe is for. The flat night background is also what makes the
colour-key fallback cut these cleanly.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Flat night. Keep this far from skin and cloth so the colour key can see a person.
BACKGROUND = (22, 14, 28)

SPECS: list[dict] = [
    {
        "id": "ireti",
        "skin": (168, 112, 78),
        "hair": (88, 62, 48),
        "cloth": (128, 36, 46),
        "trim": (232, 186, 96),
        "wrap": (196, 124, 48),
    },
    {
        "id": "ayo",
        "skin": (150, 102, 72),
        "hair": (190, 184, 176),
        "cloth": (36, 52, 96),
        "trim": (232, 186, 96),
        "beard": True,
        "elder_hair": True,
    },
    {
        "id": "tunde",
        "skin": (142, 94, 64),
        "hair": (48, 32, 26),
        "cloth": (24, 102, 96),
        "trim": (236, 196, 110),
    },
    {
        "id": "folake",
        "skin": (178, 126, 92),
        "hair": (62, 40, 34),
        "cloth": (18, 96, 108),
        "trim": (244, 200, 110),
        "wrap": (212, 156, 52),
    },
    {
        "id": "funke",
        "skin": (188, 134, 98),
        "hair": (52, 32, 28),
        "cloth": (198, 104, 36),
        "trim": (96, 28, 40),
        "wrap": (176, 48, 62),
    },
    {
        "id": "kola",
        "skin": (162, 110, 76),
        "hair": (40, 28, 24),
        "cloth": (236, 224, 198),
        "trim": (36, 64, 110),
        "glasses": True,
    },
    {
        "id": "bisi",
        "skin": (174, 118, 84),
        "hair": (64, 36, 32),
        "cloth": (132, 42, 90),
        "trim": (244, 206, 130),
    },
    {
        "id": "seyi",
        "skin": (196, 146, 112),
        "hair": (44, 30, 26),
        "cloth": (64, 78, 128),
        "trim": (232, 176, 74),
    },
]


def _darker(color: tuple[int, int, int], amount: int = 28) -> tuple[int, int, int]:
    return tuple(max(0, channel - amount) for channel in color)  # type: ignore[return-value]


def paint_portrait(spec: dict) -> Image.Image:
    """One framed figure on a flat background. Deterministic, no font, no text."""
    image = Image.new("RGB", (280, 360), BACKGROUND)
    draw = ImageDraw.Draw(image)
    skin = tuple(spec["skin"])
    hair = tuple(spec["hair"])
    cloth = tuple(spec["cloth"])
    trim = tuple(spec["trim"])
    wrap = tuple(spec["wrap"]) if spec.get("wrap") else None

    # Shoulders, then a few marks that stay on the cloth. The head is painted
    # afterwards so nothing decorative lands on the face.
    draw.ellipse((28, 214, 252, 470), fill=cloth)
    for y in range(300, 348, 24):
        for x in range(78, 210, 24):
            draw.regular_polygon((x, y, 3), 4, fill=trim)
    draw.rounded_rectangle((118, 198, 162, 246), radius=8, fill=skin)
    draw.polygon([(116, 232), (140, 270), (164, 232)], fill=trim)
    draw.ellipse((176, 292, 210, 326), fill=(214, 122, 28))
    draw.ellipse((186, 302, 200, 316), fill=(255, 208, 96))

    # Hair or headwrap sits behind the face, so only a cap and the sides show.
    if wrap:
        draw.polygon([(74, 96), (36, 210), (102, 140)], fill=wrap)
        draw.polygon([(206, 96), (244, 210), (178, 140)], fill=wrap)
        draw.ellipse((54, 24, 226, 150), fill=wrap)
    else:
        draw.ellipse((62, 34, 218, 200), fill=hair)

    draw.ellipse((76, 78, 204, 216), fill=skin)
    draw.ellipse((58, 128, 86, 162), fill=skin)
    draw.ellipse((194, 128, 222, 162), fill=skin)

    if wrap:
        # Forehead band. Kept above the eyes.
        draw.rectangle((88, 78, 192, 102), fill=wrap)
        draw.ellipse((80, 70, 200, 108), fill=wrap)

    blush = (min(255, skin[0] + 24), max(0, skin[1] - 8), max(0, skin[2] - 8))
    draw.ellipse((98, 148, 126, 164), fill=blush)
    draw.ellipse((156, 148, 184, 164), fill=blush)

    eye = (42, 26, 24)
    draw.ellipse((104, 124, 128, 146), fill=(248, 240, 224))
    draw.ellipse((154, 124, 178, 146), fill=(248, 240, 224))
    draw.ellipse((112, 130, 124, 142), fill=eye)
    draw.ellipse((162, 130, 174, 142), fill=eye)
    draw.ellipse((116, 133, 120, 137), fill=(248, 240, 224))
    draw.ellipse((166, 133, 170, 137), fill=(248, 240, 224))
    brow = hair if not wrap else _darker(wrap, 40)
    draw.arc((102, 112, 130, 132), 200, 330, fill=brow, width=3)
    draw.arc((152, 112, 180, 132), 210, 340, fill=brow, width=3)

    if spec.get("glasses"):
        gold = (232, 190, 96)
        draw.ellipse((98, 120, 134, 152), outline=gold, width=3)
        draw.ellipse((148, 120, 184, 152), outline=gold, width=3)
        draw.line((134, 136, 148, 136), fill=gold, width=3)

    draw.line((138, 146, 134, 166), fill=_darker(skin, 40), width=2)
    draw.line((134, 166, 146, 166), fill=_darker(skin, 40), width=2)

    if spec.get("beard"):
        draw.ellipse((102, 176, 178, 228), fill=hair)
        draw.ellipse((108, 150, 172, 200), fill=skin)
    draw.arc((116, 168, 164, 198), 20, 160, fill=(148, 64, 70), width=3)
    return image


def write_portraits(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in SPECS:
        path = directory / f"{spec['id']}.png"
        paint_portrait(spec).save(path, format="PNG")
        written.append(path)
    return written
