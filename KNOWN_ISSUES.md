# KNOWN_ISSUES

Audit revision 2, commit `d07801c`. The previous revision was at `c59a86a`.

Severity scale, judged against **running this for real users on a network**:

- **Critical**: exploitable now, or causes data loss in normal use.
- **High**: serious integrity, security, privacy or availability risk.
- **Medium**: a correctness or reliability defect with bounded impact.
- **Low**: hygiene or maintainability.

For a single-developer local demo, most items drop one level. **There are still no Critical findings.** Each finding was verified in code unless it is marked otherwise. Finding IDs from revision 1 are kept, so history stays traceable. New findings are tagged **(new)**.

## Remediation progress (ENGINEERING_PLAN steps 1–4.8 incl. 4.2b, and 4.11, 2026-11-27, uncommitted)

| Issue | Status | Evidence |
|---|---|---|
| M11 / L9 (red suite, no CI) | **Fixed**: cv2-dependent try-on tests skip without the extras; `.github/workflows/ci.yml` runs pytest and `tsc --noEmit` | `pytest`: 184 passed, 6 skipped, 1 xfailed (190 passed, 1 xfailed with MediaPipe installed) |
| M10 (no logging, raw errors exposed) | **Fixed**: INFO to rotating `logs/aura.log`, WARNING+ to the terminal, request IDs, generic 500 body; model `last_error` and try-on errors no longer carry paths or exception text | `logging_config.py`, `request_logging.py`, `tests/test_request_logging.py` |
| M14 (non-portable paths) | **Fixed**: relative `.env` paths resolve against `Capstone_Agents/`; media stored as file names with a startup migration; `MOVING_THE_BACKEND.md` | `services/media_paths.py`, `tests/test_media_paths.py` |
| M5 (random signing key) | **Fixed**: the API refuses to start without `AURA_MEDIA_SIGNING_KEY`; the local `.env` now has one | `main.py` lifespan, `tests/test_request_logging.py` |
| Ranking regressions | **Guarded**: `tests/test_ranking_snapshot.py` pins the order (cold start and after fixed feedback) | — |
| H3 (event-loop blocking) | **Fixed** (step 2.1): upload, purchase-impact and avatar routes are plain `def`; heavy image work capped at 2 (`services/image_slots.py`, 503 when busy); CNN pre-loaded at startup | `tests/test_upload_concurrency.py` (fails on the old routes) |
| H4 (memory) | **Improved** (step 2.2): chat and the recommendation comparison use the fine-tuned stylist (`AURA_CHAT_USE_STYLIST=1` default), so one ~1 GB GGUF is resident. Live: API ~1.6 GB with stylist + CNN loaded, base model not loaded. **Step 3 measured** a real render under chat + recommend load: the worker first peaked at 7.8 GB (ISNet cut-out ~2.7 GB kept by onnxruntime, on top of the ~5.1 GB diffusion peak). Fixed by cutting garments in a short-lived child process and freeing the Metal workspace after each layer: worker 5.1 GB, API 0.9 GB, **combined 6.0 GB** (go). `/health` now reports resident models and peak RSS for both processes | `tests/test_single_llm.py`, `tests/test_resource_report.py` |
| H5 (unbounded try-on queue) | **Fixed** (step 2.3): DB-backed queue in a separate worker process started/stopped by the API (restarted on crash, exits if the API dies); 1 active / 3 per day per user, global 10 (429); `DELETE /tryon/{id}`; unsaved looks deleted after 7 days. Virtual Look screen now renders on a "Try it on" tap and shows limit messages | `tests/test_tryon_worker.py`, live spawn/kill check |
| M15 (order holds) | **Fixed** (step 2.4): guarded "mark sold" and status updates; 72 h hold with auto-cancel and relist; at most 3 unshipped orders per buyer; checkout explains the hold | `tests/test_marketplace_holds.py`, race test in `test_characterisation.py` now passes |
| M18 (bandit) | **Fixed** (step 2.5): one embedding lookup per slate; learning loads only the outfit's items; read-update-write in one `BEGIN IMMEDIATE`; prior's compatibility weight read from settings. Note: the local `.env` sets `AURA_OUTFIT_COMPAT_WEIGHT=0.40`, so the prior now matches 0.40 there (it was silently 0.15) | `tests/test_bandit_storage.py` (3 of 4 fail on the old code) |
| M6, M7 (slates) | **Fixed** (step 2.6): one transaction per slate; `surface` and `explanation_source` columns; chat keeps only the shown outfit and stores the reply; evaluation excludes chat. Chat rows written before this change cannot be identified | `tests/test_slate_integrity.py` |
| M3 (IntegrityError → 500) | **Fixed** (step 2.7): like/follow check targets (404); any missed constraint error is a generic 409 | `tests/test_characterisation.py` |
| M17 (SSRF rebinding, slow responses) | **Fixed** (4.2): the host is resolved once, every address must be public, and the connection is made to that exact address (TLS still verified against the hostname); 20 s deadline for the whole import. The strict-xfail test now passes and the marker is removed | `tests/test_product_link.py`, `tests/test_characterisation.py`; live: python.org imports, expired/self-signed certificates and localhost are refused |
| H2 (no rate limits) | **Fixed** (4.1): DB-backed limits per user or IP (login failures 5/15 min, sign-ups 5/day per IP, chat 20/h, recommend 30/h, uploads 50/day, link imports 10/h, reports 20/day); 429 with `Retry-After`; at most 3 sockets per user; typing events throttled | `tests/test_rate_limits.py` |
| H6, M12 (body data, account deletion) | **Fixed** (4.3): consent before the first body photo (428 without it); parsing maps and landmarks are no longer stored (rebuilt at render time) and old ones are deleted on upgrade; Privacy screen with "Delete my body data", "Log out of all devices" and password-confirmed account deletion (orders kept as "Deleted user", address removed); draft privacy policy. **Owner:** review the policy text | `tests/test_privacy.py`, `tests/test_virtual_tryon.py` |
| Open sign-up gap (report/block) | **Done** (4.4): report a listing, conversation, post or user (with a snapshot); block a user, which hides their listings, posts and chats and stops messages both ways; `scripts/review_reports.py` for manual review | `tests/test_moderation.py` |
| M16 (chat grounding) | **Fixed** (4.5): replies naming a garment the user doesn't own, including an owned type in an unowned colour, are regenerated once, then replaced by the deterministic reply. Fixed 20-prompt set (fine-tuned stylist, one sampled run): first drafts with an invented piece 10%, regenerated 10%, fell back 0%, shown with an invented piece 0%. Not covered: stacking owned pieces that don't go together | `tests/test_chat_grounding.py`, `scripts/evaluate_chat_grounding.py`, `Capstone_Agents/training/chat_grounding_results.json` |
| M9 (frontend sessions) | **Fixed** (4.6): token cleared only on 401; axios 401 interceptor; "AURA is offline" screen on network errors; socket closed on logout; profile-setup failure no longer logs out | `tsc --noEmit` clean; **not tried on a device** |
| L3 (web) | **Done** (4.7): CORS from `AURA_ALLOWED_ORIGINS` with no credentials; CSP and security headers in `Capstone-App/public/_headers` (copied into the web export; no inline scripts); 7-day web sessions, 30-day app sessions. **Owner:** replace `api.yourdomain.com` | `expo export -p web` checked |
| M2, M4, L4, L5, L19 (input/response hygiene) | **Fixed** (4.8): bounded fields and email check; profile, post and listing photos must be AURA-stored images (`POST /users/me/photo` added; outside URLs refused; old ones cleared on upgrade); every upload and import is decoded and re-encoded (EXIF/GPS removed, 40 MP cap); `/weather` needs sign-in and is cached per city for 10 min; public `/health` is only `{"status":"ok"}` (details on the server machine itself); minimal `/tryon/status`; vague sign-up conflict message | `tests/test_input_hygiene.py` |
| Link-import quality (LQ1–LQ11) | **Done** (4.2b): product photo without a person preferred (up to 6 checked); category inferred from title/JSON-LD/breadcrumbs; SegFormer-B2 Clothes (ONNX, pinned revision and SHA-256) keeps only the chosen garment; preview → confirm with "Looks right / Pick a different piece / Use the original photo"; user's category wins and the item is flagged for review; previews expire after 1 h; old MediaPipe whole-outfit cut-out removed. SegFormer runs in a short-lived child process: in the API process it kept ~0.9–1.2 GB after one run, more than the step-3 headroom; in a child the API gains nothing and the child peaks at ~0.43 GB for ~0.7 s. **Owner:** read the NVlabs SegFormer licence | `tests/test_garment_cutout.py` (incl. a real-model test on a CC0 photo) |
| Virtual Look fit (VQ1–VQ15) | **Done** (4.11): body measurements in cm (front avatar + side photo scaled by height; ellipse circumferences; typed values win; no estimate when the photo checks fail; ranges until the volunteer check passes; side photo never stored; deleted with body data); garment size label, chart and flat measurements; size advice per zone on items, others' listings (viewer only) and in My Virtual Look; try-on hem and width follow the garment's size (unchanged without size information). **Owner:** run the volunteer tape-measure check | `tests/test_fit_sizing.py`, `training/MEASUREMENT_ACCURACY_PROTOCOL.md` |

## Status of revision-1 findings

The third column is the status when this review was written (commit `d07801c`), kept for history. **For the current status, use the remediation table above;** the last column points to it.

| ID | Title | Status at `d07801c` | Now (2026-11-27) |
|---|---|---|---|
| H1 | Checkout with no payment / self-purchase | **Partly fixed** → re-scored as **M15** (state machine, self-purchase blocked, seller can cancel; no hold expiry, unguarded UPDATE) | Fixed as M15 (2.4) |
| H2 | No rate limiting | **Open, wider surface** (try-on, link import, WebSocket, up to 4 LLM calls per chat message) | Fixed (4.1) |
| H3 | Blocking inference in async handlers | **Open, worse** (cut-out added to upload, and `/avatar` added) | Fixed (2.1) |
| M1 | OpenWeather errors → 500 | **Fixed** (`main.py` `_weather` and `/weather` handle errors) | Fixed |
| M2 | Unauthenticated `/weather` | Open | Fixed (4.8) |
| M3 | IntegrityError → 500 | Open for like/follow/signup. Marketplace uses `MarketplaceError` | Fixed (2.7) |
| M4 | Input validation gaps | **Partly fixed** (marketplace and order schemas bounded). Profile, post, feedback, login, item update and `ProductCreate.image_urls` still open | Fixed (4.8) |
| M5 | Ephemeral media signing key | Open (now also breaks avatar and render images) | Fixed (step 1) |
| M6 | Chat pollutes slates; stored explanation wrong | Open. Now also feeds the bandit | Fixed (2.6) |
| M7 | Non-atomic slate writes | Open (`recommendation_service.py:754-770`) | Fixed (2.6) |
| M8 | Memory / scratch GPT doc mismatch | **Open, worse**: re-scored as **H4** | Improved as H4 (2.2, step 3) |
| M9 | Frontend logs out on network error; no 401 handling | Open | Fixed (4.6) |
| M10 | Logging not configured; errors leak | Open | Fixed (step 1) |
| M11 | Test gaps | **Improved** (58 → 133 tests; marketplace, realtime, link import, try-on and bandit covered). Gaps remain (see below) | Improved (CI added; frontend tests are 5.8) |
| M12 | No account recovery or deletion | Open. **More data at stake now** (body photos, addresses) | Deletion fixed (4.3). Password reset: by the operator (`scripts/reset_password.py`); no email reset or in-app change-password yet |
| M13 | Chat outfit images expire | **Fixed** (`app_service._refresh_outfit_images`) | Fixed |
| M14 | CWD-relative paths, absolute `image_path` | Open. Now also `avatars` and `tryon_renders` paths | Fixed (step 1) |
| L1–L17 | Low items | All still open except **L13** (cart quantity; the store was simplified) and **L8** (product-by-id, which now has a direct query). New Low items L18–L22 below | L3, L4, L5 fixed (4.7, 4.8); the rest are in ENGINEERING_PLAN "Later" (5.x) or still open |

Index: [High](#high) · [Medium](#medium) · [Low](#low)

---

## High

### H2. No rate limiting, quotas or brute-force protection; the attack surface has grown
- **Where:**
  - `main.py` auth routes and `/chat/messages`;
  - `/recommend`;
  - `/wardrobe/upload` and `/wardrobe/import-link`;
  - `/avatar`, `/tryon` and `/ws`.
- **Evidence:** No limiter exists anywhere. Each new feature is expensive per call:
  - a chat message can make **up to 4 sequential LLM generations** (`app_service._choose_outfit` → `llm_stylist.pick_outfit` → `stylist_reply`, plus a regeneration), all competing for single-slot semaphores;
  - each `/tryon` call queues a multi-minute diffusion render (see H5);
  - each import-link call makes up to 10 outbound HTTP requests;
  - `/ws` accepts a socket before authentication and holds it for up to 10 s.
- **Impact:**
  - Online password guessing.
  - One user can monopolise the LLM slot, which gives everyone else 503s, or the try-on worker, which holds every other user's render for hours.
  - The server can be used as an HTTP fetcher.
- **Fix:** Per-IP and per-account limits on auth. Per-user limits on chat, recommend, upload, import-link and try-on. Cap concurrent unauthenticated sockets.
- **Depends on:** deciding on the deployment topology (limits in the proxy or in the app).

### H3. Synchronous ML work runs on the asyncio event loop (worse)
- **Where:**
  - `main.py` `upload_clothing` (async), which calls `_analyze_new_photo` → `_isolate_garment` (MediaPipe cut-out), then `vision_service.predict` (TensorFlow);
  - `purchase_impact` (async);
  - `upload_avatar` (async), which calls `tryon_service.create_avatar` → `body_analysis.parse_photo`, `validate`, `build_avatar` and `analyze_proportions`.
- **Evidence:** Every one of these calls is synchronous inside an `async def`.
- **Impact:** While any upload is processed, the **entire server stops**: REST calls, image fetches, and now WebSocket delivery and presence too. The first upload after a restart also waits for TensorFlow and MediaPipe to load.
- **Fix:** Make these routes sync `def`, or wrap the work in `await anyio.to_thread.run_sync(...)`. Pre-load models in `lifespan`.
- **Depends on:** none.

### H4. Memory oversubscription on the 8 GB target host (was M8, escalated)
- **Where:** `settings.py:22` (chat default is now Qwen2.5-3B), `main.py:107-116` (chat model loaded at startup), `stylist_selector._stylist_model` (stylist loaded lazily), `tryon_service.py:43,351` (CatVTON in the same process), `README.md:76`.
- **Evidence:**
  - With the 3B and stylist GGUFs resident, the README itself reports **"swap use was high (about 5 GB of 6 GB)"**.
  - TensorFlow (CNN, compat), MediaPipe/ONNX and torch/diffusers (SD1.5 inpainting UNet and VAE) all load into the **same process** with no coordination.
  - The worker unloads CatVTON only after 10 idle minutes. The GGUFs are never unloaded.
- **Impact:**
  - On the documented hardware, one try-on render while chat is in use can push the machine into heavy swapping or an out-of-memory kill.
  - An OOM kill also takes down the API and every WebSocket, and marks every queued render as failed on restart.
  - Separately, the README still says the scratch GPT explains outfits, but it is skipped whenever the stylist ran, and it isn't installed.
- **Fix:**
  - Run try-on in a **separate worker process** with its own memory budget.
  - Unload GGUFs, or refuse renders, while memory is low.
  - Make 1.5B the default chat model on machines with 8 GB or less (the README already suggests it).
  - Expose resident models and RSS in `/health`.
  - Make the README and the code agree on the scratch GPT's role.
- **Depends on:** a product decision on which features must run together on 8 GB.

### H5. (new) The try-on render queue is unbounded and has no cancellation
- **Where:** `services/tryon_service.py:208-249` (`request_render`), `:285-322` (one worker thread), `contracts/api_schemas.py` `TryOnRequest`
- **Evidence:**
  - Every distinct combination of items (up to 8, using any of the user's items) that is not already cached becomes a new `queued` row on an in-memory `queue.Queue`.
  - There is no per-user or global limit and no cancel endpoint.
  - One worker processes jobs in FIFO order, at minutes per render (30 DDIM steps per garment layer, 1–3 layers).
  - `/tryon/status` reports `queue_length`, but nothing enforces a limit.
- **Impact:**
  - A user with 20 items can enqueue thousands of combinations, which blocks try-on for everyone for days and fills the disk with PNGs.
  - Jobs are lost on restart, although `init_tables` does mark them failed.
- **Fix:** Limit each user to at most one active job and the queue to N jobs, returning 429 above that. Add `DELETE /tryon/{id}`. Delete unsaved renders after a retention period.
- **Depends on:** H4 (moving the worker out of process) for a durable queue.

### H6. (new) Sensitive body data with no governance or account deletion
- **Where:** `tryon_service.create_avatar` (stores full-body photos, a body parsing map, 33-point landmarks, and an `analysis_json` of body proportions), `users.profile_json` (body shape, skin tone, height), `orders.shipping_address` (name, phone, address, pincode). All files are in `uploads/`, unencrypted, and their absolute paths are in the DB.
- **Evidence:**
  - `DELETE /avatar` exists and correctly removes body photos and renders (`tryon_service.py:174-178`). That is good.
  - There is **no account deletion**, and no retention or consent records.
  - Image URLs depend on the signing key, which the current `.env` leaves unset, so it is random per process (M5).
  - Parsing maps and landmarks are kept even though the user only sees the avatar.
- **Impact:** This is the most sensitive data in the system: photos of people's bodies plus derived body measurements, together with home addresses. If the app is deployed, it likely falls under privacy law (for example India's DPDP Act or the GDPR) and needs consent, a deletion right and a minimal-retention policy. **[Assumption on legal applicability]**
- **Fix:** Explicit consent at avatar upload. Account deletion that cascades through every table and file. Delete or minimise parsing and landmark files after rendering. Encrypt the uploads volume at rest. Document retention.
- **Depends on:** M12 (account deletion), M5 (stable signing key), M14 (path handling).

---

## Medium

### M15. (new; replaces H1) Orders hold a listing indefinitely; reservation is not concurrency-safe
- **Where:** `services/marketplace_service.py:228-253` (`create_order`), `:261-288` (`update_order_status`)
- **Evidence:**
  - An order sets `products.status='sold'` immediately, with no expiry on `pending`.
  - The UPDATE is `WHERE product_id=?`, without `AND status='active'` and without a `rowcount` check. It relies on the earlier SELECT in a deferred SQLite transaction.
  - Payment is **off-app**: cash on delivery or UPI, recorded only as `payment_method`. That is documented in the module docstring.
- **Impact:**
  - Any user can lock any number of listings (up to 20 per request) as "sold" until each seller notices and cancels.
  - Under concurrent orders, the loser gets an unhandled `database is locked` 500 instead of a 409.
  - Sellers and buyers have no protection against non-payment. That is acceptable for a demo, but users should be told.
- **Fix:** Use a conditional UPDATE with a `rowcount` check. Add a `reserved_until` column that auto-cancels after N hours without shipment. Limit open orders per buyer. Show clearly in the UI that payment is arranged off-app.
- **Depends on:** H2 (limits), M3 (error mapping).

### M16. (new) Chat replies are no longer grounded or filtered
- **Where:** `services/llm_stylist.py:115-140` (compare `c59a86a`, which ran `_has_unlisted_garment` and `_has_unverified_claim` on every sentence)
- **Evidence:**
  - The 3B model now writes free text at temperature 0.7, up to 260 tokens, truncated to 1,200 characters.
  - Only markdown is stripped, and a dress paired with separates triggers one regeneration.
  - `README.md:244-245` acknowledges this: "Replies are not filtered sentence by sentence … occasionally names a piece that is not in the shown outfit".
- **Impact:**
  - The chat text can name garments the user doesn't own, or contradict the outfit card shown under it.
  - The earlier architecture rule that no model can add garments and all text is filtered no longer holds for chat.
  - The capstone report should not claim grounding for chat.
- **Fix:** Bring back a lighter filter. For example, reject or regenerate when a garment term isn't in the shown outfit or wardrobe, rather than dropping sentences. Or show the reply with an "AI text" disclaimer. Measure the rate of invented pieces on a fixed prompt set.
- **Depends on:** none.

### M17. (new) SSRF guard is open to DNS rebinding; slow responses tie up workers
- **Where:** `services/product_link_service.py:57-99`
- **Evidence:**
  - `_check_public_url` resolves the hostname with `socket.getaddrinfo`, then `requests.get` resolves it **again** when it connects. A rebinding DNS server can return a public IP the first time and `127.0.0.1` or `169.254.169.254` the second.
  - The `timeout=10` applies **per socket operation**, not to the whole request, so a server that trickles bytes can hold a threadpool worker until it reaches the 3 MB or 10 MB cap.
  - Redirect hops are re-checked, and credentials and non-http schemes are rejected. That part is correct.
- **Impact:** The server can be made to fetch from internal services (on a cloud VM, the metadata endpoint). With repeated calls, threadpool slots run out and the API stalls.
- **Fix:** Connect to the IP that was validated (a custom transport or adapter that pins the resolved address and sets SNI and the Host header). Enforce a wall-clock deadline on the whole fetch. Rate-limit per user (H2).
- **Depends on:** H2.

### M18. (new) Bandit ranking runs N+1 queries, and learning is not atomic
- **Where:** `services/bandit_ranker.py:241-253` (`rank`), `:256-281` (`learn_from_feedback`), `services/item_embeddings.py:35-54`
- **Evidence:**
  - `rank()` calls `outfit_embedding(user_id, entry["items"])` **for every candidate** (the candidate generator produces up to 750 plus refinement). Each call runs a separate `SELECT ... IN (...)` query.
  - `learn_from_feedback` calls `list_items(user_id)`, which loads and signs the **whole wardrobe**, to find 2 to 5 items. It then does an unlocked load, modify and save of the model.
  - The compatibility weight in the prior (`COMPAT_WEIGHT=0.15`) is separate from `settings.outfit_compat_weight`.
- **Impact:**
  - Hundreds of SQLite queries per `/recommend` once a user has given any feedback.
  - Two feedback requests at the same time lose one update.
  - If someone changes `AURA_OUTFIT_COMPAT_WEIGHT`, the cold-start ranking and the bandit's prior silently diverge.
- **Fix:** Pre-fetch all candidate embeddings once (`score_outfits` already does this) and pass them in. Query only the needed items. Wrap the read-modify-write in a single `BEGIN IMMEDIATE` transaction. Derive the prior from `settings`.
- **Depends on:** M11 (a ranking snapshot test), because this changes the code path behind rankings.

### M2. The unauthenticated `/weather` route spends the server's API key
Unchanged. `main.py` `current_weather` has no `Depends(current_auth)` and no caching. **Fix:** require auth and cache per city. **Depends on:** H2.

### M3. Constraint violations surface as unhandled 500s
- **Where:** `app_service.toggle_like`, `toggle_follow`, `signup` (check-then-insert), `create_post`; `marketplace_service.start_conversation` (`UNIQUE(product_id, buyer_id)` race).
- **Evidence:** `PRAGMA foreign_keys=ON`, and nothing maps `sqlite3.IntegrityError` to an HTTP error.
- **Impact:** Clients get 500s for missing targets and concurrent duplicates.
- **Fix:** Check the target exists and return 404. Map `IntegrityError` to 409 in one global handler.
- **Depends on:** M10.

### M4. Input validation gaps (partly fixed)
- **Fixed:** `ProductCreate` titles and descriptions, `OrderRequest` (at most 20 items plus an address schema), `ListingUpdate`, `MarketMessageCreate`, `ImportLinkRequest`, `DonationRequest` and `TryOnRequest` are now bounded.
- **Still open** (in `contracts/api_schemas.py`):
  - `ProfileUpdate.avatarUrl` and `PostCreate.outfit_image_url` are arbitrary strings that other users' clients render;
  - `ProductCreate.image_urls` items are arbitrary strings shown to every buyer, via the JSON `POST /marketplace/products` route;
  - `FeedbackRequest.item_ids` is unbounded and builds the SQL `IN` list;
  - `ClothingItemUpdate` strings and lists are unbounded;
  - `LoginRequest` is unbounded;
  - email addresses are not validated;
  - the `view` form field on `/avatar` is a free string, although the service validates it.
- **Impact:** Other users' devices load attacker-chosen URLs. Very large lists can hit SQLite's variable limit and return a 500.
- **Fix:** `max_length` everywhere, media-ID-only images, and `EmailStr`.
- **Depends on:** none.

### M5. The media signing key is ephemeral in the current setup
- **Where:** `settings.py:38`. Still empty in the local `.env`.
- **Impact:** Every restart now breaks wardrobe, avatar **and** try-on image links. A second worker isn't viable anyway (see the single-process constraint in ARCHITECTURE §1).
- **Fix:** Fail fast without a key outside tests.
- **Depends on:** none.

### M6. Recommendation persistence pollutes evaluation and learning data
- **Where:** `app_service.py:249` (chat calls `recommend(..., 12)`), `recommendation_service.py:754-790`, `main.py` (the explanation is replaced after persistence), `scripts/evaluate_feedback.py:49-66`.
- **Evidence:** Each chat outfit request still writes up to 12 ranked rows, and the user sees one. `recommendations.explanation` still stores the pre-explainer rule text.
- **Impact:**
  - Offline slate metrics (NDCG, hit rate) are diluted by slates nobody saw.
  - The audit trail does not show what the user actually saw.
  - The bandit learns from `component_scores` of the row the user reacted to, which is correct, but the phantom rows make the "shown vs. not chosen" analyses in the report unreliable.
- **Fix:** Add a `surface` column, persist only what was shown, and store the final explanation and its source.
- **Depends on:** M7.

### M7. Recommendation slates are not written atomically
Unchanged: `recommendation_service.py:754-770` opens a connection inside the per-row loop. **Fix:** one transaction per slate. **Depends on:** none.

### M9. Frontend session handling
Unchanged:

- `authStore.hydrate()` clears the token on any error, including a network error;
- there is no 401 interceptor;
- a failed profile setup triggers a logout.

Realtime now adds a second channel that will keep failing quietly after a session expires. **Fix:** clear the token only on 401, add an interceptor, and close the socket on logout. **Depends on:** none.

### M10. Logging is not configured, and errors leak internals
- **Where:** no `basicConfig` or `dictConfig` anywhere. `main.py` `_analyze_new_photo` and `remove_model_from_photo` return `f"Image analysis failed: {exc}"`. `tryon_service._friendly_error` stores `Render failed: {text[:300]}` in the database and returns it to the client. `local_llm.last_error` contains paths and is exposed on `/health`.
- **Impact:**
  - New INFO-level diagnostics are dropped: idle try-on unloads and stylist-pick skips. The exception lines from bandit-learning and try-on failures do reach stderr, but unformatted, with no request context and no log level config.
  - Raw exception text reaches users.
- **Fix:** Logging config, request IDs, a global handler and scrubbed errors.
- **Depends on:** none. **This should come first**, because it is how all the other issues get diagnosed.

### M11. Remaining test gaps (improved)
- **Now covered:** marketplace (`test_marketplace.py`), realtime (`test_realtime.py`), product link (`test_product_link.py`), try-on (`test_virtual_tryon.py`), bandit (`test_bandit.py`), season and weather, and garment cut-out. 133 tests are collected.
- **Still uncovered** (verified by search):
  - social like and follow;
  - session expiry;
  - wrong-password login;
  - duplicate signup;
  - concurrent orders;
  - order hold expiry (the feature doesn't exist);
  - DNS-rebinding SSRF;
  - try-on queue limits;
  - migrations from an old schema;
  - any frontend test.
- **Broken locally:** 6 try-on tests fail with `ModuleNotFoundError: cv2`, because they need optional extras and have no `importorskip`. A fresh clone that installs only `requirements.txt` therefore shows failures.
- **Fix:** `pytest.importorskip("mediapipe")` and `importorskip("cv2")` in the try-on tests, or a marker. Declare `opencv-python` explicitly. Add the missing characterisation tests.
- **Depends on:** none.

### M12. Account recovery and deletion are missing
- **Evidence:** unchanged. The `AuthNavigator` stubs are still there, and there are no reset, change-password or delete-account endpoints.
- **Impact:** H6 makes this more serious, because the data now includes body photos and home addresses.
- **Fix:** Account deletion that cascades through every table and removes uploads, avatars, renders and listing photos. Add password change and reset. Hide the stub screens.
- **Depends on:** an email provider (for reset), and L15.

### M14. Relative paths in `.env`, and absolute paths stored in the DB (wider)
- **Where:** `settings.py`, `.env` (`./aura.db`, `./uploads`), `clothing_items.image_path`, `avatars.avatar_path` / `parsing_path`, `tryon_renders.result_path`. Ownership checks match the stored string exactly (`main.py` `uploaded_image`, `tryon_service.owns_media`).
- **Impact:** Starting the server from another directory creates an empty database. Changing `AURA_UPLOAD_DIR` returns 404 for every wardrobe, avatar and render image.
- **Fix:** Anchor paths to `ROOT`. Store basenames and migrate existing rows.
- **Depends on:** L12.

---

## Low

| ID | Finding | Evidence | Impact | Fix | Depends on |
|---|---|---|---|---|---|
| L1 | Dead code and the dependencies it needs | Unchanged: `orchestrator/`, `agents/`, `tools/llm_client.py`, `tools/save_user_feedback.py`, empty `ui/app.py`, `src/mocks/data.ts`. `langgraph` and `langchain-core` are still in `requirements.txt` | Confusion. Larger installs | Delete | M11 |
| L2 | Binary backups committed to Git | Unchanged | Repository bloat | Remove | none |
| L3 | Session hygiene | Unchanged: 30-day fixed tokens, never purged, `localStorage` on web | Token theft window | Purge, sliding expiry | none |
| L4 | Information disclosure | Public `/users/{id}`, signup reveals whether an email exists, `/health` and now `/tryon/status` (missing model files, queue length) are unauthenticated | Reconnaissance | Require auth, generic messages | none |
| L5 | Upload hardening | Content type is trusted for `/wardrobe/upload` and **marketplace listing photos** (`main.py` `marketplace_create_listing` saves bytes without decoding them, and they are then **publicly served**). The link import correctly runs `PIL.verify()` | Non-image files hosted publicly under an image URL | Decode, re-encode and strip metadata before saving | H3 |
| L6 | Duplicated, divergent constants | `NEUTRALS` and colour sets in recommendation, style analysis, purchase impact, explainer, stylist selector, and now `bandit_ranker.DARK/LIGHT/NEUTRAL`. Occasion grouping is defined twice (`recommendation_service._OCCASION_GROUP` puts wedding in its own group, `bandit_ranker._GROUP_OF` puts it under formal). Feedback reward scales differ in 3 places | Inconsistent behaviour | Single vocabulary module | M11 |
| L7 | No pagination | Feed, products, chat history, wardrobe, **conversations, messages, orders and saved looks** all return everything | Response sizes grow | Cursor pagination | none |
| L8 | Per-request query overhead (partly improved) | Auth runs 2 queries with 4 sub-selects. `ensure_user` writes on reads. `_product()` runs a seller-sales COUNT **per listing** (`marketplace_service.py:71-80`). `_conversation()` runs 2 queries per conversation. `_public_render` queries the avatar view per render | N+1 query patterns | Joins and aggregates | M11 |
| L9 | Dependency and supply-chain hygiene | `pytest` and `httpx` in runtime requirements. Base Qwen download not pinned to a revision. **`download_tryon_models.py` has no hash verification** (only the stylist download is SHA-256 pinned). `cv2` is used but not declared. The local extras now pull torch, diffusers, mediapipe and onnxruntime into the API process | Builds are not reproducible. Unverified multi-GB weights | Pin revisions and hashes, lock files, separate try-on dependencies | H4 |
| L10 | Outfit-compat load failure is permanent | Unchanged | Degraded until restart | Retry | M10 |
| L11 | LLM thread safety if concurrency > 1 | Unchanged. Now matters more, because chat makes several sequential calls | | Cap at 1 | none |
| L12 | Ad-hoc migrations, schema split across modules | `database.init_database` plus `tryon_service.init_tables` | Drift | Versioned migrations in one place | none |
| L14 | Weather tool config | Unchanged | | Use `settings` | none |
| L15 | Dangling references | Unchanged for recommendations and feedback. Deleting a wardrobe item that has a listing leaves `products.wardrobe_item_id` pointing at nothing. Renders keep item IDs in JSON | Silent inconsistency | Junction tables or cleanup | M12 |
| L16 | Chat outfit trigger is over-broad | Unchanged substring matching | Unexpected outfit replies plus M6 rows | Word boundaries or a classifier | M6 |
| L17 | `main.py` mixes routing and logic | It now has photo cut-out helpers, order notification SQL and the full WebSocket loop | Harder to test | Move into services | M11 |
| L18 | (new) Realtime is limited to one process | `services/realtime.py:8-9` (documented). `hub.push` uses `anyio.from_thread.run`, which only works in AnyIO worker threads (true for FastAPI sync routes). Typing events aren't rate-limited | Can't scale out. Events are dropped silently | A broker (Redis pub/sub) if scaling. Limit typing events | H2 |
| L19 | (new) Wardrobe photos copied to public storage | `marketplace_service.copy_wardrobe_photo` copies the private wardrobe image to the **public** `/marketplace/images/` | A photo of a person (the cut-out may not have run) becomes publicly reachable by URL. It is intended, but users aren't warned | Run the cut-out first, warn in the UI | none |
| L20 | (new) The bandit's visual-taste memory grows with feedback and never decays | `bandit_ranker.update` adds embeddings into running sums per occasion group | Old tastes dominate | Exponential decay | M18 |
| L21 | (new) The cut-out deletes the original photo | `main.py` `_isolate_garment` unlinks the original after saving `-garment.jpg` | A bad cut-out can't be undone (`remove-model` only works in the other direction) | Keep the original | none |
| L22 | (new) Try-on renders are cached forever | The cache key includes avatar, items, size and steps. Unsaved `done` renders are never deleted | Disk growth | Retention job | H5 |
