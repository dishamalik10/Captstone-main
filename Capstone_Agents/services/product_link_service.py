"""Import a wardrobe photo from a shopping link (Myntra, Ajio, Amazon, H&M, ...).

The link may be a product page or a direct image URL. For a page, the product
photo is taken from the page's Open Graph / Twitter image, its schema.org
Product JSON-LD, or ``<link rel="image_src">``, in that order.

The server fetches URLs a user typed, so every hop (including redirects) must
resolve only to public internet addresses: this blocks requests to localhost,
the LAN, and cloud metadata endpoints.
"""
from __future__ import annotations

import io
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, UnidentifiedImageError

MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 4
TIMEOUT_SECONDS = 10
# Shopping sites often refuse requests that don't look like a browser.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/*;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}
SAVE_FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}


class ProductLinkError(ValueError):
    """A user-facing reason the link could not be imported."""


@dataclass
class ImportedImage:
    content: bytes
    content_type: str
    suffix: str
    source_url: str
    image_url: str
    title: str | None
    site: str


def _check_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProductLinkError("Paste a full shop link starting with https://")
    if parsed.username or parsed.password:
        raise ProductLinkError("Links with a username or password are not supported.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ProductLinkError("That website could not be found. Check the link.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            raise ProductLinkError("That link points to a private network address and cannot be imported.")


def _get(url: str, max_bytes: int) -> tuple[bytes, str, str]:
    """GET with public-address checks on every redirect hop and a hard size cap.
    Returns (body, content type, final URL)."""
    for _ in range(MAX_REDIRECTS + 1):
        _check_public_url(url)
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, stream=True, allow_redirects=False)
        except requests.RequestException as exc:
            raise ProductLinkError("The shop did not respond. Try again or use a different link.") from exc
        with response:
            if response.is_redirect and response.headers.get("location"):
                url = urljoin(url, response.headers["location"])
                continue
            if response.status_code in (401, 403, 429, 503):
                raise ProductLinkError(
                    "This shop blocked the automatic import. Open the product photo, copy its image address, and paste that instead."
                )
            if response.status_code >= 400:
                raise ProductLinkError(f"The shop returned an error ({response.status_code}) for this link.")
            body = bytearray()
            for chunk in response.iter_content(64 * 1024):
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ProductLinkError("That file is too large to import.")
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            return bytes(body), content_type, url
    raise ProductLinkError("The link redirected too many times.")


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.link_image: str | None = None
        self.main_image: str | None = None  # Amazon-style main product <img>
        self.json_ld: list[str] = []
        self.title = ""
        self._in_json_ld = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            if key and values.get("content") and key not in self.meta:
                self.meta[key] = values["content"].strip()
        elif tag == "link" and "image_src" in values.get("rel", "").lower() and values.get("href"):
            self.link_image = self.link_image or values["href"].strip()
        elif tag == "img" and values.get("id") in {"landingImage", "imgBlkFront", "main-image"} and not self.main_image:
            self.main_image = (values.get("data-old-hires") or values.get("src") or "").strip() or None
        elif tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self.json_ld.append("")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_json_ld = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self.json_ld[-1] += data
        elif self._in_title:
            self.title += data


def _json_ld_product(blocks: list[str]) -> tuple[str | None, str | None]:
    """(image URL, name) from the first schema.org Product found in JSON-LD."""
    def products(node: Any):
        if isinstance(node, list):
            for child in node:
                yield from products(child)
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "Product" in kinds:
                yield node
            yield from products(node.get("@graph", []))

    for block in blocks:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for product in products(data):
            image = product.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url") or image.get("contentUrl")
            if isinstance(image, str) and image.strip():
                name = product.get("name")
                return image.strip(), name.strip() if isinstance(name, str) else None
    return None, None


def find_product_image(html: str, page_url: str) -> tuple[str | None, str | None]:
    """(absolute product image URL, product title) from a product page's HTML."""
    parser = _MetaParser()
    parser.feed(html)
    meta = parser.meta
    ld_image, ld_name = _json_ld_product(parser.json_ld)
    image = (
        meta.get("og:image:secure_url") or meta.get("og:image") or meta.get("og:image:url")
        or meta.get("twitter:image") or meta.get("twitter:image:src") or ld_image
        or meta.get("image") or parser.link_image or parser.main_image
    )
    title = meta.get("og:title") or ld_name or meta.get("twitter:title") or re.sub(r"\s+", " ", parser.title).strip() or None
    return (urljoin(page_url, unescape(image)) if image else None), (unescape(title)[:200] if title else None)


def _normalise_image(content: bytes) -> tuple[bytes, str, str]:
    """Validate the bytes are a real image; re-encode formats the CNN pipeline doesn't accept."""
    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(content))
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ProductLinkError("The product photo could not be read. Try copying the image address instead.") from exc
    if image.format in SAVE_FORMATS:
        content_type, suffix = SAVE_FORMATS[image.format]
        return content, content_type, suffix
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=92)
    return buffer.getvalue(), "image/jpeg", ".jpg"


def import_from_link(url: str, max_image_bytes: int) -> ImportedImage:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    body, content_type, final_url = _get(url, max(MAX_PAGE_BYTES, max_image_bytes))
    title: str | None = None
    image_url = final_url
    if content_type.startswith("image/") and len(body) > max_image_bytes:
        raise ProductLinkError("That image is larger than the upload limit.")
    if not content_type.startswith("image/"):
        if len(body) > MAX_PAGE_BYTES:
            raise ProductLinkError("That page is too large to read.")
        found, title = find_product_image(body.decode("utf-8", errors="replace"), final_url)
        if not found:
            raise ProductLinkError(
                "No product photo was found on that page. Open the product photo, copy its image address, and paste that instead."
            )
        image_url = found
        body, content_type, _ = _get(image_url, max_image_bytes)
        if content_type and not content_type.startswith("image/"):
            raise ProductLinkError("The product photo link did not return an image.")
    content, content_type, suffix = _normalise_image(body)
    return ImportedImage(
        content=content, content_type=content_type, suffix=suffix, source_url=url,
        image_url=image_url, title=title, site=(urlparse(final_url).hostname or "").removeprefix("www."),
    )
