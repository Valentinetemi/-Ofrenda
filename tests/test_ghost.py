"""Segmentation and the ghost composite. No webcam, no live model weights required."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ofrenda import segment as segment_module
from ofrenda.ghost import (
    HALO_PAD,
    MOTION,
    sepia_tone,
    apply_ghost_treatment,
    composite_beside,
    float_offset,
)
from ofrenda.segment import border_color_mask, mask_is_usable, segment_person

ROOT = Path(__file__).resolve().parents[1]


def _figure(size=(90, 120)) -> Image.Image:
    image = Image.new("RGB", size, (22, 14, 28))
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 18, 60, 58), fill=(200, 150, 110))
    draw.rectangle((24, 50, 66, 112), fill=(180, 70, 40))
    return image


def test_float_rests_then_rises():
    assert float_offset(0) == (0, 0)
    _x, y = float_offset(MOTION["period_s"] / 4)
    assert y == -MOTION["amplitude_px"]


def test_browser_uses_the_same_float():
    script = (ROOT / "static" / "js" / "ghost.js").read_text(encoding="utf-8")
    assert "period * 1.7" in script
    assert "-amplitude * Math.sin" in script
    assert "amplitude_px" in script


def test_border_key_keeps_the_figure_and_drops_the_corner():
    cutout, method = segment_person(_figure(), Path("/no/such/model.tflite"))
    assert method == "border"
    arr = np.asarray(cutout)
    assert arr[0, 0, 3] == 0
    assert arr[36, 45, 3] > 180


def test_unusable_mediapipe_mask_falls_back(monkeypatch, tmp_path):
    model = tmp_path / "selfie.tflite"
    model.write_bytes(b"not a model")

    def empty_mask(image, _path):
        return np.zeros((image.size[1], image.size[0]), dtype=np.float32)

    monkeypatch.setattr(segment_module, "mediapipe_person_mask", empty_mask)
    _cutout, method = segment_person(_figure(), model)
    assert method == "border"


def test_flat_field_uses_an_ellipse(tmp_path):
    image = Image.new("RGB", (40, 50), (22, 14, 28))
    cutout, method = segment_person(image, tmp_path / "missing.tflite")
    assert method == "ellipse"
    arr = np.asarray(cutout)
    assert arr[0, 0, 3] < arr[25, 20, 3]


def test_mask_usable_bounds():
    assert not mask_is_usable(np.zeros((10, 10)))
    assert not mask_is_usable(np.ones((10, 10)))
    half = np.zeros((10, 10))
    half[:, :5] = 1
    assert mask_is_usable(half)


def test_border_mask_is_soft_on_the_figure():
    mask = border_color_mask(np.asarray(_figure()))
    assert mask[0, 0] == 0
    assert mask[36, 45] > 0.8


def test_ghost_treatment_is_translucent_and_has_a_marigold_halo():
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 29, 29), fill=(220, 40, 40, 255))
    ghost = apply_ghost_treatment(image)
    assert ghost.size == (40 + HALO_PAD * 2, 40 + HALO_PAD * 2)
    arr = np.asarray(ghost)
    center = HALO_PAD + 20
    alpha = int(arr[center, center, 3])
    assert 60 <= alpha <= 100  # about 30% opaque: a faint memory
    # Just outside the original square, the halo should be warm rather than red body.
    halo = arr[center, HALO_PAD + 4]
    assert halo[3] > 8
    assert int(halo[0]) > int(halo[2])
    assert halo[3] < 60  # a glow, not a ring


def test_composite_places_the_ghost_on_the_right_and_lifts_it():
    frame = Image.new("RGB", (120, 100), (10, 16, 40))
    sprite = Image.new("RGBA", (20, 40), (255, 255, 255, 255))
    still = composite_beside(frame, sprite, 0)
    risen = composite_beside(frame, sprite, MOTION["period_s"] / 4)

    def bright(image: Image.Image):
        # The frame is dark blue. The ghost is white. Alpha stays opaque
        # because the frame itself is opaque, so look at colour.
        rgb = np.asarray(image.convert("RGB"))
        return np.where(np.all(rgb > 200, axis=2))

    ys, xs = bright(still)
    assert len(xs) > 0
    assert xs.mean() > frame.width / 2
    risen_top = bright(risen)[0].min()
    assert ys.min() - risen_top == MOTION["amplitude_px"]


def test_ghost_is_sepia_not_cartoon_colour():
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((10, 10, 29, 29), fill=(30, 60, 220, 255))  # saturated blue
    arr = np.asarray(apply_ghost_treatment(image))
    r, g, b = (int(v) for v in arr[HALO_PAD + 20, HALO_PAD + 20, :3])
    assert r > g > b  # warm brown, the blue is gone


def test_sepia_tone_is_monotonic_in_brightness():
    dark = sepia_tone(np.array([[20.0, 20.0, 20.0]], dtype=np.float32))
    light = sepia_tone(np.array([[200.0, 200.0, 200.0]], dtype=np.float32))
    assert light.sum() > dark.sum()


def test_ghost_is_faint_and_fades_in():
    assert 0.2 <= MOTION["opacity"] <= 0.35
    assert 2.0 <= MOTION["fade_in_s"] <= 3.0
    script = (ROOT / "static" / "js" / "ghost.js").read_text(encoding="utf-8")
    assert "fade_in_s" in script and "globalAlpha" in script


def test_cutout_edge_is_feathered():
    cutout, _method = segment_person(_figure(), Path("/no/such/model.tflite"))
    alpha = np.asarray(cutout)[:, :, 3]
    # A hard cut-out is almost all 0 or 255. A feathered one has a real ramp.
    ramp = np.mean((alpha > 20) & (alpha < 235))
    assert ramp > 0.02
