import os
import re
import shutil
import smtplib
import sqlite3
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, render_template, request, send_from_directory, send_file, jsonify

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "analytics.db"

DOWNLOAD_ROOT = Path(tempfile.gettempdir()) / "downloads"
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key"
)

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    "tiktok.com", "www.tiktok.com",
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "fb.watch",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "box.com", "www.box.com",
    "dailymotion.com", "www.dailymotion.com",
    "soundcloud.com", "www.soundcloud.com",
}

QUALITY_HEIGHTS = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "4K": 2160,
}

DOWNLOAD_JOBS = {}
DOWNLOAD_JOBS_LOCK = threading.Lock()


class DownloadCancelled(Exception):
    pass


class DownloadPaused(Exception):
    pass


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                platform TEXT NOT NULL,
                quality TEXT NOT NULL,
                file_type TEXT NOT NULL,
                source_url TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def send_notification(subject, body):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipient = os.getenv("NOTIFICATION_EMAIL", "azankokarai1122@gmail.com")

    if not all([smtp_host, smtp_username, smtp_password, recipient]):
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_username
    message["To"] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
    except Exception as error:
        app.logger.warning("Notification email failed: %s", error)


def clean_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()

    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError("That platform is not enabled, or the URL is invalid.")

    return value


def platform_for(url):
    host = (urlparse(url).hostname or "").lower().replace("www.", "")

    if "youtu" in host:
        return "YouTube"
    if "tiktok" in host:
        return "TikTok"
    if "instagram" in host:
        return "Instagram"
    if "facebook" in host or host == "fb.watch":
        return "Facebook"
    if host in {"twitter.com", "x.com"}:
        return "X / Twitter"
    if "box.com" in host:
        return "Box"
    if "dailymotion" in host:
        return "Dailymotion"
    if "soundcloud" in host:
        return "SoundCloud"
    return host


def yt_options():
    """
    Cross-platform yt-dlp configuration.

    IMPORTANT:
    Do not hard-code a Windows Deno/FFmpeg path on Railway.
    If a local executable exists, it is used; otherwise yt-dlp
    can use the executable available on PATH.
    """
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "geo_bypass": False,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
    }

    deno_path = os.getenv("DENO_PATH") or shutil.which("deno")
    if deno_path:
        options["js_runtimes"] = {
            "deno": {"path": deno_path}
        }
    else:
        # Deno is the default supported JS runtime when installed.
        options["js_runtimes"] = {
            "deno": {"path": None}
        }

    ffmpeg_path = (
        os.getenv("FFMPEG_PATH")
        or shutil.which("ffmpeg")
    )

    if ffmpeg_path:
        ffmpeg_path = Path(ffmpeg_path)

        if ffmpeg_path.is_file():
            options["ffmpeg_location"] = str(
                ffmpeg_path.parent
            )
        else:
            options["ffmpeg_location"] = str(
                ffmpeg_path
            )

    # Cookies were never actually being passed to yt-dlp before, which is
    # a main cause of "Sign in to confirm you're not a bot" errors.
    # Set COOKIES_FILE env var to a full path, or just drop a cookies.txt
    # file next to app.py and it will be picked up automatically.
    cookies_path = os.getenv("COOKIES_FILE") or str(BASE_DIR / "cookies.txt")
    if Path(cookies_path).is_file():
        options["cookiefile"] = cookies_path

    # Fallback player client — helps bypass the bot-check on some requests
    # even when no cookies file is present.
    options["extractor_args"] = {
        "youtube": {
            "player_client": ["android", "web"],
        }
    }

    return options


def new_download_job(url, mode, quality):
    job_id = uuid.uuid4().hex
    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="vidloom_",
            dir=DOWNLOAD_ROOT,
        )
    )

    job = {
        "id": job_id,
        "url": url,
        "mode": mode,
        "quality": quality,
        "status": "starting",
        "percent": 0.0,
        "downloaded_bytes": 0,
        "total_bytes": 0,
        "speed": 0,
        "eta": None,
        "error": None,
        "file_path": None,
        "filename": None,
        "title": None,
        "platform": platform_for(url),
        "file_type": "MP3" if mode == "audio" else "MP4",
        "temp_dir": str(temp_dir),
        "pause_requested": False,
        "cancel_requested": False,
    }

    with DOWNLOAD_JOBS_LOCK:
        DOWNLOAD_JOBS[job_id] = job

    return job_id


def get_job(job_id):
    with DOWNLOAD_JOBS_LOCK:
        return DOWNLOAD_JOBS.get(job_id)


def update_job(job_id, **values):
    with DOWNLOAD_JOBS_LOCK:
        job = DOWNLOAD_JOBS.get(job_id)
        if job:
            job.update(values)


def is_network_error(error):
    message = str(error).lower()
    network_errors = (
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "connection refused",
        "urlopen error",
        "network is unreachable",
        "temporary failure",
        "incomplete read",
        "remote end closed",
        "connection error",
        "http error 429",
        "http error 502",
        "http error 503",
        "http error 504",
    )
    return any(item in message for item in network_errors)


def progress_hook(job_id):
    def hook(data):
        job = get_job(job_id)

        if not job:
            raise DownloadCancelled()

        if job.get("cancel_requested"):
            raise DownloadCancelled()

        if job.get("pause_requested"):
            raise DownloadPaused()

        status = data.get("status")

        if status == "downloading":
            downloaded = int(data.get("downloaded_bytes") or 0)
            total = int(
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or 0
            )

            percent = (downloaded / total * 100) if total else 0.0

            update_job(
                job_id,
                status="downloading",
                downloaded_bytes=downloaded,
                total_bytes=total,
                percent=max(0.0, min(100.0, percent)),
                speed=float(data.get("speed") or 0),
                eta=data.get("eta"),
            )

        elif status == "finished":
            downloaded = int(data.get("downloaded_bytes") or 0)
            total = int(
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or downloaded
            )

            update_job(
                job_id,
                status="processing",
                downloaded_bytes=downloaded,
                total_bytes=total,
                percent=100.0 if total else 0.0,
                speed=0,
                eta=0,
            )

    return hook


def cleanup_job_files(job):
    temp_dir = job.get("temp_dir")
    if not temp_dir:
        return

    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

def choose_video_format(info, requested_height):
    formats = info.get("formats") or []

    available_heights = sorted({
        int(fmt["height"])
        for fmt in formats
        if fmt.get("height")
        and fmt.get("vcodec") not in (None, "none")
    })

    if not available_heights:
        raise ValueError(
            "No video quality is available for this video."
        )

    lower_or_equal = [
        height
        for height in available_heights
        if height <= requested_height
    ]

    if lower_or_equal:
        source_height = max(lower_or_equal)
    else:
        source_height = min(available_heights)

    # Prefer MP4 video + M4A audio.
    # If unavailable, fall back to the best compatible streams.
    video_format = (
        f"bestvideo[height={source_height}][ext=mp4]"
        f"/bestvideo[height={source_height}]"
    )

    audio_format = (
        "bestaudio[ext=m4a]"
        "/bestaudio"
    )

    merged_format = (
        f"({video_format})+({audio_format})"
        f"/best[height={source_height}][ext=mp4]"
        f"/best[height={source_height}]"
        f"/best"
    )

    return merged_format, source_height


def run_download_job(job_id):
    job = get_job(job_id)
    if not job:
        return

    temp_dir = Path(job["temp_dir"])
    url = job["url"]
    mode = job["mode"]
    quality = job["quality"]

    try:
        update_job(job_id, status="preparing", error=None)

        requested_height = QUALITY_HEIGHTS.get(quality, 720)

        output_template = str(temp_dir / "%(id)s.%(ext)s")

        options = yt_options()
        options.update({
            "outtmpl": output_template,
            "progress_hooks": [progress_hook(job_id)],
            "continuedl": True,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 5,
        })

        # Get metadata once. This also catches YouTube access errors before
        # the download thread starts writing a partial file.
        update_job(job_id, status="preparing")

        with yt_dlp.YoutubeDL(yt_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title") or "video"
        update_job(
            job_id,
            title=title,
            platform=platform_for(url),
        )

        if mode == "audio":
            options.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
            file_type = "MP3"

        else:
            selected_format, source_height = choose_video_format(
                info,
                requested_height,
            )

            app.logger.info(
                "Requested quality=%s, selected source height=%s",
                quality,
                source_height,
            )

            options["format"] = selected_format
            options["merge_output_format"] = "mp4"
            file_type = "MP4"

        update_job(job_id, status="downloading")

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        # Find the final file only after yt-dlp/FFmpeg has completed.
        if mode == "audio":
            candidates = list(temp_dir.glob("*.mp3"))
        else:
            candidates = list(temp_dir.glob("*.mp4"))

        if not candidates:
            candidates = [
                path for path in temp_dir.iterdir()
                if path.is_file()
                and not path.name.endswith(".part")
                and not path.name.endswith(".ytdl")
            ]

        if not candidates:
            raise RuntimeError(
                "Downloaded file could not be found after processing."
            )

        downloaded = max(candidates, key=lambda p: p.stat().st_size)

        if downloaded.stat().st_size <= 0:
            raise RuntimeError("Downloaded file is empty.")

        title = info.get("title") or title
        platform = platform_for(url)
        final_size = downloaded.stat().st_size

        with get_db() as connection:
            connection.execute(
                """
                INSERT INTO downloads(
                    title, platform, quality, file_type,
                    source_url, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    platform,
                    quality,
                    file_type,
                    url,
                    now_iso(),
                ),
            )

        update_job(
            job_id,
            status="completed",
            downloaded_bytes=final_size,
            total_bytes=final_size,
            percent=100.0,
            speed=0,
            eta=0,
            file_path=str(downloaded),
            filename=downloaded.name,
            title=title,
            platform=platform,
            file_type=file_type,
        )

    except DownloadPaused:
        update_job(
            job_id,
            status="paused",
            pause_requested=False,
        )

    except DownloadCancelled:
        update_job(
            job_id,
            status="cancelled",
            cancel_requested=False,
        )
        cleanup_job_files(job)

    except Exception as error:
        app.logger.exception("Download job failed: %s", error)

        if is_network_error(error):
            update_job(
                job_id,
                status="network_error",
                error=(
                    "Network issue detected. Your partial download was "
                    "kept. Press Resume after the connection returns."
                ),
            )
        else:
            update_job(
                job_id,
                status="error",
                error=str(error),
            )


@app.route("/")
def index():
    with get_db() as connection:
        connection.execute(
            "INSERT INTO visits(created_at) VALUES (?)",
            (now_iso(),),
        )
    return render_template("index.html")


@app.route("/ads.txt")
def ads_txt():
    return send_from_directory(
        BASE_DIR,
        "ads.txt",
        mimetype="text/plain",
    )

@app.route("/sitemap.xml")
def sitemap():
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://avd.up.railway.app/</loc>
  </url>
</urlset>
"""
    return sitemap_xml, 200, {"Content-Type": "application/xml"}


@app.post("/api/info")
def api_info():
    try:
        payload = request.get_json(silent=True) or {}
        url = clean_url(payload.get("url", ""))

        with yt_dlp.YoutubeDL(yt_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = info.get("duration")
        if info.get("duration_string"):
            duration_text = info["duration_string"]
        elif duration:
            duration = int(duration)
            duration_text = f"{duration // 60}:{duration % 60:02d}"
        else:
            duration_text = "Unknown"

        view_count = info.get("view_count")

        return jsonify({
            "ok": True,
            "video": {
                "id": info.get("id"),
                "title": info.get("title") or "Untitled video",
                "creator": (
                    info.get("uploader")
                    or info.get("channel")
                    or "Unknown creator"
                ),
                "duration": duration_text,
                "views": (
                    f"{view_count:,}"
                    if view_count is not None
                    else "Not available"
                ),
                "thumbnail": info.get("thumbnail"),
                "platform": platform_for(url),
                "url": url,
            },
        })

    except Exception as error:
        app.logger.warning("Info error: %s", error)
        message = str(error)

        if "sign in to confirm you're not a bot" in message.lower():
            message = (
                "YouTube is currently asking this server to sign in or "
                "complete an anti-bot check. This cannot be permanently "
                "fixed by changing the download format."
            )

        return jsonify({
            "ok": False,
            "error": message,
        }), 400


@app.post("/api/download")
def api_download():
    try:
        payload = request.get_json(silent=True) or {}
        url = clean_url(payload.get("url", ""))
        mode = payload.get("mode", "video")
        quality = payload.get("quality", "720p")

        if mode not in {"video", "audio"}:
            raise ValueError("Unsupported media type.")

        if mode == "video" and quality not in QUALITY_HEIGHTS:
            raise ValueError("Unsupported video quality.")

        job_id = new_download_job(url, mode, quality)

        thread = threading.Thread(
            target=run_download_job,
            args=(job_id,),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "ok": True,
            "job_id": job_id,
        })

    except Exception as error:
        app.logger.exception("Could not start download: %s", error)
        return jsonify({
            "ok": False,
            "error": str(error),
        }), 400


@app.get("/api/download/<job_id>/status")
def download_status(job_id):
    job = get_job(job_id)

    if not job:
        return jsonify({
            "ok": False,
            "error": "Download job not found.",
        }), 404

    return jsonify({
        "ok": True,
        "job": {
            "id": job["id"],
            "status": job["status"],
            "percent": round(float(job.get("percent", 0)), 2),
            "downloaded_bytes": job.get("downloaded_bytes", 0),
            "total_bytes": job.get("total_bytes", 0),
            "speed": job.get("speed", 0),
            "eta": job.get("eta"),
            "error": job.get("error"),
            "title": job.get("title"),
        },
    })


@app.post("/api/download/<job_id>/pause")
def pause_download(job_id):
    job = get_job(job_id)

    if not job:
        return jsonify({"ok": False, "error": "Download job not found."}), 404

    if job["status"] != "downloading":
        return jsonify({
            "ok": False,
            "error": "Download is not currently running.",
        }), 400

    update_job(job_id, pause_requested=True)
    return jsonify({"ok": True})


@app.post("/api/download/<job_id>/resume")
def resume_download(job_id):
    job = get_job(job_id)

    if not job:
        return jsonify({"ok": False, "error": "Download job not found."}), 404

    if job["status"] not in {"paused", "network_error"}:
        return jsonify({
            "ok": False,
            "error": "Download is not paused or waiting for network.",
        }), 400

    update_job(
        job_id,
        status="starting",
        pause_requested=False,
        cancel_requested=False,
        error=None,
    )

    thread = threading.Thread(
        target=run_download_job,
        args=(job_id,),
        daemon=True,
    )
    thread.start()

    return jsonify({"ok": True})


@app.post("/api/download/<job_id>/cancel")
def cancel_download(job_id):
    job = get_job(job_id)

    if not job:
        return jsonify({"ok": False, "error": "Download job not found."}), 404

    update_job(job_id, cancel_requested=True)
    return jsonify({"ok": True})


@app.get("/api/download/<job_id>/file")
def download_file(job_id):
    job = get_job(job_id)

    if not job:
        return jsonify({"ok": False, "error": "Download job not found."}), 404

    if job["status"] != "completed":
        return jsonify({
            "ok": False,
            "error": "Download is not ready yet.",
        }), 409

    file_path = job.get("file_path")
    if not file_path:
        return jsonify({
            "ok": False,
            "error": "Downloaded file is missing.",
        }), 404

    path = Path(file_path)
    if not path.exists():
        return jsonify({
            "ok": False,
            "error": "Downloaded file no longer exists.",
        }), 404

    extension = "mp3" if job.get("mode") == "audio" else "mp4"

    safe_name = re.sub(
        r"[^\w\s.-]",
        "",
        job.get("title") or "video",
    ).strip()
    safe_name = safe_name[:90] or "video"

    return send_file(
        path,
        as_attachment=True,
        download_name=f"{safe_name}.{extension}",
        mimetype="audio/mpeg" if extension == "mp3" else "video/mp4",
    )


@app.post("/api/comments")
def api_comments():
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()[:80]
    comment = (payload.get("comment") or "").strip()[:1000]

    if len(name) < 2 or len(comment) < 3:
        return jsonify({
            "ok": False,
            "error": "Add your name and a useful comment.",
        }), 400

    timestamp = now_iso()

    with get_db() as connection:
        connection.execute(
            "INSERT INTO comments(name, comment, created_at) VALUES (?, ?, ?)",
            (name, comment, timestamp),
        )

    send_notification(
        "VidLoom VIDEO DOWNLOADER: new comment",
        f"User name: {name}\nComment: {comment}\nDate/time: {timestamp}",
    )

    return jsonify({
        "ok": True,
        "message": "Thanks, your feedback is saved.",
    })


@app.route("/admin")
def admin():
    if request.args.get("key") != os.getenv(
        "ADMIN_KEY",
        "change-admin-key",
    ):
        return "Admin access denied.", 403

    with get_db() as connection:
        visits = connection.execute(
            "SELECT COUNT(*) AS count FROM visits"
        ).fetchone()["count"]

        downloads = connection.execute(
            "SELECT COUNT(*) AS count FROM downloads"
        ).fetchone()["count"]

        comments = connection.execute(
            "SELECT COUNT(*) AS count FROM comments"
        ).fetchone()["count"]

        top_videos = connection.execute(
            """
            SELECT title, COUNT(*) AS count
            FROM downloads
            GROUP BY title
            ORDER BY count DESC
            LIMIT 5
            """
        ).fetchall()

        platforms = connection.execute(
            """
            SELECT platform, COUNT(*) AS count
            FROM downloads
            GROUP BY platform
            ORDER BY count DESC
            """
        ).fetchall()

    return render_template(
        "index.html",
        admin_data={
            "visits": visits,
            "downloads": downloads,
            "comments": comments,
            "top_videos": top_videos,
            "platforms": platforms,
        },
    )


@app.route("/googledd736139896dc604.html")
def google_verification():
    return send_from_directory(
        app.root_path,
        "googledd736139896dc604.html",
    )


init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )