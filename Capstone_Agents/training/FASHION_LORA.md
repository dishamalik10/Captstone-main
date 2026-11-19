# WearBefore Qwen fashion LoRA experiment

## What this is

This is a local MLX QLoRA experiment for the existing Qwen2.5-1.5B-Instruct model. It is designed for the Apple Silicon host detected on this machine (A18 Pro, 8 GiB unified memory). It does not change FastAPI, SQLite, llama.cpp inference, authentication, or the existing wardrobe-item validation. The MLX base checkpoint and adapter are training artifacts; serving remains on llama.cpp only after the conversion check described below succeeds.

The dataset in `fashion_sft/` contains the retained 2,100 synthetic base rows plus 24 original manually authored comparisons: 1,698 train, 213 validation, and 213 held-out test. All rows have source/license metadata, scenario-grouped splits, and item-ID audits. It contains no user's wardrobe or feedback. The generated targets are deterministic templates; the 24 added comparisons are manually authored but not expert-reviewed. Their validity does not prove styling quality.

`knowledge/fashion_heuristics.json` separates attributed sourced paraphrases from WearBefore-authored heuristics. NC-licensed RMIT color paraphrases have been removed from the SFT records. Fashionpedia is used only as an attributed CC BY 4.0 ontology/schema reference; no images or image-level annotations are included. See `FASHION_DATASET_LICENSE_AUDIT.md` for DeepFashion and Polyvore exclusions and source scope. Do not represent synthetic examples as designer-approved guidance.

## Reproduce on this Mac

The isolated `.venv-mlx` environment uses `training/requirements-mlx.txt`. The base checkpoint is `mlx-community/Qwen2.5-1.5B-Instruct-4bit`, stored locally under `model_artifacts/mlx_base/`. Acquisition requires network access once; generation and tuning run locally. No wardrobe or feedback data is uploaded.

```sh
./.venv-mlx/bin/python training/build_fashion_dataset.py
./.venv-mlx/bin/python training/validate_fashion_dataset.py
./.venv-mlx/bin/python training/validate_qwen_template.py
HF_HUB_DISABLE_XET=1 HF_HOME="$PWD/model_artifacts/mlx_cache" \
  ./.venv-mlx/bin/hf download mlx-community/Qwen2.5-1.5B-Instruct-4bit \
  --local-dir model_artifacts/mlx_base --include '*.safetensors'
./.venv-mlx/bin/python training/run_mlx_lora.py
```

The run script refuses a non-Apple/Metal host, an incomplete checkpoint, or less than 20% free system memory. The completed configuration uses rank-8 LoRA on the final 8 layers, batch 1, gradient accumulation 8, no gradient checkpointing, 832-token context, learning rate 1e-6, and 212 optimizer iterations (approximately one pass over the 1,698 train rows). Earlier runs with gradient checkpointing produced NaN losses and were stopped; this configuration completed with finite losses. The guarded run took about 12.9 minutes on this host. Training logs and the machine-readable run record are `mlx_lora_training.log` and `mlx_lora_run.json`. These observations apply to this run and machine.

## Evaluation

Run the same held-out 42 prompts against the base model and adapter:

```sh
./.venv-mlx/bin/python training/evaluate_mlx_finetune.py \
  --output training/results/base.json
./.venv-mlx/bin/python training/evaluate_mlx_finetune.py \
  --adapter training/checkpoints/wearbefore-qwen25-1_5b-lora \
  --output training/results/lora.json
```

The evaluator reports parseability, wardrobe-ID containment, presence of an explanation, unique outfit sets, latency, token counts, and MLX active memory at the end of generation (not peak RAM). These are structural proxies. Occasion fit, color harmony, and stylistic usefulness require a blinded human review; synthetic user feedback is not a substitute for real user feedback. No result should be called an accuracy or fashion-quality score.

## Deployment gate

The application's existing `AURA_LLM_MODEL_PATH` points to the original Q4_K_M GGUF. MLX-LM's direct `--export-gguf` fusion path does not support Qwen2.5. To keep llama.cpp, fuse/dequantize the adapter to local Hugging Face safetensors, convert that checkpoint with the matching llama.cpp `convert_hf_to_gguf.py`, quantize with `llama-quantize`, and run the existing API and wardrobe-containment tests against the resulting GGUF. Do not replace the current configured model until the converted file exists and passes those checks. If conversion or memory use fails, keep the adapter as an experiment and the original GGUF as the working runtime; report that deployment was not completed.

No fine-tuning result is claimed until the run record has `exit_code: 0`, held-out before/after outputs exist, and the runtime conversion passes. No improvement claim is justified by loss alone or by synthetic structural measures.

## Completed run and measured outcome

The full 212-iteration run completed with exit code 0 on the 8 GiB Apple Silicon host. The run record reports 12.85 minutes elapsed and 60% free system memory after completion. Eight validation batches were randomly sampled at evaluation points, so the final validation loss (2.839) is a logged training diagnostic, not a controlled quality result. The adapter is saved at `training/checkpoints/wearbefore-qwen25-1_5b-lora/`.

On the same 42 held-out prompts, base and adapter both produced 0/42 parseable JSON responses and 0/42 wardrobe-ID-compliant outputs. Base mean generation time was 4.40 s; adapter mean was 4.98 s. Thus this completed training run has no measured structural improvement and is not ready to replace the app's current llama.cpp GGUF. The base and adapter records are `training/results/base.json` and `training/results/lora.json`. The metric named `mlx_active_memory_gb_at_end` is MLX active memory at evaluation end, not peak process RAM. Human assessment is still required for styling quality.
