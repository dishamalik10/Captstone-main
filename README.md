# AURA: a personalised, local AI wardrobe stylist

AURA is an Expo / React Native app backed by FastAPI. It recognises uploaded garments with a trained CNN, builds complete outfits only from the user's own wardrobe, ranks them with a **per-user contextual bandit that learns from feedback**, lets a **fine-tuned stylist LLM** pick the best option, and chats about it through a local instruction model. Everything runs on the machine; no hosted LLM API is used.

## Architecture and model roles

```text
Expo app → FastAPI
  upload  → Garment CNN (EfficientNetV2B0, H&M) → category, colour, 512-d embedding
  outfits → candidate generator (every dress / top+bottom, plus layers, shoes, accessories)
          → scoring: rule signals + outfit-compatibility transformer (Polyvore)
          → critic (owned, complete, occasion/weather sanity) → diversity rerank
          → PERSONALISED RANKING: contextual bandit (Thompson sampling) per user
          → fine-tuned stylist GGUF (Qwen2.5-1.5B + LoRA) picks #1 of the top 5
  chat    → occasion from the message → same pipeline → stylist picks the outfit
          → the same stylist writes the reply (Qwen2.5-3B with AURA_CHAT_USE_STYLIST=0); the app shows every piece's photo
  feedback (like / dislike / save / wear / skip) → updates that user's bandit instantly
  try-on  → full-body photo → MediaPipe pose + body segmentation → avatar (your own photo
            on a plain backdrop) + approximate proportions → Stylist outfit → garment
            cut-out (ISNet) → CatVTON diffusion try-on, one garment layer at a time
```

| Component | What it does | Trained by this project? |
|---|---|---|
| **Garment CNN** (`fashion_cnn_final.keras`) | Category, type and colour of an uploaded photo, plus a visual embedding | Yes — H&M images, ~80% product-type validation accuracy |
| **Outfit-compatibility transformer** (`model_artifacts/outfit_compat/`) | Scores how well an outfit's pieces go together from their CNN embeddings (15% of the prior score) | Yes — Polyvore Outfits, compatibility AUC 0.865 |
| **SHIFT15M compatibility model** | Category-level fallback if the transformer is unavailable | Yes — SHIFT15M, ROC-AUC 0.775 |
| **Contextual bandit** (`services/bandit_ranker.py`) | Personalised ranking learned online from each user's reactions | Yes — learns per user at run time (no offline training step) |
| **Fine-tuned stylist** (`aura-stylist-q4_k_m.gguf`) | Picks one of the top 5 outfits on the Stylist screen and in chat, with a reason | Yes — LoRA on Qwen2.5-1.5B, 84% vs 39% base on held-out Polyvore choice |
| **Qwen2.5-3B Instruct** (`qwen2.5-3b-instruct-q4_k_m.gguf`) | Optional (`AURA_CHAT_USE_STYLIST=0`): writes chat replies instead of the stylist; needs ~2.1 GB more memory | No — open model used as downloaded |
| **Scratch AURA GPT** (`aura_fashion_gpt_final/`) | Optional per-outfit explanation on the Stylist screen | Architecture and Colab notebook only; weights are not in the repository |
| **MediaPipe Pose Landmarker + Selfie Multiclass** | Body landmarks and hair/skin/clothes segmentation for the avatar, proportions and try-on masks | No — Google models (Apache 2.0) |
| **ISNet** (`isnet-general-use.onnx`) | Cuts garments out of flat-lay photos before try-on | No — rembg release (MIT) |
| **CatVTON** (`dresscode-16k-512` on SD 1.5 inpainting) | Renders a wardrobe garment onto the user's photo | No — Chong et al., ICLR 2025 (CC BY-NC-SA 4.0, non-commercial); compact re-implementation in `ml/catvton.py` |

Rules that hold regardless of model:

1. **Only owned, complete outfits are ever shown.** The candidate generator and critic build every option from the authenticated user's available garments; neither the bandit nor any LLM can add, remove or swap garments. The stylist chooses by option number and never sees database IDs.
2. **Cold start equals the original ranker.** The bandit's prior reproduces the hand-tuned weights exactly, so a user with no feedback sees the same order as before; personalisation starts with their first reaction.
3. **Chat is grounded in the wardrobe.** The chat model receives the full owned wardrobe and the chosen outfit, recommends that outfit (its photos are shown under the reply), may suggest optional finishing touches only as "if you have…", and must say it has no live trend data. Outfits already shown in a chat are not repeated while fresh options remain.
4. **Training/inference parity.** The stylist's prompt format lives in `Capstone_Agents/ml/stylist_prompt.py` (and the scratch GPT's in `ml/explain_prompt.py`); the notebooks embed these files byte-for-byte and a test enforces it.
5. **Status endpoints:** `/health`, `/models/stylist/status` (picking + chat source), `/models/personalisation/status` (what the signed-in user's bandit has learned) and `/models/fashion-language/status`.
6. **Adding clothes (photo or shop link):** the app first asks for a preview (`POST /wardrobe/upload/preview`, `POST /wardrobe/import-link/preview`). For a shop link, the first product photo with no person in it is used. If someone is wearing the garment, SegFormer-B2 Clothes (`python -m training.download_tryon_models --only segformer_b2_clothes`, ~110 MB) cuts out each kind of garment, and the user confirms the piece and its category (`POST /wardrobe/imports/{id}/confirm`). The user's category wins over the CNN's, and a disagreement flags the item for review. Unconfirmed previews are deleted after an hour.

**Training data.** CNN: H&M product images. Compatibility transformer and stylist LoRA: Polyvore Outfits (Vasileva et al., ECCV 2018, CC BY 4.0). SHIFT15M: 50,000 temporally split outfits. See `Capstone_Agents/training/HYBRID_STYLIST.md` and `PROJECT_REPORT.md`.

**Retrieval.** Chat prompts include matching entries from the local heuristic reference JSON. This is prompt-time grounding, not training data.

## Personalised ranking (contextual bandit)

Outfit ranking is framed as a contextual bandit, the reinforcement-learning setting used by most recommender systems:

| RL term | In AURA |
|---|---|
| Context | Occasion, weather and each candidate outfit's features |
| Action | Which outfit to put first |
| Reward | The user's reaction: wear 1.0, save 0.9, like 0.85, rating (r−1)/4, skip 0.35, dislike 0 |
| Policy | Bayesian linear regression `reward ≈ w·x` with Thompson sampling |

Features (53): the 12 ranker signals (colour, occasion, weather, preferences, feedback, learned preference, novelty, trend, pattern, silhouette, fabric, learned compatibility); 8 style descriptors (dress, layered, dark / light / colourful share, patterned share, piece count, footwear) once globally and once per occasion group (formal, evening, casual, active), so "dark looks for dates" is learned separately from "light looks for the office"; and a visual-taste feature, the similarity of the outfit's CNN embeddings to what the user liked minus what they disliked.

The prior mean is the hand-tuned weighting (85% rule signals, 15% compatibility) with high prior precision on those signals and low precision on the personal style features, so the model starts from the original ranker and learns personal taste quickly. Each reaction (`POST /feedback`, the chat card's Like / Not for me / Wore it buttons, or the Stylist screen's swipes) updates that user's posterior in `bandit_models`; nothing is shared between users. The `/recommend` trace reports `contextual_bandit_thompson_sampling_then_diversity_rerank` once a user's model is active.

**Evaluation with simulated users** (`python -m training.evaluate_bandit`, about 10 s; writes `model_artifacts/bandit_evaluation.json` and `bandit_learning_curve.svg`). Four hidden tastes × 15 users × 40 rounds, synthetic wardrobes, every outfit ranked each round as in the app, real candidate generator and rule scorers:

| Policy | P(user likes the top outfit), last 10 rounds | Cumulative regret |
|---|---:|---:|
| Hand-tuned ranker (before) | 0.56 | 9.01 |
| Bandit, greedy (no exploration) | 0.71 | 3.91 |
| **Bandit + Thompson sampling (used)** | **0.70** | 5.11 |
| Best possible | 0.78 | 0 |

Learning from feedback adds about 14 percentage points over the fixed ranker. In this simulation greedy is slightly ahead of Thompson sampling, because each round's occasion already varies the context and the simulated tastes are linear in the features; the exploration scale (0.5) was chosen on this simulation. These are simulated users with a stand-in compatibility score: they show the learning mechanism works, not real-user satisfaction. `scripts/evaluate_feedback` computes metrics on real feedback once it exists.

## Hardware

**Public host:** the project owner's 16 GB Apple Silicon Mac, with every feature on. **Minimum for development and testing:** an 8 GB Mac, using the default settings (try-on off). See "Which settings for my Mac?" in the setup guide. The rest of this section was measured earlier on an 8 GiB Apple Silicon MacBook Neo (A18 Pro).

That earlier host: The chat model is Qwen2.5-3B Instruct Q4_K_M (about 2.1 GB); with the fine-tuned stylist (about 1 GB) also loaded, a chat reply takes roughly 9–17 seconds on this host and macOS swap use was high (about 5 GB of 6 GB) during testing. On machines with 8 GB or less, the 1.5B chat model (`python -m training.download_model 1.5b`) is the lighter option. The measurements below were taken earlier for Qwen 1.5B Q4_K_M, selected then as a small local model (about 1.12 GB weights plus runtime/context overhead). On this host, the installed `llama-cpp-python` 0.3.36 supports Metal offload (tensor API disabled). A local two-sample benchmark with 4 threads, 4096 context, the same prompt and 96-token cap measured 23.85 tokens/s CPU versus 35.35 tokens/s with all layers offloaded to Metal; model load was 2.83s versus 1.51s. Peak process RSS was 1.67 GiB versus 1.11 GiB. These are short local measurements, not broad performance guarantees; unified GPU memory is shared with system RAM. Metal is the default on the target setup (`AURA_LLM_GPU_LAYERS=-1`); set it to `0` for CPU. The base model is downloaded separately, not committed.

The repository also includes a small local retrieval file at `Capstone_Agents/knowledge/fashion_heuristics.json`. It is original, explicitly heuristic guidance written for this capstone, labeled CC BY 4.0; it is not empirical research, trend reporting, external source material, or training data. Retrieval adds relevant notes to local stylist prompts. The server's deterministic compatibility engine still owns outfit selection and ranking. Vision returns the trained model's color group plus a separate median RGB sample from the image center; the sample is explicitly approximate because no garment segmentation or lighting correction is performed.

## Setup guide (from a fresh clone)

Follow these steps in order to run the full app (backend, models and Expo frontend) on a new machine. Training is **not** needed: every trained model is either in Git or downloadable.

### 1. Prerequisites

- **Python 3.11**, **Node.js (LTS)** and **git**.
- **8 GB RAM minimum** (every feature except virtual try-on); **16 GB** to run try-on comfortably. On Apple Silicon, Metal speeds up the language models. Read "Which settings for my Mac?" below before starting the server.

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

#### Which settings for my Mac?

> **Everyone cloning this repo, please read this.** `.env.example`, and the code's defaults, use the **8 GB tester** settings. Only the public host changes them.

| Your Mac | Put in `Capstone_Agents/.env` | What you get |
|---|---|---|
| **8 GB** (teammates, testing) | `AURA_TRYON_ENABLED=0`<br>`AURA_PRELOAD_VISION=0`<br>(already in `.env.example`) | Everything works except virtual try-on. My Virtual Look says "Try-on is turned off on this server". The first wardrobe upload after a start takes a few seconds longer while the garment model loads. |
| **16 GB** (the public host) | `AURA_TRYON_ENABLED=1`<br>`AURA_PRELOAD_VISION=1` | Every feature, including try-on. |

- **Why try-on is off on 8 GB:** a render needs about 6 GB (try-on worker plus API). With macOS, a browser and the Expo simulator, an 8 GB Mac swaps heavily, and renders become very slow. The team decided a slow, poor result is worse than a clear "off".
- **Testing try-on on an 8 GB Mac anyway:** download the try-on models (step 3), set `AURA_TRYON_ENABLED=1`, close other apps, and restart. Nobody has measured this on 8 GB yet, so please share what you see.
- **Testers:** follow [`TESTING_8GB.md`](TESTING_8GB.md) (feature checks, memory under load, what to send back). `python -m scripts.machine_check` (in `Capstone_Agents/`) shows which profile your settings match and warns if they don't suit your RAM; add `--server` while the server runs to include its memory use.
- **Releasing** (APK and web app): see [`RELEASE.md`](RELEASE.md).
- If the try-on models are installed but try-on is off, the server prints a warning at startup saying so.

### 3. Get the models

| Model | Role in the app | How to get it |
|---|---|---|
| Garment CNN (`fashion_cnn_final.keras`) | Recognises category and colour of uploaded clothes | Already in Git |
| SHIFT15M compatibility model | Legacy pairwise compatibility | Already in Git |
| Outfit-compatibility transformer (`model_artifacts/outfit_compat/`) | Scores how well the pieces of an outfit go together | Already in Git |
| Fine-tuned stylist GGUF (`aura-stylist-q4_k_m.gguf`, ~1 GB) | Picks the #1 outfit on the Stylist screen and in chat | `python -m training.download_stylist_model` (GitHub Release, SHA-256 verified) |
| Qwen2.5-3B Instruct GGUF (~2.1 GB) | Writes chat replies | `python -m training.download_model` (Hugging Face; `… download_model 1.5b` for the lighter 1.5B) |
| Scratch AURA GPT (`model_artifacts/aura_fashion_gpt_final/`) | Optional per-outfit explanations | Train with `training/AURA_Scratch_Fashion_LM_Colab.ipynb` and copy the folder in |
| Try-on models (~2.4 GB: SD 1.5 inpainting UNet fp16, VAE, CatVTON weights, MediaPipe, ISNet) | My Virtual Look: avatar, body analysis and virtual try-on | `python -m training.download_tryon_models` (resumable, 8 parallel connections) |

From `Capstone_Agents` with the virtual environment active:

```bash
python -m training.download_stylist_model   # fine-tuned stylist, from the stylist-llm-v1 release
python -m training.download_model           # Qwen2.5-3B chat model
python -m training.download_tryon_models    # My Virtual Look (optional)
```

Both GGUFs land in `model_artifacts/llm/`, which is git-ignored. If you prefer a browser, download `aura-stylist-q4_k_m.gguf` from the repository's **Releases** page (tag `stylist-llm-v1`) and place it at `Capstone_Agents/model_artifacts/llm/aura-stylist-q4_k_m.gguf`.

Every model is optional at startup: a missing one disables only its own role and the app falls back safely (for example, the ranker's order is kept when the stylist is absent). The server never downloads weights on its own.

### 4. Start the backend

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

This one command also starts the try-on worker (a separate process, `services/tryon_worker.py`) when the try-on models are installed, and stops it on shutdown; its log is `logs/tryon-worker.log`. Do not add `--reload` when other people use the app: it restarts the server (and reloads every model) on each file save. `AURA_MEDIA_SIGNING_KEY` must be set in `Capstone_Agents/.env` or the server refuses to start (see `.env.example`). Routine logs go to `Capstone_Agents/logs/aura.log`; the terminal shows only warnings and errors.

Check it:

- `http://127.0.0.1:8000/health`: which models are present and loaded, and memory use. The details are shown only when called on the server machine itself; from anywhere else (including through the Cloudflare tunnel) it returns just `{"status": "ok"}`.
- `http://127.0.0.1:8000/models/stylist/status`: should report `"source": "fine_tuned_stylist"` (outfit picking) and `"chat": "fine_tuned_stylist"` (the stylist also writes replies; `base_chat_model` with `AURA_CHAT_USE_STYLIST=0`).
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
4. **AI Stylist** (`/recommend`): the ranker builds complete outfits from your own clothes, the outfit-compatibility model and your personal bandit score them, the fine-tuned stylist picks #1 and explains why. Each card shows every piece together. The response's `agent_trace` shows which model did what.
5. **Chat** (`/chat/messages`): ask for an outfit for an occasion ("outfit for a date", "kal office ke liye kya pehnu?") or any styling question. The stylist picks the outfit and writes the reply, and the card shows all pieces.
6. **React** with Like / Not for me / Wore it under a chat outfit (or swipe on the Stylist screen). Your ranking adapts immediately; `/models/personalisation/status` shows what it has learned.
7. **My Virtual Look** (Profile → My virtual look, or **Try it on me** under a Stylist outfit): upload one full-body photo (`POST /avatar`). AURA frames your own photo as your avatar and estimates approximate proportions (shoulder:hip, waist:hip, torso:leg), a body-shape label and skin depth, which you can copy into your style profile. Each Stylist outfit is then rendered on the avatar (`POST /tryon`, polled at `GET /tryon/{id}`): bottom, then top, then outer layer, or a dress as one garment. Renders are cached per avatar and outfit; **Save look** stores it and counts as a "save" for your ranking. An optional side photo renders the same outfits side-on. `DELETE /avatar` removes your photos, measurements, height and every look.
8. **Sizes and fit** (ENGINEERING_PLAN 4.11):
   - **Body measurements** (My Virtual Look → Body measurements):
     - Enter your height, then add a side photo (`POST /body/measurements/estimate`). AURA measures your front avatar and the side photo, scales both by your height, and estimates chest, waist and hip (width and depth as an ellipse), plus shoulder width, inseam and arm length.
     - The side photo is never stored.
     - Loose clothing, arms against the body or a front-facing "side" photo give no estimate, with the reason, rather than a bad one.
     - You can type or correct any value (`PUT /body/measurements`). Typed values always win.
     - Estimates are shown as ranges until the volunteer tape-measure check (`training/MEASUREMENT_ACCURACY_PROTOCOL.md`, `scripts/measurement_accuracy.py`) shows a zone is within ±4 cm.
   - **Garment sizes:** add the size label (M, UK 12, EU 50, 32/32…) and optionally flat measurements on the item screen, or when adding the item. Link imports fill the size when the shop page names exactly one.
   - **Size advice** (`GET /wardrobe/{user}/{item}/fit`, `GET /marketplace/products/{id}/fit`):
     - Chest, waist and hip are rated tight / snug / regular / relaxed / loose against a generic size chart or the garment's measurements, with your fit preference. Length is rated too when known.
     - It is shown on the item screen, on other people's listings (for you only), and per piece in My Virtual Look.
     - It is marked "estimated" when it relies on photos, the generic chart or your usual size. It never changes recommendations.
   - **Try-on fit:** a garment's length (measured, or words like crop, kurta, shorts, midi, maxi) moves the hem in the try-on mask. Garments with no size information render exactly as before. Widening the mask for roomier sizes exists but is off (`AURA_TRYON_FIT_WIDEN=0`): in the first render check it produced a flat bar at the hips rather than looser fabric.

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
| `AURA_LLM_MODEL_PATH` | `model_artifacts/llm/qwen2.5-3b-instruct-q4_k_m.gguf` | Chat model GGUF weights |
| `AURA_FASHION_LM_PATH` | `model_artifacts/aura_fashion_gpt_final` | Optional scratch-trained AURA fashion GPT directory |
| `AURA_STYLIST_LLM_PATH` | `model_artifacts/llm/aura-stylist-q4_k_m.gguf` | Fine-tuned stylist GGUF (~1 GB, not in Git; `python -m training.download_stylist_model`) |
| `AURA_STYLIST_LLM_ENABLED` | `1` | Let the fine-tuned stylist pick the #1 outfit (Stylist screen and chat); `0` falls back to the ranker order / chat model |
| `AURA_CHAT_USE_STYLIST` | `1` | The fine-tuned stylist also writes chat replies and the recommendation comparison, so one ~1 GB model is resident. `0` uses the base chat model (Qwen2.5-3B) for those instead; it writes more fluent replies but needs ~2.1 GB more memory |
| `AURA_BANDIT_ENABLED` | `1` | Personalised contextual-bandit ranking from feedback; `0` keeps the hand-tuned order |
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

- **My Virtual Look is a generated visual preview, not a fit simulation.** CatVTON repaints the garment area of your photo to show colour, print, sleeve length, neckline and overall silhouette. It has no 3D body or cloth physics. Garment size moves only the hem and width of the area it repaints, so use the size advice (not the picture) to judge fit; the app shows this disclaimer under every look. Fine prints (pinstripes, small logos) blur at the 512x384 render size; a closed jacket hides the top beneath it; shoes and accessories are not drawn; colours can drift slightly. The body-shape proportions are 2D estimates from one front photo (clothing, pose and camera angle shift them), reported as ratios with a confidence level. Measurements in cm need the side photo and your height too, are unvalidated estimates until the volunteer check, and are shown as ranges. On the 8 GB development Mac a render takes about 5 minutes for the first garment (model load and Metal warm-up) and about 1.5 minutes for each further garment; avatar creation takes under a second. Garment labels come from the CNN, so a mislabelled item (e.g. a skirt filed as shoes) is layered wrongly until it is corrected in the wardrobe.

- `/recommend` is ranked over the authenticated user's available wardrobe by the hand-tuned prior until the user gives feedback, then by their contextual bandit. If the fine-tuned stylist is installed and enabled, it may move one of the top five options to #1 (by option number only). When the scratch model directory exists, it explains each outfit from the selected garments, occasion, weather and saved preferences only; a strict parser requires the exact selected ID list and the keys `item_ids` and `explanation`, and invalid output falls back to the evidence-grounded rule explanation. Check the response's `agent_trace` and each recommendation's `explanation_source`.
- `/chat/messages`: for outfit requests the occasion is detected from English keywords (date, meeting, office, travel, party, wedding, …; otherwise "casual"), the fine-tuned stylist picks among the top 5 (falling back to the chat model, then the ranker), and the chat model (the stylist by default, Qwen2.5-3B with `AURA_CHAT_USE_STYLIST=0`) writes a free-form reply. Replies are not filtered sentence by sentence, but each one is checked for garments the user doesn't own, including owned types in an unowned colour (`services/chat_grounding.py`): such a reply is regenerated once, and if it still names one the deterministic reply is shown instead. Sentences phrased as an idea ("if you have…") or a gap ("you don't have a blazer") may mention other pieces. A reply that pairs a dress with separates is also regenerated once. `python -m scripts.evaluate_chat_grounding` measures the invented-piece rate on a fixed set of 20 prompts. Missing/broken model files produce an actionable 503; generation errors are not hidden by a deterministic or hosted fallback.
- Known chat limitations: the chat model can still stack owned pieces that don't go together (for example jeans with trousers) or recommend owned pieces other than the shown outfit — the grounding check covers unowned garments only; Hindi occasion words (for example "shaadi") are not detected; chat replies are in English; the stylist picker sees the occasion but not free-text wishes such as "bolder".
- Each recommendation response is recorded as a ranked API slate, and feedback IDs are checked against that user's exact recommendation before accepting a judgement.
- Private wardrobe, preference, upload, recommendation, and feedback APIs require a valid owner session; uploaded wardrobe images use short-lived signed URLs and are checked against their owning database row.
- A real local CPU inference smoke check on the MacBook Neo loaded the downloaded GGUF and answered a fashion prompt in about 6 seconds (96 token cap), with about 1.8 GiB peak process RSS and no swap. This is one prompt, not a benchmark or quality claim. A real authenticated recommendation request also returned a local LLM explanation whose candidate IDs remained a subset of that account's wardrobe.
- Legacy agent modules share the same local `call_llm` adapter.
- Trend refresh no longer invokes hosted search or generation. It returns historical cache data marked stale, or an empty, clearly unavailable result; OpenWeather remains an unrelated optional third-party service.
- Small local models (1.5B–3B) produce weaker fashion reasoning than hosted larger models. Ownership constraints are enforced in application logic, not only through prompting.

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

To check the HTTP endpoint without any external inference credentials, use the UI chat after configuring local weights. `/health` (called on the server machine) contains `llm.present` and `llm.loaded` fields. A missing model is expected to report unavailable; a successful inference requires actual local weights.
