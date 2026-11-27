"""Import a wardrobe photo from a shopping link (Myntra, Ajio, Amazon, H&M, ...).

The link may be a product page or a direct image URL. For a page, the product
photo is taken from the page's Open Graph / Twitter image, its schema.org
Product JSON-LD, or ``<link rel="image_src">``, in that order.

The server fetches URLs a user typed, so every hop (including redirects) must
resolve only to public internet addresses: this blocks requests to localhost,
the LAN, and cloud metadata endpoints. The connection is made to the exact address
that passed the check (never a second DNS lookup, so a rebinding DNS answer can't
swap in a private address), with TLS still verified against the real hostname. No
proxy is used, and one import (page plus photo, all redirects) has 20 seconds in all.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import certifi
import urllib3
from urllib3.connection import HTTPConnection, HTTPSConnection
from services.image_sanitize import ImageRejected, reencode

MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 4
TIMEOUT_SECONDS = 10  # per connect / read
TOTAL_SECONDS = 20  # the whole import
# Shopping sites often refuse requests that don't look like a browser.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/*;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


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
    # 4.2b: text that hints at the garment category (title, JSON-LD category, breadcrumbs),
    # and whether the chosen photo was checked and has no person in it (None: not checked).
    hints: tuple[str, ...] = ()
    person_free: bool | None = None
    # 4.11: the size named on the page, when the page names exactly one (most list them all).
    size: str | None = None


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    port: int
    family: int
    sockaddr: tuple
    path: str


def _check_public_url(url: str) -> _Target:
    """Validate the URL and resolve it once; every address must be public. Returns the
    address to connect to (the first one), so the fetch can't be pointed anywhere else."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProductLinkError("Paste a full shop link starting with https://")
    if parsed.username or parsed.password:
        raise ProductLinkError("Links with a username or password are not supported.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ProductLinkError("That link has an invalid port.") from exc
    try:
        infos = socket.getaddrinfo(parsed.hostname, port)
    except socket.gaierror as exc:
        raise ProductLinkError("That website could not be found. Check the link.") from exc
    infos = [info for info in infos if info[0] in (socket.AF_INET, socket.AF_INET6)]
    if not infos:
        raise ProductLinkError("That website could not be found. Check the link.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            raise ProductLinkError("That link points to a private network address and cannot be imported.")
    path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    return _Target(parsed.scheme, parsed.hostname, port, infos[0][0], infos[0][4], path)


class _PinnedMixin:
    """Connect to the address that passed ``_check_public_url``, nothing else."""

    _aura_target: _Target

    def _new_conn(self) -> socket.socket:
        target = self._aura_target
        sock = socket.socket(target.family, socket.SOCK_STREAM)
        timeout = self.timeout if isinstance(self.timeout, (int, float)) else TIMEOUT_SECONDS
        sock.settimeout(timeout)
        try:
            sock.connect(target.sockaddr)
        except OSError:
            sock.close()
            raise
        return sock


class _PinnedHTTPConnection(_PinnedMixin, HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedMixin, HTTPSConnection):
    pass


class _Response:
    """The small part of a response the importer reads."""

    def __init__(self, connection: HTTPConnection, response: urllib3.BaseHTTPResponse, deadline: float) -> None:
        self._connection, self._response, self._deadline = connection, response, deadline
        self.status_code = response.status
        self.headers = {key.lower(): value for key, value in response.headers.items()}
        self.is_redirect = response.status in (301, 302, 303, 307, 308)

    def iter_content(self, size: int):
        for chunk in self._response.stream(size):
            if time.monotonic() > self._deadline:
                raise ProductLinkError("The shop took too long to respond. Try again or use a different link.")
            yield chunk

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args) -> bool:
        self._response.release_conn()
        self._connection.close()
        return False


def _open(url: str, deadline: float) -> _Response:
    target = _check_public_url(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProductLinkError("The shop took too long to respond. Try again or use a different link.")
    timeout = min(TIMEOUT_SECONDS, remaining)
    if target.scheme == "https":
        connection: HTTPConnection = _PinnedHTTPSConnection(
            target.host, target.port, timeout=timeout, cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(),
        )
    else:
        connection = _PinnedHTTPConnection(target.host, target.port, timeout=timeout)
    connection._aura_target = target
    try:
        connection.request("GET", target.path, headers=HEADERS, preload_content=False)
        return _Response(connection, connection.getresponse(), deadline)
    except Exception:
        connection.close()
        raise


def _get(url: str, max_bytes: int, deadline: float) -> tuple[bytes, str, str]:
    """GET with public-address checks on every redirect hop and a hard size cap.
    Returns (body, content type, final URL)."""
    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = _open(url, deadline)
        except ProductLinkError:
            raise
        except (ssl.SSLError, urllib3.exceptions.SSLError) as exc:
            raise ProductLinkError("That shop's secure connection could not be verified, so it was not imported.") from exc
        except (OSError, urllib3.exceptions.HTTPError) as exc:
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
            try:
                for chunk in response.iter_content(64 * 1024):
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise ProductLinkError("That file is too large to import.")
            except (OSError, urllib3.exceptions.HTTPError) as exc:
                raise ProductLinkError("The shop did not respond. Try again or use a different link.") from exc
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            return bytes(body), content_type, url
    raise ProductLinkError("The link redirected too many times.")


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.og_images: list[str] = []  # every og:image, in page order (4.2b)
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
            if key in {"og:image", "og:image:secure_url", "og:image:url"} and values.get("content"):
                self.og_images.append(values["content"].strip())
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


def _nodes(node: Any, kind: str):
    if isinstance(node, list):
        for child in node:
            yield from _nodes(child, kind)
    elif isinstance(node, dict):
        kinds = node.get("@type")
        if kind in (kinds if isinstance(kinds, list) else [kinds]):
            yield node
        yield from _nodes(node.get("@graph", []), kind)


def _image_urls(image: Any) -> list[str]:
    if isinstance(image, list):
        return [url for entry in image for url in _image_urls(entry)]
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    return [image.strip()] if isinstance(image, str) and image.strip() else []


def _json_ld(blocks: list[str]) -> tuple[list[str], str | None, list[str]]:
    """(all image URLs, name, category hints) from the first schema.org Product in JSON-LD;
    hints are its ``category`` and any BreadcrumbList names."""
    images: list[str] = []
    name: str | None = None
    hints: list[str] = []
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for crumbs in _nodes(data, "BreadcrumbList"):
            for entry in crumbs.get("itemListElement") or []:
                label = entry.get("name") or (entry.get("item") or {}).get("name") if isinstance(entry, dict) else None
                if isinstance(label, str):
                    hints.append(label)
        for product in _nodes(data, "Product"):
            if not images and _image_urls(product.get("image")):
                images = _image_urls(product.get("image"))
                name = product.get("name").strip() if isinstance(product.get("name"), str) else None
                if isinstance(product.get("category"), str):
                    hints.insert(0, product["category"])
    return images, name, hints


def find_product_size(html: str) -> str | None:
    """The garment size a product page names, when its JSON-LD Product (or its single
    offer) gives exactly one ``size``. Pages listing every available size give None."""
    parser = _MetaParser()
    parser.feed(html)
    for block in parser.json_ld:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for product in _nodes(data, "Product"):
            offers = product.get("offers")
            candidates = [product.get("size")]
            if isinstance(offers, dict):
                candidates.append(offers.get("size"))
            for size in candidates:
                if isinstance(size, dict):
                    size = size.get("name")
                if isinstance(size, list) and len(size) == 1:
                    size = size[0]
                if isinstance(size, str) and 0 < len(size.strip()) <= 20:
                    return size.strip()
    return None


def _json_ld_product(blocks: list[str]) -> tuple[str | None, str | None]:
    """(image URL, name) from the first schema.org Product found in JSON-LD."""
    images, name, _ = _json_ld(blocks)
    return (images[0], name) if images else (None, None)


MAX_CANDIDATE_IMAGES = 6


def find_product_images(html: str, page_url: str) -> tuple[list[str], str | None, list[str]]:
    """(candidate product photo URLs, best first; title; category hints) from a product
    page. The first URL is what ``find_product_image`` returns."""
    first, title = find_product_image(html, page_url)
    parser = _MetaParser()
    parser.feed(html)
    ld_images, _, hints = _json_ld(parser.json_ld)
    urls: list[str] = []
    for url in [first] + ld_images + parser.og_images:
        if url:
            absolute = urljoin(page_url, unescape(url))
            if absolute not in urls:
                urls.append(absolute)
    return urls[:MAX_CANDIDATE_IMAGES], title, hints


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
    """Validate the bytes are a real image and re-encode them (no metadata is kept)."""
    try:
        return reencode(content)
    except ImageRejected as exc:
        raise ProductLinkError("The product photo could not be read. Try copying the image address instead.") from exc


def import_from_link(
    url: str, max_image_bytes: int, has_person: Callable[[bytes], bool | None] | None = None,
) -> ImportedImage:
    """Fetch a product photo from a shop link (a product page or a direct image URL).

    With ``has_person``, a product page's photos (up to 6) are checked in order and the
    first one with no person in it is used (4.2b): shops usually list the model shot
    first and a flat lay later. If every photo shows a person, the first is used.
    """
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    deadline = time.monotonic() + TOTAL_SECONDS
    body, content_type, final_url = _get(url, max(MAX_PAGE_BYTES, max_image_bytes), deadline)
    title: str | None = None
    image_url = final_url
    if content_type.startswith("image/") and len(body) > max_image_bytes:
        raise ProductLinkError("That image is larger than the upload limit.")
    if not content_type.startswith("image/"):
        if len(body) > MAX_PAGE_BYTES:
            raise ProductLinkError("That page is too large to read.")
        page = body.decode("utf-8", errors="replace")
        found, title, hints = find_product_images(page, final_url)
        if not found:
            raise ProductLinkError(
                "No product photo was found on that page. Open the product photo, copy its image address, and paste that instead."
            )
        image_url, (content, content_type, suffix), person_free = _pick_photo(
            found, max_image_bytes, deadline, has_person)
        return ImportedImage(
            content=content, content_type=content_type, suffix=suffix, source_url=url, image_url=image_url,
            title=title, site=(urlparse(final_url).hostname or "").removeprefix("www."),
            hints=tuple(([title] if title else []) + hints), person_free=person_free,
            size=find_product_size(page),
        )
    content, content_type, suffix = _normalise_image(body)
    person_free = None if has_person is None else _no_person(has_person, content)
    return ImportedImage(
        content=content, content_type=content_type, suffix=suffix, source_url=url,
        image_url=image_url, title=title, site=(urlparse(final_url).hostname or "").removeprefix("www."),
        person_free=person_free,
    )


def _no_person(has_person: Callable[[bytes], bool | None], content: bytes) -> bool | None:
    person = has_person(content)
    return None if person is None else not person


def _pick_photo(
    urls: list[str], max_image_bytes: int, deadline: float,
    has_person: Callable[[bytes], bool | None] | None,
) -> tuple[str, tuple[bytes, str, str], bool | None]:
    """(URL, (re-encoded bytes, content type, suffix), person_free) of the photo to import."""
    first: tuple[str, tuple[bytes, str, str], bool | None] | None = None
    error: ProductLinkError | None = None
    for image_url in urls:
        if first is not None and time.monotonic() > deadline - 3:
            break  # keep what we have rather than time out
        try:
            body, content_type, _ = _get(image_url, max_image_bytes, deadline)
            if content_type and not content_type.startswith("image/"):
                raise ProductLinkError("The product photo link did not return an image.")
            image = _normalise_image(body)
        except ProductLinkError as exc:
            error = error or exc
            continue
        if has_person is None:
            return image_url, image, None
        person_free = _no_person(has_person, image[0])
        if person_free:
            return image_url, image, True
        first = first or (image_url, image, person_free)
    if first is None:
        raise error or ProductLinkError("The product photo could not be downloaded.")
    return first
