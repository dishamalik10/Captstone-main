# WearBefore synthetic fashion SFT dataset

This dataset contains 2,124 instruction examples: 2,100 locally generated synthetic examples across 21 topics, plus 24 original manually authored outfit comparisons. It contains no user wardrobe data, user feedback, expert-reviewed answers, or LLM-generated target responses. Each example labels its scenario group, topic, source IDs, license/provenance, and `synthetic: true`.

The 100 fictional generated wardrobe scenarios are kept whole across deterministic 80/10/10 train/validation/test splits; 24 additional manual comparison examples use separate scenario IDs. Current totals are 1,698/213/213. Topics include color relationships, proportions, silhouette, pattern and texture coordination, layering, aesthetics and occasions, plus explicit comparison of two candidate outfits. Every training row uses MLX-LM's `messages` chat format and also retains flat `instruction`/`response` fields for audit. Assistant targets use JSON with `selected_item_ids` and `answer`; incomplete scenarios teach abstention instead of adding items.

Run `python training/build_fashion_dataset.py` to regenerate, then `python training/validate_fashion_dataset.py` to check JSONL parsing, source attribution, duplicate instructions, group leakage, near-duplicate wardrobes, and exact wardrobe-ID containment. Use `python training/validate_qwen_template.py` to check tokenization against the local Qwen tokenizer and configured sequence length.

Licensing is recorded per example. No NC-licensed source is used in the SFT splits. The comparison examples cite Fashionpedia only for its CC BY 4.0 ontology/schema; they do not use its images or image-level annotations. University of Arkansas and Iowa State paraphrases carry CC BY 4.0 attribution. Consult `manifest.json`, `knowledge/fashion_heuristics.json`, and `training/FASHION_DATASET_LICENSE_AUDIT.md` for source scope.

Most rows are deterministic template-generated examples; the added comparison rows are manually authored. A passing validator checks structure and ID containment only; it does not certify fashion quality, expertise, generalization, or factual accuracy. The corpus is a starting point for an experiment and needs blinded human review before any quality claim.

The generated wardrobe values were re-seeded to fix a modulo-cycle collision that had repeated wardrobes across scenario IDs. The original 2,100 row count and topic coverage remain. The 24 extra hand-authored comparisons are not expert-reviewed.
