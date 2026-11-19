"""Check that every chat example fits the local Qwen tokenizer/context budget."""
from __future__ import annotations
import json
from pathlib import Path
import yaml
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model_artifacts/mlx_base"
DATA = ROOT / "training/fashion_sft"
CONFIG = ROOT / "training/mlx_lora_config.yaml"


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    limit = int(cfg["max_seq_length"])
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    counts = {}
    oversized = []
    for split in ("train", "valid", "test"):
        lengths = []
        for line_no, line in enumerate((DATA / f"{split}.jsonl").open(encoding="utf-8"), 1):
            row = json.loads(line)
            messages = row["messages"]
            if [m.get("role") for m in messages] != ["system", "user", "assistant"]:
                raise ValueError(f"{split}:{line_no}: bad chat roles")
            encoded = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
            token_count = len(encoded["input_ids"])
            lengths.append(token_count)
            if token_count > limit:
                oversized.append({"split": split, "line": line_no, "tokens": token_count})
        counts[split] = {"rows": len(lengths), "max_tokens": max(lengths), "over_limit": sum(n > limit for n in lengths)}
    report = {"status": "valid" if not oversized else "invalid", "tokenizer": str(MODEL), "max_seq_length": limit, "splits": counts, "oversized_examples": oversized[:20]}
    print(json.dumps(report, indent=2))
    if oversized:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
