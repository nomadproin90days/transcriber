import os
import uuid
import json
import time
import re
import threading
from pathlib import Path

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB upload limit

DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# In-memory job store
jobs: dict[str, dict] = {}

# Lazy-loaded whisper model
_whisper_model = None
_model_lock = threading.Lock()


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        with _model_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel
                _whisper_model = WhisperModel(
                    "base",
                    device="cpu",
                    compute_type="int8",
                )
    return _whisper_model


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "instagram.com" in url_lower:
        return "instagram"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    if "linkedin.com" in url_lower:
        return "linkedin"
    return "other"


def download_audio(url: str, output_path: str) -> dict:
    """Download audio from a URL using yt-dlp. Returns info dict."""
    import yt_dlp

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", "Unknown"),
        "thumbnail": info.get("thumbnail", ""),
    }


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio file using faster-whisper."""
    model = get_whisper_model()

    # Find the actual file (yt-dlp may add .mp3 extension)
    path = Path(audio_path)
    actual = None
    for ext in [".mp3", ".m4a", ".wav", ".webm", ".ogg", ""]:
        candidate = path.with_suffix(ext)
        if candidate.exists():
            actual = candidate
            break
    if not actual:
        # Try glob
        matches = list(path.parent.glob(f"{path.stem}.*"))
        if matches:
            actual = matches[0]

    if not actual:
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    segments, info = model.transcribe(
        str(actual),
        beam_size=5,
        language=None,  # auto-detect
        vad_filter=True,
    )

    transcript_segments = []
    full_text_parts = []

    for segment in segments:
        transcript_segments.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
        })
        full_text_parts.append(segment.text.strip())

    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "segments": transcript_segments,
        "full_text": " ".join(full_text_parts),
    }


def process_job(job_id: str, url: str):
    """Background worker for a transcription job."""
    job = jobs[job_id]
    try:
        job["status"] = "downloading"
        job["message"] = "Downloading audio..."

        output_path = str(DOWNLOAD_DIR / job_id)
        info = download_audio(url, output_path)
        job["video_info"] = info

        job["status"] = "transcribing"
        job["message"] = "Transcribing audio..."

        result = transcribe_audio(output_path)
        job["result"] = result
        job["status"] = "done"
        job["message"] = "Complete"

    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)

    finally:
        # Clean up audio files
        for f in DOWNLOAD_DIR.glob(f"{job_id}*"):
            try:
                f.unlink()
            except OSError:
                pass


def process_upload_job(job_id: str, file_path: str, filename: str):
    """Background worker for uploaded file transcription."""
    job = jobs[job_id]
    try:
        job["status"] = "transcribing"
        job["message"] = "Transcribing audio..."
        job["video_info"] = {"title": filename, "duration": 0, "uploader": "Upload", "thumbnail": ""}

        result = transcribe_audio(file_path)
        job["result"] = result
        job["status"] = "done"
        job["message"] = "Complete"

    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)

    finally:
        try:
            Path(file_path).unlink()
        except OSError:
            pass


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "URL is required"}), 400

    url = data["url"].strip()
    platform = detect_platform(url)

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "url": url,
        "platform": platform,
        "status": "queued",
        "message": "Starting...",
        "video_info": None,
        "result": None,
        "created_at": time.time(),
    }

    thread = threading.Thread(target=process_job, args=(job_id, url), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "platform": platform})


@app.route("/api/transcribe/batch", methods=["POST"])
def api_transcribe_batch():
    data = request.get_json()
    if not data or not data.get("urls"):
        return jsonify({"error": "URLs are required"}), 400

    urls = [u.strip() for u in data["urls"] if u.strip()]
    if not urls:
        return jsonify({"error": "No valid URLs provided"}), 400

    job_ids = []
    for url in urls[:20]:  # Max 20 at a time
        job_id = str(uuid.uuid4())[:8]
        platform = detect_platform(url)
        jobs[job_id] = {
            "id": job_id,
            "url": url,
            "platform": platform,
            "status": "queued",
            "message": "Starting...",
            "video_info": None,
            "result": None,
            "created_at": time.time(),
        }
        thread = threading.Thread(target=process_job, args=(job_id, url), daemon=True)
        thread.start()
        job_ids.append({"job_id": job_id, "url": url, "platform": platform})

    return jsonify({"jobs": job_ids})


@app.route("/api/transcribe/upload", methods=["POST"])
def api_transcribe_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    job_id = str(uuid.uuid4())[:8]
    ext = Path(file.filename).suffix or ".mp3"
    file_path = str(DOWNLOAD_DIR / f"{job_id}{ext}")
    file.save(file_path)

    jobs[job_id] = {
        "id": job_id,
        "url": f"upload://{file.filename}",
        "platform": "upload",
        "status": "queued",
        "message": "Starting...",
        "video_info": None,
        "result": None,
        "created_at": time.time(),
    }

    thread = threading.Thread(
        target=process_upload_job,
        args=(job_id, file_path, file.filename),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id, "platform": "upload"})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/history")
def api_history():
    completed = [
        j for j in jobs.values()
        if j["status"] == "done"
    ]
    completed.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(completed[:50])


if __name__ == "__main__":
    print("\n  Transcriber running at http://localhost:5000\n")
    app.run(debug=False, port=5000)
