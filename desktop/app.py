import re
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.request import Request, urlopen

import yt_dlp

APP_NAME = "VidLoom"
QUALITYS = [2160, 1440, 1080, 720, 480, 360, 240, 144]
BG = "#030612"
CARD = "#08132d"
CARD2 = "#0b1734"
TEXT = "#eef4ff"
MUTED = "#91a3c9"
BLUE = "#2677ff"
PURPLE = "#743cff"
BORDER = "#244a9d"


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def ydl_options():
    # Do not force a single YouTube player client. yt-dlp's current
    # extractor selection is more reliable across changing source responses.
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "http_headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"},
    }


def normalize_url(value):
    text = (value or "").strip()
    # Accept pasted text containing a URL, not only a pure URL field.
    match = re.search(r"https?://[^\s<>'\"]+", text, re.I)
    if match:
        text = match.group(0).rstrip(".,);]")
    elif re.match(r"^(www\.)?[a-z0-9.-]+\.[a-z]{2,}(/|$)", text, re.I):
        text = "https://" + text
    return text


def valid_url(url):
    return bool(re.match(r"^https?://[^\s]+$", url, re.I))


def format_heights(info):
    out = set()
    for f in info.get("formats") or []:
        try:
            h = int(f.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if h > 0 and f.get("vcodec") not in (None, "none"):
            out.add(h)
    return out


def progressive_heights(info):
    out = set()
    for f in info.get("formats") or []:
        try:
            h = int(f.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if h > 0 and f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none"):
            out.add(h)
    return out


def exact_format(info, height):
    if height not in format_heights(info):
        return None
    if ffmpeg_available():
        return f"bestvideo[height={height}]+bestaudio/best[height={height}]"
    if height in progressive_heights(info):
        return f"best[height={height}][vcodec!=none][acodec!=none]"
    return None


def conversion_source(info, target):
    higher = [h for h in format_heights(info) if h > target]
    if not higher or not ffmpeg_available():
        return None
    return f"bestvideo[height={min(higher)}]+bestaudio/best[height={min(higher)}]"


def human_bytes(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB"


class VidLoomApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VidLoom — Professional Video Downloader")
        self.geometry("1240x820")
        self.minsize(1020, 700)
        self.configure(bg=BG)
        self.info = None
        self.thumb_ref = None
        self.output_dir = Path.home() / "Downloads" / "VidLoom"
        self.mode = "video"
        self.quality_value = None
        self._build()

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("VL.Horizontal.TProgressbar", troughcolor="#0b1734", background=BLUE, bordercolor="#0b1734", lightcolor=BLUE, darkcolor=BLUE)

        # Premium header with subtle glow strips.
        top = tk.Frame(self, bg=BG, height=78)
        top.pack(fill="x")
        tk.Frame(top, bg=PURPLE, height=2).pack(fill="x")
        brand = tk.Frame(top, bg=BG)
        brand.pack(side="left", padx=28, pady=12)
        logo = tk.Label(brand, text="▷", fg="#35d8ff", bg=BG, font=("Segoe UI", 34, "bold"))
        logo.pack(side="left", padx=(0, 10))
        names = tk.Frame(brand, bg=BG)
        names.pack(side="left")
        tk.Label(names, text="VidLoom", fg=TEXT, bg=BG, font=("Segoe UI", 24, "bold")).pack(anchor="w")
        tk.Label(names, text="VIDEO DOWNLOADER", fg="#9b8cff", bg=BG, font=("Segoe UI", 7, "bold")).pack(anchor="w")
        tk.Label(top, text="FAST  •  PRIVATE  •  LOCAL", fg=MUTED, bg=BG, font=("Segoe UI", 10, "bold")).pack(side="right", padx=30)

        self._search_bar()
        self._platforms()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=30, pady=(0, 24))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self.preview = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BLUE)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._preview_contents()

        self.panel = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        self.panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._download_panel()

    def _context_menu(self, widget):
        menu = tk.Menu(self, tearoff=0, bg="#0b1734", fg=TEXT, activebackground=BLUE, activeforeground="white", bd=0)
        menu.add_command(label="Paste", command=lambda: self._paste_into(widget))
        menu.add_command(label="Copy", command=lambda: self._copy_from(widget))
        menu.add_command(label="Cut", command=lambda: self._cut_from(widget))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._select_all(widget))

        def popup(event):
            widget.focus_set()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        widget.bind("<Button-3>", popup)
        widget.bind("<Control-Button-3>", popup)

    def _paste_into(self, widget):
        try:
            text = self.clipboard_get()
            widget.delete(0, "end")
            widget.insert(0, normalize_url(text))
        except tk.TclError:
            pass

    def _copy_from(self, widget):
        try:
            self.clipboard_clear()
            self.clipboard_append(widget.selection_get())
        except tk.TclError:
            pass

    def _cut_from(self, widget):
        self._copy_from(widget)
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def _select_all(self, widget):
        widget.select_range(0, "end")
        widget.icursor("end")

    def _search_bar(self):
        title = tk.Label(self, text="DOWNLOAD VIDEOS & AUDIO", fg=TEXT, bg=BG, font=("Segoe UI", 22, "bold"))
        title.pack(pady=(18, 3))
        tk.Label(self, text="Paste a public media URL and let VidLoom detect the real formats", fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(pady=(0, 12))

        outer = tk.Frame(self, bg=BLUE, padx=2, pady=2)
        outer.pack(fill="x", padx=42, pady=(0, 18))
        inner = tk.Frame(outer, bg="#070f24")
        inner.pack(fill="x")
        tk.Label(inner, text="🔗", fg="#63d8ff", bg="#070f24", font=("Segoe UI", 15)).pack(side="left", padx=(14, 8))
        self.url = tk.Entry(inner, bg="#070f24", fg=TEXT, insertbackground="white", relief="flat", font=("Segoe UI", 12))
        self.url.pack(side="left", fill="x", expand=True, ipady=13)
        self.url.bind("<FocusIn>", self._clear_placeholder)
        self.url.bind("<Return>", lambda _e: self.fetch())
        self._context_menu(self.url)
        tk.Button(inner, text="GO  →", command=self.fetch, bg=BLUE, fg="white", activebackground="#4b8dff", relief="flat", font=("Segoe UI", 11, "bold"), padx=28, pady=10).pack(side="right", padx=4, pady=4)

        self.url.insert(0, "Paste video URL here…")

    def _platforms(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=42, pady=(0, 16))
        platforms = [("▶", "YouTube", "#ff3030"), ("♪", "TikTok", "#40d9ff"), ("◎", "Instagram", "#ff4b9b"), ("f", "Facebook", "#3182ff"), ("𝕏", "X", "#dbe6ff"), ("●", "Reddit", "#ff6b36"), ("V", "Vimeo", "#45b8ff"), ("P", "Pinterest", "#ff3d67"), ("▣", "Twitch", "#a66bff")]
        for icon, name, accent in platforms:
            box = tk.Frame(row, bg=CARD2, highlightthickness=1, highlightbackground="#1b356d", width=100, height=64)
            box.pack(side="left", expand=True, fill="x", padx=3)
            box.pack_propagate(False)
            tk.Label(box, text=icon, fg=accent, bg=CARD2, font=("Segoe UI", 19, "bold")).pack(pady=(4, 0))
            tk.Label(box, text=name, fg="#cbd7f1", bg=CARD2, font=("Segoe UI", 8)).pack()

    def _preview_contents(self):
        tk.Label(self.preview, text="MEDIA PREVIEW", fg="#8ba1cf", bg=CARD, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(18, 8))
        self.thumb = tk.Label(self.preview, text="Paste a public URL above\nand click GO", fg="#9aaad0", bg="#040914", font=("Segoe UI", 18, "bold"), justify="center")
        self.thumb.pack(fill="both", expand=True, padx=20, pady=8)
        self.title_label = tk.Label(self.preview, text="", fg=TEXT, bg=CARD, font=("Segoe UI", 14, "bold"), anchor="w", justify="left", wraplength=700)
        self.title_label.pack(fill="x", padx=20, pady=(5, 2))
        self.meta_label = tk.Label(self.preview, text="Public media only • DRM/login-protected media is not bypassed", fg=MUTED, bg=CARD, font=("Segoe UI", 9), anchor="w")
        self.meta_label.pack(fill="x", padx=20, pady=(0, 18))

    def _download_panel(self):
        tk.Label(self.panel, text="Download Video", fg=TEXT, bg=CARD, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(18, 16))
        tabs = tk.Frame(self.panel, bg=CARD)
        tabs.pack(fill="x", padx=20)
        self.video_btn = tk.Button(tabs, text="▣  Video", command=lambda: self.set_mode("video"), relief="flat", bg=PURPLE, fg="white", font=("Segoe UI", 10, "bold"), pady=10)
        self.video_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.audio_btn = tk.Button(tabs, text="♫  Audio", command=lambda: self.set_mode("audio"), relief="flat", bg="#101e40", fg="#a8b4d4", font=("Segoe UI", 10, "bold"), pady=10)
        self.audio_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        tk.Label(self.panel, text="Select Quality", fg=TEXT, bg=CARD, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(22, 6))
        self.quality_list = tk.Listbox(self.panel, bg="#071027", fg="#dce6ff", selectbackground="#225fe0", selectforeground="white", relief="flat", height=9, font=("Segoe UI", 10), activestyle="none")
        self.quality_list.pack(fill="x", padx=20)
        self.quality_list.bind("<<ListboxSelect>>", self._quality_selected)
        self.quality_hint = tk.Label(self.panel, text="Analyze a URL to see REAL available qualities.", fg=MUTED, bg=CARD, font=("Segoe UI", 9), wraplength=350, justify="left")
        self.quality_hint.pack(anchor="w", padx=20, pady=(8, 12))

        self.download_btn = tk.Button(self.panel, text="↓  DOWNLOAD", command=self.download, state="disabled", relief="flat", bg=BLUE, fg="white", activebackground="#4d91ff", font=("Segoe UI", 12, "bold"), pady=12)
        self.download_btn.pack(fill="x", padx=20, pady=(4, 12))
        self.progress = ttk.Progressbar(self.panel, style="VL.Horizontal.TProgressbar", maximum=100)
        self.progress.pack(fill="x", padx=20, pady=(4, 8))
        self.status = tk.Label(self.panel, text="Ready", fg="#b7c6e7", bg=CARD, font=("Segoe UI", 9), wraplength=350, justify="left")
        self.status.pack(anchor="w", padx=20, pady=(0, 8))
        self.folder_label = tk.Label(self.panel, text=f"Save: {self.output_dir}", fg="#687ca7", bg=CARD, font=("Segoe UI", 8), wraplength=350, justify="left")
        self.folder_label.pack(anchor="w", padx=20)
        tk.Button(self.panel, text="Choose folder", command=self.browse, bg="#101e40", fg="#b8c5e4", relief="flat", pady=7).pack(fill="x", padx=20, pady=(8, 18))

    def _clear_placeholder(self, *_):
        if self.url.get() == "Paste video URL here…":
            self.url.delete(0, "end")

    def set_mode(self, mode):
        self.mode = mode
        active, inactive = PURPLE, "#101e40"
        self.video_btn.config(bg=active if mode == "video" else inactive, fg="white" if mode == "video" else "#a8b4d4")
        self.audio_btn.config(bg=active if mode == "audio" else inactive, fg="white" if mode == "audio" else "#a8b4d4")

    def browse(self):
        selected = filedialog.askdirectory(initialdir=str(self.output_dir.parent))
        if selected:
            self.output_dir = Path(selected)
            self.folder_label.config(text=f"Save: {self.output_dir}")

    def fetch(self):
        url = normalize_url(self.url.get())
        if not valid_url(url) or url == "https://paste-a-public-video-url-here":
            messagebox.showwarning(APP_NAME, "Paste a valid public video URL first.")
            return
        self.url.delete(0, "end")
        self.url.insert(0, url)
        self.info = None
        self.quality_value = None
        self.quality_list.delete(0, "end")
        self.download_btn.config(state="disabled")
        self.progress["value"] = 0
        self.status.config(text="Detecting URL… connecting to the source and reading real formats…")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            with yt_dlp.YoutubeDL(ydl_options()) as ydl:
                info = ydl.extract_info(url, download=False)
            self.info = info
            heights = format_heights(info)
            self.after(0, lambda: self._show_info(info, heights))
        except Exception as exc:
            self.after(0, lambda e=exc: self.status.config(text=self.clean_error(e)))

    def _show_info(self, info, heights):
        self.quality_list.delete(0, "end")
        for h in QUALITYS:
            available = h in heights
            self.quality_list.insert("end", f"{'●' if available else '○'}  {h}p   • {'AVAILABLE' if available else 'not available'}")
            if not available:
                self.quality_list.itemconfig("end", fg="#5d6d92")
        self.quality_value = None
        self.title_label.config(text=info.get("title") or "Untitled media")
        self.meta_label.config(text=f"{info.get('extractor_key') or info.get('extractor') or 'Source'}  •  {info.get('duration_string') or 'Unknown duration'}  •  Public media only")
        self.quality_hint.config(text="Real source qualities only. No silent downgrade. Select an AVAILABLE quality.")
        self.status.config(text="URL detected successfully. Select a real available quality.")
        self._set_thumbnail(info.get("thumbnail"))

    def _set_thumbnail(self, url):
        if not url:
            self.thumb.config(text="No thumbnail available", image="")
            return
        self.thumb.config(text="Loading preview…", image="")
        threading.Thread(target=self._thumbnail_worker, args=(url,), daemon=True).start()

    def _thumbnail_worker(self, url):
        try:
            from io import BytesIO
            from PIL import Image, ImageTk
            data = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read()
            image = Image.open(BytesIO(data)).convert("RGB")
            image.thumbnail((780, 410))
            photo = ImageTk.PhotoImage(image)
            self.after(0, lambda p=photo: self._apply_thumbnail(p))
        except Exception:
            self.after(0, lambda: self.thumb.config(text="Preview unavailable", image=""))

    def _apply_thumbnail(self, photo):
        self.thumb_ref = photo
        self.thumb.config(image=photo, text="")

    def _quality_selected(self, *_):
        if not self.info:
            return
        sel = self.quality_list.curselection()
        if not sel:
            return
        h = QUALITYS[sel[0]]
        if h not in format_heights(self.info):
            self.quality_value = None
            self.download_btn.config(state="disabled")
            self.quality_hint.config(text="This quality is not available. Please select another quality.")
            return
        self.quality_value = h
        self.download_btn.config(state="normal")
        self.quality_hint.config(text=f"Selected {h}p. VidLoom will request this quality exactly.")

    def download(self):
        if not self.info or not self.quality_value:
            return
        self.download_btn.config(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.quality_value
            fmt = exact_format(self.info, target)
            convert = False
            if not fmt:
                fmt = conversion_source(self.info, target)
                convert = bool(fmt)
            if not fmt:
                raise RuntimeError(f"{target}p is not available from this source. Please select another quality.")

            opts = ydl_options()
            opts.update({
                "outtmpl": str(self.output_dir / "%(title).120s-%(id)s.%(ext)s"),
                "format": "bestaudio/best" if self.mode == "audio" else fmt,
                "progress_hooks": [self.progress_hook],
            })
            if self.mode == "video" and convert:
                opts["merge_output_format"] = "mp4"
                opts["postprocessor_args"] = ["-vf", f"scale=-2:{target}", "-c:v", "libx264", "-crf", "23", "-c:a", "aac"]
            elif self.mode == "video" and ffmpeg_available():
                opts["merge_output_format"] = "mp4"
            if self.mode == "audio" and ffmpeg_available():
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url.get().strip()])
            self.after(0, lambda: self.status.config(text=f"Download complete • {target}p • saved to {self.output_dir}"))
            self.after(0, lambda: messagebox.showinfo(APP_NAME, "Download completed successfully."))
        except Exception as exc:
            self.after(0, lambda e=exc: self.status.config(text=self.clean_error(e)))
        finally:
            self.after(0, lambda: self.download_btn.config(state="normal" if self.quality_value else "disabled"))

    def progress_hook(self, data):
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = done * 100 / total if total else 0
            speed = data.get("speed") or 0
            eta = data.get("eta")
            text = f"Downloading… {pct:.1f}% • {human_bytes(speed)}/s"
            if eta is not None:
                text += f" • ETA {int(eta)}s"
            self.after(0, lambda p=pct, t=text, d=done, tt=total: self._update_progress(p, t, d, tt))

    def _update_progress(self, pct, text, done, total):
        self.progress.config(value=pct)
        self.status.config(text=text + (f" • {human_bytes(done)} / {human_bytes(total)}" if total else f" • {human_bytes(done)}"))

    @staticmethod
    def clean_error(exc):
        text = str(exc).replace("ERROR: ", "").strip()
        low = text.lower()
        if "private" in low:
            return "This media is private and cannot be downloaded."
        if "login" in low or "sign in" in low or "cookies" in low:
            return "This media requires login and cannot be downloaded here."
        if "drm" in low:
            return "DRM-protected media cannot be downloaded."
        if "unsupported url" in low:
            return "This website is not supported by the installed yt-dlp extractor."
        if "unable to extract" in low or "unexpected response" in low or "403" in low or "429" in low:
            return "The source could not be read right now. Please check the public URL and try again."
        return text[:500] or "Unable to process this link."


if __name__ == "__main__":
    VidLoomApp().mainloop()
