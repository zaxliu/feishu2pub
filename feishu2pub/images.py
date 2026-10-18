"""Prepare downloaded Feishu images for upload to Zhihu."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

# Formats Zhihu accepts as-is; everything else is converted to PNG.
PASSTHROUGH = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "GIF": ("image/gif", "gif")}


@dataclass
class Prepared:
    data: bytes
    mime: str
    ext: str
    width: int
    height: int


def trim_border(im: Image.Image, pad: int = 24, threshold: int = 12) -> Image.Image:
    """Crop uniform background around the content.

    Whiteboard snapshots are square canvases with large blank margins; the
    background colour is sampled from the bottom-right corner.
    """
    rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((rgb.width - 1, rgb.height - 1)))
    mask = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > threshold else 0)
    box = mask.getbbox()
    if not box:
        return im
    l, t, r, b = box
    return im.crop((max(l - pad, 0), max(t - pad, 0), min(r + pad, im.width), min(b + pad, im.height)))


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def prepare(path: Path, trim: bool) -> Prepared:
    """Trimmed images are re-encoded losslessly as PNG; others keep their bytes."""
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        if trim:
            out = trim_border(im)
            return Prepared(_png(out), "image/png", "png", out.width, out.height)
        if im.format in PASSTHROUGH:
            mime, ext = PASSTHROUGH[im.format]
            return Prepared(raw, mime, ext, im.width, im.height)
        return Prepared(_png(im), "image/png", "png", im.width, im.height)


WECHAT_LIMIT = 1_000_000  # media/uploadimg accepts jpg/png under 1MB


def shrink(p: Prepared, limit: int = WECHAT_LIMIT) -> Prepared:
    """Fit WeChat's upload limit, keeping diagrams sharp where possible.

    Order: keep as is -> palette PNG (lossless-looking for whiteboards) ->
    JPEG at decreasing quality and scale.
    """
    if p.ext in ("jpg", "png") and len(p.data) < limit:
        return p
    with Image.open(io.BytesIO(p.data)) as im:
        im.load()
        rgb = im.convert("RGB")
    if p.ext in ("png", "gif"):
        data = _png(rgb.quantize(256))
        if len(data) < limit:
            return Prepared(data, "image/png", "png", rgb.width, rgb.height)
    for scale in (1.0, 0.85, 0.7, 0.55):
        cur = rgb if scale == 1.0 else rgb.resize(
            (int(rgb.width * scale), int(rgb.height * scale)), Image.Resampling.LANCZOS)
        for quality in (90, 82, 75):
            buf = io.BytesIO()
            cur.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() < limit:
                return Prepared(buf.getvalue(), "image/jpeg", "jpg", cur.width, cur.height)
    raise ValueError("image cannot be shrunk below the WeChat upload limit")
