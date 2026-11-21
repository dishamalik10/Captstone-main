"""Download the fine-tuned AURA stylist GGUF from this repository's GitHub Release.

The ~1 GB model is too large for Git, so it is published as a release asset.
The file is checked against its SHA-256 before it is installed, and it is
written to a ``partial_`` file first so an interrupted download never looks
like a finished model.

    python -m training.download_stylist_model
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

from settings import settings

RELEASE_TAG = "stylist-llm-v1"
FILENAME = "aura-stylist-q4_k_m.gguf"
URL = f"https://github.com/dishamalik10/Captstone-main/releases/download/{RELEASE_TAG}/{FILENAME}"
SHA256 = "2b90ab85daa5ece8cfa44271cce38de725aeb37c063fff7a0415ed4f888e7021"
SIZE_BYTES = 986_048_160
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(target: Path | None = None) -> Path:
    target = Path(target or settings.stylist_llm_model_path).expanduser()
    if target.is_file() and target.stat().st_size == SIZE_BYTES and sha256_of(target) == SHA256:
        print(f"Already installed and verified: {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name("partial_" + target.name)
    try:
        from tqdm.auto import tqdm
    except ImportError:  # progress bar is optional
        tqdm = None
    print(f"Downloading {URL}")
    digest = hashlib.sha256()
    with urllib.request.urlopen(URL) as response, partial.open("wb") as out:
        bar = tqdm(total=SIZE_BYTES, unit="B", unit_scale=True, desc=FILENAME) if tqdm else None
        for block in iter(lambda: response.read(CHUNK), b""):
            out.write(block)
            digest.update(block)
            if bar:
                bar.update(len(block))
        if bar:
            bar.close()
    if digest.hexdigest() != SHA256:
        partial.unlink(missing_ok=True)
        raise SystemExit("Checksum mismatch: the download is corrupt or not the released model. Try again.")
    os.replace(partial, target)
    print(f"Installed and verified: {target}")
    return target


if __name__ == "__main__":
    download(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
