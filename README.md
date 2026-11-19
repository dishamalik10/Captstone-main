# AURA: local language generation for a wardrobe stylist

AURA is an existing Expo / React Native application backed by FastAPI. Garment recognition uses the existing local Keras model. Outfit items are selected and ranked by deterministic rules over the authenticated user's available wardrobe. The scratch-trained AURA fashion GPT can explain those fixed recommendations after its Colab checkpoint is installed locally; it cannot choose or change item IDs. Existing stylist chat and legacy prompt-agent modules retain their separate local GGUF model service. No hosted LLM inference API is used.

## Architecture and model roles

```text
Expo app → FastAPI → authenticated wardrobe + deterministic outfit ranking
                  ├→ optional scratch-trained AURA GPT → validated explanation only
                  ├→ existing local llama.cpp GGUF → stylist chat/legacy agents
                  ├→ SQLite, auth, uploads
                  └→ optional OpenWeather context (non-LLM API)
```

1. **Scratch fashion model:** a GPT-style decoder with 4 layers, 256 hidden units, 4 attention heads, and an 8,000-token vocabulary. The training notebook loads the supplied random-initialized weights locally and does not download a pretrained base. It is not included in this repository and is not claimed as trained until you run the notebook.
2. **Existing chat model:** the separately configured Qwen2.5-1.5B GGUF remains for chat and legacy agents. It is not used as the scratch fashion model or as a substitute when a configured scratch checkpoint fails validation.
3. **Training data:** the scratch workflow uses the existing Google Drive fashion knowledge and instruction JSONL files only. No copy is included here and no data is generated. The existing Qwen LoRA workflow remains available as a separate, preserved workflow.
4. **Recommendation inference:** the deterministic ranker and critic choose only available wardrobe rows from SQLite. When the scratch checkpoint exists and validates, AURA uses it to explain the chosen items. Its JSON must preserve the exact ranked item IDs; otherwise the backend keeps its evidence-grounded rule explanation.
5. **Retrieval:** stylist prompts retrieve matching entries from the local heuristic reference JSON. This is prompt-time grounding, not training data. The trend cache remains optional and separate.

## Hardware

The development host is an Apple Silicon MacBook Neo with A18 Pro and 8 GiB unified RAM. Qwen 1.5B Q4_K_M is selected as a small local model (about 1.12 GB weights plus runtime/context overhead). On this host, the installed `llama-cpp-python` 0.3.36 supports Metal offload (tensor API disabled). A local two-sample benchmark with 4 threads, 4096 context, the same prompt and 96-token cap measured 23.85 tokens/s CPU versus 35.35 tokens/s with all layers offloaded to Metal; model load was 2.83s versus 1.51s. Peak process RSS was 1.67 GiB versus 1.11 GiB. These are short local measurements, not broad performance guarantees; unified GPU memory is shared with system RAM. Metal is the default on the target setup (`AURA_LLM_GPU_LAYERS=-1`); set it to `0` for CPU. The base model is downloaded separately, not committed.

The repository also includes a small local retrieval file at `Capstone_Agents/knowledge/fashion_heuristics.json`. It is original, explicitly heuristic guidance written for this capstone, labeled CC BY 4.0; it is not empirical research, trend reporting, external source material, or training data. Retrieval adds relevant notes to local stylist prompts. The server's deterministic compatibility engine still owns outfit selection and ranking. Vision returns the trained model's color group plus a separate median RGB sample from the image center; the sample is explicitly approximate because no garment segmentation or lighting correction is performed.

## Backend setup

Use Python 3.11. From `Capstone_Agents`:

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
# macOS Metal build (optional acceleration):
CMAKE_ARGS="-DGGML_METAL=on" python -m pip install -r requirements-local.txt
# CPU-only alternative:
python -m pip install -r requirements-local.txt
cp .env.example .env                  # Windows: copy .env.example .env
```

Set `AURA_LLM_MODEL_PATH` to a GGUF path and perform a one-time authorized download:

```bash
python -m training.download_model
```

The script fetches `Qwen/Qwen2.5-1.5B-Instruct-GGUF` Q4_K_M. To use an already obtained file, copy it to the configured model path instead. The FastAPI service will start if the file is absent so non-chat routes remain usable; `/health` reports status and chat returns HTTP 503 with a clear local-model error. It will not download weights at startup. When weights exist, startup loads the model once and shutdown releases it.

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/docs`. The existing frontend runs from `Capstone-App` with `npm install` and `npx expo start --web`; its API URL remains configurable as `EXPO_PUBLIC_API_URL`.

## Environment

See `Capstone_Agents/.env.example`. Main local model settings:

| Setting | Default | Purpose |
|---|---|---|
| `AURA_LLM_MODEL_PATH` | `model_artifacts/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf` | Local GGUF weights |
| `AURA_FASHION_LM_PATH` | `model_artifacts/aura_fashion_gpt_final` | Optional scratch-trained AURA fashion GPT directory |
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

- `/recommend` is ranked by deterministic rules over the authenticated user's available wardrobe. When the scratch model directory exists, the AURA scratch GPT receives the real available wardrobe, saved style preferences, weather, occasion, and fixed candidates to write constrained explanations. A strict parser requires the exact selected ID list and expected JSON keys; invalid output falls back to the evidence-grounded rule explanation. It cannot select or add item IDs. The Qwen GGUF remains for chat/legacy agents and is not substituted when a configured scratch model fails. Check `/models/fashion-language/status` and the response's explanation source.
- `/chat/messages` uses local generation. Missing/broken model files produce an actionable 503; generation errors are not hidden by a deterministic or hosted fallback.
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
