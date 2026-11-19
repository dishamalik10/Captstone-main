"""Supervised LoRA fine-tuning. Expects prepared train/validation JSONL splits."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path

from settings import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=settings.dataset_path)
    parser.add_argument("--output", type=Path, default=settings.checkpoint_path / "lora")
    parser.add_argument("--base", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--allow-low-memory", action="store_true",
                        help="Override the 12 GiB system-memory preflight; training may fail or swap heavily.")
    args = parser.parse_args()
    if args.epochs <= 0 or args.max_length < 32:
        parser.error("--epochs must be positive and --max-length must be at least 32.")
    try:
        total_ram = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        total_ram = 0
    if total_ram and total_ram < 12 * 1024**3 and not args.allow_low_memory:
        parser.error(f"LoRA training preflight found {total_ram / 1024**3:.1f} GiB RAM; this experiment recommends at least 12 GiB. Use --allow-low-memory only if you accept likely slowdown or OOM risk.")

    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    if torch.cuda.is_available():
        gpu_ram = torch.cuda.get_device_properties(0).total_memory
        if gpu_ram < 12 * 1024**3 and not args.allow_low_memory:
            parser.error(f"GPU has {gpu_ram / 1024**3:.1f} GiB VRAM; at least 12 GiB is recommended for this LoRA setup. Use --allow-low-memory only if you accept likely OOM risk.")
    elif not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
        print("Warning: no CUDA/MPS accelerator detected; CPU fine-tuning may be very slow.")
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    if torch.cuda.is_available():
        dtype = torch.float16
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        dtype = torch.float16
    else:
        dtype = torch.float32
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=dtype)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
    data = load_dataset("json", data_files={"train": str(args.data / "train.jsonl"),
                                              "validation": str(args.data / "validation.jsonl")})

    def tokenize(batch):
        input_rows, mask_rows, label_rows, keep = [], [], [], []
        for question, answer in zip(batch["instruction"], batch["response"]):
            system = {"role": "system", "content": "You are AURA, a concise practical fashion stylist. Ground garment advice in the user's stated wardrobe and never invent owned items."}
            user = {"role": "user", "content": question}
            assistant = {"role": "assistant", "content": answer}
            prompt_ids = tokenizer.apply_chat_template(
                [system, user], tokenize=True, add_generation_prompt=True
            )
            full_ids = tokenizer.apply_chat_template(
                [system, user, assistant], tokenize=True, add_generation_prompt=False
            )
            valid = len(full_ids) <= args.max_length and full_ids[:len(prompt_ids)] == prompt_ids
            keep.append(valid)
            if not valid:
                full_ids = full_ids[:args.max_length]
                prompt_length = len(full_ids)
            else:
                prompt_length = len(prompt_ids)
            input_rows.append(full_ids)
            mask_rows.append([1] * len(full_ids))
            label_rows.append([-100] * prompt_length + full_ids[prompt_length:])
        return {"input_ids": input_rows, "attention_mask": mask_rows,
                "labels": label_rows, "keep": keep}

    tokenized = data.map(tokenize, batched=True, remove_columns=data["train"].column_names)
    raw_counts = {split: len(tokenized[split]) for split in tokenized}
    tokenized = tokenized.filter(lambda row: row["keep"])
    dropped_for_length = {split: raw_counts[split] - len(tokenized[split]) for split in tokenized}
    tokenized = tokenized.remove_columns(["keep"])
    if not len(tokenized["train"]) or not len(tokenized["validation"]):
        raise ValueError("No valid train/validation examples remain after token-length checks.")
    args.output.mkdir(parents=True, exist_ok=True)
    from transformers import DataCollatorForSeq2Seq
    trainer = Trainer(model=model, args=TrainingArguments(
        output_dir=str(args.output), num_train_epochs=args.epochs, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, learning_rate=2e-4, logging_steps=10,
        save_strategy="epoch", eval_strategy="epoch", report_to="none",
        fp16=torch.cuda.is_available(), gradient_checkpointing=True,
        save_total_limit=2, load_best_model_at_end=True, metric_for_best_model="eval_loss",
        greater_is_better=False, seed=args.seed, data_seed=args.seed), train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"], tokenizer=tokenizer,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model,
                                             label_pad_token_id=-100, pad_to_multiple_of=8))
    trainer.train(resume_from_checkpoint=(str(args.resume_from_checkpoint)
                                         if args.resume_from_checkpoint else None))
    trainer.save_model(str(args.output / "adapter"))
    tokenizer.save_pretrained(str(args.output / "adapter"))
    manifest_path = args.data / "manifest.json"
    dataset_manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.is_file() else {}
    (args.output / "run_metadata.json").write_text(json.dumps({
        "base_model": args.base, "max_length": args.max_length, "epochs": args.epochs,
        "lora_rank": 8, "lora_alpha": 16, "dataset_manifest": str(manifest_path),
        "dataset_version": dataset_manifest.get("version"),
        "dataset_licenses": dataset_manifest.get("licenses", []),
        "train_records": len(tokenized["train"]), "validation_records": len(tokenized["validation"]),
        "dropped_for_length": dropped_for_length,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "best_eval_loss": trainer.state.best_metric,
        "seed": args.seed,
        "learning_rate": 2e-4,
        "gradient_accumulation_steps": 8,
        "batch_size_per_device": 1,
        "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "torch_version": torch.__version__,
        "transformers_version": importlib.metadata.version("transformers"),
        "peft_version": importlib.metadata.version("peft"),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else ("mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"),
        "base_revision": getattr(model.config, "_commit_hash", None),
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
