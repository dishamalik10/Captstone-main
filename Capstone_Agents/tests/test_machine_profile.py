"""Machine profiles (decision log 2026-11-27, "Option A"): a fresh clone is 8 GB-safe.

If the team rolls back to "Option B" (everything on by default), update these tests as
part of the documented rollback in ENGINEERING_PLAN.md.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from database import init_database
from services import tryon_service
from settings import settings

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_clone_defaults_are_8gb_safe():
    """Without any AURA_* variables or .env, try-on and CNN preloading are off."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("AURA_")}
    code = (
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"
        "from settings import settings\n"
        "print(settings.tryon_enabled, settings.preload_vision)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    assert result.stdout.split() == ["False", "False"]


def test_env_example_ships_the_8gb_profile():
    lines = (ROOT / ".env.example").read_text().splitlines()
    assert "AURA_TRYON_ENABLED=0" in lines and "AURA_PRELOAD_VISION=0" in lines


def test_try_on_off_is_reported_and_refused():
    init_database()
    tryon_service.init_tables()
    object.__setattr__(settings, "tryon_enabled", False)
    try:
        status = tryon_service.status()
        assert status["enabled"] is False and status["tryon_ready"] is False
        with pytest.raises(RuntimeError, match="turned off"):
            tryon_service.request_render("anyone", ["item"])
    finally:
        object.__setattr__(settings, "tryon_enabled", True)


def test_machine_check_warns_about_mismatched_profiles():
    from scripts import machine_check

    object.__setattr__(settings, "tryon_enabled", True)
    try:
        assert any("under 16 GB" in note for note in machine_check.advice(8.0))
        assert not any("16 GB machine with try-on OFF" in note for note in machine_check.advice(16.0))
    finally:
        object.__setattr__(settings, "tryon_enabled", True)
    object.__setattr__(settings, "tryon_enabled", False)
    try:
        assert any("16 GB machine with try-on OFF" in note for note in machine_check.advice(16.0))
        assert not any("under 16 GB" in note for note in machine_check.advice(8.0))
    finally:
        object.__setattr__(settings, "tryon_enabled", True)
