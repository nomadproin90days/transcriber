import os
import uuid
import json
import time
import re
import secrets
import threading
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB upload limit
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

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


def validate_url(url: str) -> bool:
    """Reject non-HTTP URLs and local/private addresses."""
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return False
    # Block local/private IPs
    blocked = ['localhost', '127.0.0.1', '0.0.0.0', '10.', '172.16.', '192.168.', '[::1]', 'file://']
    return not any(b in url.lower() for b in blocked)


def download_audio(url: str, output_path: str) -> dict:
    """Download video, extract a thumbnail frame, then extract audio."""
    if not validate_url(url):
        raise ValueError("Invalid URL. Only public HTTP/HTTPS URLs are allowed.")
    import yt_dlp
    import subprocess

    # Step 1: Download full video (we need it for the thumbnail frame)
    video_path = output_path + "_video"
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": video_path + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Find the downloaded video file
    video_file = None
    for f in DOWNLOAD_DIR.glob(f"{Path(video_path).name}.*"):
        if f.suffix in ('.mp4', '.webm', '.mkv', '.mov', '.flv'):
            video_file = f
            break

    # Step 2: Extract a thumbnail frame from the video using ffmpeg
    thumb_path = DOWNLOAD_DIR / f"{Path(output_path).name}_thumb.jpg"
    if video_file:
        try:
            # Grab a frame from 1 second in (or 0 if video is very short)
            duration = info.get("duration", 0)
            seek_time = min(1, duration / 2) if duration and duration > 0 else 0
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(seek_time),
                    "-i", str(video_file),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(thumb_path),
                ],
                capture_output=True,
                timeout=15,
            )
        except Exception as e:
            print(f"[thumbnail] ffmpeg frame extract failed: {e}")

    # Step 3: Extract audio from the video
    audio_path = output_path + ".mp3"
    if video_file:
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_file),
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-q:a", "2",
                    audio_path,
                ],
                capture_output=True,
                timeout=60,
            )
        except Exception as e:
            print(f"[audio] ffmpeg extract failed: {e}")

    # Clean up video file (keep thumb and audio)
    if video_file:
        try:
            video_file.unlink()
        except OSError:
            pass

    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", "Unknown"),
        "has_thumbnail": thumb_path.exists(),
        "original_url": url,
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
        # Clean up audio files but KEEP the thumbnail
        for f in DOWNLOAD_DIR.glob(f"{job_id}*"):
            if "_thumb.jpg" in f.name:
                continue  # keep thumbnail for serving
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


@app.route("/api/thumbnail/<job_id>")
def api_thumbnail(job_id):
    """Serve the locally extracted thumbnail frame."""
    from flask import send_file
    thumb_path = DOWNLOAD_DIR / f"{job_id}_thumb.jpg"
    if thumb_path.exists():
        return send_file(str(thumb_path), mimetype="image/jpeg")
    return "", 404


@app.route("/api/download-video", methods=["POST"])
def api_download_video():
    """Download video file and serve it to the user."""
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "URL is required"}), 400

    url = data["url"].strip()
    if not validate_url(url):
        return jsonify({"error": "Invalid URL"}), 400

    import yt_dlp

    job_id = str(uuid.uuid4())[:8]
    output_path = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")

    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Find the downloaded file
        video_file = None
        for f in DOWNLOAD_DIR.glob(f"{job_id}.*"):
            video_file = f
            break

        if not video_file:
            return jsonify({"error": "Download failed"}), 500

        from flask import send_file
        title = info.get("title", "video")
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:80]

        return send_file(
            str(video_file),
            as_attachment=True,
            download_name=f"{safe_title}{video_file.suffix}",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up after sending
        for f in DOWNLOAD_DIR.glob(f"{job_id}.*"):
            try:
                f.unlink()
            except OSError:
                pass


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"error": "URL is required"}), 400

    url = data["url"].strip()
    if not validate_url(url):
        return jsonify({"error": "Invalid URL. Only public HTTP/HTTPS URLs are allowed."}), 400

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

    safe_name = secure_filename(file.filename)
    allowed_ext = {'.mp4', '.mp3', '.wav', '.m4a', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.flac'}
    ext = Path(safe_name).suffix.lower() or ".mp3"
    if ext not in allowed_ext:
        return jsonify({"error": f"File type {ext} not supported"}), 400

    job_id = str(uuid.uuid4())[:8]
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
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  Transcriber running at http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
