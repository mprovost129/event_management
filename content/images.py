from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def prepare_image(upload, *, max_dimension):
    if not upload:
        return upload
    if not isinstance(upload, UploadedFile):
        return upload
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError("Images must be 10 MB or smaller.")
    try:
        image = Image.open(upload)
        image_format = image.format
        image = ImageOps.exif_transpose(image)
        image.load()
    except (OSError, ValueError) as exc:
        raise ValidationError("Upload a valid JPEG, PNG, or WebP image.") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Upload a JPEG, PNG, or WebP image.")

    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    output = BytesIO()
    output_format = image_format
    if output_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    save_options = (
        {"quality": 88, "optimize": True}
        if output_format != "PNG"
        else {"optimize": True}
    )
    image.save(output, format=output_format, **save_options)
    extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[output_format]
    return ContentFile(
        output.getvalue(), name=f"{Path(upload.name).stem[:80]}{extension}"
    )
