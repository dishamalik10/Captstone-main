"""Decode and re-encode every uploaded or imported image (ENGINEERING_PLAN 4.8).

Re-encoding means only pixels are stored: no EXIF (GPS position, device, time), no
embedded thumbnails or comments, and nothing that only pretends to be an image. The
photo's EXIF rotation is applied first, so it still displays the right way up.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 40_000_000  # ~40 MP; larger is refused (decompression-bomb guard)


class ImageRejected(ValueError):
    """The bytes are not a usable image."""


def reencode(content: bytes) -> tuple[bytes, str, str]:
    """Return (clean bytes, content type, suffix): PNG when the image has transparency,
    otherwise JPEG."""
    try:
        with Image.open(io.BytesIO(content)) as probe:
            if probe.width * probe.height > MAX_PIXELS:
                raise ImageRejected("That image is too large (over 40 megapixels).")
            probe.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
            buffer = io.BytesIO()
            if has_alpha:
                image.convert("RGBA").save(buffer, format="PNG", optimize=True)
                return buffer.getvalue(), "image/png", ".png"
            image.convert("RGB").save(buffer, format="JPEG", quality=92)
            return buffer.getvalue(), "image/jpeg", ".jpg"
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageRejected("That file is not a readable image.") from exc
