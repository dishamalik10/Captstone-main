"""Compare the base and LoRA-adapted model on the identical held-out test set."""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path

from settings import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--test", type=Path, default=settings.dataset_path / "test.jsonl")
    parser.add_argument("--output", type=Path, default=settings.checkpoint_path / "comparison")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--generation-samples", type=int, default=50)
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()
    if args.max_length < 32 or args.generation_samples < 1:
        parser.error("--max-length must be at least 32 and --generation-samples must be positive.")

    import torch
    from datasets import load_dataset
    from peft import PeftModel
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              DataCollatorForSeq2Seq, Trainer, TrainingArguments)

    metadata_path = args.adapter.parent / "run_metadata.json"
    train_metadata = json.loads(metadata_path.read_text("utf-8")) if metadata_path.is_file() else {}
    base_model = args.base or train_metadata.get("base_model") or "Qwen/Qwen2.5-1.5B-Instruct"
    base_revision = train_metadata.get("base_revision")
    tokenizer = AutoTokenizer.from_pretrained(base_model, revision=base_revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    raw = load_dataset("json", data_files=str(args.test), split="train").shuffle(seed=args.seed)
    if not len(raw):
        raise ValueError("The held-out test split is empty.")
    dataset_manifest_path = args.test.parent / "manifest.json"
    dataset_manifest = (json.loads(dataset_manifest_path.read_text("utf-8"))
                        if dataset_manifest_path.is_file() else {})

    def encode(batch):
        ids_rows, masks, labels, prompts, kept = [], [], [], [], []
        for instruction, answer in zip(batch["instruction"], batch["response"]):
            prompt = tokenizer.apply_chat_template(
                [{"role": "system", "content": "You are AURA, a concise practical fashion stylist. Ground garment advice in the user's stated wardrobe and never invent owned items."},
                 {"role": "user", "content": instruction}],
                tokenize=True, add_generation_prompt=True,
            )
            full = tokenizer.apply_chat_template(
                [{"role": "system", "content": "You are AURA, a concise practical fashion stylist. Ground garment advice in the user's stated wardrobe and never invent owned items."},
                 {"role": "user", "content": instruction}, {"role": "assistant", "content": answer}],
                tokenize=True, add_generation_prompt=False,
            )
            valid = len(full) <= args.max_length and full[:len(prompt)] == prompt
            kept.append(valid)
            if not valid:
                full = full[:args.max_length]
                prompt_length = len(full)
            else:
                prompt_length = len(prompt)
            ids_rows.append(full)
            masks.append([1] * len(full))
            labels.append([-100] * prompt_length + full[prompt_length:])
            prompts.append(prompt)
        return {"input_ids": ids_rows, "attention_mask": masks,
                "labels": labels, "prompt_ids": prompts, "keep": kept}

    encoded = raw.map(encode, batched=True)
    encoded = encoded.filter(lambda row: row["keep"])
    if not len(encoded):
        raise ValueError("No held-out examples fit the configured token length.")
    generation_records = encoded.select(range(min(args.generation_samples, len(encoded))))
    prompt_ids = generation_records["prompt_ids"]
    eval_data = encoded.remove_columns([c for c in encoded.column_names if c != "input_ids" and c != "attention_mask" and c != "labels"])
    collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, label_pad_token_id=-100)
    eval_args = TrainingArguments(output_dir=str(args.output / "tmp"), report_to="none",
                                  per_device_eval_batch_size=1)

    if torch.cuda.is_available():
        dtype = torch.float16
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        dtype = torch.float16
    else:
        dtype = torch.float32

    def evaluate_model(with_adapter: bool) -> tuple[dict, list[str]]:
        model = AutoModelForCausalLM.from_pretrained(
            base_model, revision=base_revision, torch_dtype=dtype
        )
        if with_adapter:
            model = PeftModel.from_pretrained(model, args.adapter)
        model.eval()
        metrics = Trainer(model=model, args=eval_args, data_collator=collator).evaluate(eval_dataset=eval_data)
        loss = metrics.get("eval_loss")
        metrics["perplexity"] = math.exp(loss) if loss is not None and loss < 50 else None
        generated = []
        device = next(model.parameters()).device
        for ids in prompt_ids:
            tensor = torch.tensor([ids], dtype=torch.long, device=device)
            with torch.inference_mode():
                output = model.generate(tensor, max_new_tokens=160, do_sample=False,
                                        pad_token_id=tokenizer.pad_token_id)
            generated.append(tokenizer.decode(output[0][len(ids):], skip_special_tokens=True).strip())
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return metrics, generated

    base_metrics, base_outputs = evaluate_model(False)
    adapter_metrics, adapter_outputs = evaluate_model(True)
    args.output.mkdir(parents=True, exist_ok=True)
    generations = args.output / "generations.jsonl"
    with generations.open("w", encoding="utf-8") as stream:
        for index, (record, base_text, adapter_text) in enumerate(zip(generation_records, base_outputs, adapter_outputs)):
            stream.write(json.dumps({"example_id": record.get("record_id", str(index)),
                                     "participant_id": record.get("participant_id"),
                                     "instruction": record["instruction"],
                                     "base_response": base_text,
                                     "adapter_response": adapter_text}, ensure_ascii=False) + "\n")
    report = {"base_model": base_model, "base_revision": base_revision,
              "adapter": str(args.adapter), "dataset_manifest": str(dataset_manifest_path),
              "dataset_version": dataset_manifest.get("version"),
              "test_file": str(args.test), "examples_scored": len(eval_data),
              "seed": args.seed,
              "generation_examples": len(base_outputs),
              "base": base_metrics, "adapter_model": adapter_metrics,
              "generation_outputs": str(generations),
              "interpretation": "Lower held-out loss is one language-model metric; it does not establish better fashion advice. Have blinded human raters assess factual wardrobe grounding, helpfulness, clarity, and unsafe/invented item mentions."}
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
