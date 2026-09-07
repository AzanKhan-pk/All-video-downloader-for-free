import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"), static_url_path="/static")

QUALITY_HEIGHTS = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080, "1440p": 1440, "4K": 2160}
ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch", "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "v.redd.it", "redd.it", "vimeo.com", "www.vimeo.com",
    "player.vimeo.com", "dailymotion.com", "www.dailymotion.com", "dai.ly", "twitch.tv", "www.twitch.tv", "m.twitch.tv",
    "clips.twitch.tv", "soundcloud.com", "www.soundcloud.com", "snd.sc", "bilibili.com", "www.bilibili.com", "b23.tv",
    "pinterest.com", "www.pinterest.com", "pin.it",
}


def clean_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Please enter a valid http or https URL.")
    allowed = {h[4:] if h.startswith("www.") else h for h in ALLOWED_HOSTS}
    if host not in ALLOWED_HOSTS and bare not in allowed:
        raise ValueError("This platform is not currently supported.")
    return value


def platform_for(url):
    host = (urlparse(url).hostname or "").lower()
    names = [("youtube", "YouTube"), ("tiktok", "TikTok"), ("instagram", "Instagram"), ("facebook", "Facebook"),
             ("reddit", "Reddit"), ("vimeo", "Vimeo"), ("dailymotion", "Dailymotion"), ("twitch", "Twitch"),
             ("soundcloud", "SoundCloud"), ("bilibili", "Bilibili"), ("pinterest", "Pinterest")]
    for needle, name in names:
        if needle in host:
            return name
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return "X / Twitter"
    return host or "Unknown"


def ydl_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }


def friendly_error(exc):
    text = str(exc).replace("ERROR: ", "").strip()
    low = text.lower()
    if "unsupported url" in low:
        return "This link is not supported."
    if "private" in low:
        return "This media is private."
    if "sign in" in low or "login" in low or "cookies" in low:
        return "This media requires login and cannot be downloaded here."
    if "drm" in low:
        return "DRM-protected media cannot be downloaded."
    if "unavailable" in low:
        return "This media is unavailable or the link is incorrect."
    if "requested format" in low or "no video formats" in low:
        return "No compatible downloadable format was found. Try another quality."
    return text[:300] or "Could not process this link."


def extract(url):
    with yt_dlp.YoutubeDL(ydl_options()) as ydl:
        return ydl.extract_info(url, download=False)


def available_qualities(info):
    heights = sorted({int(f["height"]) for f in (info.get("formats") or []) if f.get("height") and f.get("vcodec") not in (None, "none")}, reverse=True)
    return [h for h in heights if h >= 144]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/<page>")
def pages(page):
    allowed = {"privacy": "privacy.html", "about": "about.html", "how-to-use": "how-to-use.html", "faq": "faq.html", "terms": "terms.html"}
    if page in allowed:
        return render_template(allowed[page])
    if page == "ads.txt":
        return send_from_directory(ROOT, "ads.txt", mimetype="text/plain")
    if page == "manifest.json":
        return send_from_directory(ROOT, "manifest.json", mimetype="application/manifest+json")
    if page == "service-worker.js":
        return send_from_directory(ROOT, "service-worker.js", mimetype="application/javascript")
    if page == "robots.txt":
        return "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n", 200, {"Content-Type": "text/plain"}
    if page == "googledd736139896dc604.html":
        return send_from_directory(ROOT, page)
    return jsonify({"ok": False, "error": "Page not found."}), 404


@app.get("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    paths = ["/", "/about", "/how-to-use", "/faq", "/privacy", "/terms"]
    xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(f"<url><loc>{base}{p}</loc></url>" for p in paths) + "</urlset>"
    return xml, 200, {"Content-Type": "application/xml"}


@app.post("/api/info")
def api_info():
    try:
        payload = request.get_json(silent=True) or {}
        url = clean_url(payload.get("url"))
        info = extract(url)
        duration = info.get("duration")
        duration = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "Not available"
        views = f"{int(info['view_count']):,}" if isinstance(info.get("view_count"), (int, float)) else "Not available"
        return jsonify({"ok": True, "video": {
            "id": info.get("id"), "title": info.get("title") or "Untitled media",
            "creator": info.get("uploader") or info.get("channel") or "Unknown creator",
            "duration": duration, "views": views, "thumbnail": info.get("thumbnail"),
            "platform": platform_for(url), "url": url,
            "available_qualities": [f"{h}p" for h in available_qualities(info)],
        }})
    except Exception as exc:
        return jsonify({"ok": False, "error": friendly_error(exc)}), 400


@app.post("/api/download")
def api_download():
    temp_dir = Path(tempfile.mkdtemp(prefix="vidloom_"))
    try:
        payload = request.get_json(silent=True) or {}
        url = clean_url(payload.get("url"))
        mode = payload.get("mode", "video")
        quality = payload.get("quality", "720p")
        if mode not in {"video", "audio"}:
            raise ValueError("Unsupported media type.")
        options = ydl_options()
        if mode == "audio":
            options["format"] = "bestaudio/best"
        else:
            height = QUALITY_HEIGHTS.get(quality, 720)
            options["format"] = f"best[height<={height}][ext=mp4][vcodec!=none][acodec!=none]/best[height<={height}][vcodec!=none][acodec!=none]/best[height<={height}]/best"
        options["outtmpl"] = str(temp_dir / "%(title).80s-%(id)s.%(ext)s")
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
        files = [p for p in temp_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("The download finished without producing a file.")
        path = max(files, key=lambda p: p.stat().st_size)
        if path.stat().st_size < 1024:
            raise RuntimeError("The downloaded file is empty or invalid.")
        title = re.sub(r"[^\w\s.-]", "", info.get("title") or "video").strip()[:90] or "video"
        ext = path.suffix.lstrip(".").lower() or "bin"
        mimetype = "audio/*" if mode == "audio" else "video/mp4"
        return send_file(path, as_attachment=True, download_name=f"{title}.{ext}", mimetype=mimetype)
    except Exception as exc:
        return jsonify({"ok": False, "error": friendly_error(exc)}), 400
