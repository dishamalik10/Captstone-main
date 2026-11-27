# Fashion dataset license and provenance audit

Reviewed: 2026-10-30. This records project decisions, not legal advice. The audit distinguishes dataset-level terms from underlying image rights. No DeepFashion, Polyvore, or Fashionpedia image dataset was downloaded for this work.

## Dataset decisions

| Resource | Useful signal | Terms checked | Decision in WearBefore SFT |
|---|---|---|---|
| DeepFashion | 800K+ images, 50 categories, 1,000 attributes, landmarks, and cross-domain pairs | CUHK/MMLab terms state non-commercial research only, disclaim ownership of images, prohibit commercial use of images and derived data, and restrict redistribution. | Excluded. No data, labels, images, or derived examples used. |
| Polyvore Outfits | 68,306 outfits, 261,058 items; outfit-level compatibility relationships | The original project repository links the dataset but its BSD license is for code. The current linked dataset card says access is academic/non-profit and states the authors do not own underlying images/metadata; elsewhere on that same card it asserts CC BY 4.0 and commercial permissions. Because these terms conflict and third-party rights remain unclear, this project does not treat Polyvore as commercially cleared. | Excluded. No images, item records, outfit records, compatibility labels, or examples derived from Polyvore used. |
| Fashionpedia | Expert-built ontology; 27 main apparel categories, 19 garment parts, 294 fine-grained attributes; useful for separating item category/parts from recorded visual attributes. | The Fashionpedia license page explicitly applies CC BY 4.0 to its annotations and ontology, while stating image copyright belongs to others and image use must follow the image hosts' terms. | Used only as an attributed schema/ontology reference to organize category, garment-part, and attribute fields. No Fashionpedia images or image-level annotations are used. The hand-authored compatibility explanations are WearBefore heuristics, not Fashionpedia findings. |

Sources: [DeepFashion official terms](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html), [Polyvore original project repository](https://github.com/mvasil/fashion-compatibility), [linked Polyvore dataset terms/card](https://huggingface.co/datasets/mvasil/polyvore-outfits), [Fashionpedia official license](https://fashionpedia.github.io/home/data_license.html), [Fashionpedia project description](https://fashionpedia.github.io/home/index.html), [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/).

The Fashionpedia reference is limited to the ontology/schema. It does not make Fashionpedia a source for outfit compatibility, color harmony, proportion recommendations, or occasion suitability. Those example judgments are clearly labeled as original, non-empirical WearBefore heuristics.

## Runtime models (not used for training)

| Model | Use in AURA | Licence | Decision |
|---|---|---|---|
| SegFormer-B2 Clothes (`mattmdjaga/segformer_b2_clothes`, revision `584abc1e1d260e23c0fc627c5217a09b2b461046`, ONNX export, SHA-256 `a93a8dac171b5c1fcc53632a8bfc180bfd9759ea69a3e207451bb07f76add54f`) | Garment isolation on imports and uploads (ENGINEERING_PLAN 4.2b): keeps only the chosen garment from a photo of someone wearing it. Runs locally; no images leave the server. | The model card lists the licence as "other", pointing to the NVlabs SegFormer licence (https://github.com/NVlabs/SegFormer/blob/master/LICENSE), which is believed to be non-commercial. The fine-tune's training data (ATR human-parsing) has its own research terms. **Owner action:** read the NVlabs licence to confirm. | Accepted for a free, non-commercial release only. If AURA ever charges money or shows ads, replace it (for example with a commercially licensed hosted segmentation API) before doing so. |
| Test fixture `tests/fixtures/blouse_and_jeans_cc0.jpg` | Real-photo test of the SegFormer cut-out | CC0 1.0 (Wikimedia Commons, by Keymeulen) | Used; attribution in `tests/fixtures/README.md`. |

## Other training provenance

The original synthetic corpus previously marked several color-theory rows as paraphrases of RMIT's CC BY-NC 4.0 resource. Those training rows are now attributed to the original WearBefore heuristic source and carry no RMIT source ID. This removes the NC source from the training splits. RMIT remains listed in the runtime knowledge registry for transparency but is not in the generated SFT manifest's used-source list. Other sourced examples retain row-level attribution to CC BY material from the University of Arkansas apparel workbook and Iowa State dress/diversity textbook.

The 2,100 programmatically authored fictional wardrobe examples remain in the corpus. A verified modulo-cycle collision in wardrobe generation was fixed: scenario attribute assignments are now independently seeded, so an ID change no longer produces a repeated wardrobe. This changes the generated fictional wardrobe values while preserving row count and topic coverage.

An additional 24 manually authored comparisons are included. They are fictional, created for this project, and explicitly **not expert-reviewed**. Their prompts require comparison of two supplied outfits across recorded color, fit/proportions, and occasion tags, along with uncertainty. All selected items must come from the supplied wardrobe. No user wardrobe, feedback, human annotation, image, or LLM-generated target response is included.

## Current dataset inventory

- Total: 2,124 examples; the original 2,100 retained plus 24 curated comparison examples.
- Splits: 1,698 train / 213 validation / 213 test.
- Scenario groups: 100 generated wardrobe cases plus 24 manually authored cases; each scenario stays in exactly one split.
- Original topic coverage: 21 topics × 100 examples each.
- Additional curated comparisons: 24, split 18 / 3 / 3 by scenario group.
- All records use Qwen-compatible `messages` with `system`, `user`, and `assistant` roles. The tokenizer check against the local Qwen tokenizer found maximum example length 832 tokens; `max_seq_length` is 832.
- Exact duplicate instructions: 0. Duplicate instruction/response pairs: 0.
- Cross-split scenario leaks: 0. A same-topic wardrobe feature-overlap check uses full item signatures (category, name, color, fabric, pattern, fit, texture, season); measured maximum overlap is 0.50, below the 0.80 near-duplicate threshold.
- Training rows from NC-licensed sources: 0.
- Selected IDs and both comparison candidates are checked against the prompt's wardrobe. Curated answers must select one of the two supplied candidates.

Validation checks structure and traceability. It does not establish styling expertise, real-world compatibility, diversity across cultures, or user preference. The 24 manually authored rows and template-generated base corpus still need independent stylist review and a larger, representative held-out human evaluation before claims about fashion quality.

Rebuild and verify with:

```sh
./.venv-mlx/bin/python training/build_fashion_dataset.py
./.venv-mlx/bin/python training/validate_fashion_dataset.py
```
