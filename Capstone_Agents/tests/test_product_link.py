import io
import socket

import pytest
from PIL import Image

from services import product_link_service as links
from services.product_link_service import ProductLinkError, find_product_image, import_from_link


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (20, 40, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_og_image_is_preferred_and_made_absolute():
    html = """<html><head><title>Shop</title>
      <meta property="og:title" content="Roadster Men Black Slim Fit Jeans">
      <meta property="og:image" content="/images/jeans.jpg?w=800&amp;q=90">
    </head></html>"""
    image, title = find_product_image(html, "https://www.myntra.com/jeans/roadster/123")
    assert image == "https://www.myntra.com/images/jeans.jpg?w=800&q=90"
    assert title == "Roadster Men Black Slim Fit Jeans"


def test_json_ld_product_image_used_when_no_meta_tags():
    html = """<script type="application/ld+json">
      {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList"},
        {"@type": "Product", "name": "Linen Shirt", "image": ["https://cdn.shop.com/shirt.webp"]}
      ]}</script>"""
    assert find_product_image(html, "https://shop.com/p/1") == ("https://cdn.shop.com/shirt.webp", "Linen Shirt")


def test_amazon_main_image_fallback():
    html = """<span id="productTitle">Cotton Kurta</span>
      <img id="landingImage" src="https://m.media-amazon.com/small.jpg"
           data-old-hires="https://m.media-amazon.com/images/I/kurta._SL1500_.jpg">"""
    assert find_product_image(html, "https://www.amazon.in/dp/B0")[0] == "https://m.media-amazon.com/images/I/kurta._SL1500_.jpg"


def test_page_without_product_photo_returns_none():
    assert find_product_image("<html><title>Sign in</title></html>", "https://x.com")[0] is None


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/health",
    "http://localhost/admin",
    "http://10.0.0.5/item.jpg",
    "http://192.168.1.20/item.jpg",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
])
def test_private_addresses_are_blocked(url):
    with pytest.raises(ProductLinkError, match="private network"):
        links._check_public_url(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://shop.com/a.jpg", "https://user:pw@shop.com/"])
def test_unsupported_urls_are_rejected(url):
    with pytest.raises(ProductLinkError):
        links._check_public_url(url)


def test_redirect_to_private_address_is_blocked(monkeypatch):
    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
    monkeypatch.setattr(links.socket, "getaddrinfo", lambda host, port: private if host == "internal" else public)

    class Redirect:
        is_redirect = True
        status_code = 302
        headers = {"location": "http://internal/secret"}
        def __enter__(self): return self
        def __exit__(self, *args): return False

    monkeypatch.setattr(links, "_open", lambda url, deadline: (links._check_public_url(url), Redirect())[1])
    with pytest.raises(ProductLinkError, match="private network"):
        import_from_link("https://shop.example/product", 5_000_000)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, status: int = 200):
        self.body, self.status_code = body, status
        self.headers = {"content-type": content_type}
        self.is_redirect = False
    def iter_content(self, size):
        yield self.body
    def __enter__(self): return self
    def __exit__(self, *args): return False


def fake_web(monkeypatch, pages: dict[str, FakeResponse]):
    monkeypatch.setattr(links, "_check_public_url", lambda url: None)
    monkeypatch.setattr(links, "_open", lambda url, deadline: pages[url])


def test_product_page_import_downloads_the_product_photo(monkeypatch):
    fake_web(monkeypatch, {
        "https://shop.example/p/42": FakeResponse(
            b'<meta property="og:image" content="https://cdn.shop.example/42.png">'
            b'<meta property="og:title" content="Blue Tee">', "text/html; charset=utf-8"),
        "https://cdn.shop.example/42.png": FakeResponse(png_bytes(), "image/png"),
    })
    result = import_from_link("shop.example/p/42", 5_000_000)  # scheme added automatically
    assert result.content_type == "image/jpeg" and result.suffix == ".jpg"  # re-encoded, metadata dropped (4.8)
    assert result.title == "Blue Tee"
    assert result.site == "shop.example"
    assert result.image_url == "https://cdn.shop.example/42.png"


def test_direct_image_link_and_blocked_shop(monkeypatch):
    fake_web(monkeypatch, {
        "https://cdn.shop.example/a.png": FakeResponse(png_bytes(), "image/png"),
        "https://blocked.example/p": FakeResponse(b"captcha", "text/html", status=403),
        "https://fake.example/x.png": FakeResponse(b"not really an image", "image/png"),
    })
    assert import_from_link("https://cdn.shop.example/a.png", 5_000_000).title is None
    with pytest.raises(ProductLinkError, match="blocked the automatic import"):
        import_from_link("https://blocked.example/p", 5_000_000)
    with pytest.raises(ProductLinkError, match="could not be read"):
        import_from_link("https://fake.example/x.png", 5_000_000)


def test_the_whole_import_has_one_time_limit(monkeypatch):
    """A slow shop can't hold a request thread past TOTAL_SECONDS (page + photo + redirects)."""
    clock = iter([0.0, 5.0, 25.0, 30.0, 35.0])
    monkeypatch.setattr(links.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(links, "_check_public_url", lambda url: None)

    class Slow:
        status_code, is_redirect = 200, False
        headers = {"content-type": "image/png"}

        def __init__(self, deadline):
            self.deadline = deadline

        def iter_content(self, size):
            for chunk in (b"a", b"b"):
                if links.time.monotonic() > self.deadline:
                    raise ProductLinkError("The shop took too long to respond.")
                yield chunk

        def __enter__(self): return self
        def __exit__(self, *args): return False

    monkeypatch.setattr(links, "_open", lambda url, deadline: Slow(deadline))
    with pytest.raises(ProductLinkError, match="too long"):
        import_from_link("https://slow.example/a.png", 5_000_000)


def test_tls_is_verified_against_the_real_hostname():
    target = links._Target("https", "shop.example", 443, socket.AF_INET, ("93.184.216.34", 443), "/p")
    connection = links._PinnedHTTPSConnection(target.host, target.port, cert_reqs="CERT_REQUIRED", ca_certs=links.certifi.where())
    assert connection.host == "shop.example"  # SNI, certificate check and Host header use the name
    assert connection.cert_reqs == "CERT_REQUIRED"
