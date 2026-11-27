"""Try-on jobs: DB-backed queue, fair-use limits, deletion, retention and the worker process (H5, Q9, Q15)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from database import connection, ensure_user, init_database, row, utc_now
from main import app
from services import tryon_service, tryon_worker
from services.tryon_service import TryOnLimitError
from settings import ROOT, settings


class InstantModel:
    """Stands in for CatVTON: installed, never actually rendered by these tests."""

    loaded = False

    def missing_files(self):
        return []

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False


@pytest.fixture(autouse=True)
def fresh_tables(monkeypatch):
    init_database()
    tryon_service.init_tables()
    monkeypatch.setattr(tryon_service, "model", InstantModel())
    with connection() as db:
        db.execute("DELETE FROM tryon_renders")
        db.execute("DELETE FROM tryon_usage")
        db.execute("DELETE FROM tryon_worker")


def _user_with_avatar(prefix: str = "tw") -> tuple[str, list[str]]:
    user_id = f"{prefix}_{uuid.uuid4().hex[:8]}"
    ensure_user(user_id)
    item_ids = []
    with connection() as db:
        db.execute(
            """INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at)
               VALUES(?,?,?,?,?,?,?,1,?)""",
            (f"avatar_{user_id}", user_id, "front", "avatar.png", "parsing.png", "[]", "{}", utc_now()),
        )
        for index in range(4):
            item_id = f"{user_id}_item{index}"
            item_ids.append(item_id)
            db.execute(
                """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                   image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item_id, user_id, "Top", "Shirt", "g", "White", f"{item_id}.jpg", "{}", utc_now()),
            )
    return user_id, item_ids


def _finish(render_id: str) -> None:
    with connection() as db:
        db.execute("UPDATE tryon_renders SET status='done' WHERE render_id=?", (render_id,))


def test_one_active_render_per_user():
    user_id, items = _user_with_avatar()
    tryon_service.request_render(user_id, [items[0]])
    with pytest.raises(TryOnLimitError, match="already have a look rendering"):
        tryon_service.request_render(user_id, [items[1]])


def test_cached_look_is_returned_without_counting_against_limits():
    user_id, items = _user_with_avatar()
    first = tryon_service.request_render(user_id, [items[0]])
    again = tryon_service.request_render(user_id, [items[0]])  # same outfit while it renders
    assert again["render_id"] == first["render_id"]
    assert row("SELECT COUNT(*) AS n FROM tryon_usage WHERE user_id=?", (user_id,))["n"] == 1


def test_daily_limit_survives_deleting_looks():
    user_id, items = _user_with_avatar()
    for index in range(settings.tryon_daily_limit):
        render = tryon_service.request_render(user_id, [items[index]])
        _finish(render["render_id"])
        tryon_service.delete_render(user_id, render["render_id"])  # deleting must not refund the quota
    with pytest.raises(TryOnLimitError, match="today's"):
        tryon_service.request_render(user_id, [items[3]])


def test_daily_limit_counts_only_the_last_24_hours():
    user_id, items = _user_with_avatar()
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    with connection() as db:
        for _ in range(settings.tryon_daily_limit):
            db.execute("INSERT INTO tryon_usage(user_id, created_at) VALUES (?, ?)", (user_id, old))
    assert tryon_service.request_render(user_id, [items[0]])["status"] == "queued"


def test_global_queue_limit():
    for _ in range(settings.tryon_queue_limit):
        user_id, items = _user_with_avatar("busy")
        tryon_service.request_render(user_id, [items[0]])
    user_id, items = _user_with_avatar("late")
    with pytest.raises(TryOnLimitError, match="queue is full"):
        tryon_service.request_render(user_id, [items[0]])


def test_limit_is_served_as_429():
    with TestClient(app) as client:
        signup = client.post("/auth/signup", json={"full_name": "Limit User", "email": f"limit-{uuid.uuid4().hex[:6]}@example.com",
                                                   "password": "secure-pass-123"}).json()
        user_id, auth = signup["user"]["id"], {"Authorization": f"Bearer {signup['token']}"}
        with connection() as db:
            db.execute(
                """INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at)
                   VALUES(?,?,?,?,?,?,?,1,?)""",
                (f"avatar_{user_id}", user_id, "front", "a.png", "p.png", "[]", "{}", utc_now()),
            )
            for index in range(2):
                db.execute(
                    """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                       image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (f"{user_id}_i{index}", user_id, "Top", "Shirt", "g", "White", "x.jpg", "{}", utc_now()),
                )
        assert client.post("/tryon", headers=auth, json={"item_ids": [f"{user_id}_i0"]}).status_code == 202
        limited = client.post("/tryon", headers=auth, json={"item_ids": [f"{user_id}_i1"]})
        assert limited.status_code == 429 and "rendering" in limited.json()["detail"]
        assert client.get("/tryon/status").json()["queue_length"] == 1


def test_delete_route_cancels_a_queued_look_and_hides_other_users_looks():
    with TestClient(app) as client:
        owner = client.post("/auth/signup", json={"full_name": "Owner", "email": f"own-{uuid.uuid4().hex[:6]}@example.com",
                                                  "password": "secure-pass-123"}).json()
        other = client.post("/auth/signup", json={"full_name": "Other", "email": f"oth-{uuid.uuid4().hex[:6]}@example.com",
                                                  "password": "secure-pass-123"}).json()
        user_id = owner["user"]["id"]
        with connection() as db:
            db.execute(
                """INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at)
                   VALUES(?,?,?,?,?,?,?,1,?)""",
                (f"avatar_{user_id}", user_id, "front", "a.png", "p.png", "[]", "{}", utc_now()),
            )
            db.execute(
                """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                   image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (f"{user_id}_i0", user_id, "Top", "Shirt", "g", "White", "x.jpg", "{}", utc_now()),
            )
        render = client.post("/tryon", headers={"Authorization": f"Bearer {owner['token']}"},
                             json={"item_ids": [f"{user_id}_i0"]}).json()
        other_auth = {"Authorization": f"Bearer {other['token']}"}
        owner_auth = {"Authorization": f"Bearer {owner['token']}"}
        assert client.delete(f"/tryon/{render['render_id']}", headers=other_auth).status_code == 404
        assert client.delete(f"/tryon/{render['render_id']}", headers=owner_auth).status_code == 204
        assert client.get(f"/tryon/{render['render_id']}", headers=owner_auth).status_code == 404
    assert tryon_service.claim_next() is None  # the cancelled job never runs


def test_claim_takes_the_oldest_job_exactly_once():
    first_user, first_items = _user_with_avatar()
    second_user, second_items = _user_with_avatar()
    first = tryon_service.request_render(first_user, [first_items[0]])
    second = tryon_service.request_render(second_user, [second_items[0]])
    assert tryon_service.claim_next() == first["render_id"]
    assert tryon_service.claim_next() == second["render_id"]
    assert tryon_service.claim_next() is None


def test_a_look_deleted_while_rendering_is_discarded():
    from PIL import Image

    user_id, items = _user_with_avatar()
    kept = tryon_service.request_render(user_id, [items[0]])
    assert tryon_service.claim_next() == kept["render_id"]
    assert tryon_service._finish_render(kept["render_id"], Image.new("RGB", (8, 8)))
    stored = row("SELECT status, result_path FROM tryon_renders WHERE render_id=?", (kept["render_id"],))
    assert stored["status"] == "done" and (settings.upload_dir / stored["result_path"]).is_file()

    gone = tryon_service.request_render(user_id, [items[1]])
    assert tryon_service.claim_next() == gone["render_id"]
    tryon_service.delete_render(user_id, gone["render_id"])  # the user deletes it mid-render
    before = set(settings.upload_dir.glob("look_*.png"))
    assert not tryon_service._finish_render(gone["render_id"], Image.new("RGB", (8, 8)))
    assert set(settings.upload_dir.glob("look_*.png")) == before  # nothing left behind


def test_worker_restart_fails_interrupted_jobs_but_keeps_queued_ones():
    first_user, first_items = _user_with_avatar()
    second_user, second_items = _user_with_avatar()
    running = tryon_service.request_render(first_user, [first_items[0]])
    tryon_service.claim_next()
    queued = tryon_service.request_render(second_user, [second_items[0]])
    tryon_service.recover_interrupted()
    assert row("SELECT status FROM tryon_renders WHERE render_id=?", (running["render_id"],))["status"] == "failed"
    assert row("SELECT status FROM tryon_renders WHERE render_id=?", (queued["render_id"],))["status"] == "queued"


def test_retention_deletes_old_unsaved_looks_and_keeps_saved_ones():
    user_id, items = _user_with_avatar()
    old = (datetime.now(timezone.utc) - timedelta(days=settings.tryon_retention_days + 1)).isoformat()
    names = {}
    with connection() as db:
        for label, saved in (("unsaved", 0), ("saved", 1)):
            name = f"look_retention_{label}_{uuid.uuid4().hex[:6]}.png"
            (settings.upload_dir / name).write_bytes(b"png")
            names[label] = name
            db.execute(
                """INSERT INTO tryon_renders(render_id,user_id,avatar_id,cache_key,item_ids,status,result_path,saved,
                   created_at,updated_at) VALUES(?,?,?,?,?,'done',?,?,?,?)""",
                (f"look_{label}_{user_id}", user_id, f"avatar_{user_id}", label, json.dumps([items[0]]), name, saved, old, old),
            )
    assert tryon_service.cleanup_expired() == 1
    assert not (settings.upload_dir / names["unsaved"]).exists()
    assert (settings.upload_dir / names["saved"]).exists()
    assert row("SELECT 1 AS ok FROM tryon_renders WHERE render_id=?", (f"look_saved_{user_id}",))


def test_status_reports_the_worker_from_its_heartbeat():
    assert tryon_service.status()["worker_running"] is False
    tryon_service.heartbeat()
    assert tryon_service.status()["worker_running"] is True
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with connection() as db:
        db.execute("UPDATE tryon_worker SET heartbeat_at=?", (stale,))
    assert tryon_service.status()["worker_running"] is False


def test_api_starts_and_stops_the_worker_process(monkeypatch):
    started, stopped = [], []
    monkeypatch.setattr(tryon_worker, "should_spawn", lambda: True)
    monkeypatch.setattr(tryon_worker.supervisor, "start", lambda: started.append(1))
    monkeypatch.setattr(tryon_worker.supervisor, "stop", lambda: stopped.append(1))
    with TestClient(app):
        assert started == [1] and stopped == []
    assert stopped == [1]


def test_worker_process_heartbeats_and_exits_when_stopped():
    """A real child process against the test database (no models are loaded)."""
    env = {**tryon_worker.worker_env(), "AURA_TRYON_SPAWN_WORKER": "0"}
    process = subprocess.Popen(
        [sys.executable, "-m", "services.tryon_worker", "--parent-pid", str(os.getpid())],
        cwd=str(ROOT), env=env,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline and not tryon_service.status()["worker_running"]:
            time.sleep(0.2)
        assert tryon_service.status()["worker_running"], "worker never wrote a heartbeat"
        assert row("SELECT pid FROM tryon_worker WHERE id=1")["pid"] == process.pid
    finally:
        process.terminate()
        assert process.wait(15) == 0  # clean exit on SIGTERM


def test_supervisor_restarts_a_crashed_worker_and_stops_it(monkeypatch):
    monkeypatch.setattr(tryon_worker.WorkerSupervisor, "CHECK_SECONDS", 0.2)
    supervisor = tryon_worker.WorkerSupervisor()
    supervisor.start()
    try:
        first = supervisor._process
        assert supervisor.running
        first.kill()  # simulate a crash in the diffusion stack
        first.wait(10)
        deadline = time.time() + 15
        while time.time() < deadline and (supervisor._process is first or not supervisor.running):
            time.sleep(0.1)
        assert supervisor._process is not first and supervisor.running, "worker was not restarted"
        replacement = supervisor._process
    finally:
        supervisor.stop()
    assert replacement.poll() is not None and not supervisor.running
