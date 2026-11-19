# AURA hybrid stylist: how to train and install it

AURA's outfit suggestions come from three parts working together:

| Part | What it does | Where it is trained |
|---|---|---|
| Garment CNN (existing) | Recognises each uploaded garment and produces a 512-number visual fingerprint (`fashion_feature_normalization` layer) | Already trained on H&M images |
| **Outfit-compatibility transformer** (new, trained from scratch) | Scores whether *these specific garments* look good together | `AURA_Outfit_Compatibility_Polyvore_Colab.ipynb` on Polyvore Outfits |
| **Stylist LLM** (new, LoRA fine-tune of Qwen2.5-1.5B-Instruct) | Picks the best of the top five complete, owned outfits for the occasion, weather, body shape, height, skin tone and preferences, and explains why | `AURA_Stylist_LLM_LoRA_Colab.ipynb` |

The recommender still guarantees every suggestion uses only the user's available garments and is a complete outfit (dress, or top + bottom, plus shoes when owned). The LLM chooses an option *number* and never sees database IDs, so it cannot invent clothes. If anything is missing or invalid, the app falls back automatically: no compatibility model → previous rule signals; no stylist model → the base Qwen chat GGUF with the same prompt; no GGUF at all → ranker order.

## Step 1 — compatibility model (free Colab T4, about 1–1.5 hours)
1. Copy `model_artifacts/fashion_cnn_final.keras` and `fashion_cnn.metadata.json` to Google Drive: `MyDrive/AURA/aura_models/`.
2. Upload `training/AURA_Outfit_Compatibility_Polyvore_Colab.ipynb` to Colab, select **T4 GPU**, **Run all**.
3. Download `MyDrive/AURA/outfit_compat/outfit_compat.weights.h5` and `outfit_compat.config.json` into `Capstone_Agents/model_artifacts/outfit_compat/`.
4. Restart the backend; `GET /models/outfit-compatibility/status` shows `available: true` and the held-out test metrics.

## Step 2 — stylist LLM (free Colab T4, about 1.5–2.5 hours)
1. Upload `training/AURA_Stylist_LLM_LoRA_Colab.ipynb`, select **T4 GPU**, **Run all** (it reuses Step 1's Drive outputs).
2. Download `MyDrive/AURA/stylist_llm/aura-stylist-q4_k_m.gguf` (~1 GB) to `Capstone_Agents/model_artifacts/llm/`.
3. With `requirements-local.txt` installed, restart the backend; `GET /models/stylist/status` returns `fine_tuned_stylist`.

If Colab disconnects, run all again: fingerprints are cached per shard in Drive and LLM training resumes from its last checkpoint.

## What the evaluation files measure
- `outfit_compat/evaluation.json`: compatibility AUC and fill-in-the-blank accuracy on the official Polyvore **test** splits (nondisjoint and the harder disjoint split), next to a CNN cosine-similarity baseline and chance. Report the disjoint numbers as the generalisation estimate.
- `stylist_llm/evaluation.json`: on 300 held-out test looks, how often each method picks the real human-composed outfit out of five options — random (20%), the compatibility model alone, base Qwen zero-shot and the fine-tuned model — broken down by distractor type (`occasion`, `season`, `visual`), plus valid-JSON rate and avoided-colour violations.

## Claims to keep precise in the report
- The compatibility model is trained from scratch; it sits on top of AURA's own frozen CNN rather than an end-to-end image encoder, so expect lower numbers than published end-to-end models. Cite those papers as reference points.
- Polyvore images are clean product shots; user photos are not. Ask testers to photograph garments flat on a plain background.
- Occasion and season labels come from human outfit titles, so they are noisy. The stylist's explanation wording is template-trained; judge it with a small human rating.
- Body shape, height and skin tone are user-stated inputs the LLM reads. Polyvore has no body-type labels, so do not claim learned body-type expertise.
- Polyvore Outfits: Vasileva et al., *Learning Type-Aware Embeddings for Fashion Compatibility*, ECCV 2018, CC BY 4.0 (academic, non-profit use requested by the authors).
