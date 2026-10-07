"""Image checks and re-encoding with Pillow (docs/06: type allow-list, size limit, content
sniffing, re-encode). Why re-encode: the stored file is produced by us, so metadata (GPS in
EXIF), polyglot payloads and malformed chunks from the original never reach other users."""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import AppError

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})  # never SVG (it can carry script)
MAX_PIXELS = 40_000_000  # decompression-bomb guard: refuse anything above ~40 megapixels
MAX_SIDE = 1600  # stored images are resized to fit; enough for menus and backgrounds
WEBP_QUALITY = 82

Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # Pillow raises DecompressionBombError above 2x this


class InvalidImage(AppError):
    status_code, code = 422, "invalid_image"


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    width: int
    height: int
    content_type: str = "image/webp"


def clean_image(raw: bytes) -> CleanImage:
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            pixels = probe.width * probe.height
            probe.verify()  # structural check before decoding pixel data
        if fmt not in ALLOWED_FORMATS:
            raise InvalidImage("unsupported_type", details={"allowed": sorted(ALLOWED_FORMATS)})
        if pixels > MAX_PIXELS:
            raise InvalidImage("too_many_pixels")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            out = _normalised(img)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise InvalidImage() from None
    buffer = io.BytesIO()
    out.save(buffer, "WEBP", quality=WEBP_QUALITY, method=4)  # no EXIF or ICC copied
    return CleanImage(buffer.getvalue(), out.width, out.height)


def _normalised(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)  # keep the photo upright once EXIF is dropped
    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img
