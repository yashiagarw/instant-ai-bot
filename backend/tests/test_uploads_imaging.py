"""Photo checks without storage: real type from the bytes, size, decoding, resize and complete metadata removal."""

import io

import pillow_heif
import pytest
from PIL import Image, PngImagePlugin

from app.uploads.imaging import ImageRejected, process, sniff

MB = 1024 * 1024
GPS_IFD = 0x8825


def photo(fmt="JPEG", size=(1200, 800), mode="RGB", exif=None, **kw) -> bytes:
    img = Image.new(mode, size, (200, 80, 30) if mode == "RGB" else (200, 80, 30, 128))
    out = io.BytesIO()
    if fmt == "HEIF":
        pillow_heif.from_pillow(img).save(out, format="HEIF", exif=exif.tobytes() if exif else None)
    else:
        img.save(out, fmt, **({"exif": exif} if exif is not None else {}), **kw)
    return out.getvalue()


def camera_exif(orientation=1) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    exif[0x0110] = "Model X"  # Model
    exif[0x0112] = orientation
    exif[GPS_IFD] = {1: "N", 2: (28.0, 37.0, 12.5), 3: "E", 4: (77.0, 13.0, 44.4)}  # Delhi
    return exif


def assert_clean(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG"
    assert dict(img.getexif()) == {} and img.getexif().get_ifd(GPS_IFD) == {}
    assert not ({"exif", "xmp", "icc_profile", "comment", "XML:com.adobe.xmp"} & set(img.info))
    for secret in (b"Exif", b"SecretCam", b"Model X", b"Location"):
        assert secret not in data
    return img


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (photo("JPEG"), "jpeg"),
        (photo("PNG"), "png"),
        (photo("WEBP"), "webp"),
        (photo("HEIF"), "heic"),
        (photo("GIF"), None),
        (b"%PDF-1.7\n1 0 obj", None),
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", None),
        (b"MZ\x90\x00 an exe renamed photo.jpg", None),
    ],
)
def test_type_comes_from_the_bytes(data, kind):
    assert sniff(data) == kind


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (photo("GIF"), "wrong_type"),
        (b"%PDF-1.7\n" + b"x" * 1000, "wrong_type"),
        (b"<?php echo 1; ?>", "wrong_type"),
        (b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 50, "unreadable"),  # right magic, broken file
    ],
)
def test_wrong_types_are_refused(data, code):
    with pytest.raises(ImageRejected) as e:
        process(data, 10 * MB, 2000)
    assert e.value.code == code


def test_oversize_files_and_decompression_bombs_are_refused():
    with pytest.raises(ImageRejected) as e:
        process(b"\xff\xd8\xff" + b"0" * (10 * MB), 10 * MB, 2000)
    assert e.value.code == "too_large"
    bomb = photo("PNG", size=(12000, 12000))  # a tiny file that decodes to 144 megapixels
    assert len(bomb) < MB
    with pytest.raises(ImageRejected) as e:
        process(bomb, 10 * MB, 2000)
    assert e.value.code == "too_large"


def test_jpeg_exif_and_gps_are_removed_and_the_photo_turned_upright():
    src = photo("JPEG", size=(1200, 800), exif=camera_exif(orientation=6))  # camera held sideways
    assert b"SecretCam" in src and Image.open(io.BytesIO(src)).getexif().get_ifd(GPS_IFD)
    out = process(src, 10 * MB, 2000)
    img = assert_clean(out.data)
    assert (img.width, img.height) == (800, 1200) == (out.width, out.height)  # rotation applied, then dropped
    assert out.source_type == "jpeg"


def test_png_text_and_webp_exif_are_removed():
    info = PngImagePlugin.PngInfo()
    info.add_text("Location", "28.6139 N, 77.2090 E")
    assert_clean(process(photo("PNG", pnginfo=info), 10 * MB, 2000).data)
    webp = photo("WEBP", exif=camera_exif())
    assert b"SecretCam" in webp
    assert_clean(process(webp, 10 * MB, 2000).data)


def test_heic_is_accepted_cleaned_and_converted():
    heic = photo("HEIF", exif=camera_exif())
    out = process(heic, 10 * MB, 2000)
    assert out.source_type == "heic"
    assert_clean(out.data)


def test_large_photos_are_resized_to_2000_px_and_transparency_is_flattened():
    out = process(photo("JPEG", size=(4000, 3000)), 10 * MB, 2000)
    assert (out.width, out.height) == (2000, 1500)
    small = process(photo("JPEG", size=(640, 480)), 10 * MB, 2000)
    assert (small.width, small.height) == (640, 480)  # never enlarged
    rgba = process(photo("PNG", size=(300, 200), mode="RGBA"), 10 * MB, 2000)
    assert Image.open(io.BytesIO(rgba.data)).mode == "RGB"
