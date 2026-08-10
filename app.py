import os
import re
import smtplib
import sqlite3
import tempfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, render_template, request, send_from_directory, send_file, jsonify
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "analytics.db"
import tempfile
from pathlib import Path

DOWNLOAD_ROOT = Path(tempfile.gettempdir()) / "downloads"
DOWNLOAD_ROOT.mkdir(exist_ok=True)
app = Flask(__name__)
# Railway deployment fix: send_file import
@app.route("/ads.txt")
def ads_txt():
    return send_from_directory(".", "ads.txt", mimetype="text/plain")

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key")

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    "tiktok.com",
    "www.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "fb.watch",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "box.com",
    "www.box.com",
    "dailymotion.com",
    "www.dailymotion.com",
    "soundcloud.com",
    "www.soundcloud.com",
}

QUALITY_HEIGHTS = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "4K": 2160,
}


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
    recipient = os.getenv(
        "NOTIFICATION_EMAIL",
        "azankokarai1122@gmail.com",
    )

    if not all([smtp_host, smtp_username, smtp_password, recipient]):
        app.logger.info(
            "Email skipped because SMTP environment variables are not configured."
        )
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
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        # Windows filename safety
        "restrictfilenames": True,
        "windowsfilenames": True,

        # Network
        "geo_bypass": False,

        # YouTube JavaScript runtime
        "js_runtimes": {
            "deno": {}
        },

        # FFmpeg
        "ffmpeg_location": r"C:\Users\AZAN KHAN\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-essentials_build\bin",
    }
@app.route("/")
def index():
    with get_db() as connection:
        connection.execute(
            "INSERT INTO visits(created_at) VALUES (?)",
            (now_iso(),),
        )

    return render_template("index.html")


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

        if not url:
            raise ValueError("Please enter a valid URL.")

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
            }
        })

    except Exception as error:
        app.logger.warning("Info error: %s", error)

        return jsonify({
            "ok": False,
            "error": (
                "Could not read this link. Make sure the media is public "
                "and the URL is correct."
            )
        }), 400

@app.post("/api/download")
def api_download():
    payload = request.get_json(silent=True) or {}

    try:
        url = clean_url(payload.get("url", ""))
        mode = payload.get("mode", "video")
        quality = payload.get("quality", "720p")

        if not url:
            raise ValueError("Please enter a valid URL.")

        if mode not in {"video", "audio"}:
            raise ValueError("Unsupported media type.")

        quality_map = {
            "360p": 360,
            "480p": 480,
            "720p": 720,
            "1080p": 1080,
            "1440p": 1440,
            "4K": 2160,
        }

        if mode == "video" and quality not in quality_map:
            raise ValueError("Unsupported video quality.")

        requested_height = quality_map.get(quality, 720)

        # -------------------------------------------------
        # Temporary download folder
        # -------------------------------------------------
        temp_dir = Path(
            tempfile.mkdtemp(
                prefix="vidloom_",
                dir=DOWNLOAD_ROOT
            )
        )

        output_template = str(
            temp_dir / "%(id)s.%(ext)s"
        )

        options = yt_options()

        options.update({
            "outtmpl": output_template,
            "noplaylist": True,
            "windowsfilenames": True,
            "restrictfilenames": True,
        })

        # -------------------------------------------------
        # AUDIO
        # -------------------------------------------------
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

        # -------------------------------------------------
        # VIDEO
        # -------------------------------------------------
        else:

            # First get available formats
            check_options = yt_options()

            with yt_dlp.YoutubeDL(check_options) as check_ydl:
                info_check = check_ydl.extract_info(
                    url,
                    download=False
                )

            formats = info_check.get("formats") or []

            # Find video heights
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

            # Never upscale
            if requested_height > max(available_heights):
                raise ValueError(
                    f"{quality} is not available for this video."
                )

            # Select requested quality or closest quality below it
            lower_or_equal = [
                h for h in available_heights
                if h <= requested_height
            ]

            if lower_or_equal:
                source_height = max(lower_or_equal)
            else:
                source_height = min(available_heights)

            app.logger.info(
                "Requested quality: %s, selected source height: %s",
                requested_height,
                source_height
            )

            # -------------------------------------------------
            # Prefer MP4 video + M4A audio
            # -------------------------------------------------
            video_format = (
                f"bestvideo[height={source_height}][ext=mp4]"
                f"/bestvideo[height={source_height}]"
            )

            audio_format = (
                "bestaudio[ext=m4a]"
                "/bestaudio"
            )

            combined_format = (
                f"{video_format}+{audio_format}"
                f"/best[height={source_height}][ext=mp4]"
                f"/best[height={source_height}]"
                f"/best"
            )

            options["format"] = combined_format
            options["merge_output_format"] = "mp4"

            file_type = "MP4"

        # -------------------------------------------------
        # DOWNLOAD
        # -------------------------------------------------
        app.logger.info("Starting %s download: %s", mode, url)

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

        # -------------------------------------------------
        # FIND DOWNLOADED FILE
        # -------------------------------------------------
        if mode == "audio":

            mp3_files = list(temp_dir.glob("*.mp3"))

            if not mp3_files:
                raise RuntimeError(
                    "MP3 file was not created."
                )

            downloaded = mp3_files[0]

        else:

            mp4_files = list(temp_dir.glob("*.mp4"))

            if not mp4_files:
                # Sometimes yt-dlp may produce another container
                all_files = [
                    f for f in temp_dir.iterdir()
                    if f.is_file()
                ]

                if not all_files:
                    raise RuntimeError(
                        "Downloaded video file could not be found."
                    )

                downloaded = all_files[0]

            else:
                downloaded = mp4_files[0]

        if not downloaded.exists():
            raise RuntimeError(
                "Downloaded file does not exist."
            )

        app.logger.info(
            "Download completed: %s",
            downloaded
        )

        # -------------------------------------------------
        # DATABASE
        # -------------------------------------------------
        title = info.get("title") or "video"
        platform = platform_for(url)
        timestamp = now_iso()

        with get_db() as connection:
            connection.execute(
                """
                INSERT INTO downloads(
                    title,
                    platform,
                    quality,
                    file_type,
                    source_url,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    platform,
                    quality,
                    file_type,
                    url,
                    timestamp,
                ),
            )

        # -------------------------------------------------
        # SEND FILE
        # -------------------------------------------------
        response = send_file(
            downloaded,
            as_attachment=True,
            download_name=(
                f"{info.get('id') or 'video'}.mp3"
                if mode == "audio"
                else f"{info.get('id') or 'video'}.mp4"
            ),
            mimetype=(
                "audio/mpeg"
                if mode == "audio"
                else "video/mp4"
            ),
        )

        return response

    except Exception as error:
        app.logger.exception(
            "Download error: %s",
            error
        )

        return jsonify({
            "ok": False,
            "error": str(error)
        }), 400


@app.post("/api/comments")
def api_comments():
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()[:80]
    comment = (payload.get("comment") or "").strip()[:1000]

    if len(name) < 2 or len(comment) < 3:
        return jsonify(
            {
                "ok": False,
                "error": "Add your name and a useful comment."
            }
        ), 400

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
        "message": "Thanks, your feedback is saved."
    })


@app.route("/admin")
def admin():
    if request.args.get("key") != os.getenv(
        "ADMIN_KEY",
        "change-admin-key"
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

    admin_data = {
        "visits": visits,
        "downloads": downloads,
        "comments": comments,
        "top_videos": top_videos,
        "platforms": platforms,
    }

    return render_template(
        "index.html",
        admin_data=admin_data
    )


init_db()


@app.route("/googledd736139896dc604.html")
def google_verification():
    return send_from_directory(
        app.root_path,
        "googledd736139896dc604.html"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )