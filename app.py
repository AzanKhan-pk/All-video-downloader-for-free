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
        "restrictfilenames": True,
        "geo_bypass": False,
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

        QUALITY_MAP = {
            "360p": 360,
            "480p": 480,
            "720p": 720,
            "1080p": 1080,
            "1440p": 1440,
            "4K": 2160,
        }

        if mode == "video" and quality not in QUALITY_MAP:
            raise ValueError("Unsupported video quality.")

        height = QUALITY_MAP.get(quality, 720)

        temp_dir = Path(
            tempfile.mkdtemp(
                prefix="avd_",
                dir=DOWNLOAD_ROOT
            )
        )

        output_template = str(
            temp_dir / "%(title)s.%(ext)s"
        )

        options = yt_options()
        options["outtmpl"] = output_template

        # AUDIO
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

        # VIDEO
        else:
            # Get the available formats from the source
            with yt_dlp.YoutubeDL(yt_options()) as check_ydl:
                info_check = check_ydl.extract_info(
                    url,
                    download=False
                )

            formats = info_check.get("formats") or []

            # Find the highest available video resolution
            available_heights = sorted({
                int(fmt.get("height"))
                for fmt in formats
                if fmt.get("height")
                and fmt.get("vcodec") not in (None, "none")
            })

            if not available_heights:
                raise ValueError(
                    "No video quality is available for this video."
                )

            # If requested quality is higher than the source,
            # do not upscale it.
            if height > max(available_heights):
                raise ValueError(
                    f"{quality} is not available for this video. "
                    "Please select another quality."
                )

            # Find the best source quality that is >= requested quality.
            # This allows FFmpeg to create the requested lower resolution
            # when the exact resolution does not exist.
            source_heights = [
                h for h in available_heights
                if h >= height
            ]

            source_height = min(source_heights)

            # Download the selected source quality with best audio.
            options["format"] = (
                f"bestvideo[height={source_height}]+"
                f"bestaudio/"
                f"best[height={source_height}]"
            )

            options["merge_output_format"] = "mp4"

            # If the source resolution is higher than requested,
            # FFmpeg will resize the video to the requested height.
            if source_height > height:
                options["postprocessors"] = [{
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }]

                options["postprocessor_args"] = [
                    "-vf",
                    f"scale=-2:{height}",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "23",
                    "-preset",
                    "medium",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                ]

            file_type = "MP4"

        # DOWNLOAD
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=True
            )

            prepared_file = Path(
                ydl.prepare_filename(info)
            )

        # FIND DOWNLOADED FILE
        if mode == "audio":
            downloaded = prepared_file.with_suffix(".mp3")

        else:
            downloaded = prepared_file

            if not downloaded.exists():
                mp4_files = list(
                    temp_dir.glob("*.mp4")
                )

                if mp4_files:
                    downloaded = mp4_files[0]

        if not downloaded.exists():
            files = [
                f for f in temp_dir.iterdir()
                if f.is_file()
            ]

            if not files:
                raise RuntimeError(
                    "Downloaded file could not be found."
                )

            downloaded = files[0]

        # DATABASE
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

        # NOTIFICATION
        send_notification(
            "VIDLOOM: download",
            (
                f"Video title: {title}\n"
                f"Platform: {platform}\n"
                f"Quality: {quality}\n"
                f"File type: {file_type}\n"
                f"Date/time: {timestamp}"
            ),
        )

        # SAFE FILENAME
        extension = downloaded.suffix.lower()

        safe_name = re.sub(
            r"[^a-zA-Z0-9 _.-]",
            "",
            title or "video"
        )

        safe_name = safe_name[:90].strip()

        if not safe_name:
            safe_name = "VidLoom_Download"

        filename = f"{safe_name}{extension}"

        # SEND FILE
        response = send_file(
            downloaded,
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream",
            max_age=0,
        )

        response.headers["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )

        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )

        response.headers["Pragma"] = "no-cache"

        response.headers["X-Content-Type-Options"] = "nosniff"

        return response

    except ValueError as error:
        app.logger.warning(
            "Download validation error: %s",
            error
        )

        return jsonify({
            "ok": False,
            "error": str(error)
        }), 400

    except Exception as error:
        app.logger.exception(
            "Download error: %s",
            error
        )

        return jsonify({
            "ok": False,
            "error": (
                "Download failed. Make sure the URL is public "
                "and the selected quality is available."
            )
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
        "ALL VIDEO DOWNLOADER: new comment",
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