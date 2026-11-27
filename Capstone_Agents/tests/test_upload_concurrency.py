"""Uploads run off the event loop and heavy image work is capped (H3)."""
import inspect
import threading
import time
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import main
from main import app
from services import image_slots
from services.vision_service import vision_service

PASSWORD = "secure-pass-123"


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), (200, 200, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _prediction():
    value = {"label": "T-shirt", "confidence": 0.9, "top_3": [{"label": "T-shirt", "confidence": 0.9}]}
    return {
        "product_type": value, "garment_group": {**value, "label": "Garment Upper body"},
        "color_group": {**value, "label": "White"}, "category": "Top",
        "color_sample": {"rgb": [200, 200, 200], "hex": "#C8C8C8", "method": "test"},
    }


def _account(client, email):
    response = client.post("/auth/signup", json={"full_name": "Upload User", "email": email, "password": PASSWORD})
    return response.json()["user"]["id"], {"Authorization": f"Bearer {response.json()['token']}"}


def test_heavy_upload_routes_are_not_coroutines():
    # A sync def route runs in the thread pool; an async one would block the event loop.
    for route in (main.upload_clothing, main.purchase_impact, main.upload_avatar):
        assert not inspect.iscoroutinefunction(route), route.__name__


def test_server_keeps_answering_while_an_upload_is_being_analysed(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_predict(_path):
        started.set()
        release.wait(10)
        return _prediction()

    monkeypatch.setattr(vision_service, "predict", slow_predict)
    monkeypatch.setattr(main, "cutout_garment", lambda image: None)
    with TestClient(app) as client:
        user_id, auth = _account(client, "upload-concurrency@example.com")
        result = {}

        def upload():
            result["response"] = client.post(
                "/wardrobe/upload", headers=auth, data={"user_id": user_id},
                files={"file": ("a.jpg", _jpeg(), "image/jpeg")},
            )

        worker = threading.Thread(target=upload)
        worker.start()
        assert started.wait(10), "upload never reached the CNN"
        t0 = time.perf_counter()
        health = client.get("/auth/me", headers=auth)  # a cheap route: measures blocking only
        elapsed = time.perf_counter() - t0
        release.set()
        worker.join(10)
    assert health.status_code == 200 and elapsed < 2.0
    assert result["response"].status_code == 201, result["response"].text


def test_upload_returns_503_when_all_image_slots_stay_busy(monkeypatch):
    monkeypatch.setattr(image_slots, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(image_slots, "WAIT_SECONDS", 0.05)
    monkeypatch.setattr(vision_service, "predict", lambda _path: _prediction())
    monkeypatch.setattr(main, "cutout_garment", lambda image: None)
    image_slots._slots.acquire()  # another request holds the only slot
    try:
        with TestClient(app) as client:
            user_id, auth = _account(client, "upload-busy@example.com")
            response = client.post(
                "/wardrobe/upload", headers=auth, data={"user_id": user_id},
                files={"file": ("a.jpg", _jpeg(), "image/jpeg")},
            )
    finally:
        image_slots._slots.release()
    assert response.status_code == 503
    assert "busy" in response.json()["detail"]


def test_image_slots_allow_the_configured_number_at_once():
    slots = threading.BoundedSemaphore(2)
    original = image_slots._slots
    image_slots._slots = slots
    try:
        with image_slots.image_slot(0.01), image_slots.image_slot(0.01):
            try:
                with image_slots.image_slot(0.01):
                    raise AssertionError("a third slot should not be granted")
            except image_slots.ImageBusyError:
                pass
        with image_slots.image_slot(0.01):  # released again afterwards
            pass
    finally:
        image_slots._slots = original


def test_cnn_is_loaded_at_startup_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(vision_service, "load", lambda: calls.append(1))
    object.__setattr__(main.settings, "preload_vision", True)
    try:
        with TestClient(app):
            pass
    finally:
        object.__setattr__(main.settings, "preload_vision", False)
    assert calls == [1]
