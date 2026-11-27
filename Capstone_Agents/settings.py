from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _path(name: str, default: Path) -> Path:
    """A path setting. Relative values (e.g. ``./aura.db`` in .env) are resolved against
    the backend folder, not the shell's working directory, so the server finds the same
    files wherever it is started from."""
    value = os.getenv(name)
    path = Path(value).expanduser() if value else Path(default)
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class Settings:
    fashion_lm_path: Path = _path("AURA_FASHION_LM_PATH", ROOT / "model_artifacts" / "aura_fashion_gpt_final")
    llm_model_path: Path = _path("AURA_LLM_MODEL_PATH", ROOT / "model_artifacts" / "llm" / "qwen2.5-3b-instruct-q4_k_m.gguf")
    llm_context_length: int = int(os.getenv("AURA_LLM_CONTEXT_LENGTH", "4096"))
    llm_max_input_tokens: int = int(os.getenv("AURA_LLM_MAX_INPUT_TOKENS", "3072"))
    llm_max_output_tokens: int = int(os.getenv("AURA_LLM_MAX_OUTPUT_TOKENS", "384"))
    llm_concurrency: int = int(os.getenv("AURA_LLM_CONCURRENCY", "1"))
    llm_queue_timeout_seconds: float = float(os.getenv("AURA_LLM_QUEUE_TIMEOUT_SECONDS", "30"))
    llm_threads: int = int(os.getenv("AURA_LLM_THREADS", "4"))
    # Metal offload was benchmarked on the target Apple Silicon host; set to 0 for CPU.
    llm_gpu_layers: int = int(os.getenv("AURA_LLM_GPU_LAYERS", "-1"))
    llm_temperature: float = float(os.getenv("AURA_LLM_TEMPERATURE", "0.4"))
    llm_top_p: float = float(os.getenv("AURA_LLM_TOP_P", "0.9"))
    llm_base_model: str = os.getenv("AURA_LLM_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    dataset_path: Path = _path("AURA_DATASET_PATH", ROOT / "training" / "data" / "prepared")
    checkpoint_path: Path = _path("AURA_CHECKPOINT_PATH", ROOT / "training" / "checkpoints")
    database_path: Path = _path("AURA_DATABASE_PATH", ROOT / "aura.db")
    upload_dir: Path = _path("AURA_UPLOAD_DIR", ROOT / "uploads")
    log_dir: Path = _path("AURA_LOG_DIR", ROOT / "logs")
    # Required by the API (checked at startup). The random fallback only serves scripts
    # and tools that import settings without serving media.
    media_signing_key: str = os.getenv("AURA_MEDIA_SIGNING_KEY") or secrets.token_hex(32)
    model_path: Path = _path("AURA_MODEL_PATH", ROOT / "model_artifacts" / "fashion_cnn_final.keras")
    metadata_path: Path = _path("AURA_METADATA_PATH", ROOT / "model_artifacts" / "fashion_cnn.metadata.json")
    compatibility_model_path: Path = _path("AURA_COMPATIBILITY_MODEL_PATH", ROOT / "model_artifacts" / "shift15m_compatibility_safe.keras")
    compatibility_vocab_path: Path = _path("AURA_COMPATIBILITY_VOCAB_PATH", ROOT / "model_artifacts" / "shift15m_subcategory_vocab.json")
    trend_cache_path: Path = _path("AURA_TREND_CACHE_PATH", ROOT / "model_artifacts" / "fashion_trends.cache.json")
    # Polyvore-trained item-level outfit compatibility model (see
    # training/AURA_Outfit_Compatibility_Polyvore_Colab.ipynb).
    outfit_compat_weights_path: Path = _path("AURA_OUTFIT_COMPAT_WEIGHTS", ROOT / "model_artifacts" / "outfit_compat" / "outfit_compat.weights.h5")
    outfit_compat_config_path: Path = _path("AURA_OUTFIT_COMPAT_CONFIG", ROOT / "model_artifacts" / "outfit_compat" / "outfit_compat.config.json")
    # Share of the final score given to the item-level compatibility model when installed.
    outfit_compat_weight: float = float(os.getenv("AURA_OUTFIT_COMPAT_WEIGHT", "0.15"))
    # Fine-tuned stylist GGUF from training/AURA_Stylist_LLM_LoRA_Colab.ipynb.
    # Only this fine-tuned model may reorder the ranker's top options; the base
    # chat GGUF never does. Set ENABLED=0 if it fails its evaluation bar.
    stylist_llm_model_path: Path = _path("AURA_STYLIST_LLM_PATH", ROOT / "model_artifacts" / "llm" / "aura-stylist-q4_k_m.gguf")
    stylist_llm_enabled: bool = os.getenv("AURA_STYLIST_LLM_ENABLED", "1") not in {"0", "false", "False"}
    # Serve chat (and the recommendation comparison text) from the fine-tuned stylist GGUF
    # when it is installed, so an 8 GB host holds one ~1 GB model. With 0, or when the
    # stylist is missing, the base chat GGUF at AURA_LLM_MODEL_PATH is used instead.
    chat_use_stylist: bool = os.getenv("AURA_CHAT_USE_STYLIST", "1") not in {"0", "false", "False"}
    # Personalised contextual-bandit ranking learned from each user's feedback.
    bandit_enabled: bool = os.getenv("AURA_BANDIT_ENABLED", "1") not in {"0", "false", "False"}
    # Virtual try-on ("My Virtual Look"): local models from training/download_tryon_models.py.
    tryon_model_dir: Path = _path("AURA_TRYON_MODEL_DIR", ROOT / "model_artifacts" / "tryon")
    # Off by default so a fresh clone runs on an 8 GB Mac (decision 2026-11-27, "Option A").
    # The 16 GB host turns it on in .env. To go back to on-by-default ("Option B"), change
    # this "0" and AURA_PRELOAD_VISION's "0" below to "1" (see ENGINEERING_PLAN decision log).
    tryon_enabled: bool = os.getenv("AURA_TRYON_ENABLED", "0") not in {"0", "false", "False"}
    # Renders run in a separate worker process that the API starts and stops itself.
    tryon_spawn_worker: bool = os.getenv("AURA_TRYON_SPAWN_WORKER", "1") not in {"0", "false", "False"}
    # Fair-use limits: renders take minutes and most of the machine's memory.
    tryon_max_active_per_user: int = int(os.getenv("AURA_TRYON_MAX_ACTIVE_PER_USER", "1"))
    tryon_daily_limit: int = int(os.getenv("AURA_TRYON_DAILY_LIMIT", "3"))
    tryon_queue_limit: int = int(os.getenv("AURA_TRYON_QUEUE_LIMIT", "10"))
    # Unsaved looks (and failed renders) are deleted after this many days.
    tryon_retention_days: int = int(os.getenv("AURA_TRYON_RETENTION_DAYS", "7"))
    # Render size (multiple of 8, 3:4). 512x384 keeps a render to a few minutes on an 8 GB Mac.
    tryon_height: int = int(os.getenv("AURA_TRYON_HEIGHT", "512"))
    tryon_width: int = int(os.getenv("AURA_TRYON_WIDTH", "384"))
    tryon_steps: int = int(os.getenv("AURA_TRYON_STEPS", "30"))
    tryon_guidance: float = float(os.getenv("AURA_TRYON_GUIDANCE", "2.5"))
    # "auto" picks Apple Metal (mps) when available, else CPU.
    tryon_device: str = os.getenv("AURA_TRYON_DEVICE", "auto")
    # CatVTON attention weights: dresscode-16k-512 (tops, bottoms, dresses; trained at 512x384),
    # vitonhd-16k-512 (tops only) or mix-48k-1024 (trained at 1024x768).
    tryon_attention: str = os.getenv("AURA_TRYON_ATTENTION", "dresscode-16k-512")
    # Cut garments out in a short-lived child process: ISNet keeps ~2 GB of CPU memory
    # once used, which the worker would otherwise hold next to the diffusion model.
    tryon_isolate_cutout: bool = os.getenv("AURA_TRYON_ISOLATE_CUTOUT", "1") not in {"0", "false", "False"}
    # 4.11: widen the try-on mask for roomier sizes/cuts. Off: in the one render check
    # (2026-11-27) the extra width became a flat bar at the hips, not looser fabric. The
    # hem (garment length) adjustment stays on.
    tryon_fit_widen: bool = os.getenv("AURA_TRYON_FIT_WIDEN", "0") not in {"0", "false", "False"}
    # SegFormer garment isolation for imports/uploads (4.2b); used when its model is installed.
    garment_segmentation: bool = os.getenv("AURA_GARMENT_SEGMENTATION", "1") not in {"0", "false", "False"}
    # Per-account / per-IP limits on logins, sign-ups, chat, outfits and uploads (4.1).
    rate_limits_enabled: bool = os.getenv("AURA_RATE_LIMITS", "1") not in {"0", "false", "False"}
    # Concurrent heavy image jobs (CNN, garment cut-out, body analysis) across all requests.
    image_concurrency: int = int(os.getenv("AURA_IMAGE_CONCURRENCY", "2"))
    # Load the garment CNN at startup so the first upload does not pay ~6 s. Off by default
    # (8 GB-safe, loads on the first upload instead); the host turns it on in .env.
    preload_vision: bool = os.getenv("AURA_PRELOAD_VISION", "0") not in {"0", "false", "False"}
    max_upload_bytes: int = int(os.getenv("AURA_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    allowed_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("AURA_ALLOWED_ORIGINS", "*").split(",")
        if value.strip()
    )


settings = Settings()
