"""Machine check for testers (README "Which settings for my Mac?", TESTING_8GB.md).

    python -m scripts.machine_check              # before starting the server
    python -m scripts.machine_check --server     # while the server runs: adds its memory use

Prints a report to paste into the team's test notes. It names the machine profile your
settings correspond to and warns when they don't suit your RAM. No secrets or personal
data are printed: no .env values except the AURA_* feature switches, no file paths outside
the repo, no user data.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from settings import settings  # noqa: E402

GB = 1 << 30


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def memory() -> dict[str, float | None]:
    """Total RAM and swap in use (GB). macOS via sysctl, Linux via /proc/meminfo."""
    total = swap_used = None
    if sys.platform == "darwin":
        value = _sysctl("hw.memsize")
        total = int(value) / GB if value else None
        swap = _sysctl("vm.swapusage")  # "total = 2048.00M  used = 1024.00M  free = ..."
        if swap and "used =" in swap:
            used = swap.split("used =")[1].split()[0]
            swap_used = float(used[:-1]) / (1024 if used.endswith("M") else 1)
    elif Path("/proc/meminfo").exists():
        info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        kb = lambda key: int(info[key].split()[0]) if key in info else 0  # noqa: E731
        total = kb("MemTotal") / (1 << 20)
        swap_used = (kb("SwapTotal") - kb("SwapFree")) / (1 << 20)
    return {"total_gb": round(total, 1) if total else None, "swap_used_gb": round(swap_used, 2) if swap_used is not None else None}


def models() -> dict[str, bool]:
    from services.garment_segmenter import model_path as segformer_path
    from services.tryon_service import model as tryon_model

    return {
        "garment_cnn": settings.model_path.is_file(),
        "chat_gguf": settings.llm_model_path.is_file(),
        "stylist_gguf": settings.stylist_llm_model_path.is_file(),
        "tryon_models": not tryon_model.missing_files(),
        "segformer": segformer_path().is_file(),
    }


def advice(total_gb: float | None) -> list[str]:
    notes = []
    big = total_gb is not None and total_gb >= 15
    if total_gb is None:
        notes.append("Could not read total RAM.")
    elif not big and settings.tryon_enabled:
        notes.append("Try-on is ON on a machine under 16 GB: expect heavy swap and slow renders. "
                     "Fine for a deliberate try-on test; otherwise set AURA_TRYON_ENABLED=0.")
    elif big and not settings.tryon_enabled:
        notes.append("16 GB machine with try-on OFF. If this is the host, set AURA_TRYON_ENABLED=1 and AURA_PRELOAD_VISION=1.")
    if settings.tryon_enabled and not models()["tryon_models"]:
        notes.append("Try-on is ON but its models are missing: run python -m training.download_tryon_models.")
    if not models()["garment_cnn"]:
        notes.append("The garment CNN is missing: see README step 3.")
    if not settings.chat_use_stylist:
        notes.append("AURA_CHAT_USE_STYLIST=0 loads a second chat model (~2 GB); keep it 1 on 8 GB.")
    return notes or ["Settings suit this machine."]


def server() -> dict | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as response:  # loopback only
            body = json.loads(response.read())
    except OSError:
        return None
    return body.get("resources")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", action="store_true", help="also read the running server's memory use")
    args = parser.parse_args()
    mem = memory()
    report = {
        "machine": {"os": f"{platform.system()} {platform.release()}", "arch": platform.machine(),
                    "chip": _sysctl("machdep.cpu.brand_string") if sys.platform == "darwin" else None,
                    "python": platform.python_version(), **mem},
        "profile": "16 GB host" if settings.tryon_enabled and settings.preload_vision
                   else "8 GB tester" if not settings.tryon_enabled else "custom",
        "switches": {"AURA_TRYON_ENABLED": int(settings.tryon_enabled), "AURA_PRELOAD_VISION": int(settings.preload_vision),
                     "AURA_CHAT_USE_STYLIST": int(settings.chat_use_stylist), "AURA_LLM_GPU_LAYERS": settings.llm_gpu_layers},
        "models_installed": models(),
        "advice": advice(mem["total_gb"]),
    }
    if args.server:
        report["server_resources"] = server() or "server not reachable on 127.0.0.1:8000"
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
