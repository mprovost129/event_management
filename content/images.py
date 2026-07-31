from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

# A 10 MB cap bounds bytes on disk, not decoded pixels. A highly compressed
# image can be small on disk and enormous in memory, so bound the pixel count
# explicitly rather than relying on Pillow's warn-only default.
MAX_IMAGE_PIXELS = 50_000_000

# Full-size images are what a visitor sees when they open a photo. Thumbnails
# are what a gallery grid loads, and a grid may load dozens at once.
FULL_MAX_DIMENSION = 2400
THUMBNAIL_MAX_DIMENSION = 600

TOO_LARGE_MESSAGE = (
    "That image is too detailed to process. Use one under 50 megapixels."
)


def _decode(upload):
    """Validate an upload and return an oriented, loaded Pillow image."""
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError("Images must be 10 MB or smaller.")
    try:
        image = Image.open(upload)
        image_format = image.format
        width, height = image.size
        if width * height > MAX_IMAGE_PIXELS:
            raise ValidationError(TOO_LARGE_MESSAGE)
        image = ImageOps.exif_transpose(image)
        image.load()
    except Image.DecompressionBombError as exc:
        raise ValidationError(TOO_LARGE_MESSAGE) from exc
    except (OSError, ValueError) as exc:
        raise ValidationError("Upload a valid JPEG, PNG, or WebP image.") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Upload a JPEG, PNG, or WebP image.")
    return image, image_format


def _encode(image, image_format, *, max_dimension, stem, suffix=""):
    """Resize a copy of the image and re-encode it as a new file."""
    resized = image.copy()
    resized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    if image_format == "JPEG" and resized.mode not in ("RGB", "L"):
        resized = resized.convert("RGB")
    save_options = (
        {"optimize": True}
        if image_format == "PNG"
        else {"quality": 88, "optimize": True}
    )
    output = BytesIO()
    resized.save(output, format=image_format, **save_options)
    return ContentFile(
        output.getvalue(), name=f"{stem}{suffix}{EXTENSIONS[image_format]}"
    )


def prepare_image(upload, *, max_dimension):
    """Return a single validated, resized, re-encoded copy of an upload.

    Re-encoding is deliberate: it strips EXIF metadata, including GPS
    coordinates from phone cameras, and neutralizes payloads hidden inside
    otherwise valid image files.
    """
    if not upload or not isinstance(upload, UploadedFile):
        return upload
    image, image_format = _decode(upload)
    stem = Path(upload.name).stem[:80]
    return _encode(image, image_format, max_dimension=max_dimension, stem=stem)


def prepare_image_with_thumbnail(upload):
    """Return a (full_size, thumbnail) pair from one decode of the upload."""
    if not upload or not isinstance(upload, UploadedFile):
        return upload, None
    image, image_format = _decode(upload)
    stem = Path(upload.name).stem[:80]
    full = _encode(image, image_format, max_dimension=FULL_MAX_DIMENSION, stem=stem)
    thumbnail = _encode(
        image,
        image_format,
        max_dimension=THUMBNAIL_MAX_DIMENSION,
        stem=stem,
        suffix="-thumb",
    )
    return full, thumbnail
