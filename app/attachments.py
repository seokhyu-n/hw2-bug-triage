"""Screenshot attachments on reports: limits and image-type detection.

The type is decided from the file's first bytes, never from the browser's Content-Type or the file
name, so a renamed non-image is rejected and the developer screen only ever serves real images.
"""
import re
from dataclasses import dataclass

MAX_FILES = 3
MAX_BYTES = 5 * 1024 * 1024  # per file; the Claude API also limits a single image to 5 MB
ALLOWED = "PNG, JPG, WEBP, GIF"

_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


class AttachmentError(ValueError):
    """Shown to the reporter as is (Korean)."""


@dataclass
class Upload:
    filename: str
    data: bytes


def sniff(data: bytes) -> str | None:
    """Media type from magic bytes, or None when it is not an allowed image."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def extension(media_type: str) -> str:
    return _EXT[media_type]


def safe_name(filename: str) -> str:
    """Display name only (files are stored under server-made names): no paths, no control chars."""
    name = re.split(r"[\\/]", filename or "")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:80] or "screenshot"


def validate(uploads: list[Upload]) -> list[tuple[str, str, bytes]]:
    """Check count, size and type. Returns (display name, media type, bytes) per file."""
    uploads = [u for u in uploads if u.data]  # an empty file input sends one empty part
    if len(uploads) > MAX_FILES:
        raise AttachmentError(f"사진은 {MAX_FILES}장까지 첨부할 수 있습니다")
    out = []
    for u in uploads:
        name = safe_name(u.filename)
        if len(u.data) > MAX_BYTES:
            raise AttachmentError(f"{name}: 사진 한 장은 {MAX_BYTES // (1024 * 1024)}MB 이하여야 합니다")
        media_type = sniff(u.data)
        if media_type is None:
            raise AttachmentError(f"{name}: 이미지 파일({ALLOWED})만 첨부할 수 있습니다")
        out.append((name, media_type, u.data))
    return out
