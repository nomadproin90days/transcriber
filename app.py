import os
import uuid
import json
import time
import re
import secrets
import logging
import threading
import mimetypes
from pathlib import Path

from flask import Flask, render_template, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB upload limit
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))


@app.after_request
def security_headers(response):
    origin = request.headers.get("Origin", "")
    allowed_origins = [
        "https://luxetidestudio.com",
        "https://www.luxetidestudio.com",
        "https://iamryanxmas-transcriber.hf.space",
        "http://localhost:5173",
        "http://localhost:5050",
    ]
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["X-Content-Type-Options"] = "nosniff"
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


def find_thumbnail_path(job_name: str) -> Path | None:
    """Locate the saved thumbnail for a job, regardless of extension."""
    matches = sorted(DOWNLOAD_DIR.glob(f"{job_name}_thumb.*"))
    return matches[0] if matches else None


def convert_thumbnail_to_jpg(src: Path, dest: Path) -> bool:
    """Convert a thumbnail to JPEG when ffmpeg can decode it."""
    import subprocess

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), str(dest)],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except Exception as exc:
        print(f"[thumbnail] ffmpeg conversion failed for {src.name}: {exc}")
        return False
    return dest.exists()


def store_thumbnail_file(src: Path, thumb_stem: Path) -> bool:
    """Persist a thumbnail so the browser can fetch it later."""
    suffix = src.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        dest = thumb_stem.with_suffix(suffix)
        src.replace(dest)
        return dest.exists()

    jpg_dest = thumb_stem.with_suffix(".jpg")
    if convert_thumbnail_to_jpg(src, jpg_dest):
        try:
            src.unlink()
        except OSError:
            pass
        return True

    fallback_dest = thumb_stem.with_suffix(suffix or ".bin")
    src.replace(fallback_dest)
    return fallback_dest.exists()


def thumbnail_extension_from_response(content_type: str, url: str) -> str:
    """Choose a file extension for a downloaded thumbnail."""
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    by_type = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type in by_type:
        return by_type[content_type]

    ext = Path(url.split("?", 1)[0]).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ext
    return ".jpg"


def download_audio(url: str, output_path: str) -> dict:
    """Download audio and thumbnail using yt-dlp."""
    if not validate_url(url):
        raise ValueError("Invalid URL. Only public HTTP/HTTPS URLs are allowed.")
    import yt_dlp
    import urllib.request
    import ssl

    job_name = Path(output_path).name
    thumb_stem = DOWNLOAD_DIR / f"{job_name}_thumb"

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
        "writethumbnail": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    }

    platform = detect_platform(url)
    logging.info(f"[yt-dlp] downloading from {platform}: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        logging.error(f"[yt-dlp] download failed for {platform} URL {url}: {type(exc).__name__}: {exc}")
        raise

    logging.info(f"[yt-dlp] download complete: {info.get('title', 'unknown')} ({info.get('duration', 0)}s)")

    # yt-dlp saves thumbnail as {output_path}.webp or .jpg or .png
    # Find it and convert to jpg if needed
    thumb_found = False
    for ext in [".webp", ".jpg", ".jpeg", ".png"]:
        src = Path(output_path + ext)
        if src.exists():
            thumb_found = store_thumbnail_file(src, thumb_stem)
            break

    # Fallback: try downloading thumbnail URL directly
    if not thumb_found:
        thumb_url = info.get("thumbnail", "")
        if not thumb_url:
            thumbnails = info.get("thumbnails", [])
            if thumbnails:
                thumb_url = thumbnails[-1].get("url", "")
        if thumb_url:
            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(thumb_url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                })
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    thumb_ext = thumbnail_extension_from_response(
                        resp.headers.get("Content-Type", ""),
                        thumb_url,
                    )
                    thumb_path = thumb_stem.with_suffix(thumb_ext)
                    with open(thumb_path, "wb") as f:
                        f.write(resp.read())
                thumb_found = thumb_path.exists()
            except Exception as e:
                print(f"[thumbnail] direct download failed: {e}")

    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", "Unknown"),
        "has_thumbnail": find_thumbnail_path(job_name) is not None,
        "original_url": url,
    }


def resolve_audio_path(audio_path: str) -> Path:
    """Find the audio file after yt-dlp/ffmpeg post-processing."""
    path = Path(audio_path)
    for ext in [".mp3", ".m4a", ".wav", ".webm", ".ogg", ""]:
        candidate = path.with_suffix(ext)
        if candidate.exists():
            return candidate

    matches = list(path.parent.glob(f"{path.stem}.*"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"Audio file not found: {audio_path}")


def build_transcript_result(segments, info) -> dict:
    """Normalize Whisper output for the API."""
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


def run_transcription_pass(model, actual: Path, *, vad_filter: bool) -> dict:
    """Run one transcription attempt with configurable VAD."""
    segments, info = model.transcribe(
        str(actual),
        beam_size=5,
        language=None,  # auto-detect
        vad_filter=vad_filter,
    )
    return build_transcript_result(segments, info)


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio file using faster-whisper."""
    model = get_whisper_model()
    actual = resolve_audio_path(audio_path)

    result = run_transcription_pass(model, actual, vad_filter=True)
    if result["segments"] or result["full_text"]:
        return result

    print(f"[transcribe] empty transcript for {actual.name} with VAD enabled; retrying without VAD")
    return run_transcription_pass(model, actual, vad_filter=False)


def format_timestamp(seconds: float, srt: bool = False) -> str:
    """Format seconds into HH:MM:SS,ms or HH:MM:SS.ms."""
    td = time.gmtime(seconds)
    ms = int((seconds % 1) * 1000)
    if srt:
        return f"{time.strftime('%H:%M:%S', td)},{ms:03d}"
    return f"{time.strftime('%H:%M:%S', td)}.{ms:03d}"


def generate_srt(segments: list[dict]) -> str:
    """Generate SRT format string from segments."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = format_timestamp(seg["start"], srt=True)
        end = format_timestamp(seg["end"], srt=True)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(f"{seg['text']}\n")
    return "\n".join(lines)


def generate_vtt(segments: list[dict]) -> str:
    """Generate WebVTT format string from segments."""
    lines = ["WEBVTT\n"]
    for seg in segments:
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        lines.append(f"{start} --> {end}")
        lines.append(f"{seg['text']}\n")
    return "\n".join(lines)


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
        logging.error(f"[job {job_id}] failed: {type(e).__name__}: {e}")
        job["status"] = "error"
        job["message"] = str(e)

    finally:
        # Clean up audio files but KEEP the thumbnail
        for f in DOWNLOAD_DIR.glob(f"{job_id}*"):
            if "_thumb." in f.name:
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


@app.route("/robots.txt")
def robots():
    from flask import Response
    content = "User-agent: *\nAllow: /\n\nSitemap: https://iamryanxmas-transcriber.hf.space/sitemap.xml\n"
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    from flask import Response
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://luxetidestudio.com/transcriber</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://luxetidestudio.com/instagram-transcript</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://luxetidestudio.com/tiktok-transcript</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://luxetidestudio.com/youtube-transcript</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>"""
    return Response(content, mimetype="application/xml")


@app.route("/api/thumbnail/<job_id>")
def api_thumbnail(job_id):
    """Serve the locally extracted thumbnail frame."""
    from flask import send_file
    thumb_path = find_thumbnail_path(job_id)
    if thumb_path and thumb_path.exists():
        mimetype = mimetypes.guess_type(str(thumb_path))[0] or "application/octet-stream"
        return send_file(str(thumb_path), mimetype=mimetype)
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
        logging.info(f"[yt-dlp] video download requested: {url}")
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


@app.route("/api/export/<job_id>/<file_format>")
def api_export(job_id, file_format):
    """Export the transcript in SRT, VTT, or TXT format."""
    job = jobs.get(job_id)
    if not job or job.get("status") != "done" or not job.get("result"):
        return jsonify({"error": "Job not found or not complete"}), 404

    segments = job["result"]["segments"]
    title = job.get("video_info", {}).get("title", "transcript")
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:80]

    if file_format == "srt":
        content = generate_srt(segments)
        mimetype = "text/plain"
        filename = f"{safe_title}.srt"
    elif file_format == "vtt":
        content = generate_vtt(segments)
        mimetype = "text/vtt"
        filename = f"{safe_title}.vtt"
    elif file_format == "txt":
        content = job["result"]["full_text"]
        mimetype = "text/plain"
        filename = f"{safe_title}.txt"
    else:
        return jsonify({"error": "Invalid format. Supported: srt, vtt, txt"}), 400

    from flask import Response
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  Transcriber running at http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
