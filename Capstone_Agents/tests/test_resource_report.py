"""Step 3: /health reports resident models and peak memory; the worker reports its own;
garment cut-out runs in a child process so its memory is not kept by the worker."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
from services import body_analysis, tryon_service
from services.vision_service import vision_service


def test_health_reports_resident_models_and_peak_memory(monkeypatch):
    monkeypatch.setattr(vision_service, "_model", object())
    with TestClient(app, client=("127.0.0.1", 50000)) as client:  # details are local-only
        resources = client.get("/health").json()["resources"]
    assert resources["api_peak_rss_mb"] > 0
    assert "garment_cnn" in resources["api_resident_models"]
    assert "base_chat_gguf" not in resources["api_resident_models"]
    assert set(resources["tryon_worker"]) == {"running", "model_loaded", "peak_rss_mb"}


def test_worker_heartbeat_carries_its_peak_memory():
    tryon_service.init_tables()
    tryon_service.heartbeat()
    worker = tryon_service.worker_resources()
    assert worker["running"] and worker["peak_rss_mb"] > 0


@pytest.mark.skipif(not body_analysis.garment_cutter.available(), reason="ISNet model not downloaded")
def test_garment_cutout_runs_outside_the_worker_process(monkeypatch, tmp_path: Path):
    settings = tryon_service.settings
    previous = settings.tryon_isolate_cutout
    object.__setattr__(settings, "tryon_isolate_cutout", True)  # frozen settings dataclass
    monkeypatch.setattr(body_analysis.garment_cutter, "_session", None)
    photo = Image.new("RGB", (400, 500), "white")
    ImageDraw.Draw(photo).rectangle([100, 80, 300, 420], fill=(30, 60, 140))
    path = tmp_path / "garment.png"
    photo.save(path)
    try:
        [cut] = tryon_service.cut_garments([path])
    finally:
        object.__setattr__(settings, "tryon_isolate_cutout", previous)
    assert body_analysis.garment_cutter._session is None, "ISNet was loaded in the worker process"
    assert cut.mode == "RGB" and cut.width <= photo.width and cut.height <= photo.height
    assert cut.getpixel((cut.width // 2, cut.height // 2))[2] > 100  # the navy garment survived
