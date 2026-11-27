# PROJECT_CONTEXT

**Audit revision 2.** Re-audited 2026-11-27 at commit `d07801c` on branch `main`.

- The first audit was at `c59a86a`.
- Four commits landed in between, adding about 8.9k lines across 79 files.
- I read the source directly, re-ran the backend tests and re-ran the TypeScript check.
- No application source was modified.

Each statement is marked **[Verified]** (seen in code or command output) or **[Assumption]** (inferred, not proven).

## What the product is

AURA is a personal wardrobe stylist built as a capstone project. The deadline in project memory was 2026-11-22, which has passed. **[Verified]**

Core flow:

1. Users upload photos of their clothes, or import them from a shop link.
2. A Keras CNN tags each garment's category and colour. If a person is wearing the garment in the photo, they are cut out of it.
3. A deterministic rule ranker builds complete outfits only from garments the user owns.

On top of the ranker:

- a **per-user contextual bandit** (Thompson sampling) re-ranks candidates once the user has given feedback;
- a Polyvore outfit-compatibility transformer contributes 15% of the score;
- a **fine-tuned Qwen2.5-1.5B LoRA "stylist"** GGUF may promote one of the top 5 options to #1, and it also picks the outfit for chat;
- **Qwen2.5-3B Instruct** now writes the chat replies (the default changed from 1.5B);
- a scratch-trained 5.24M-parameter GPT explainer is still optional and still not installed.

Other features:

- **My Virtual Look:** body-photo analysis with MediaPipe, plus diffusion try-on with CatVTON on Stable Diffusion 1.5 inpainting.
- **Donations:** lists clothes that have never been worn, with a CSV export.
- **Peer-to-peer marketplace:** listings with photos, an order state machine, and buyer–seller chat over WebSockets.
- **Social feed.** **[Verified]**

No hosted LLM is used. Outbound network calls:

- OpenWeather;
- **arbitrary user-supplied shop URLs** (`services/product_link_service.py`);
- model downloaders (`training/download_*.py`). **[Verified]**

## What changed since the previous audit (c59a86a → d07801c)

| Commit | Summary |
|---|---|
| `35b5cd5` | Contextual-bandit ranking, stylist-picked chat outfits, 3B chat model |
| `c07be7e` | Project report update |
| `80eb259` | Occasion-aware ranking table, My Virtual Look try-on |
| `d07801c` | Weather/season-aware outfits, donations, shop-link import, marketplace with live chat, try-on fixes |

New backend modules:

- `services/bandit_ranker.py`
- `services/tryon_service.py`
- `services/body_analysis.py` (556 LOC)
- `ml/catvton.py`
- `services/garment_cutout.py`
- `services/marketplace_service.py`
- `services/realtime.py`
- `services/product_link_service.py`
- `services/donation_service.py`
- `services/season_classifier.py`
- `training/download_tryon_models.py`
- `training/evaluate_bandit.py`

New frontend screens: VirtualLook, SellItem, Conversation, Messages, MyOrders and Donate. There is also a realtime client (`src/services/realtime.ts`, `hooks/useRealtime.ts`). **[Verified: `git diff --stat`]**

`main.py` grew to about 1,030 LOC and now has around 60 routes, including one WebSocket route. **[Verified]**

## Repository layout

```
Captstone-main/
├── README.md, PROJECT_REPORT.md         Setup guide, architecture claims, capstone report
├── Capstone_Agents/                      FastAPI backend + ML (Python 3.11)
│   ├── main.py               (~1.0k LOC) All HTTP + WebSocket routes, auth dependency, lifespan
│   ├── settings.py                       Env-driven frozen dataclass config (now incl. bandit, try-on)
│   ├── database.py                       SQLite schema + ad-hoc migrations (try-on tables live in tryon_service)
│   ├── contracts/api_schemas.py          Pydantic request/response models (live)
│   ├── services/                         Business logic (≈5.5k LOC): app_service (auth/social/chat),
│   │                                      marketplace_service, realtime, wardrobe, recommendation,
│   │                                      bandit_ranker, explainer, LLM adapters, vision, try-on,
│   │                                      body_analysis, garment_cutout, product_link, donation
│   ├── ml/                               Prompt contracts, outfit-compat model, CatVTON wrapper
│   ├── agents/, orchestrator/            Legacy LangGraph pipeline: still NOT reachable from main.py
│   ├── tools/                            weather_tool (live); llm_client, save_user_feedback (legacy)
│   ├── ui/app.py                         Still an empty file
│   ├── scripts/, training/               Offline evaluation, Colab notebooks, model downloaders
│   ├── tests/                            106 test functions → 133 collected
│   └── model_artifacts/                  CNN, SHIFT15M, outfit_compat, bandit eval in Git; GGUFs + tryon/ ignored
├── Capstone-App/                         Expo SDK 57 / React Native 0.86 / React 19 client
└── _design-snapshots/, aura_colab_training_bundle.zip, _backup_*.tar.gz, empty root package-lock.json
```

## How to run

| Component | Command | Entry point |
|---|---|---|
| Backend | `python -m uvicorn main:app --port 8000` (run from `Capstone_Agents/`) | `main.py` `app = FastAPI(...)` |
| Must be one process | WebSocket presence and the try-on queue live in process memory (`services/realtime.py:8-9`, `tryon_service.py:285`) | **Do not run more than one uvicorn worker** |
| Frontend | `npx expo start --web` (from `Capstone-App/`) | `index.ts` → `App.tsx` |
| Optional models | `python -m training.download_stylist_model`, `python -m training.download_model` (3B default, `1.5b` arg for lighter), `python -m training.download_tryon_models` | |
| Tests | `python -m pytest -q` (from `Capstone_Agents/`) | `tests/conftest.py` sets a temp DB and upload dir |

## Current health snapshot

| Check | Previous (`c59a86a`) | Now (`d07801c`) |
|---|---|---|
| Backend tests | 58 passed | **127 passed, 6 failed**. All 6 failures are in `tests/test_virtual_tryon.py`, which raises `ModuleNotFoundError: No module named 'cv2'` because the local venv lacks the try-on extras (`mediapipe`, `diffusers`). The tests do not skip when those are absent **[Verified]** |
| Frontend type check | exit 0 | exit 0 **[Verified]** |
| Frontend tests | none | none **[Verified]** |
| Lint / CI | none | none **[Verified]** |
| Logging configured | no | **still no** (no `basicConfig` / `dictConfig`) **[Verified]** |
| Local `.env` | signing key empty, origins `*` | unchanged **[Verified, values not printed]** |
| Installed models | stylist + Qwen 1.5B | unchanged. The new default chat model (Qwen 3B) and `model_artifacts/tryon/` are **not installed**. The local `.env` still points chat at 1.5B **[Verified]** |

## Domain vocabulary

Terms carried over from the previous revision:

- **Base / core**: one Dress, or one Top plus one Bottom.
- **Candidate**: a base plus optional add-ons.
- **Critic**: the rule check that rejects unowned or incomplete outfits.
- **Slate / run**: the persisted output of one recommendation call.
- **Stylist**: the fine-tuned Qwen 1.5B LoRA.
- **Scratch GPT**: the optional 5.24M-parameter explainer.

New terms:

- **Bandit / personalised policy**: per-user Bayesian linear model over 61 features (12 rule signals, 8 style descriptors × 5, 1 visual-taste feature). Stored as JSON in `bandit_models`. Rewards: wear 1.0, save 0.9, like 0.85, skip 0.35, dislike 0.0.
- **Target season**: Summer, Mild or Winter, derived from temperature. **Season label**: Summer, Winter or All-season per item.
- **Avatar**: the user's own full-body photo on a plain backdrop, plus a parsing map, landmarks and a body-proportion analysis.
- **Render / look**: a queued CatVTON try-on job (`tryon_renders`), cached per avatar + items + render settings.
- **Listing / order / conversation**: marketplace entities. Order states are `pending → shipped → completed`, or `cancelled`. Payment is cash on delivery or UPI, arranged **off-app**.

## Model evaluation numbers (from committed artifacts, not re-run)

- **Stylist pick accuracy:** fine-tuned 0.837, base Qwen zero-shot 0.39, compatibility-only 0.53, random 0.20. Source: `model_artifacts/stylist_llm_evaluation.json`.
- **Outfit-compat transformer:** AUC 0.865, FITB 0.52. Source: `model_artifacts/outfit_compat/evaluation.json`.
- **Bandit:** evaluated on **simulated users** (`model_artifacts/bandit_evaluation.json`, `training/evaluate_bandit.py`). That is not evidence about real users. **[Verified source; numbers not re-run]**

## Related documents

- `ARCHITECTURE.md`: components, boundaries and traced workflows, updated for the new features.
- `KNOWN_ISSUES.md`: findings, with the status of each earlier finding.
- `ENGINEERING_PLAN.md`: re-prioritised remediation plan.
