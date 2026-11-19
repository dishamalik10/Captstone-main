from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import urlencode

from settings import settings


SIGNED_MEDIA_TTL_SECONDS = 15 * 60


def media_signature(user_id: str, filename: str, expires: int) -> str:
    message = f"{user_id}\n{filename}\n{expires}".encode("utf-8")
    return hmac.new(
        settings.media_signing_key.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def signed_media_url(user_id: str, image_path: str | Path) -> str:
    filename = Path(image_path).name
    expires = int(time.time()) + SIGNED_MEDIA_TTL_SECONDS
    query = urlencode({
        "user_id": user_id,
        "expires": expires,
        "signature": media_signature(user_id, filename, expires),
    })
    return f"/uploads/{filename}?{query}"


def verify_media_signature(
    user_id: str, filename: str, expires: int, signature: str
) -> bool:
    now = int(time.time())
    if expires < now or expires > now + SIGNED_MEDIA_TTL_SECONDS + 5:
        return False
    expected = media_signature(user_id, filename, expires)
    return hmac.compare_digest(expected, signature)
