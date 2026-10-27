"""Make a cut-out person look like a visit, not a sticker.

The browser uses the same float as `float_offset`. Ghost mode asks
`/api/ghost/motion` for these numbers so the tests and the page cannot drift.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageFilter

# Keep this dict in sync with the sine in static/js/ghost.js.
MOTION = {
    "amplitude_px": 10,
    "period_s": 3.2,
    "drift": 0.28,
    "opacity": 0.78,
    "scale": 0.74,
    "side": "right",
}

# Bump when the treatment changes so cached sprites are rebuilt.
GHOST_VERSION = 1

# Marigold, the flower on the altar.
GLOW_RGB = (255, 168, 64)
WARM_RGB = (255, 228, 196)
HALO_PAD = 18


def float_offset(t: float) -> tuple[int, int]:
    """Gentle bob. `t` is seconds. Negative y is up, matching the canvas."""
    amplitude = float(MOTION["amplitude_px"])
    period = float(MOTION["period_s"])
    drift = float(MOTION["drift"])
    y = round(-amplitude * math.sin(2 * math.pi * t / period))
    x = round(amplitude * drift * math.sin(2 * math.pi * t / (period * 1.7)))
    return int(x), int(y)


def feather_mask(mask: np.ndarray, radius: float = 2.0) -> np.ndarray:
    """Soften a 0–1 mask so the cut edge is not a pair of scissors."""
    if radius <= 0:
        return np.clip(mask, 0.0, 1.0).astype(np.float32)
    image = Image.fromarray(np.clip(mask * 255.0, 0, 255).astype(np.uint8), "L")
    blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(blurred).astype(np.float32) / 255.0


def _pad(image: Image.Image, pad: int) -> Image.Image:
    """Room around the figure so the halo is not clipped by the photo edge."""
    canvas = Image.new("RGBA", (image.width + pad * 2, image.height + pad * 2), (0, 0, 0, 0))
    canvas.paste(image, (pad, pad))
    return canvas


def _over(base: np.ndarray, sprite: np.ndarray) -> np.ndarray:
    """Porter-Duff source-over. Both arrays are float RGBA in 0–255."""
    src_a = sprite[:, :, 3:4] / 255.0
    dst_a = base[:, :, 3:4] / 255.0
    out_a = src_a + dst_a * (1.0 - src_a)
    out_rgb = sprite[:, :, :3] * src_a + base[:, :, :3] * dst_a * (1.0 - src_a)
    safe = np.maximum(out_a, 1e-6)
    out_rgb = np.divide(out_rgb, safe, out=np.zeros_like(out_rgb), where=out_a > 1e-6)
    return np.concatenate([np.clip(out_rgb, 0, 255), np.clip(out_a * 255.0, 0, 255)], axis=2)


def apply_ghost_treatment(image: Image.Image, opacity: float | None = None) -> Image.Image:
    """Translucent figure, a little candle-warm, with a soft marigold ring.

    Steps:
    1. Pad the cut-out so the glow has somewhere to live.
    2. Dilate the alpha and subtract the body, leaving a ring.
    3. Blur that ring and colour it marigold.
    4. Pull the figure's colour a little toward warm white, then lower its alpha
       so the room (or the webcam) shows through the chest and the face.
    5. Composite the figure over the ring. The face stays the face.
    """
    if opacity is None:
        opacity = float(MOTION["opacity"])
    rgba = _pad(image.convert("RGBA"), HALO_PAD)
    arr = np.asarray(rgba).astype(np.float32)
    alpha = arr[:, :, 3]

    dilated = np.asarray(Image.fromarray(alpha.astype(np.uint8), "L").filter(ImageFilter.MaxFilter(9))).astype(
        np.float32
    )
    ring = np.clip(dilated - alpha, 0, 255)
    ring_alpha = (
        np.asarray(Image.fromarray(ring.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius=4))).astype(
            np.float32
        )
        / 255.0
    )

    glow = np.zeros_like(arr)
    glow[:, :, 0] = GLOW_RGB[0]
    glow[:, :, 1] = GLOW_RGB[1]
    glow[:, :, 2] = GLOW_RGB[2]
    glow[:, :, 3] = ring_alpha * 255.0 * 0.9

    warm = np.array(WARM_RGB, dtype=np.float32)
    body = np.zeros_like(arr)
    body[:, :, :3] = np.clip(arr[:, :, :3] * 0.84 + warm * 0.16, 0, 255)
    body[:, :, 3] = alpha * float(opacity)

    return Image.fromarray(_over(glow, body).astype(np.uint8), "RGBA")


def composite_beside(
    frame: Image.Image,
    ghost: Image.Image,
    t: float,
    *,
    side: str | None = None,
    scale: float | None = None,
) -> Image.Image:
    """Place the ghost on one side of a still frame, floating at time `t`.

    The live webcam path does this in the browser. This function is the same
    placement, so a still can be checked without a camera.
    """
    if side is None:
        side = str(MOTION["side"])
    if scale is None:
        scale = float(MOTION["scale"])
    base = frame.convert("RGBA")
    sprite = ghost.convert("RGBA")
    target_h = max(1, int(base.height * scale))
    target_w = max(1, int(sprite.width * (target_h / sprite.height)))
    sprite = sprite.resize((target_w, target_h), Image.Resampling.LANCZOS)
    dx, dy = float_offset(t)
    margin = int(base.width * 0.06)
    if side == "left":
        x = margin + dx
    else:
        x = base.width - target_w - margin + dx
    y = int(base.height * 0.16) + dy
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(sprite, (x, y), sprite)
    return Image.alpha_composite(base, layer)
