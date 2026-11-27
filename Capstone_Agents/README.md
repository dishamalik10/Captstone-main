# AURA backend

**Hybrid stylist:** outfit suggestions now combine a Polyvore-trained, item-level outfit-compatibility model with a LoRA-fine-tuned Qwen stylist that picks among the top five owned outfits using occasion, weather, body shape, height, skin tone and preferences. Training notebooks and install steps: [training/HYBRID_STYLIST.md](training/HYBRID_STYLIST.md).

The FastAPI backend and its local LLM setup are documented in the [repository README](../README.md).

From this directory, install `requirements.txt` for the API and `requirements-local.txt` for the optional local GGUF runtime. Configure `AURA_LLM_MODEL_PATH` in `.env`, download the licensed Qwen GGUF explicitly with `python -m training.download_model`, then start the API with:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The legacy `agents/` and `orchestrator/` modules use the same `services.local_llm` adapter as stylist chat. Outfit ranking in `services/recommendation_service.py` remains deterministic and uses only the authenticated user's available wardrobe. The scratch-trained fashion GPT is configured separately with `AURA_FASHION_LM_PATH`; when present, `services.aura_fashion_lm` may explain a fixed server-ranked outfit. The response contract rejects duplicate, unavailable, unowned, or changed item IDs and invalid JSON. If generation fails, the existing rule explanation is returned. The Qwen GGUF remains dedicated to chat and legacy agents.

Run the scratch model training notebook from Colab: `training/AURA_Scratch_Fashion_LM_Colab.ipynb`. It uses the existing Drive datasets and saves the final model and tokenizer separately at `AURA/models/aura_fashion_gpt_final`. Download/sync that directory to `model_artifacts/aura_fashion_gpt_final` (or point `AURA_FASHION_LM_PATH` to its location), then install `requirements-local.txt`. Check `/models/fashion-language/status` before evaluation. The current Mac environment does not contain the scratch checkpoint, so this integration falls back to the rule explanation until Colab training has been run and the output installed.

The existing Expo `AIStylistScreen` already calls the backend `/recommend` endpoint; no second application is needed. Live weather is optional, and trend summaries come only from local cache data.

The backend stores recommendation run IDs and rank positions, and validates feedback against the exact recommendation owned by that user. After collecting actual user judgments, run `python -m scripts.evaluate_feedback` to compute descriptive feedback metrics; an empty or small sample is reported as such rather than treated as model quality evidence.

## Train, transfer, and verify the scratch fashion model

The training notebook must be run in a live Google Colab session because this local Mac session cannot access your Google Drive or Tesla T4 runtime. Open [Google Colab](https://colab.research.google.com), select **File → Upload notebook**, and upload `training/AURA_Scratch_Fashion_LM_Colab.ipynb`. In **Runtime → Change runtime type**, select **T4 GPU**, then use **Runtime → Run all** and approve the Drive mount. Wait for the last cell to finish; it runs test evaluation only after training and final-model saving. Training is complete only when the notebook reports completion and writes `AURA/models/aura_fashion_gpt_final` plus the final evaluation JSON under `AURA/training_logs`.

Copy the entire `AURA/models/aura_fashion_gpt_final` folder from Drive into this project as `model_artifacts/aura_fashion_gpt_final` (or set `AURA_FASHION_LM_PATH` to its full local path). Keep the tokenizer files and model weights together. Then, from this directory:

```sh
source .venv312/bin/activate
pip install -r requirements-local.txt
export AURA_FASHION_LM_PATH="$PWD/model_artifacts/aura_fashion_gpt_final"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

After server startup, `GET http://127.0.0.1:8000/models/fashion-language/status` should report `weights_present: true`; `ready` becomes true after the first recommendation loads the model. Call the authenticated `/recommend` endpoint using the app, then check `/health`: `fashion_lm.loaded` must be true, and the recommendation must report `explanation_source: "aura_fashion_lm"`. A missing or incompatible checkpoint stays on the deterministic explanation path.

To compare the loaded scratch model with the deterministic baseline on the same eight synthetic scenarios, run this from the project directory after installing the model:

```sh
python scripts/evaluate_scenarios.py --require-scratch-model
python scripts/make_blind_styling_rating.py
```

The first command refuses to run as a scratch-model evaluation unless local weights load. It writes paired explanations to `training/checkpoints/fashion-evaluation/scratch-vs-rules.jsonl`; the second writes a blinded CSV and a separate key. Have a person rate grounding, fashion rationale, weather/occasion fit, and clarity before claiming better fashion styling. These software fixtures check schema, wardrobe IDs, and safety constraints; they cannot establish fashion understanding by themselves. The rule engine selects outfits today, while the scratch model only explains the fixed selection, so this integration does not yet let the language model independently reason over or choose outfits.
