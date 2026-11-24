"""Download the local models used by "My Virtual Look" (body analysis + virtual try-on).

Everything runs on this machine; nothing is sent to a cloud API. About 2.4 GB in total:

* Stable Diffusion 1.5 inpainting UNet (fp16) + DDIM scheduler config   ~1.7 GB  CreativeML OpenRAIL-M
* sd-vae-ft-mse VAE                                                      ~0.33 GB MIT
* CatVTON "dresscode-16k-512" self-attention weights                     ~0.2 GB  CC BY-NC-SA 4.0 (non-commercial)
* MediaPipe Pose Landmarker (full) and Selfie Multiclass segmenter       ~25 MB   Apache 2.0
* rembg ISNet general-use background remover (for garment photos)       ~0.18 GB MIT

    python -m training.download_tryon_models

Files land in ``model_artifacts/tryon/`` (git-ignored). Downloads resume where they
stopped, and re-running skips finished files.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from settings import settings

HF = "https://huggingface.co/{repo}/resolve/main/{path}"
FILES = {
    # target path (relative to the try-on dir) -> source URL
    "sd-inpainting/unet/config.json": HF.format(repo="stable-diffusion-v1-5/stable-diffusion-inpainting", path="unet/config.json"),
    "sd-inpainting/unet/diffusion_pytorch_model.fp16.safetensors": HF.format(repo="stable-diffusion-v1-5/stable-diffusion-inpainting", path="unet/diffusion_pytorch_model.fp16.safetensors"),
    "sd-inpainting/scheduler/scheduler_config.json": HF.format(repo="stable-diffusion-v1-5/stable-diffusion-inpainting", path="scheduler/scheduler_config.json"),
    "sd-vae-ft-mse/config.json": HF.format(repo="stabilityai/sd-vae-ft-mse", path="config.json"),
    "sd-vae-ft-mse/diffusion_pytorch_model.safetensors": HF.format(repo="stabilityai/sd-vae-ft-mse", path="diffusion_pytorch_model.safetensors"),
    # Trained at 512x384 on DressCode (tops, bottoms, dresses): matches AURA's render size. On this
    # Mac the 1024px "mix-48k-1024" weights rendered skirts as leggings and invented patterns at 512px.
    "catvton/dresscode-16k-512/attention/model.safetensors": HF.format(repo="zhengchong/CatVTON", path="dresscode-16k-512/attention/model.safetensors"),
    "pose_landmarker_full.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    "selfie_multiclass_256x256.tflite": "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
    "isnet-general-use.onnx": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx",
}
CHUNK = 1 << 20


def _remote_size(url: str) -> int | None:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            length = response.headers.get("Content-Length")
            return int(length) if length else None
    except OSError:
        return None


PARALLEL_THRESHOLD = 32 * CHUNK
CONNECTIONS = 8


def _fetch_range(url: str, part: Path, first: int, last: int, attempts: int = 8) -> None:
    """Download bytes first..last (inclusive) into ``part``, resuming and retrying."""
    import time

    want = last - first + 1
    for attempt in range(attempts):
        have = part.stat().st_size if part.is_file() else 0
        if have >= want:
            return
        request = urllib.request.Request(url, headers={"Range": f"bytes={first + have}-{last}"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, part.open("ab") as out:
                if response.status != 206:
                    raise OSError("server ignored the byte range")
                for block in iter(lambda: response.read(CHUNK), b""):
                    out.write(block)
        except OSError as exc:
            print(f"  {part.name}: {exc}; retrying", flush=True)
            time.sleep(min(30, 2 ** attempt))
    if not part.is_file() or part.stat().st_size < want:
        raise SystemExit(f"{part.name} did not finish; run the command again to resume.")


def _fetch_parallel(url: str, target: Path, size: int) -> None:
    """Split a large file across several connections (the CDN limits speed per connection)."""
    import threading
    import time

    step = -(-size // CONNECTIONS)
    parts = [(target.with_name(f"partial{i}_{target.name}"), i * step, min(size, (i + 1) * step) - 1)
             for i in range(CONNECTIONS)]
    print(f"Downloading {target.name} ({size / 1e6:.0f} MB, {CONNECTIONS} connections)", flush=True)
    errors: list[BaseException] = []

    def worker(part, first, last):
        try:
            _fetch_range(url, part, first, last)
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=part, daemon=True) for part in parts]
    for thread in threads:
        thread.start()
    while any(thread.is_alive() for thread in threads):
        time.sleep(15)
        done = sum(part.stat().st_size for part, _, _ in parts if part.is_file())
        print(f"  {target.name}: {done / 1e6:.0f}/{size / 1e6:.0f} MB", flush=True)
    if errors:
        raise SystemExit(f"{target.name} did not finish ({errors[0]}); run the command again to resume.")
    assembled = target.with_name("partial_" + target.name)
    with assembled.open("wb") as out:
        for part, _, _ in parts:
            with part.open("rb") as handle:
                while block := handle.read(16 * CHUNK):
                    out.write(block)
    if assembled.stat().st_size != size:
        raise SystemExit(f"{target.name} assembled to the wrong size; delete its partial files and retry.")
    assembled.rename(target)
    for part, _, _ in parts:
        part.unlink(missing_ok=True)


def _fetch(url: str, target: Path) -> None:
    expected = _remote_size(url)
    if target.is_file() and (expected is None or target.stat().st_size == expected):
        print(f"Already present: {target.name}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if expected and expected >= PARALLEL_THRESHOLD:
        _fetch_parallel(url, target, expected)
        return
    partial = target.with_name("partial_" + target.name)
    start = partial.stat().st_size if partial.is_file() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    print(f"Downloading {target.name}" + (f" (resuming at {start / 1e6:.0f} MB)" if start else ""), flush=True)
    with urllib.request.urlopen(request, timeout=60) as response:
        if start and response.status != 206:  # server ignored the range: start over
            start = 0
        with partial.open("ab" if start else "wb") as out:
            done, last = start, 0
            for block in iter(lambda: response.read(CHUNK), b""):
                out.write(block)
                done += len(block)
                if expected and done - last >= 100 * CHUNK:
                    print(f"  {target.name}: {done / 1e6:.0f}/{expected / 1e6:.0f} MB", flush=True)
                    last = done
    if expected and partial.stat().st_size != expected:
        raise SystemExit(f"{target.name} is incomplete; run the command again to resume.")
    partial.rename(target)


def download(root: Path | None = None) -> Path:
    root = Path(root or settings.tryon_model_dir)
    # Small files first so body analysis works while the large weights are still downloading.
    for relative, url in sorted(FILES.items(), key=lambda entry: "safetensors" in entry[0]):
        _fetch(url, root / relative)
    print(f"Try-on models ready in {root}")
    return root


if __name__ == "__main__":
    download(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
