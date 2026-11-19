"""One-time authorized download of the Apache-2.0 Qwen2.5 1.5B GGUF."""
from huggingface_hub import hf_hub_download
from settings import settings


def download() -> str:
    path = hf_hub_download(
        repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        local_dir=str(settings.llm_model_path.parent),
    )
    settings.llm_model_path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize the downloaded name to the configured path when needed.
    import shutil
    if path != str(settings.llm_model_path):
        shutil.copy2(path, settings.llm_model_path)
    return str(settings.llm_model_path)


if __name__ == "__main__":
    print(download())
