import os
import re
import secrets
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
from urllib.parse import urlencode, urlparse

import requests
import yt_dlp
from flask import Flask, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from yt_dlp.utils import DownloadCancelled as YtDlpStopSignal

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "analytics.db"
DOWNLOAD_ROOT = Path(tempfile.gettempdir()) / "avd_downloads"
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"

QUALITY_HEIGHTS = {"144p": 144, "240p": 240, "360p": 360, "480p": 480, "720p": 720, "1080p": 1080, "1440p": 1440, "2K": 1440, "4K": 2160}
ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com", "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "v.redd.it", "redd.it",
    "vimeo.com", "www.vimeo.com", "player.vimeo.com", "dailymotion.com", "www.dailymotion.com", "dai.ly",
    "twitch.tv", "www.twitch.tv", "m.twitch.tv", "clips.twitch.tv", "soundcloud.com", "www.soundcloud.com", "snd.sc",
    "bilibili.com", "www.bilibili.com", "b23.tv", "pinterest.com", "www.pinterest.com", "pin.it",
}
DOWNLOAD_JOBS = {}
DOWNLOAD_JOBS_LOCK = threading.Lock()
FFMPEG_PATH = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH") or shutil.which("ffprobe")
FFMPEG_AVAILABLE = bool(FFMPEG_PATH and FFPROBE_PATH)


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS downloads (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, platform TEXT NOT NULL, quality TEXT NOT NULL, file_type TEXT NOT NULL, source_url TEXT, created_at TEXT NOT NULL, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT, google_sub TEXT UNIQUE, created_at TEXT NOT NULL);
        """)
        cols = {row["name"] for row in db.execute("PRAGMA table_info(downloads)").fetchall()}
        if "user_id" not in cols:
            db.execute("ALTER TABLE downloads ADD COLUMN user_id INTEGER")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with get_db() as db:
        return db.execute("SELECT id,name,email FROM users WHERE id=?", (uid,)).fetchone()


def clean_url(value):
    value = (value or "").strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Please enter a valid http or https URL.")
    allowed = {h[4:] if h.startswith("www.") else h for h in ALLOWED_HOSTS}
    if host not in ALLOWED_HOSTS and bare not in allowed:
        raise ValueError("This public platform is not currently supported.")
    return value


def platform_for(url):
    host = (urlparse(url).hostname or "").lower()
    tests = [("YouTube", "youtube"), ("TikTok", "tiktok"), ("Instagram", "instagram"), ("Facebook", "facebook"), ("X / Twitter", "twitter"), ("X / Twitter", "x.com"), ("Reddit", "reddit"), ("Vimeo", "vimeo"), ("Dailymotion", "dailymotion"), ("Twitch", "twitch"), ("SoundCloud", "soundcloud"), ("Bilibili", "bilibili"), ("Pinterest", "pinterest")]
    for name, needle in tests:
        if needle in host:
            return name
    if host in {"youtu.be"}: return "YouTube"
    if host in {"fb.watch"}: return "Facebook"
    if host in {"dai.ly"}: return "Dailymotion"
    if host in {"snd.sc"}: return "SoundCloud"
    if host in {"b23.tv"}: return "Bilibili"
    return host or "Unknown"


def humanize_error(error):
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(error or "")).strip()
    if msg.startswith("ERROR: "): msg = msg[7:]
    low = msg.lower()
    if "unsupported url" in low: return "This link is not supported."
    if "private" in low and "video" in low: return "This media is private and cannot be downloaded."
    if "login" in low or "sign in" in low or "cookies" in low: return "This media requires a login and cannot be downloaded here."
    if "drm" in low: return "This media is DRM-protected and cannot be downloaded."
    if "geo" in low and "restrict" in low: return "This media is region-restricted and unavailable from this server."
    if "requested format is not available" in low or "no video formats" in low: return "That exact quality is not available. Please select another quality."
    if "ffmpeg" in low or "ffprobe" in low: return "FFmpeg could not process this media on the server."
    return msg[:320] or "Could not read this public media link."


def base_options():
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "restrictfilenames": True, "windowsfilenames": True, "continuedl": True, "overwrites": True, "retries": 8, "fragment_retries": 8, "file_access_retries": 5, "socket_timeout": 30,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}}}
    if FFMPEG_PATH:
        p = Path(FFMPEG_PATH)
        opts["ffmpeg_location"] = str(p.parent if p.is_file() else p)
    cookies = os.getenv("COOKIES_FILE") or str(BASE_DIR / "cookies.txt")
    if Path(cookies).is_file(): opts["cookiefile"] = cookies
    return opts


def extract(url, download=False, options=None):
    options = options or base_options()
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=download)
    except Exception as first:
        if "tiktok.com" in url and (m := re.search(r"/video/(\d+)", url)):
            retry = f"https://www.tiktok.com/@_/video/{m.group(1)}"
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(retry, download=download)
        raise first


def choose_exact_format(info, requested):
    formats = info.get("formats") or []
    heights = sorted({int(f["height"]) for f in formats if f.get("height") and f.get("vcodec") not in (None, "none")})
    if not heights:
        raise ValueError("The source did not expose reliable video quality information. Please try another link.")
    if requested > max(heights):
        raise ValueError(f"Please select another quality. This source is only available up to {max(heights)}p.")
    source = max(h for h in heights if h <= requested)
    clause = f"={source}"
    progressive = f"best[height{clause}][ext=mp4][vcodec!=none][acodec!=none]/best[height{clause}][vcodec!=none][acodec!=none]"
    if FFMPEG_AVAILABLE:
        split = f"bestvideo[height{clause}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height{clause}]+bestaudio"
        return f"{split}/{progressive}", source
    return progressive, source


def new_job(url, mode, quality):
    jid = uuid.uuid4().hex
    folder = Path(tempfile.mkdtemp(prefix="avd_", dir=DOWNLOAD_ROOT))
    job = {"id": jid, "url": url, "mode": mode, "quality": quality, "status": "starting", "percent": 0.0, "downloaded_bytes": 0, "total_bytes": 0, "speed": 0.0, "eta": None, "error": None, "file_path": None, "filename": None, "title": None, "platform": platform_for(url), "user_id": session.get("user_id"), "temp_dir": str(folder), "pause_requested": False, "cancel_requested": False}
    with DOWNLOAD_JOBS_LOCK: DOWNLOAD_JOBS[jid] = job
    return jid


def get_job(jid):
    with DOWNLOAD_JOBS_LOCK: return DOWNLOAD_JOBS.get(jid)


def update_job(jid, **values):
    with DOWNLOAD_JOBS_LOCK:
        if jid in DOWNLOAD_JOBS: DOWNLOAD_JOBS[jid].update(values)


def hook(jid):
    def on_progress(data):
        job = get_job(jid)
        if not job or job.get("cancel_requested") or job.get("pause_requested"):
            raise YtDlpStopSignal("Stopped by user")
        if data.get("status") == "downloading":
            done = int(data.get("downloaded_bytes") or 0); total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            update_job(jid, status="downloading", downloaded_bytes=done, total_bytes=total, percent=(done / total * 100 if total else 0), speed=float(data.get("speed") or 0), eta=data.get("eta"))
        elif data.get("status") == "finished":
            done = int(data.get("downloaded_bytes") or 0)
            update_job(jid, status="processing", downloaded_bytes=done, percent=100, speed=0, eta=0)
    return on_progress


def find_final(folder, mode):
    wanted = ".mp3" if mode == "audio" else ".mp4"
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == wanted]
    if not files:
        raise RuntimeError("The server did not produce a final media file.")
    p = max(files, key=lambda x: x.stat().st_size)
    if p.stat().st_size < 1024: raise RuntimeError("The downloaded file is empty or invalid.")
    with p.open("rb") as f: head = f.read(64).lstrip().lower()
    if head.startswith(b"<html") or head.startswith(b"<!doctype") or head.startswith(b"{\"error"):
        raise RuntimeError("The source returned an error page instead of media.")
    return p


def run_job(jid):
    job = get_job(jid)
    if not job: return
    folder = Path(job["temp_dir"])
    try:
        update_job(jid, status="preparing")
        info = extract(job["url"], False)
        title = info.get("title") or "media"
        update_job(jid, title=title)
        opts = base_options(); opts["outtmpl"] = str(folder / "%(id)s.%(ext)s"); opts["progress_hooks"] = [hook(jid)]
        if job["mode"] == "audio":
            if not FFMPEG_AVAILABLE: raise RuntimeError("MP3 requires FFmpeg and ffprobe on the server.")
            opts["format"] = "bestaudio/best"; opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            file_type = "MP3"
        else:
            requested = QUALITY_HEIGHTS[job["quality"]]
            opts["format"], source = choose_exact_format(info, requested)
            if FFMPEG_AVAILABLE: opts["merge_output_format"] = "mp4"
            update_job(jid, source_height=source)
            file_type = "MP4"
        update_job(jid, status="downloading")
        with yt_dlp.YoutubeDL(opts) as ydl: info = ydl.extract_info(job["url"], download=True)
        final = find_final(folder, job["mode"]); size = final.stat().st_size
        with get_db() as db:
            db.execute("INSERT INTO downloads(title,platform,quality,file_type,source_url,created_at,user_id) VALUES(?,?,?,?,?,?,?)", (info.get("title") or title, platform_for(job["url"]), job["quality"], file_type, job["url"], now_iso(), job.get("user_id")))
        update_job(jid, status="completed", downloaded_bytes=size, total_bytes=size, percent=100, speed=0, eta=0, file_path=str(final), filename=final.name, title=info.get("title") or title)
    except Exception as error:
        stop = isinstance(error, YtDlpStopSignal)
        if not stop:
            cur = error
            for _ in range(5):
                if isinstance(cur, YtDlpStopSignal): stop = True; break
                cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
        if stop:
            j = get_job(jid) or {}
            if j.get("cancel_requested"):
                update_job(jid, status="cancelled", cancel_requested=False)
                shutil.rmtree(folder, ignore_errors=True)
            else: update_job(jid, status="paused", pause_requested=False)
        else:
            update_job(jid, status="error", error=humanize_error(error))
            app.logger.exception("download failed")


@app.get("/")
def index():
    with get_db() as db: db.execute("INSERT INTO visits(created_at) VALUES(?)", (now_iso(),))
    return render_template("index.html", user=current_user())


@app.post("/api/info")
def api_info():
    try:
        url = clean_url((request.get_json(silent=True) or {}).get("url"))
        info = extract(url, False)
        formats = info.get("formats") or []
        heights = sorted({int(f["height"]) for f in formats if f.get("height") and f.get("vcodec") not in (None, "none")}, reverse=True)
        return jsonify(ok=True, video={"id": info.get("id"), "title": info.get("title") or "Untitled media", "creator": info.get("uploader") or info.get("channel") or "Unknown creator", "duration": info.get("duration_string") or "Not available", "views": f"{int(info['view_count']):,}" if isinstance(info.get("view_count"), (int,float)) else "Not available", "thumbnail": info.get("thumbnail"), "platform": platform_for(url), "url": url, "qualities": heights})
    except Exception as error:
        return jsonify(ok=False, error=humanize_error(error)), 400


@app.post("/api/download")
def api_download():
    try:
        data = request.get_json(silent=True) or {}; url = clean_url(data.get("url")); mode = data.get("mode", "video"); quality = data.get("quality", "720p")
        if mode not in {"video", "audio"}: raise ValueError("Unsupported media type.")
        if mode == "video" and quality not in QUALITY_HEIGHTS: raise ValueError("Unsupported quality.")
        jid = new_job(url, mode, quality); threading.Thread(target=run_job, args=(jid,), daemon=True).start(); return jsonify(ok=True, job_id=jid)
    except Exception as error: return jsonify(ok=False, error=humanize_error(error)), 400


@app.get("/api/download/<jid>/status")
def download_status(jid):
    job = get_job(jid)
    if not job: return jsonify(ok=False, error="Download job not found."), 404
    return jsonify(ok=True, job={k: job.get(k) for k in ("id","status","percent","downloaded_bytes","total_bytes","speed","eta","error","title","source_height")})


@app.post("/api/download/<jid>/pause")
def pause(jid):
    job = get_job(jid)
    if not job: return jsonify(ok=False, error="Download job not found."), 404
    update_job(jid, pause_requested=True); return jsonify(ok=True)


@app.post("/api/download/<jid>/resume")
def resume(jid):
    job = get_job(jid)
    if not job or job.get("status") not in {"paused","error"}: return jsonify(ok=False, error="Download is not paused."), 400
    update_job(jid, status="starting", pause_requested=False, cancel_requested=False, error=None); threading.Thread(target=run_job,args=(jid,),daemon=True).start(); return jsonify(ok=True)


@app.post("/api/download/<jid>/cancel")
def cancel(jid):
    job = get_job(jid)
    if not job: return jsonify(ok=False, error="Download job not found."), 404
    update_job(jid, cancel_requested=True); return jsonify(ok=True)


@app.get("/api/download/<jid>/file")
def file_download(jid):
    job = get_job(jid)
    if not job or job.get("status") != "completed": return jsonify(ok=False, error="Download is not ready."), 409
    path = Path(job["file_path"])
    if not path.exists(): return jsonify(ok=False, error="Downloaded file is missing."), 404
    safe = re.sub(r"[^\w\s.-]", "", job.get("title") or "video").strip()[:90] or "video"
    ext = "mp3" if job["mode"] == "audio" else "mp4"
    return send_file(path, as_attachment=True, download_name=f"{safe}.{ext}", mimetype="audio/mpeg" if ext == "mp3" else "video/mp4")


@app.post("/api/comments")
def comments():
    data = request.get_json(silent=True) or {}; name = (data.get("name") or "").strip()[:80]; comment = (data.get("comment") or "").strip()[:1000]
    if len(name) < 2 or len(comment) < 3: return jsonify(ok=False,error="Add your name and feedback."),400
    with get_db() as db: db.execute("INSERT INTO comments(name,comment,created_at) VALUES(?,?,?)",(name,comment,now_iso()))
    send_feedback_email(name, comment)
    return jsonify(ok=True,message="Thanks! Your feedback was saved.")


def send_feedback_email(name, comment):
    host = os.getenv("SMTP_HOST"); username = os.getenv("SMTP_USERNAME"); password = os.getenv("SMTP_PASSWORD")
    if not all([host,username,password]): return
    msg = EmailMessage(); msg["Subject"]="All Video Downloader feedback"; msg["From"]=username; msg["To"]="azankokarai1122@gmail.com"; msg.set_content(f"From: {name}\n\n{comment}")
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT","587")), timeout=15) as s: s.starttls(); s.login(username,password); s.send_message(msg)
    except Exception as error: app.logger.warning("feedback email failed: %s",error)


@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}; name=(data.get("name") or "").strip()[:80]; email=(data.get("email") or "").strip().lower(); password=data.get("password") or ""
    if len(name)<2 or "@" not in email or len(password)<8: return jsonify(ok=False,error="Enter a name, valid email, and password of at least 8 characters."),400
    try:
        with get_db() as db:
            cur=db.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",(name,email,generate_password_hash(password),now_iso())); uid=cur.lastrowid
        session["user_id"]=uid; return jsonify(ok=True,user={"name":name,"email":email})
    except sqlite3.IntegrityError: return jsonify(ok=False,error="An account with this email already exists."),409


@app.post("/api/auth/login")
def login():
    data=request.get_json(silent=True) or {}; email=(data.get("email") or "").strip().lower(); password=data.get("password") or ""
    with get_db() as db: user=db.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not user or not user["password_hash"] or not check_password_hash(user["password_hash"],password): return jsonify(ok=False,error="Incorrect email or password."),401
    session["user_id"]=user["id"]; return jsonify(ok=True,user={"name":user["name"],"email":user["email"]})


@app.post("/api/auth/logout")
def logout(): session.clear(); return jsonify(ok=True)


@app.get("/api/auth/me")
def me():
    u=current_user(); return jsonify(ok=True,user=(dict(u) if u else None))


@app.get("/api/history")
def history():
    u=current_user()
    if not u: return jsonify(ok=True,items=[])
    with get_db() as db: rows=db.execute("SELECT id,title,platform,quality,file_type,source_url,created_at FROM downloads WHERE user_id=? ORDER BY id DESC LIMIT 100",(u["id"],)).fetchall()
    return jsonify(ok=True,items=[dict(r) for r in rows])


@app.get("/auth/google")
def google_start():
    client=os.getenv("GOOGLE_CLIENT_ID")
    if not client: return jsonify(ok=False,error="Google login is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on the server."),503
    state=secrets.token_urlsafe(24); session["oauth_state"]=state
    params={"client_id":client,"redirect_uri":url_for("google_callback",_external=True),"response_type":"code","scope":"openid email profile","state":state,"access_type":"online"}
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?"+urlencode(params))


@app.get("/auth/google/callback")
def google_callback():
    code=request.args.get("code"); state=request.args.get("state")
    if not code or not state or not secrets.compare_digest(state,session.pop("oauth_state", "")): return "Google login could not be verified.",400
    client=os.getenv("GOOGLE_CLIENT_ID"); secret=os.getenv("GOOGLE_CLIENT_SECRET"); redirect_uri=url_for("google_callback",_external=True)
    token=requests.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":client,"client_secret":secret,"redirect_uri":redirect_uri,"grant_type":"authorization_code"},timeout=15).json()
    access=token.get("access_token")
    if not access: return "Google login failed.",400
    profile=requests.get("https://openidconnect.googleapis.com/v1/userinfo",headers={"Authorization":f"Bearer {access}"},timeout=15).json()
    sub=profile.get("sub"); email=(profile.get("email") or "").lower(); name=profile.get("name") or email.split("@")[0]
    if not sub or not email: return "Google did not return a usable profile.",400
    with get_db() as db:
        user=db.execute("SELECT id FROM users WHERE google_sub=? OR email=?",(sub,email)).fetchone()
        if user: uid=user["id"]; db.execute("UPDATE users SET google_sub=?,name=? WHERE id=?",(sub,name,uid))
        else: uid=db.execute("INSERT INTO users(name,email,google_sub,created_at) VALUES(?,?,?,?)",(name,email,sub,now_iso())).lastrowid
    session["user_id"]=uid; return redirect(url_for("index"))


@app.get("/privacy")
def privacy(): return render_template("privacy.html")
@app.get("/about")
def about(): return render_template("about.html")
@app.get("/how-to-use")
def how_to_use(): return render_template("how-to-use.html")
@app.get("/faq")
def faq(): return render_template("faq.html")
@app.get("/terms")
def terms(): return render_template("terms.html")
@app.get("/manifest.json")
def manifest(): return send_from_directory(BASE_DIR,"manifest.json",mimetype="application/manifest+json")
@app.get("/service-worker.js")
def sw(): return send_from_directory(BASE_DIR,"service-worker.js",mimetype="application/javascript")
@app.get("/ads.txt")
def ads(): return send_from_directory(BASE_DIR,"ads.txt",mimetype="text/plain")


@app.get("/admin")
def admin():
    if request.args.get("key") != os.getenv("ADMIN_KEY", "change-admin-key"): return "Admin access denied.",403
    with get_db() as db:
        data={"visits":db.execute("SELECT COUNT(*) c FROM visits").fetchone()["c"],"downloads":db.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"],"comments":db.execute("SELECT COUNT(*) c FROM comments").fetchone()["c"]}
    return jsonify(data)


init_db()
if __name__ == "__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=os.getenv("FLASK_DEBUG","0")=="1")
