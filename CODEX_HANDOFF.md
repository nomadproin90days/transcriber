# Luxetide Studio - Codex Handoff Document
**Date:** March 28, 2026
**Status:** Transcription Tool Live & Routing Fixed

---

## Current State

### 1. Frontend (Vercel)
- **URL:** https://luxetidestudio.com
- **Framework Preset:** Set to **"Other"** (Not Vite) in Vercel Dashboard. This is critical for the `vercel.json` rewrites to work.
- **Theme:** Switched to **Light Mode** (White background) by removing the `dark` class from `<html>` in `index.html`.
- **Routes:** 
  - `/transcriber`: Main tool.
  - `/instagram-transcript`: SEO Landing Page.
  - `/tiktok-transcript`: SEO Landing Page.
  - `/youtube-transcript`: SEO Landing Page.

### 2. Backend (Hugging Face)
- **URL:** https://iamryanxmas-transcriber.hf.space
- **New Features:** Supports SRT, VTT, and TXT export via `GET /api/export/<job_id>/<format>`.
- **CORS:** Configured to allow `luxetidestudio.com`.

### 3. Threads to Millions Integration
- **Status:** Rebranded from "Lexie Media" to "Luxetide Studio".
- **Backlink:** "Free Transcriber Tool" added to footer.

---

## Critical Files
- `ryan-portfolio/vercel.json`: Handles SPA rewrites and build commands.
- `ryan-portfolio/src/pages/Transcriber.tsx`: Core logic for transcription and downloads.
- `transcriber/app.py`: Flask backend with Whisper integration and export formatters.

---

## Pending Manual Tasks for Ryan
- **Apify Token:** Must be rotated and updated in the local `.env` (which is now git-ignored).
- **Vercel Settings:** If deployments fail, ensure "Framework Preset" remains set to "Other".

---

## Next Steps for Codex
1. **SEO Copy:** Flesh out the H2s and FAQ sections on the new platform-specific landing pages.
2. **Blog Hub:** Implement a minimalist blog system in `ryan-portfolio` to target long-tail transcription keywords.
3. **Analytics:** Ensure Google Search Console is tracking the new `/transcriber` sub-routes for the new keywords.

---
*Generated for Codex continuation.*
