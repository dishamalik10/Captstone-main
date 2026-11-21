# AURA: local language generation for a wardrobe stylist

AURA is an existing Expo / React Native application backed by FastAPI. Garment recognition uses the existing local Keras model. Outfit candidates are built and ranked by deterministic rules over the authenticated user's available wardrobe. Three local language models sit on top of that ranker, each with one job and a validated fallback. No hosted LLM inference API is used.

## Architecture and model roles

```text
Expo app → FastAPI → authenticated wardrobe + deterministic outfit ranking (top 5 options)
                  ├→ fine-tuned stylist GGUF (Qwen2.5-1.5B + LoRA) → may move one option to #1; also serves chat
                  ├→ scratch-trained AURA GPT (5.24M params) → validated explanation of each outfit
                  ├→ base Qwen2.5-1.5B GGUF → fallback only (chat / explanations when the models above are absent)
                  ├→ SQLite, auth, uploads
                  └→ optional OpenWeather context (non-LLM API)
```

| Model | Job in `/recommend` | Job in `/chat/messages` | When it is absent or its output fails validation |
|---|---|---|---|
| Rule ranker + critic | Builds complete, owned outfits and orders them | Supplies the selected recommendation | — (always on) |
| **Fine-tuned stylist** (`aura-stylist-q4_k_m.gguf`, LoRA on Qwen2.5-1.5B, `training/AURA_Stylist_LLM_LoRA_Colab.ipynb`) | Picks one of the top 5 options as #1 by option number (never sees item IDs) and gives the #1 reason | Answers chat (`AURA_CHAT_USE_STYLIST=1`) | Ranker order is kept; chat uses base Qwen |
| **Scratch AURA GPT** (`aura_fashion_gpt_final/`, `training/AURA_Scratch_Fashion_LM_Colab.ipynb`) | Explains each outfit; must return exactly `{"item_ids", "explanation"}` with the selected IDs unchanged | — | Evidence-grounded rule explanation |
| **Base Qwen2.5-1.5B** (`qwen2.5-1.5b-instruct-q4_k_m.gguf`) | Only when neither model above ran: writes the top-two comparison and outfit notes | Only when the stylist is not installed or chat routing is off | Rule text / HTTP 503 for chat |

Rules that hold regardless of model:

1. **Only the fine-tuned stylist may change the order**, and only among complete, owned options the ranker built. The untuned base Qwen model never reorders outfits. The `/recommend` trace reports `may_change_rank` and `changed_rank` for the stylist step.
2. **No model can add, remove or swap garments.** The scratch GPT's JSON must repeat the selected IDs exactly; every model's text is filtered for unlisted garments, colours and unsupported claims before it is shown.
3. **Training/inference parity.** The scratch GPT's prompt format lives in `Capstone_Agents/ml/explain_prompt.py` and the stylist's in `ml/stylist_prompt.py`; both notebooks embed these files byte-for-byte and a test enforces it.
4. **Status endpoints:** `/health`, `/models/stylist/status` (picking + chat source) and `/models/fashion-language/status`.

**Training data.** The scratch GPT trains on the Google Drive fashion-knowledge corpus (Stage 1) and the `constraint_v2` instruction set reformatted into the explain contract (Stage 2). The stylist LoRA trains on choose-the-real-outfit examples built from Polyvore Outfits (Vasileva et al., ECCV 2018, CC BY 4.0). See `Capstone_Agents/training/HYBRID_STYLIST.md`. Results are reported in `PROJECT_REPORT.md` only after the runs complete.

**Retrieval.** Stylist prompts retrieve matching entries from the local heuristic reference JSON. This is prompt-time grounding, not training data. The trend cache remains optional and separate.

## Hardware

The development host is an Apple Silicon MacBook Neo with A18 Pro and 8 GiB unified RAM. Qwen 1.5B Q4_K_M is selected as a small local model (about 1.12 GB weights plus runtime/context overhead). On this host, the installed `llama-cpp-python` 0.3.36 supports Metal offload (tensor API disabled). A local two-sample benchmark with 4 threads, 4096 context, the same prompt and 96-token cap measured 23.85 tokens/s CPU versus 35.35 tokens/s with all layers offloaded to Metal; model load was 2.83s versus 1.51s. Peak process RSS was 1.67 GiB versus 1.11 GiB. These are short local measurements, not broad performance guarantees; unified GPU memory is shared with system RAM. Metal is the default on the target setup (`AURA_LLM_GPU_LAYERS=-1`); set it to `0` for CPU. The base model is downloaded separately, not committed.

The repository also includes a small local retrieval file at `Capstone_Agents/knowledge/fashion_heuristics.json`. It is original, explicitly heuristic guidance written for this capstone, labeled CC BY 4.0; it is not empirical research, trend reporting, external source material, or training data. Retrieval adds relevant notes to local stylist prompts. The server's deterministic compatibility engine still owns outfit selection and ranking. Vision returns the trained model's color group plus a separate median RGB sample from the image center; the sample is explicitly approximate because no garment segmentation or lighting correction is performed.

## Setup guide (from a fresh clone)

Follow these steps in order to run the full app (backend, models and Expo frontend) on a new machine. Training is **not** needed: every trained model is either in Git or downloadable.

### 1. Prerequisites

- **Python 3.11**, **Node.js (LTS)** and **git**.
- About 8 GB RAM is enough (the development Mac has 8 GiB). On Apple Silicon, Metal speeds up the language models.

### 2. Clone and install the backend

```bash
git clone https://github.com/dishamalik10/Captstone-main.git
cd Captstone-main/Capstone_Agents
python3.11 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
# Local language-model runtime. macOS with Metal acceleration:
CMAKE_ARGS="-DGGML_METAL=on" python -m pip install -r requirements-local.txt
# Windows / Linux / CPU-only instead:
# python -m pip install -r requirements-local.txt
cp .env.example .env                  # Windows: copy .env.example .env
```

Edit `Capstone_Agents/.env`:

- `AURA_MEDIA_SIGNING_KEY`: set a stable random secret so wardrobe image links survive restarts. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `OPENWEATHER_API_KEY` (optional): live weather for recommendations.
- On a machine without Metal, set `AURA_LLM_GPU_LAYERS=0`.

No OpenAI, Gemini, Claude or other LLM API keys are needed.

### 3. Get the models

| Model | Role in the app | How to get it |
|---|---|---|
| Garment CNN (`fashion_cnn_final.keras`) | Recognises category and colour of uploaded clothes | Already in Git |
| SHIFT15M compatibility model | Legacy pairwise compatibility | Already in Git |
| Outfit-compatibility transformer (`model_artifacts/outfit_compat/`) | Scores how well the pieces of an outfit go together | Already in Git |
| Fine-tuned stylist GGUF (`aura-stylist-q4_k_m.gguf`, ~1 GB) | Picks the #1 outfit with a reason; answers chat | `python -m training.download_stylist_model` (GitHub Release, SHA-256 verified) |
| Base Qwen2.5-1.5B GGUF (~1.1 GB) | Fallback for chat and explanations | `python -m training.download_model` (Hugging Face) |
| Scratch AURA GPT (`model_artifacts/aura_fashion_gpt_final/`) | Optional per-outfit explanations | Train with `training/AURA_Scratch_Fashion_LM_Colab.ipynb` and copy the folder in |

From `Capstone_Agents` with the virtual environment active:

```bash
python -m training.download_stylist_model   # fine-tuned stylist, from the stylist-llm-v1 release
python -m training.download_model           # base Qwen fallback
```

Both GGUFs land in `model_artifacts/llm/`, which is git-ignored. If you prefer a browser, download `aura-stylist-q4_k_m.gguf` from the repository's **Releases** page (tag `stylist-llm-v1`) and place it at `Capstone_Agents/model_artifacts/llm/aura-stylist-q4_k_m.gguf`.

Every model is optional at startup: a missing one disables only its own role and the app falls back safely (for example, the ranker's order is kept when the stylist is absent). The server never downloads weights on its own.

### 4. Start the backend

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Check it:

- `http://127.0.0.1:8000/health`: which models are present and loaded.
- `http://127.0.0.1:8000/models/stylist/status`: should report `fine_tuned_stylist` for both picking and chat.
- `http://127.0.0.1:8000/docs`: interactive API.

To use the app from a physical phone, start with `--host 0.0.0.0` instead.

### 5. Start the app

```bash
cd ../Capstone-App
npm install
cp .env.example .env
npx expo start --web
```

Set `EXPO_PUBLIC_API_URL` in `Capstone-App/.env`: `http://127.0.0.1:8000` for web and the iOS simulator, `http://10.0.2.2:8000` for the Android emulator, or your computer's LAN IP (for example `http://192.168.1.20:8000`) for a physical phone.

### 6. Use the model features

1. **Sign up** in the app.
2. **Upload garments.** The CNN tags each one's category and colour.
3. **Set preferences**, for example colours to avoid.
4. **AI Stylist** (`/recommend`): the ranker builds complete outfits from your own clothes, the outfit-compatibility model scores them, the fine-tuned stylist picks #1 and explains why, and each outfit gets an explanation. The response's `agent_trace` shows which model did what.
5. **Chat** (`/chat/messages`): styling questions answered by the fine-tuned stylist.

### 7. Verify the install

```bash
cd ../Capstone_Agents
python -m pytest -q
```

The tests mock the language-model runtime and need no model downloads.

## Environment

See `Capstone_Agents/.env.example`. Main local model settings:

| Setting | Default | Purpose |
|---|---|---|
| `AURA_LLM_MODEL_PATH` | `model_artifacts/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf` | Local GGUF weights |
| `AURA_FASHION_LM_PATH` | `model_artifacts/aura_fashion_gpt_final` | Optional scratch-trained AURA fashion GPT directory |
| `AURA_STYLIST_LLM_PATH` | `model_artifacts/llm/aura-stylist-q4_k_m.gguf` | Fine-tuned stylist GGUF (~1 GB, not in Git; `python -m training.download_stylist_model`) |
| `AURA_STYLIST_LLM_ENABLED` | `1` | Allow the fine-tuned stylist to pick #1; set `0` if it fails its evaluation bar |
| `AURA_CHAT_USE_STYLIST` | `1` | Serve chat from the fine-tuned stylist when installed; `0` keeps base Qwen for chat |
| `AURA_LLM_BASE_MODEL` | `Qwen/Qwen2.5-1.5B-Instruct` | Base model identity for training |
| `AURA_LLM_CONTEXT_LENGTH` | `4096` | llama.cpp context |
| `AURA_LLM_MAX_INPUT_TOKENS` | `3072` | Approximate input bound |
| `AURA_LLM_MAX_OUTPUT_TOKENS` | `384` | Response cap |
| `AURA_LLM_CONCURRENCY` | `1` | Concurrent generation slots |
| `AURA_LLM_QUEUE_TIMEOUT_SECONDS` | `30` | Maximum wait for a generation slot |
| `AURA_LLM_THREADS` | `4` | CPU threads |
| `AURA_LLM_GPU_LAYERS` | `-1` | Metal offload all layers on the tested Apple Silicon runtime; use `0` for CPU |
| `AURA_MEDIA_SIGNING_KEY` | random per backend process | HMAC key for 15-minute private wardrobe image URLs; set a stable random secret in `.env` to keep links valid across restarts |
| `AURA_LLM_TEMPERATURE`, `AURA_LLM_TOP_P` | `0.4`, `0.9` | Sampling |
| `AURA_DATASET_PATH` | `training/data/prepared` | Prepared split directory |
| `AURA_CHECKPOINT_PATH` | `training/checkpoints` | Adapter/checkpoints |

No OpenAI, Gemini, Claude, Groq, or other LLM credentials are needed. `OPENWEATHER_API_KEY` is still optional for live weather; weather does not generate language.

## Scratch fashion model training in Colab

Open `Capstone_Agents/training/AURA_Scratch_Fashion_LM_Colab.ipynb` in Google Colab with a Tesla T4 runtime and run every cell from top to bottom. It mounts Google Drive, checks the supplied dataset paths and schemas, loads only the local scratch model/tokenizer, pretrains on fixed 512-token causal blocks, and fine-tunes instruction responses with prompt labels masked to `-100`. Stage checkpoints and metrics stay under `/content/drive/MyDrive/AURA`; training can resume from the latest checkpoint. The existing instruction test split is read only in the notebook's final held-out evaluation cell after training and checkpoint selection. The final HF model/tokenizer are saved under `AURA/models/aura_fashion_gpt_final`.

Training has not been run from this Mac session because its Colab runtime and mounted Drive are not available here. No training metrics or fashion-reasoning claims are asserted. After Colab finishes, download/sync the entire final-model directory (config, tokenizer files, and weights) to `Capstone_Agents/model_artifacts/aura_fashion_gpt_final`, or set `AURA_FASHION_LM_PATH` to its local location. Install `requirements-local.txt` in the backend environment to enable Transformers inference. `/health` and `/models/fashion-language/status` report the scratch model state. The existing Expo AI Stylist screen already calls `/recommend`; it will display the backend's validated explanation without a separate frontend app or new route.

The trained model is currently used as a constrained explainer, while deterministic ranking controls outfit selection. This division is intentional: the small scratch model cannot invent items or override the wardrobe, occasion, or weather guardrails. Rule-based fallback remains active if its output is invalid. The training loss and validation loss are language-model metrics, not evidence of strong fashion reasoning.

## Existing Qwen LoRA workflow

> **For the stylist model the app uses, follow `Capstone_Agents/training/HYBRID_STYLIST.md`** (Colab T4: compatibility notebook, then `AURA_Stylist_LLM_LoRA_Colab.ipynb`). The CSV-based workflow below is the older general-purpose route. Local Apple Silicon (MLX) LoRA attempts on the 8 GB development Mac diverged to NaN loss; see `training/results/mlx_training_trial_summary.json` and the project report.

The repository contains no authorized fashion conversation dataset, so training is intentionally a user-provided workflow. Start with the blank [CSV header template](Capstone_Agents/training/dataset_template.csv), add human-authored rows, and convert them with `python -m training.convert_dataset_csv /path/to/responses.csv --output training/data/raw.jsonl`. Required fields are `participant_id` (pseudonymous, never a name/email), `instruction`, `response`, `source`, and `license`. The split is participant-disjoint to avoid placing one participant in both training and test. Do not put private or unlicensed records in Git. Keep raw data, prepared splits, checkpoints, and evaluation output outside application source control.

```bash
python -m pip install -r training/requirements.txt
python -m training.prepare_dataset /path/to/licensed_records.jsonl --output training/data/prepared
python -m training.finetune --data training/data/prepared --output training/checkpoints/aura-lora
python -m training.evaluate --base Qwen/Qwen2.5-1.5B-Instruct --adapter training/checkpoints/aura-lora/adapter --output training/checkpoints/aura-lora/comparison
python -m training.make_blind_human_eval training/checkpoints/aura-lora/comparison/generations.jsonl
```

The ready-to-upload notebook is [AURA_LoRA_Colab.ipynb](Capstone_Agents/training/AURA_LoRA_Colab.ipynb). The fine-tuner uses Qwen's chat template and calculates loss on the response tokens, with gradient checkpointing and resumable Trainer checkpoints. It saves a PEFT LoRA adapter and base-model reference; it does not retrain the foundation model from scratch. It requires 12 GiB system RAM and 12 GiB GPU VRAM by default; `--allow-low-memory` is an explicit risky override. Local CPU training can be very slow. Evaluation compares base and adapter held-out loss and deterministic generations; it writes local/private outputs under the ignored checkpoint directory. Have raters judge the randomized `human-ratings.csv` for factual wardrobe grounding, helpfulness, clarity, and invented items, without showing them the separately written blind key. After installing the upstream llama.cpp conversion tools, merge/export and convert the resulting model:

```bash
python -c 'from peft import PeftModel; from transformers import AutoModelForCausalLM, AutoTokenizer; b="Qwen/Qwen2.5-1.5B-Instruct"; a="training/checkpoints/aura-lora/adapter"; m=PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(b),a).merge_and_unload(); m.save_pretrained("training/checkpoints/aura-merged",safe_serialization=True); AutoTokenizer.from_pretrained(b).save_pretrained("training/checkpoints/aura-merged")'
python /path/to/llama.cpp/convert_hf_to_gguf.py training/checkpoints/aura-merged --outfile training/checkpoints/aura-f16.gguf --outtype f16
/path/to/llama.cpp/build/bin/llama-quantize training/checkpoints/aura-f16.gguf model_artifacts/llm/aura-finetuned-q4_k_m.gguf Q4_K_M
```

Point `AURA_LLM_MODEL_PATH` at the resulting GGUF. GPU RAM or Apple Metal build compatibility may constrain local fine-tuning; the pipeline can instead run on a suitable training host. No metrics are asserted until you actually run evaluation. The evaluation command records held-out metrics in its output file; it does not create a performance claim in the repository.

## Behavior and limitations

- `/recommend` is ranked by deterministic rules over the authenticated user's available wardrobe. If the fine-tuned stylist is installed and enabled, it may move one of the top five options to #1 (by option number only). When the scratch model directory exists, it explains each outfit from the selected garments, occasion, weather and saved preferences only; a strict parser requires the exact selected ID list and the keys `item_ids` and `explanation`, and invalid output falls back to the evidence-grounded rule explanation. Check the response's `agent_trace` and each recommendation's `explanation_source`.
- `/chat/messages` uses local generation: the fine-tuned stylist when installed, otherwise base Qwen. Missing/broken model files produce an actionable 503; generation errors are not hidden by a deterministic or hosted fallback.
- Each recommendation response is recorded as a ranked API slate, and feedback IDs are checked against that user's exact recommendation before accepting a judgement.
- Private wardrobe, preference, upload, recommendation, and feedback APIs require a valid owner session; uploaded wardrobe images use short-lived signed URLs and are checked against their owning database row.
- A real local CPU inference smoke check on the MacBook Neo loaded the downloaded GGUF and answered a fashion prompt in about 6 seconds (96 token cap), with about 1.8 GiB peak process RSS and no swap. This is one prompt, not a benchmark or quality claim. A real authenticated recommendation request also returned a local LLM explanation whose candidate IDs remained a subset of that account's wardrobe.
- Legacy agent modules share the same local `call_llm` adapter.
- Trend refresh no longer invokes hosted search or generation. It returns historical cache data marked stale, or an empty, clearly unavailable result; OpenWeather remains an unrelated optional third-party service.
- Small 1.5B models may produce weaker fashion reasoning and structured JSON than hosted larger models. Validate ownership constraints in application logic, not only through prompting.

## Verification

Small tests mock the llama.cpp binding and require no model download:

```bash
cd Capstone_Agents
python -m pytest -q
```

After real users have supplied explicit save/like/wear/skip/dislike/rating feedback, compute descriptive judged-slate metrics from the database:

```bash
python -m scripts.evaluate_feedback --output training/checkpoints/feedback-evaluation.json
```

The report includes judgement coverage, NDCG and hit rate where computable. Unjudged items are excluded from relevance judgments. These observational metrics are not a randomized comparison; collect adequate feedback before drawing conclusions.

Real local integration check after installing the runtime and weights:

```bash
python -c 'from services.local_llm import generate_response; print(generate_response("Suggest a concise outfit principle."))'
```

To check the HTTP endpoint without any external inference credentials, use the UI chat after configuring local weights. `/health` contains `llm.present` and `llm.loaded` fields. A missing model is expected to report unavailable; a successful inference requires actual local weights.
