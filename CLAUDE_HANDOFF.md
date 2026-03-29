# Transcriber - Claude Handoff

**Date:** March 28, 2026
**Status:** Local app verified, transcript + thumbnail fixes applied

---

## Current State

### 1. Repo Scope
- This repository contains the Flask backend and a single-file frontend in `templates/index.html`.
- It does **not** contain the separate Vercel/portfolio frontend referenced in older handoff notes.
- Brand/domain context: **Luxetide Studio** / `luxetidestudio.com`.

### 2. Backend + UI
- Main app entrypoint: `app.py`
- UI route: `GET /`
- Supports:
  - single URL transcription
  - batch transcription
  - file upload transcription
  - video download
  - thumbnail download
  - transcript export in `srt`, `vtt`, and `txt`

### 3. Local Runtime
- Default local port in `app.py`: `5050`
- Production (Fly.io / Docker): `8080`
- Override with: `PORT=<port> ./run.sh`
- Verified locally on **March 28, 2026**

---

## Important Endpoints
- `GET /` - app UI
- `POST /api/transcribe` - transcribe one remote URL
- `POST /api/transcribe/batch` - transcribe up to 20 URLs
- `POST /api/transcribe/upload` - transcribe an uploaded file
- `GET /api/status/<job_id>` - poll job status
- `GET /api/history` - recent completed jobs
- `GET /api/thumbnail/<job_id>` - serve extracted thumbnail
- `POST /api/download-video` - download original video
- `GET /api/export/<job_id>/<file_format>` - export transcript as `srt`, `vtt`, or `txt`

---

## What Was Fixed

### Thumbnail reliability
- Thumbnail handling now works across `.jpg`, `.jpeg`, `.png`, and `.webp`.
- If JPEG conversion fails, the app now keeps the original thumbnail file instead of deleting it.
- `/api/thumbnail/<job_id>` now serves the correct mimetype for the actual saved image.

### Empty transcript fallback
- If the first faster-whisper pass returns an empty transcript with VAD enabled, the app now retries without VAD.
- This improves results for clips where speech detection is too aggressive on the first pass.

---

## Verification Completed
- `./venv/bin/python -m py_compile app.py` passed.
- Local app successfully served at `http://localhost:7860`.
- Verified with a short spoken YouTube clip:
  - transcript returned with non-empty text
  - thumbnail endpoint returned `200 OK`

---

## Known Context
- Older docs in this repo mix together:
  - this Flask repo
  - a separate `ryan-portfolio` frontend repo
  - deployment notes for Vercel and Hugging Face
- For work inside this repository, treat `app.py` and `templates/index.html` as the source of truth.

---

## Key Files
- `app.py` - Flask app, background job processing, transcript export, thumbnail handling
- `templates/index.html` - full frontend UI
- `run.sh` - local runner
- `requirements.txt` - Python dependencies

---

## Recommended Next Checks
1. ~~Normalize port references~~ — done: local=5050, production=8080.
2. Test a few real Instagram/TikTok URLs to see whether extractor or rate-limit issues still appear.
3. If needed, add lightweight backend logging around `yt-dlp` failures for easier debugging.
