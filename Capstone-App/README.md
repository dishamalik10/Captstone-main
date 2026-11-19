# AURA mobile app

This Expo 57 application is connected to the AURA FastAPI/CNN backend in the
sibling `Capstone_Agents` folder.

## What is real

- Email/password accounts with PBKDF2 password hashing and expiring server sessions
- Persistent user profiles
- Camera/gallery wardrobe upload with CNN classification
- Persistent per-user wardrobe loading, correction, and deletion
- Personalized outfit recommendations made only from uploaded clothes
- Occasion and weather context
- Skip/save/wear feedback stored for future ranking
- Marketplace inventory and order records
- Social feed likes/follows and persisted posts
- Wardrobe-grounded persisted stylist chat

External Google/Apple/Facebook login, transactional email, and payment capture
are not configured. Live weather needs an optional OpenWeather credential. Stylist
chat uses the local model configured by the backend and does not need an LLM key.

## Run locally

Start the backend in one PowerShell window:

```powershell
cd D:\AURA-Full-App\Capstone_Agents
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Create `D:\AURA-Full-App\Capstone-App\.env` from `.env.example`.

- Android emulator: `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`
- iOS simulator or web: `EXPO_PUBLIC_API_URL=http://127.0.0.1:8000`
- Physical phone: use the computer's LAN IP, such as
  `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000`

Then start Expo:

```powershell
cd D:\AURA-Full-App\Capstone-App
npm install
npx expo start
```

The phone and computer must use the same network. Restart Expo after changing
`.env`, because `EXPO_PUBLIC_` variables are bundled into the client.

After backend code changes, stop the old API process and restart Uvicorn. A
process already listening on port 8000 does not automatically load new routes
unless Uvicorn was started with `--reload`.

## Required wardrobe composition

The stylist needs enough complementary uploaded garments to form an outfit:

- one dress, or
- at least one top and one bottom

Footwear, outerwear, and accessories improve complete outfit generation but are
not required for the first recommendation.

## Validation

```powershell
npx tsc --noEmit
npx expo config --type public
```
