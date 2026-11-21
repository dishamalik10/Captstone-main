# Model artifacts

| Path | In Git? | Produced by |
|---|---|---|
| `fashion_cnn_final.keras`, `fashion_cnn.metadata.json` | Yes | Garment CNN training (H&M). The metadata JSON must keep the exact class order used in training. |
| `shift15m_compatibility_safe.keras`, `shift15m_*.json` | Yes | SHIFT15M compatibility training |
| `outfit_compat/outfit_compat.weights.h5`, `outfit_compat.config.json` | Yes (small) | `training/AURA_Outfit_Compatibility_Polyvore_Colab.ipynb` |
| `outfit_compat/evaluation.json`, `stylist_llm_evaluation.json` | Yes | Held-out results from the two Colab notebooks |
| `aura_fashion_gpt_final/` (config, tokenizer, `model.safetensors`, ~21 MB) | **No**: not trained yet; optional (explanations fall back to rules / base Qwen) | Train with `training/AURA_Scratch_Fashion_LM_Colab.ipynb`, then copy the folder here |
| `llm/aura-stylist-q4_k_m.gguf` (~1 GB) | **No**: over GitHub's 100 MB limit | `training/AURA_Stylist_LLM_LoRA_Colab.ipynb`; download with `python -m training.download_stylist_model` (GitHub Release `stylist-llm-v1`) |
| `llm/qwen2.5-1.5b-instruct-q4_k_m.gguf` (~1.1 GB) | **No** | `python -m training.download_model` |

`llm/` is git-ignored. Every model is optional at startup: a missing artifact disables only its own role, and `/health` reports which ones are present.
