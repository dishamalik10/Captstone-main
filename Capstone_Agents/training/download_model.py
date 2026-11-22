"""One-time authorized download of the Apache-2.0 Qwen2.5 Instruct GGUF used for chat.

    python -m training.download_model          # Qwen2.5-3B (default chat model, ~2.1 GB)
    python -m training.download_model 1.5b     # smaller Qwen2.5-1.5B (~1.1 GB) for low-memory machines

For 1.5B, also set AURA_LLM_MODEL_PATH=./model_artifacts/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf.
"""
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

from settings import settings

MODELS = {
    "3b": ("Qwen/Qwen2.5-3B-Instruct-GGUF", "qwen2.5-3b-instruct-q4_k_m.gguf"),
    "1.5b": ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
}


def download(size: str = "3b") -> str:
    repo_id, filename = MODELS[size]
    folder = settings.llm_model_path.parent
    folder.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(folder))
    target = folder / filename
    if Path(path) != target:
        shutil.copy2(path, target)
    return str(target)


if __name__ == "__main__":
    print(download(sys.argv[1] if len(sys.argv) > 1 else "3b"))
