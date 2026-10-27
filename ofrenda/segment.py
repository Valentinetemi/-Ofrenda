"""Lift a person out of a portrait.

Two segmenters, on purpose:

1. MediaPipe's selfie segmenter. This is a small on-device model. For the
   square float16 model shipped in ``models/``, the label list is ``selfie``
   and there is one confidence mask: how sure each pixel is "person". The
   older two-class card (background at 0, person at 1) is handled too, by
   reading the labels instead of assuming an index.

2. A border-colour key. Sample the rim, and keep pixels that are not that
   colour. Painted sample portraits and photos against a plain wall work
   here. A busy photograph usually does not, which is why MediaPipe goes first.

A mask that covers almost nothing, or almost the whole frame, is thrown away.
If both fail, an ellipse fades the photo out at the edges so ghost mode still
has a shape to float. The webcam frame is never sent anywhere. Only the
portrait already stored on this machine is segmented, and only once.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from ofrenda.ghost import apply_ghost_treatment, feather_mask

logger = logging.getLogger("ofrenda.segment")

_lock = threading.Lock()
_segmenter = None
_segmenter_failed = False


def mask_is_usable(mask: np.ndarray) -> bool:
    """Reject an empty mask, a full-frame mask, and a handful of specks."""
    if mask.size == 0:
        return False
    fraction = float(np.mean(mask > 0.45))
    return 0.05 <= fraction <= 0.80


def border_color_mask(rgb: np.ndarray) -> np.ndarray:
    """Soft mask of pixels that differ from the colour of the rim.

    The rim is a few pixels on each edge. Distance is plain RGB, which is
    enough when the background is a flat wall or the flat night colour of the
    sample portraits. It is not a substitute for a person segmenter on a
    cluttered photo.
    """
    height, width, _ = rgb.shape
    rim = max(2, min(height, width) // 40)
    edges = np.concatenate(
        [
            rgb[:rim].reshape(-1, 3),
            rgb[-rim:].reshape(-1, 3),
            rgb[:, :rim].reshape(-1, 3),
            rgb[:, -rim:].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.float32)
    background = np.median(edges, axis=0)
    distance = np.linalg.norm(rgb.astype(np.float32) - background, axis=2)
    # 12 absorbs a little compression noise. 42 is a clearly different surface.
    return np.clip((distance - 12.0) / 30.0, 0.0, 1.0).astype(np.float32)


def elliptical_mask(height: int, width: int) -> np.ndarray:
    """Last resort: a soft oval, so a failed cut-out still reads as a figure."""
    yy, xx = np.ogrid[0:height, 0:width]
    ny = (yy - height * 0.46) / (height * 0.48)
    nx = (xx - width * 0.50) / (width * 0.40)
    radius = np.sqrt(nx * nx + ny * ny)
    return np.clip(1.2 - radius, 0.0, 1.0).astype(np.float32)


def _person_index(labels: list[str], mask_count: int) -> int:
    for index, label in enumerate(labels):
        name = label.casefold()
        if "person" in name or "selfie" in name or "human" in name:
            return index if index < mask_count else mask_count - 1
    # Official two-class selfie card: background, then person.
    if mask_count >= 2:
        return 1
    return 0


def mediapipe_person_mask(image: Image.Image, model_path: Path) -> np.ndarray | None:
    """Person confidence in 0–1, or None if MediaPipe cannot run."""
    global _segmenter, _segmenter_failed
    if not model_path.is_file():
        return None
    try:
        import mediapipe as mp
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision import ImageSegmenter, ImageSegmenterOptions, RunningMode
    except Exception as exc:
        logger.warning("MediaPipe is not importable (%s). Using the colour key.", exc)
        return None

    with _lock:
        if _segmenter_failed:
            return None
        if _segmenter is None:
            try:
                _segmenter = ImageSegmenter.create_from_options(
                    ImageSegmenterOptions(
                        base_options=BaseOptions(model_asset_path=str(model_path)),
                        running_mode=RunningMode.IMAGE,
                        output_category_mask=False,
                        output_confidence_masks=True,
                    )
                )
            except Exception:
                logger.exception("Could not start the MediaPipe selfie segmenter")
                _segmenter_failed = True
                return None
        segmenter = _segmenter
        rgb = np.asarray(image.convert("RGB"))
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        try:
            result = segmenter.segment(mp_image)
            labels = [str(label) for label in (segmenter.labels or [])]
            masks = result.confidence_masks or []
            if not masks:
                return None
            index = _person_index(labels, len(masks))
            # numpy_view is only valid until the next call. Copy now.
            mask = np.array(masks[index].numpy_view(), dtype=np.float32, copy=True).squeeze()
        except Exception:
            logger.exception("MediaPipe segmentation failed")
            return None
    if mask.ndim != 2:
        return None
    return mask


def apply_alpha(image: Image.Image, mask: np.ndarray) -> Image.Image:
    """Resize the mask to the photo, feather it, and write it into the alpha."""
    rgba = np.array(image.convert("RGBA"))
    height, width = rgba.shape[:2]
    if mask.shape[:2] != (height, width):
        resized = Image.fromarray(np.clip(mask * 255.0, 0, 255).astype(np.uint8), "L")
        resized = resized.resize((width, height), Image.Resampling.BILINEAR)
        mask = np.asarray(resized).astype(np.float32) / 255.0
    soft = feather_mask(mask, radius=2.0)
    rgba[:, :, 3] = (rgba[:, :, 3].astype(np.float32) * np.clip(soft, 0, 1)).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def segment_person(image: Image.Image, model_path: Path) -> tuple[Image.Image, str]:
    """Return an RGBA cut-out and the name of the method that produced it."""
    mask = None
    method = "ellipse"
    if model_path.is_file():
        guessed = mediapipe_person_mask(image, model_path)
        if guessed is not None and mask_is_usable(guessed):
            mask = guessed
            method = "mediapipe"
        elif guessed is not None:
            coverage = float(np.mean(guessed > 0.45))
            logger.info("MediaPipe mask rejected (coverage %.2f). Trying the colour key.", coverage)

    if mask is None:
        bordered = border_color_mask(np.asarray(image.convert("RGB")))
        if mask_is_usable(bordered):
            mask = bordered
            method = "border"
    if mask is None:
        mask = elliptical_mask(image.height, image.width)
        method = "ellipse"

    coverage = float(np.mean(np.asarray(mask) > 0.45))
    logger.info("segmenter=%s coverage=%.2f", method, coverage)
    return apply_alpha(image, mask), method


def ghost_sprite(image: Image.Image, model_path: Path) -> tuple[Image.Image, str]:
    """Cut the person out and give them the marigold ghost treatment."""
    cutout, method = segment_person(image, model_path)
    return apply_ghost_treatment(cutout), method


def mediapipe_runtime_status(model_path: Path) -> str:
    """'ready', 'missing-model', or 'unavailable'. Used by the health check."""
    if not model_path.is_file():
        return "missing-model"
    try:
        import mediapipe as mp

        blank = np.zeros((8, 8, 3), dtype=np.uint8)
        mp.Image(image_format=mp.ImageFormat.SRGB, data=blank)
    except Exception as exc:
        logger.warning("MediaPipe runtime unavailable: %s", exc)
        return "unavailable"
    return "ready"
