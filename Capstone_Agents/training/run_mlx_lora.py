"""Run the pinned, local MLX LoRA experiment with a hardware preflight log."""
from __future__ import annotations
import hashlib, json, os, platform, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get("AURA_MLX_CONFIG", ROOT / "training/mlx_lora_config.yaml")).resolve()
MODEL = ROOT / "model_artifacts/mlx_base"
DATA = ROOT / "training/fashion_sft"
RUN_STEM = "mlx_lora" if CONFIG.name == "mlx_lora_config.yaml" else CONFIG.stem
LOG = ROOT / f"training/{RUN_STEM}_training.log"
REPORT = ROOT / f"training/{RUN_STEM}_run.json"


def free_percent() -> int:
    out = subprocess.check_output(["memory_pressure"], text=True)
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", out)
    if not match:
        raise RuntimeError("Could not parse memory_pressure output; refusing to start.")
    return int(match.group(1))


def main():
    import mlx.core as mx
    import mlx_lm
    if platform.machine() != "arm64" or not mx.metal.is_available():
        raise SystemExit("MLX Metal is unavailable on this host; refusing to train.")
    if not (MODEL / "model.safetensors").exists():
        raise SystemExit("Base checkpoint is incomplete; refusing to train.")
    if not all((DATA / f"{split}.jsonl").exists() for split in ("train", "valid", "test")):
        raise SystemExit("Dataset splits are missing; refusing to train.")
    free = free_percent()
    if free < 20:
        raise SystemExit(f"Only {free}% system memory is free; close apps and retry.")
    config_hash = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    start = time.time()
    metadata = {
        "start_unix": start, "host_architecture": platform.machine(), "python": sys.version,
        "mlx": mx.__version__ if hasattr(mx, "__version__") else "unknown",
        "mlx_lm": getattr(mlx_lm, "__version__", "unknown"), "metal_available": bool(mx.metal.is_available()),
        "system_ram_bytes": os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"),
        "system_memory_free_percent_before": free, "model_bytes": (MODEL / "model.safetensors").stat().st_size,
        "config_sha256": config_hash, "config": str(CONFIG), "dataset_manifest": str(DATA / "manifest.json"),
        "command": [str(ROOT / ".venv-mlx/bin/mlx_lm.lora"), "--config", str(CONFIG)],
    }
    REPORT.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with LOG.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(metadata["command"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
        while proc.poll() is None:
            time.sleep(10)
            free = free_percent()
            if free < 12:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                metadata["stopped_for_memory_pressure"] = True
                metadata["system_memory_free_percent_at_stop"] = free
                break
    metadata["end_unix"] = time.time()
    metadata["elapsed_seconds"] = metadata["end_unix"] - start
    metadata["exit_code"] = proc.returncode
    metadata["system_memory_free_percent_after"] = free_percent()
    REPORT.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    raise SystemExit(proc.returncode)

if __name__ == "__main__":
    main()
