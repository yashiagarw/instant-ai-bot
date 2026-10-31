"""Check and clean an uploaded photo: the real type from the file's first bytes (never the name or the declared
type), at most `max_bytes`, decoded by Pillow, turned upright, resized to `max_px` on the longest side and saved as a
new JPEG with no metadata at all (EXIF, GPS, XMP, ICC, comments). Only the re-encoded pixels are ever stored."""

import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()

ALLOWED = ("jpeg", "png", "webp", "heic")
MAX_PIXELS = 50_000_000  # a 10 MB file that decodes to more is a decompression bomb, not a car photo
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
PIL_FORMATS = {"jpeg": {"JPEG", "MPO"}, "png": {"PNG"}, "webp": {"WEBP"}, "heic": {"HEIF"}}
MESSAGES = {
    "too_large": "This photo is too big. Please use one under 10 MB.",
    "wrong_type": "This file is not a photo we can use. Please send a JPEG, PNG, WebP or HEIC photo.",
    "unreadable": "We couldn't read this photo. Please take or choose another one.",
}


class ImageRejected(ValueError):
    def __init__(self, code: str):
        super().__init__(MESSAGES[code])
        self.code = code


@dataclass
class Processed:
    data: bytes
    width: int
    height: int
    source_type: str  # what the file really was


def sniff(data: bytes) -> str | None:
    """jpeg / png / webp / heic from the magic bytes, else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in HEIF_BRANDS:
        return "heic"
    return None


def process(data: bytes, max_bytes: int, max_px: int) -> Processed:
    if len(data) > max_bytes:
        raise ImageRejected("too_large")
    kind = sniff(data)
    if kind is None:
        raise ImageRejected("wrong_type")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in PIL_FORMATS[kind]:
                raise ImageRejected("wrong_type")
            img.load()
            upright = ImageOps.exif_transpose(img)  # apply the camera's rotation before its metadata is dropped
    except Image.DecompressionBombError as e:
        raise ImageRejected("too_large") from e
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as e:
        raise ImageRejected("unreadable") from e
    if upright.mode in ("RGBA", "LA", "P"):
        rgba = upright.convert("RGBA")
        upright = Image.new("RGB", rgba.size, "white")
        upright.paste(rgba, mask=rgba.getchannel("A"))
    elif upright.mode != "RGB":
        upright = upright.convert("RGB")
    upright.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    # A fresh image: pixels only. Nothing from the original's info (exif, xmp, icc_profile, comments) is carried.
    clean = Image.frombytes("RGB", upright.size, upright.tobytes())
    out = io.BytesIO()
    clean.save(out, "JPEG", quality=85, optimize=True)
    return Processed(out.getvalue(), clean.width, clean.height, kind)
