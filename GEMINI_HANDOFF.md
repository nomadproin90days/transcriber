# Transcriber Project - Handoff Document
**Last Updated:** March 29, 2026
**Updated by:** Claude Opus 4.6
**For:** Ryan Christmas / AI Assistants

---

## Project Overview

A **free social media video transcription tool** built for Ryan Christmas / Luxetide Studio. Transcribes videos from Instagram Reels, TikTok, YouTube Shorts, Twitter/X, and Facebook using local AI (faster-whisper).

**Brand name:** Luxetide Studio
**Domain:** luxetidestudio.com

---

## Architecture

### Backend (HF Spaces - Docker)
- **Repo:** https://huggingface.co/spaces/iamryanxmas/transcriber
- **GitHub Mirror:** https://github.com/nomadproin90days/transcriber
- **Live URL:** https://iamryanxmas-transcriber.hf.space
- **Stack:** Flask, yt-dlp, faster-whisper (base model, CPU, int8)
- **Dockerfile:** Python 3.12-slim + ffmpeg, gunicorn with 2 workers / 4 threads

### Frontend (Vercel - React SPA)
- **Repo:** https://github.com/nomadproin90days/ryan-portfolio
- **Live URL:** https://luxetidestudio.com
- **Stack:** React 19, Vite, Tailwind CSS 4, react-router 7, motion
- **Routing:** SPA with `vercel.json` rewrites to `index.html` for all routes

---

## Recent Changes (March 29, 2026)

### SEO Fixes (Critical)
- **Added `useHead` hook** (`src/hooks/useHead.ts`) — dynamically sets per-page title, meta description, canonical URL, OG tags, Twitter cards, and JSON-LD schema on route change. This was the #1 blocker: the SPA shell served homepage meta tags on every route, and the canonical tag pointed to `/` on all pages.
- **Transcriber page** now has: title "Free Social Media Video Transcription Tool | Luxetide Studio", correct canonical `https://luxetidestudio.com/transcriber`, WebApplication schema markup
- **Platform pages** (Instagram, TikTok, YouTube) each have unique titles, descriptions, canonicals, and schema
- **Requested Google indexing** for `/transcriber`, `/instagram-transcript`, `/tiktok-transcript`, `/youtube-transcript` via Google Search Console
- **Full SEO research report** saved to `SEO-RESEARCH-REPORT.md` in the transcriber repo

### Instagram Cookie Auth
- **Added Instagram session cookie support** to `app.py` — reads `INSTAGRAM_COOKIES` env var (base64-encoded Netscape cookie file), decodes to temp file, passes to yt-dlp, cleans up after
- **HF Spaces secret** `INSTAGRAM_COOKIES` set with Safari session cookies
- **Cookie expiry:** `sessionid` valid until March 2027, `ds_user_id` expires June 27, 2026 (re-export needed before then)

### Rate Limiting & Protection
- **Per-IP Instagram rate limit:** 10 requests/hour per IP address to protect session cookies from burn
- **Stats endpoint:** `GET /api/stats` returns platform request counts and job status breakdown

### Batch Mode Removed
- **Removed `/api/transcribe/batch` endpoint** from backend — prevents mass Instagram requests that would burn the session
- **Removed Batch Mode tab** from frontend UI — now shows only "Single Video" and "Upload"

### Error Handling
- **Friendly error messages** for Instagram login/rate-limit errors, private videos, and unsupported URLs — users no longer see raw yt-dlp stack traces

---

## Current State

### Working
- Single video transcription from all platforms (Instagram, TikTok, YouTube, Twitter/X, Facebook)
- Instagram Reels downloading via session cookies
- File upload transcription (MP4, MP3, WAV, etc.)
- Export to SRT, VTT, TXT formats
- Video download feature
- Per-page SEO tags on all transcriber routes
- Google indexing requested for all pages

### Known Issues
- **Google hasn't indexed `/transcriber` yet** — indexing was requested on March 29, 2026. Check GSC in a few days.
- **SPA rendering limitation** — meta tags are set client-side via JS. Googlebot executes JS so it works, but SSR/pre-rendering would be more reliable long-term.
- **Instagram cookies expire** — `ds_user_id` cookie expires June 27, 2026. Set a reminder to re-export cookies from Safari before then. Process: `python3 -m yt_dlp --cookies-from-browser safari --cookies /tmp/ig_cookies.txt -s https://www.instagram.com/`, then base64 encode and update the HF Spaces secret.
- **HF Spaces free tier** — 2 vCPU / 16GB RAM, sleeps after inactivity. Transcription takes 15-30s per video. No GPU.

---

## SEO Strategy (from research report)

### Key Findings
- "video transcription tool" (260/mo) SERP is 100% listicles — tool page can't rank directly
- "social media transcript generator" is an **unclaimed category** with no dominant player
- Closest competitors: VideoTranscriberAI, Submagic, GetTranscribe, GetTheScript
- Multiple competitors (Transcript24, Proactor.ai) are 404ing on their tool pages
- Active Reddit demand in r/SideProject and r/ContentCreators

### Priority Actions
1. Add 1500+ words of content to `/transcriber` (features, use cases, FAQ)
2. Add FAQ schema markup for featured snippet eligibility
3. Publish competing listicle ("Best Free Video Transcription Tools 2026")
4. Post on Reddit threads linking to tool
5. Get listed in existing "best transcription tools" roundups

### Differentiators to Surface in Content
- All social platforms in one tool (competitors are single-platform)
- Privacy-first / local Whisper AI (no competitor claims this)
- Free, no signup required
- File upload + URL paste

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves Flask template (HF Spaces only) |
| POST | `/api/transcribe` | Start transcription job from URL |
| POST | `/api/transcribe/upload` | Start transcription from file upload |
| GET | `/api/status/<job_id>` | Poll job status |
| GET | `/api/export/<job_id>/<format>` | Download SRT/VTT/TXT |
| POST | `/api/download-video` | Download original video |
| GET | `/api/thumbnail/<job_id>` | Get video thumbnail |
| GET | `/api/stats` | Usage statistics |
| GET | `/api/history` | Recent completed jobs |
| GET | `/robots.txt` | SEO robots file |
| GET | `/sitemap.xml` | SEO sitemap |

---

## Frontend Routes

| Path | Component | SEO Title |
|------|-----------|-----------|
| `/transcriber` | `Transcriber.tsx` | Free Social Media Video Transcription Tool |
| `/instagram-transcript` | `InstagramTranscriber.tsx` | Free Instagram Reel Transcript Generator |
| `/tiktok-transcript` | `TikTokTranscriber.tsx` | Free TikTok Video Transcript Generator |
| `/youtube-transcript` | `YouTubeTranscriber.tsx` | Free YouTube Video & Shorts Transcript Generator |

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

### Deploying Backend to HF Spaces
```bash
cd /Users/mac/Documents/projects/transcriber
git push hf main
```

### Deploying Frontend to Vercel
```bash
cd /Users/mac/Documents/projects/ryan-portfolio
git push origin main
# Or: npx vercel --prod
```

### Refreshing Instagram Cookies
```bash
python3 -m yt_dlp --cookies-from-browser safari --cookies /tmp/ig_cookies.txt -s https://www.instagram.com/
# Keep only Instagram cookies
grep "\.instagram\.com" /tmp/ig_cookies.txt > /tmp/ig_only.txt
# Add Netscape header
(echo "# Netscape HTTP Cookie File"; echo ""; cat /tmp/ig_only.txt) > /tmp/ig_final.txt
# Base64 encode
base64 -i /tmp/ig_final.txt | tr -d '\n'
# Update INSTAGRAM_COOKIES secret at:
# https://huggingface.co/spaces/iamryanxmas/transcriber/settings
```

---

*Updated by Claude Opus 4.6 on March 29, 2026, following SEO research campaign, meta tag fixes, Instagram cookie auth, rate limiting, and batch mode removal.*
