# ARCHITECTURE

Audit revision 2, commit `d07801c`. This describes the code as it is, not the intended design. Each claim is tagged **[Verified]** (read in code) or **[Assumption]**.

## 1. System context

```
┌──────────────────────┐  HTTP + Bearer token   ┌───────────────────────────────────────────────────┐
│ Expo app (iOS/Android│ ─────────────────────▶ │ FastAPI, ONE uvicorn process (Capstone_Agents)    │
│ /web) Capstone-App   │ ◀───────────────────── │                                                   │
│                      │  JSON, signed images   │ in-process state:                                 │
│  realtime.ts ────────┼── WebSocket /ws ──────▶│   • ConnectionHub (presence, chat push)           │
└──────────────────────┘  (auth = first frame)  │   • try-on job queue + 1 worker thread            │
                                                │ storage: SQLite aura.db, local uploads/ dir       │
                                                │ models (all in this process):                     │
                                                │   TensorFlow: garment CNN, SHIFT15M, outfit-compat│
                                                │   llama.cpp: stylist 1.5B GGUF, chat 3B GGUF      │
                                                │   torch/diffusers: CatVTON (SD1.5 inpaint, ~GBs)  │
                                                │   MediaPipe/ONNX: body parsing, garment cutout    │
                                                │   torch/transformers: scratch GPT (optional)      │
                                                └──────┬───────────────────────┬────────────────────┘
                                                       │ requests              │ requests (user URLs)
                                                       ▼                       ▼
                                                 OpenWeather API        Arbitrary shop websites
```

- Everything still runs in **one Python process**: the API, the WebSocket hub, the try-on worker thread and every model. **[Verified]**
- Two subsystems are **hard-wired to a single process**. The WebSocket hub keeps its connection dict in memory (`services/realtime.py:25-37`, with a docstring saying so). The try-on worker uses an in-memory `queue.Queue` and one thread (`tryon_service.py:285-296`). **[Verified]**
- The only datastore is SQLite, with a new connection per query (`database.py:16-25`). **[Verified]**

## 2. Backend layering

```
main.py (≈60 routes + /ws; auth dependency; some SQL and shaping inline)
  ├─ app_service.py           auth, sessions, profile, social, chat orchestration
  ├─ marketplace_service.py   listings, photos, orders (state machine), conversations, unread
  ├─ realtime.py              ConnectionHub: connect/disconnect/push; chat_partners, members
  ├─ wardrobe_service.py      clothing CRUD, replace_image, signed URLs
  ├─ product_link_service.py  fetch shop page/image with public-IP checks per hop
  ├─ garment_cutout.py        remove a wearer from a garment photo (via body_analysis models)
  ├─ donation_service.py      never-worn items, CSV, mark donated
  ├─ recommendation_service.py candidate gen → 11 rule signals + season cap → compat blend
  │     ├─ bandit_ranker.py   Thompson-sampled re-score once user has feedback; learns on /feedback
  │     ├─ season_classifier  target season / item season labels
  │     ├─ agentic_recommender, outfit_compat_service, compatibility_service, trend_service,
  │     │  fashion_analysis
  │     └─ stylist_selector   fine-tuned GGUF picks #1 of top 5
  ├─ recommendation_explainer.py  (unchanged) rule notes; scratch GPT or base-chat comparison
  ├─ llm_stylist.py           chat reply (3B), pick_outfit fallback; dress-rule regeneration
  ├─ local_llm.py             llama.cpp wrapper (now accepts multi-turn history)
  ├─ tryon_service.py         avatars, render queue/worker, layered CatVTON rendering, media ownership
  │     ├─ body_analysis.py   MediaPipe parsing, validation, proportions, masks, cleanup
  │     └─ ml/catvton.py      SD1.5 inpainting UNet + CatVTON attention weights (safetensors)
  ├─ vision_service.py        CNN inference + 512-d embedding
  └─ database.py              schema/migrations (+ tryon_service.init_tables at startup)
```

Observations:

- Schema ownership is **split**. Most tables are created in `database.init_database()`, but `avatars` and `tryon_renders` are created in `tryon_service.init_tables()`, which `lifespan` calls separately. **[Verified: `main.py:107-108`, `tryon_service.py:46-87`]**
- `main.py` still mixes routing with logic. Examples: order notification SQL (`marketplace_order`), photo cut-out and analysis helpers (`_isolate_garment`, `_analyze_new_photo`), the `remove-model` flow and wear-log shaping. **[Verified]**
- `marketplace_service` replaced the old marketplace code in `app_service`. The duplicated logic from revision 1 is gone, but `ProductCreate` (a JSON image-URL endpoint) and `/marketplace/listings` (multipart upload) are still two ways to create a listing. **[Verified]**
- The compatibility weight has **two sources of truth**: `settings.outfit_compat_weight` (used in `_score_entries`) and `bandit_ranker.COMPAT_WEIGHT = 0.15` (used for the bandit's prior). They agree only at the default. **[Verified: `settings.py:84`, `bandit_ranker.py:43`]**

### Dead or unreachable code (unchanged) [Verified]
`orchestrator/`, `agents/*`, `tools/llm_client.py`, `tools/save_user_feedback.py`, the empty `ui/app.py`, most of `contracts/schemas.py`, and `Capstone-App/src/mocks/data.ts` (now trimmed but still unused). `POST /social/posts` is still not called by the frontend.

## 3. Data model

Tables from revision 1 are unchanged except where noted.

| Table | Change in rev 2 | Notes |
|---|---|---|
| `clothing_items` | + `source_url`, `source_title`, `donated_at` | `image_path` is still an absolute path |
| `products` | + `size`, `brand`, `wardrobe_item_id`, `updated_at` | Status `active / paused / sold` |
| `orders` | + `shipping_address` (JSON: name, phone, address, pincode), `payment_method`, `updated_at` | **Stores personal data** |
| `bandit_models` | new | One row per user. `state_json` holds a 61×61 precision matrix, the `b` vector and a taste memory. Load, modify and save are not atomic |
| `conversations` | new | `UNIQUE(product_id, buyer_id)`, FK cascades |
| `conversation_messages` | new | `read_at` for read receipts. Indexed by conversation and time |
| `avatars` | new (created in `tryon_service`) | Absolute `avatar_path` and `parsing_path`, `landmarks_json`, `analysis_json` (**body proportions**) |
| `tryon_renders` | new (created in `tryon_service`) | Job status, progress, absolute `result_path`, `cache_key`. Interrupted jobs are marked failed at startup |

Migrations are still ad-hoc `ALTER TABLE ... ADD COLUMN` statements with no version table. **[Verified]**

## 4. Authentication and authorization

Unchanged from revision 1:

- opaque bearer tokens, SHA-256 hashed at rest;
- PBKDF2 at 310k iterations;
- `require_owner` checks on routes that carry a `user_id`;
- every wardrobe query filters by owner. **[Verified]**

New in revision 2:

- **WebSocket `/ws`**: the connection is accepted first, and the client then has 10 s to send `{"type":"auth","token":...}`. That token is resolved with the same `session_user` as HTTP, and the socket is closed with code 4401 on failure. Typing events are forwarded only to members of the conversation. **[Verified: `main.py:416-465`]**
- **Marketplace:** listing edits and deletes check `seller_id` (`_own_listing`). Order status changes check that the caller is the buyer or the seller, and validate against a `TRANSITIONS` table. Conversation reads and writes check membership. Self-purchase is rejected. **[Verified: `marketplace_service.py:153-288,377-422`]**
- **Try-on and avatars:** every query is filtered by `user_id`. Render items must all belong to the caller. `/uploads/{file}` now also accepts avatar and render files owned by the user in the signed URL (`tryon_service.owns_media`). **[Verified]**
- **Shop-link import:** the URL scheme must be http or https, credentials in the URL are rejected, and every redirect hop must resolve only to globally routable IPs. **[Verified: `product_link_service.py:57-99`]**
- **New unauthenticated routes:** `/marketplace/images/{filename}` (listing photos, public by design) and `/tryon/status`. `/weather` is still unauthenticated. **[Verified]**
- **Still absent:** rate limiting, roles or admin, password reset, account deletion. The Forgot Password and OTP stubs are unchanged. **[Verified]**

## 5. Critical workflows (traced end to end)

### 5.1 Wardrobe upload and cut-out
`POST /wardrobe/upload` is still **`async def`**. After it writes the file, it calls `_analyze_new_photo`, which runs these steps:

1. `_isolate_garment`, which uses PIL and `cutout_garment` (MediaPipe person segmentation).
2. If a person is detected, save `*-garment.jpg` and delete the original.
3. `vision_service.predict` (TensorFlow).
4. `create_item`.

All of these are synchronous CPU or ML work **on the event loop**. The same pattern is in `/wardrobe/purchase-impact` and `/avatar`. **[Verified: `main.py:590-638,954-985`]**

### 5.2 Shop-link import (`POST /wardrobe/import-link`, sync def)
1. `import_from_link` calls `_get(url)`, which on each hop resolves the hostname and rejects non-global addresses, then calls `requests.get(stream=True, allow_redirects=False, timeout=10)`. The body is capped at 3 MB for pages and at the upload limit for images.
2. For an HTML page, it parses Open Graph, Twitter, JSON-LD, `link rel=image_src` and Amazon `<img>` tags, then fetches the image the same way.
3. `PIL.verify()`, and re-encode if the format is not JPEG, PNG or WebP.
4. The normal photo pipeline (5.1) runs.

The address check resolves DNS **separately** from `requests`, which resolves again when it connects. **[Verified: `product_link_service.py:63-79`]**

### 5.3 Recommendation (`POST /recommend`)
The flow is the same as in revision 1, with these changes:

- **Weather:** errors are now caught and fall back to 25 °C (`main.py:747-755`). **[Verified]**
- **Occasion score:** now uses a per-garment occasion-fit table (`_OCCASION_FIT`) plus tag penalties. **[Verified]**
- **Weather score:** adds a 22–30 °C band and caps out-of-season outfits at 40 (`SEASON_MISMATCH_CAP`). That is below the critic's weather floor, so they are filtered unless nothing else qualifies. **[Verified]**
- **Rule weights:** now come from `bandit_ranker.RULE_WEIGHTS`. Occasion is weighted 0.30. **[Verified]**
- **Bandit:** if `bandit_enabled` and the user's model has at least one update, `bandit_ranker.rank()` samples weights and computes `bandit_score` for every eligible candidate. For each candidate it calls `outfit_embedding()`, which runs `embeddings_for_items()`, which is **one SQL query per candidate**. The sort and the diversity rerank then use `bandit_score`. **[Verified: `bandit_ranker.py:241-253`, `item_embeddings.py:35-54`]**
- The stylist pick, the explanation (unchanged module) and the response now include a `season` field.
- Persistence is still one connection per recommendation row (`recommendation_service.py:754-770`). **[Verified]**

### 5.4 Feedback → learning
`POST /feedback` validates ownership as before. `save_feedback` inserts the row, then runs `bandit_ranker.learn_from_feedback`:

1. Load the recommendation row.
2. Load `list_items(user)`. This loads the **whole wardrobe** and signs a URL for every item.
3. Compute features and the embedding.
4. Load the model, update it, and save it (an UPSERT).

The read-modify-write has no lock or transaction. Exceptions are logged, but logging is not configured. **[Verified: `recommendation_service.py:823-832`, `bandit_ranker.py:256-281`]**

### 5.5 Chat (`POST /chat/messages`)
1. Load up to 40 items, then run the keyword intent check (unchanged).
2. If an outfit is wanted: `recommend(..., limit=12)`, which **still persists up to 12 rows**. Then filter by requested colour, exclude outfits already shown in this session, and keep the top 5.
3. Pick an outfit with `_choose_outfit`. This is **LLM call #1**: the stylist chooses. If the stylist fails, the chat model's `pick_outfit` runs as **LLM call #2**.
4. `stylist_reply` runs the chat model (3B by default, temperature 0.7, up to 260 tokens) with multi-turn history. That is **LLM call #3**. If the reply pairs a dress with separates, it regenerates once, which is **LLM call #4**.
5. **The reply is not filtered for unlisted garments or unsupported claims.** This was removed in this revision, and the README says so. The reply is markdown-stripped, truncated to 1,200 characters, and stored.
6. Chat history now re-signs outfit images on read. **[Verified: `app_service.py:225-320,323-362`, `llm_stylist.py:115-140`]**

### 5.6 Marketplace
- **Sell:** `POST /marketplace/listings` takes multipart data with up to 5 photos. Each photo is checked by declared content type and size (it is not decoded) and saved to `uploads/marketplace/`, which is **publicly served**. A wardrobe photo can be copied there instead. Then `create_listing` validates category, condition and price. **[Verified]**
- **Buy:** `create_order` runs in one transaction. For each distinct product it checks `status='active'`, rejects self-purchase, inserts a `pending` order with the shipping address and payment method, and sets `products.status='sold'`. That UPDATE has no status guard. `main.py` then pushes an `order:placed` event to the seller. No money moves in-app. **[Verified]**
- **Fulfil:** the seller moves `pending → shipped`, which sets the linked wardrobe item `available=0`. The buyer moves `shipped → completed`. Either party can cancel while the order is `pending`, which relists the product. There is **no timeout** on `pending`. **[Verified]**
- **Chat:** REST endpoints store and authorise messages. `hub.push`, which runs `anyio.from_thread.run` from threadpool handlers, delivers them to connected sockets. The client falls back to polling. **[Verified]**

### 5.7 My Virtual Look
1. **`POST /avatar`** (async). Decode the photo and limit it to 1600 px. Then `body_analysis.parse_photo` (MediaPipe), `validate`, `build_avatar` and `analyze_proportions`. Save the avatar and parsing PNGs, insert the row, and delete the previous avatar for that view along with its renders. **[Verified]**
2. **`POST /tryon`** (sync). Check that try-on is enabled and the model files exist, that an avatar exists, and that all items are owned. Look up the cache key. On a miss, insert a `queued` row and put it on `_jobs`. There is **no per-user or global queue limit**. **[Verified: `tryon_service.py:208-249`]**
3. **Worker thread:** load CatVTON (SD1.5 inpainting UNet in fp16 plus VAE on MPS or CPU). For each layer (bottom or dress, then top, then outerwear), cut out the garment, build a mask, render a 3:4 crop for 30 DDIM steps, composite it, and clean up leftover clothing. Progress goes to the DB. The model unloads after 10 idle minutes. The README describes a render as taking "a few minutes" at 512×384. **[Verified]**
4. The client polls `GET /tryon/{id}`. The result is served through a signed `/uploads/` URL. `DELETE /avatar` removes every body photo, parsing map and render. **[Verified]**

### 5.8 Donations
`unworn_items` lists items with no `wear` feedback, filtered by age. `mark_donated` sets `donated_at` and `available=0`. A CSV export is available. **[Verified: `donation_service.py`]**

## 6. Model lifecycle and memory (8 GB target host)

| Model | Loaded | Approx. size | Runtime |
|---|---|---|---|
| Chat model: **Qwen2.5-3B Q4_K_M** (new default) | At startup (`lifespan`, because `AURA_CHAT_USE_STYLIST=0` now selects the base chat model) | ~2.1 GB | llama.cpp / Metal |
| Fine-tuned stylist 1.5B | Lazily, on the first `/recommend` or chat outfit | ~1.0 GB | llama.cpp / Metal |
| Garment CNN, SHIFT15M, outfit-compat | Lazily | ~70 MB on disk, plus TF runtime | TensorFlow |
| MediaPipe / ONNX parsing models | Lazily on avatar upload or garment cut-out | small to moderate | mediapipe / onnxruntime |
| **CatVTON (SD1.5 inpainting + VAE)** | Lazily on the first render. Unloaded after 10 min idle | **several GB** **[Assumption from SD1.5 fp16 sizes]** | torch / diffusers (MPS) |
| Scratch GPT | Lazily if its directory exists (it doesn't) | ~21 MB | torch |

The README itself reports **about 5 GB of macOS swap** with just the 3B and stylist models loaded (`README.md:76`). Try-on adds a diffusion model on top of that, in the same process. Nothing coordinates memory between llama.cpp, TensorFlow and torch. **[Verified README text and code; total footprint is an assumption]**

The explainer's base-model fallback (unchanged code, `recommendation_explainer.py:233`) now uses the **3B** chat model, which is already resident by default. The memory risk of a second GGUF loading now comes from the other direction: the stylist is lazily added next to an already-loaded 3B model. **[Verified]**

## 7. Frontend architecture

- Navigation, Zustand and React Query are unchanged. There are new `locationStore` and `realtimeStore` stores.
- `src/services/realtime.ts` opens the WebSocket, authenticates with the first frame and handles reconnects. `useRealtime` invalidates queries when events arrive. **[Verified file presence; reconnection logic not deeply reviewed]**
- `src/services/index.ts` (~600 LOC) maps every API, including the new marketplace, try-on, donations and import-link calls. **[Verified]**
- **Unchanged:** no axios 401 interceptor, and `hydrate()` still clears the token on any error (`authStore.ts:77-91`). **[Verified]**

## 8. Configuration

New settings:

- `AURA_BANDIT_ENABLED` (default 1)
- `AURA_TRYON_*`: enabled, model directory, device, attention, size, steps, guidance
- The chat model default is now 3B
- `AURA_OUTFIT_COMPAT_WEIGHT` default changed from 0.40 to 0.15
- `AURA_CHAT_USE_STYLIST` default changed from 1 to 0 **[Verified: `settings.py`]**

Unchanged problems:

- Relative paths in `.env` resolve against the CWD.
- The media signing key falls back to a random per-process key.
- The weather tool reads its key at import time. **[Verified]**

New requirements:

- `requirements.txt`: `websockets`.
- `requirements-local.txt`: `accelerate`, `diffusers`, `mediapipe`, `onnxruntime`.
- `cv2` is imported by `body_analysis` but is **not declared**. It is only available transitively. **[Verified: tests fail with `No module named 'cv2'`]**

## 9. Observability

- Logging is **still not configured**. New modules log useful INFO and EXCEPTION lines: bandit update failures, try-on failures, idle unload and realtime drops. Under uvicorn defaults, INFO-level lines are dropped and the rest go unformatted to stderr. **[Verified grep]**
- Try-on progress is persisted per job, which is a good pattern. `/tryon/status` reports queue length and missing files. **[Verified]**
- There is still no request ID, metrics or tracing. **[Verified]**
