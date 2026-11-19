from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    fashion_lm_path: Path = Path(
        os.getenv(
            "AURA_FASHION_LM_PATH",
            ROOT / "model_artifacts" / "aura_fashion_gpt_final",
        )
    ).expanduser()
    llm_model_path: Path = Path(os.getenv("AURA_LLM_MODEL_PATH", ROOT / "model_artifacts" / "llm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"))
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
    dataset_path: Path = Path(os.getenv("AURA_DATASET_PATH", ROOT / "training" / "data" / "prepared"))
    checkpoint_path: Path = Path(os.getenv("AURA_CHECKPOINT_PATH", ROOT / "training" / "checkpoints"))
    database_path: Path = Path(os.getenv("AURA_DATABASE_PATH", ROOT / "aura.db"))
    upload_dir: Path = Path(os.getenv("AURA_UPLOAD_DIR", ROOT / "uploads"))
    media_signing_key: str = os.getenv("AURA_MEDIA_SIGNING_KEY") or secrets.token_hex(32)
    model_path: Path = Path(
        os.getenv(
            "AURA_MODEL_PATH",
            ROOT / "model_artifacts" / "fashion_cnn_final.keras",
        )
    )
    metadata_path: Path = Path(
        os.getenv(
            "AURA_METADATA_PATH",
            ROOT / "model_artifacts" / "fashion_cnn.metadata.json",
        )
    )
    compatibility_model_path: Path = Path(
        os.getenv(
            "AURA_COMPATIBILITY_MODEL_PATH",
            ROOT / "model_artifacts" / "shift15m_compatibility_safe.keras",
        )
    )
    compatibility_vocab_path: Path = Path(
        os.getenv(
            "AURA_COMPATIBILITY_VOCAB_PATH",
            ROOT / "model_artifacts" / "shift15m_subcategory_vocab.json",
        )
    )
    trend_cache_path: Path = Path(
        os.getenv(
            "AURA_TREND_CACHE_PATH",
            ROOT / "model_artifacts" / "fashion_trends.cache.json",
        )
    )
    # Polyvore-trained item-level outfit compatibility model (see
    # training/AURA_Outfit_Compatibility_Polyvore_Colab.ipynb).
    outfit_compat_weights_path: Path = Path(
        os.getenv(
            "AURA_OUTFIT_COMPAT_WEIGHTS",
            ROOT / "model_artifacts" / "outfit_compat" / "outfit_compat.weights.h5",
        )
    )
    outfit_compat_config_path: Path = Path(
        os.getenv(
            "AURA_OUTFIT_COMPAT_CONFIG",
            ROOT / "model_artifacts" / "outfit_compat" / "outfit_compat.config.json",
        )
    )
    # Share of the final score given to the item-level compatibility model when installed.
    outfit_compat_weight: float = float(os.getenv("AURA_OUTFIT_COMPAT_WEIGHT", "0.40"))
    # Stylist LLM that picks among the top outfit options (fine-tuned GGUF from
    # training/AURA_Stylist_LLM_LoRA_Colab.ipynb). Falls back to the chat GGUF.
    stylist_llm_model_path: Path = Path(
        os.getenv(
            "AURA_STYLIST_LLM_PATH",
            ROOT / "model_artifacts" / "llm" / "aura-stylist-q4_k_m.gguf",
        )
    )
    stylist_llm_enabled: bool = os.getenv("AURA_STYLIST_LLM_ENABLED", "1") not in {"0", "false", "False"}
    max_upload_bytes: int = int(os.getenv("AURA_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    allowed_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("AURA_ALLOWED_ORIGINS", "*").split(",")
        if value.strip()
    )


settings = Settings()
