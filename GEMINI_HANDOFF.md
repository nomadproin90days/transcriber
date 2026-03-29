# Transcriber Project - Gemini Handoff Document
**Date:** March 28, 2026
**Update by:** Gemini (Interactive CLI)
**For:** Ryan Christmas / AI Assistants

---

## Project Overview

A **free social media video transcription tool** built for Ryan Christmas / Luxetide Studio. Transcribes videos from Instagram Reels, TikTok, YouTube Shorts, Twitter/X, and Facebook using local AI (Whisper).

**Brand name:** Luxetide Studio
**Domain:** luxetidestudio.com

---

## Architecture & Recent Updates

### Backend (HF Spaces)
- **Repo:** https://huggingface.co/spaces/iamryanxmas/transcriber
- **Live URL:** https://iamryanxmas-transcriber.hf.space
- **Update:** Added `GET /api/export/<job_id>/<file_format>` (supports `srt`, `vtt`, `txt`) for direct caption/transcript downloads.
- **Update:** Implemented `generate_srt` and `generate_vtt` formatters in `app.py`.

### Frontend (Vercel - portfolio site)
- **Repo:** https://github.com/nomadproin90days/ryan-portfolio
- **Live URL:** https://luxetidestudio.com
- **Update:** Updated `Transcriber.tsx` with dedicated SRT/VTT/TXT export buttons.
- **Update:** Created platform-specific landing pages for SEO:
  - `/instagram-transcript` -> `InstagramTranscriber.tsx`
  - `/tiktok-transcript` -> `TikTokTranscriber.tsx`
  - `/youtube-transcript` -> `YouTubeTranscriber.tsx`
- **Update:** Registered new routes in `App.tsx` and added quick links to `Layout.tsx` footer.
- **Update:** Secured project by adding `.env` and `.env.local` to `.gitignore`.

### Threads to Millions Integration
- **Repo:** https://github.com/nomadproin90days/threadstomillions-project
- **Update:** Rebranded from "Lexie Media LLC" to "Luxetide Studio" in `Footer.tsx` and `public/llms.txt`.
- **Update:** Added a "Free Transcriber Tool" backlink in the global footer for cross-domain SEO.

---

## Current State & Known Issues

### BLOCKING: Vercel SPA routing is broken
- **Status:** **PENDING ACTION**.
- **Fix:** Ryan must go to [Vercel Dashboard](https://vercel.com/iamryanxmas-6981s-projects/ryan-portfolio/settings) -> Framework Preset -> set to **"Other"** (instead of Vite). This ensures the `rewrites` in `vercel.json` are applied so that `/transcriber` and other routes don't 404.

### Instagram rate-limiting
- **Status:** Cloud IPs are still occasionally flagged by Instagram.
- **Workaround:** Added a UI note on the Instagram transcriber page advising users to use the **Upload** tab as a fallback.

### Apify Token Rotation
- **Status:** **PENDING ACTION**.
- **Fix:** Ryan needs to rotate the Apify API token in the Apify dashboard and update the local `.env` file.

---

## Next Steps (Priority Order)

1. **Fix Vercel Routing:** Change Framework Preset to "Other" in Vercel.
2. **Rotate Tokens:** Apify and any other exposed keys in `.env`.
3. **SEO Content:** Add FAQ sections and platform-specific guides to the new landing pages.
4. **Blog Hub:** Implement a simple blog system in `ryan-portfolio` to target long-tail keywords.
5. **Backlink Expansion:** Add backlinks from other Luxetide properties to the transcriber tool.

---

## Local Development

### Backend
```bash
cd /Users/mac/Documents/projects/transcriber
source venv/bin/activate
python app.py
# Runs on http://localhost:5050
```

### Frontend
```bash
cd /Users/mac/Documents/projects/ryan-portfolio
npm run dev
# Runs on http://localhost:5173
```

---

*This handoff was updated by Gemini on March 28, 2026, following the implementation of export features and SEO landing pages.*
