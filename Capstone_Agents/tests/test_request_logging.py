"""Request IDs, the access line and the generic 500 body."""
import logging

from fastapi.testclient import TestClient

from main import app
from logging_config import request_id_var


@app.get("/__test_boom")
def _boom():
    raise RuntimeError("secret detail /Users/someone/model.gguf")


@app.get("/__test_request_id")
def _request_id():
    logging.getLogger("aura.test").info("inside handler")
    return {"request_id": request_id_var.get()}


def test_every_response_carries_a_request_id_seen_by_the_handler():
    with TestClient(app) as client:
        response = client.get("/__test_request_id")
    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 12
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_unhandled_errors_return_a_generic_body_and_log_the_details(caplog):
    caplog.set_level(logging.INFO)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/__test_boom")
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Internal server error.", "request_id": response.headers["x-request-id"]}
    assert "secret" not in response.text
    assert any("Unhandled error on GET /__test_boom" in r.getMessage() and r.exc_info for r in caplog.records)


def test_access_line_omits_the_query_string(caplog):
    caplog.set_level(logging.INFO, logger="aura.request")
    with TestClient(app) as client:
        client.get("/__test_request_id?signature=abc123&user_id=u1")
    lines = [r.getMessage() for r in caplog.records if r.name == "aura.request"]
    assert any(line.startswith("GET /__test_request_id -> 200") for line in lines)
    assert not any("abc123" in line or "user_id" in line for line in lines)


def test_log_file_is_written_with_request_ids(tmp_path):
    from logging_config import LOG_FORMAT, RequestIdFilter
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(tmp_path / "aura.log")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    logger = logging.getLogger("aura.test.file")
    logger.addHandler(handler)
    token = request_id_var.set("abcdef123456")
    try:
        logger.warning("hello")
    finally:
        request_id_var.reset(token)
        logger.removeHandler(handler)
        handler.close()
    assert "[abcdef123456] aura.test.file: hello" in (tmp_path / "aura.log").read_text()


def test_api_refuses_to_start_without_a_signing_key(monkeypatch):
    import pytest

    monkeypatch.delenv("AURA_MEDIA_SIGNING_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AURA_MEDIA_SIGNING_KEY is not set"):
        with TestClient(app):
            pass
