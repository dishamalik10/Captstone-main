# Releasing AURA (ENGINEERING_PLAN 4.9 and 4.10)

The code side is ready:
- `Capstone-App/app.json` has the Android package `com.aurastylist.app`.
- `Capstone-App/eas.json` has APK build profiles.
- `Capstone-App/public/_headers` holds the web security headers.

What's left needs accounts that only the owner has. Do the steps in order. `yourdomain.com` stands for the real domain.

## 0. Before releasing

- [ ] **Host settings.** The 16 GB host's `Capstone_Agents/.env` has the host profile:
  - `AURA_TRYON_ENABLED=1`
  - `AURA_PRELOAD_VISION=1`
  - a stable `AURA_MEDIA_SIGNING_KEY`
  - `AURA_ALLOWED_ORIGINS=https://app.yourdomain.com`

  Check with `python -m scripts.machine_check`: it should say `"profile": "16 GB host"`.
- [ ] **8 GB testers.** At least one tester has completed `TESTING_8GB.md` with no red memory pressure.
- [ ] **Measurement accuracy check.** Run it (`Capstone_Agents/training/MEASUREMENT_ACCURACY_PROTOCOL.md`), or accept that estimates are shown as ranges until then. The release doesn't wait for it (VQ12).
- [ ] **SegFormer licence.** Read NVIDIA's SegFormer licence (https://github.com/NVlabs/SegFormer/blob/master/LICENSE) and confirm non-commercial use is fine (LQ11).
- [ ] **Privacy policy.** Review the privacy policy text in `Capstone-App/src/screens/legal/privacyPolicy.ts`.

## 1. API at `api.yourdomain.com` (Cloudflare Tunnel)

1. Buy the domain and add it to Cloudflare.
2. On the host:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create aura
   ```
   Then route `api.yourdomain.com` to `http://127.0.0.1:8000`.
3. Start the API (no `--reload`) and the tunnel.
4. From another network, run:
   ```bash
   curl https://api.yourdomain.com/health
   ```
   It must return only `{"status":"ok"}`. The detailed view is for the host itself.

## 2. Android APK (4.9)

1. Create an Expo account, then run:
   ```bash
   npm install -g eas-cli
   cd Capstone-App
   eas login
   ```
2. In `eas.json`, replace `https://api.yourdomain.com` in both profiles with the real API URL.
3. Build:
   ```bash
   eas build -p android --profile preview
   ```
   Let EAS create and keep the signing key. Download the `.apk` when the build finishes.
4. Install it on a real Android phone and run the feature checks in `TESTING_8GB.md` section 1 against the public API.
5. Create a GitHub Release (for example `v1.0.0`), attach the `.apk`, and use these install notes:

   > **Installing AURA on Android**
   > 1. Download `aura.apk` on your phone.
   > 2. Open it. If Android asks, allow your browser to **install unknown apps** (Settings → Apps → your browser → Install unknown apps).
   > 3. Tap **Install**, then open AURA.
   >
   > AURA is not on the Play Store, which is why this permission is needed. You can turn it off again after installing.

## 3. Web app at `app.yourdomain.com` (4.10)

1. In `Capstone-App/public/_headers`, replace every `api.yourdomain.com` with the real API host.
2. Build:
   ```bash
   cd Capstone-App
   EXPO_PUBLIC_API_URL=https://api.yourdomain.com npx expo export -p web
   ```
   The output goes to `dist/`.
3. Check the build:
   - `dist/_headers` exists;
   - `grep -c "<script>" dist/index.html` prints `0` (no inline scripts, which the CSP would block).
4. Create a Cloudflare Pages project, upload `dist/` (or run `npx wrangler pages deploy dist`), and add the custom domain `app.yourdomain.com`.
5. Open the site and repeat a few of the feature checks.

**iPhone users ("Add to Home Screen"):**

> 1. Open **app.yourdomain.com** in Safari.
> 2. Tap the **Share** button, then **Add to Home Screen**.
> 3. Open AURA from the new icon. It runs full screen, like an app.

## 4. After release

- Watch `Capstone_Agents/logs/aura.log` and `/health` on the host for the first days.
- Review reports: `python -m scripts.review_reports`.
- Password reset requests (sent to support; AURA can't send reset emails yet): check that the request really comes from the account's owner, then run `python -m scripts.reset_password --email ...` and reply with the new password.
- If testers report that Option A works badly, follow the "Machine profiles" rollback in the ENGINEERING_PLAN decision log.
