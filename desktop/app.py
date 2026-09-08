import os
import re
import shutil
import sys
import threading
import tkinter as tk
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.request import Request, urlopen

import yt_dlp
from PIL import Image, ImageTk

APP_NAME = "VidLoom"
QUALITYS = [2160, 1440, 1080, 720, 480, 360, 240, 144]
BG = "#030612"
PANEL = "#07122a"
PANEL2 = "#0a1735"
TEXT = "#f3f7ff"
MUTED = "#8fa2ca"
BLUE = "#2378ff"
CYAN = "#1fd5ff"
PURPLE = "#743cff"
BORDER = "#1d55b5"


def resource_path(relative):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def ydl_options():
    # Use yt-dlp's current extractor defaults. Do not force a fragile
    # YouTube player client that can make otherwise public URLs fail.
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 8,
        "fragment_retries": 8,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            )
        },
    }


def normalize_url(value):
    text = (value or "").strip()
    match = re.search(r"https?://[^\s<>'\"]+", text, re.I)
    if match:
        text = match.group(0).rstrip(".,);]")
    elif re.match(r"^(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/|$)", text, re.I):
        text = "https://" + text
    return text


def valid_url(url):
    return bool(re.match(r"^https?://[^\s]+$", url or "", re.I))


def available_formats(info):
    """Return only real source video formats grouped by exact height."""
    result = {}
    for fmt in info.get("formats") or []:
        try:
            height = int(fmt.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if height not in QUALITYS:
            continue
        if fmt.get("vcodec") in (None, "none"):
            continue
        result.setdefault(height, []).append(fmt)
    return result


def exact_selector(info, height):
    """Build a selector that cannot silently fall back to another height."""
    formats = available_formats(info).get(height, [])
    if not formats:
        return None

    if ffmpeg_available():
        # Both branches require the requested height exactly.
        return f"bestvideo[height={height}]+bestaudio/best[height={height}]"

    progressive = [
        f for f in formats
        if f.get("acodec") not in (None, "none")
    ]
    if progressive:
        best = sorted(progressive, key=lambda f: (f.get("tbr") or 0), reverse=True)[0]
        return best.get("format_id")
    return None


def human_bytes(value):
    n = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class VidLoomApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VidLoom — Professional Video Downloader")
        self.geometry("1450x900")
        self.minsize(1120, 720)
        self.configure(bg=BG)

        self.info = None
        self.thumb_ref = None
        self.logo_ref = None
        self.output_dir = Path.home() / "Downloads" / "VidLoom"
        self.mode = "video"
        self.quality_value = None
        self.quality_map = {}
        self.fetching = False
        self.downloading = False

        self._build()

    def _build(self):
        self._header()
        self._address_bar()
        self._platforms()

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=30, pady=(0, 18))
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_columnconfigure(2, weight=0)
        shell.grid_rowconfigure(0, weight=1)

        self._sidebar(shell)

        self.preview = tk.Frame(
            shell, bg=PANEL, highlightthickness=1, highlightbackground=BORDER
        )
        self.preview.grid(row=0, column=1, sticky="nsew", padx=(12, 8))
        self._preview()

        self.panel = tk.Frame(
            shell, bg=PANEL, width=380,
            highlightthickness=1, highlightbackground=BORDER
        )
        self.panel.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        self.panel.grid_propagate(False)
        self._download_panel()
        self._bottom_status()

    def _header(self):
        bar = tk.Frame(self, bg=BG, height=70)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        logo_box = tk.Frame(bar, bg=BG)
        logo_box.pack(side="left", padx=(26, 10), pady=8)
        logo = self._load_logo((48, 48))
        if logo:
            self.logo_ref = logo
            tk.Label(logo_box, image=logo, bg=BG).pack(side="left", padx=(0, 10))
        else:
            tk.Label(logo_box, text="▷", fg=CYAN, bg=BG,
                     font=("Segoe UI", 30, "bold")).pack(side="left", padx=(0, 10))

        names = tk.Frame(logo_box, bg=BG)
        names.pack(side="left")
        tk.Label(names, text="VidLoom", fg=TEXT, bg=BG,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w")
        tk.Label(names, text="VIDEO DOWNLOADER", fg="#a28bff", bg=BG,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")

        nav = tk.Frame(bar, bg=BG)
        nav.pack(side="right", padx=28)
        for label in ("Home", "Downloader", "Platforms", "About", "Feedback", "Guide", "FAQ"):
            tk.Label(nav, text=label, fg=MUTED, bg=BG,
                     font=("Segoe UI", 9)).pack(side="left", padx=10)
        tk.Button(nav, text="⇩  Install App", command=self._install_info,
                  bg=PURPLE, fg="white", activebackground=BLUE, relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), padx=16, pady=8).pack(side="left", padx=(16, 0))
        tk.Frame(self, bg="#122d67", height=1).pack(fill="x")

    def _address_bar(self):
        title = tk.Frame(self, bg=BG)
        title.pack(fill="x", pady=(13, 8))
        tk.Label(title, text="Download Videos & Audios", fg=TEXT, bg=BG,
                 font=("Segoe UI", 28, "bold")).pack()
        tk.Label(title, text="Fast   ·   Simple   ·   Free", fg=MUTED, bg=BG,
                 font=("Segoe UI", 10)).pack(pady=(0, 8))

        outer = tk.Frame(self, bg=BLUE, padx=2, pady=2)
        outer.pack(fill="x", padx=170, pady=(0, 13))
        inner = tk.Frame(outer, bg="#061027")
        inner.pack(fill="x")
        tk.Label(inner, text="↗", fg=CYAN, bg="#061027",
                 font=("Segoe UI", 17, "bold")).pack(side="left", padx=(14, 9))

        self.url = tk.Entry(inner, bg="#061027", fg=TEXT, insertbackground="white",
                            relief="flat", font=("Segoe UI", 12))
        self.url.pack(side="left", fill="x", expand=True, ipady=12)
        self.url.bind("<Return>", lambda _e: self.fetch())
        self.url.bind("<FocusIn>", self._clear_placeholder)
        self.url.bind("<Button-3>", self._entry_context)
        self.url.insert(0, "Paste video URL here…")

        tk.Button(inner, text="Go  →", command=self.fetch, bg=BLUE, fg="white",
                  activebackground="#4c94ff", relief="flat", bd=0,
                  font=("Segoe UI", 11, "bold"), padx=24, pady=10).pack(side="right", padx=4, pady=4)

    def _platforms(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=165, pady=(0, 14))
        platforms = [
            ("▶", "YouTube", "#ff2d35"), ("♪", "TikTok", "#25f4ee"),
            ("◎", "Instagram", "#ff4f9a"), ("f", "Facebook", "#3182f6"),
            ("𝕏", "X", "#f2f5ff"), ("●", "Reddit", "#ff6b32"),
            ("V", "Vimeo", "#35b9ff"), ("P", "Pinterest", "#ff355f"),
            ("▣", "Twitch", "#a970ff")
        ]
        for icon, name, accent in platforms:
            box = tk.Frame(row, bg="#07142f", highlightthickness=1,
                           highlightbackground="#1a356d", width=100, height=62)
            box.pack(side="left", expand=True, fill="x", padx=3)
            box.pack_propagate(False)
            tk.Label(box, text=icon, fg=accent, bg="#07142f",
                     font=("Segoe UI", 19, "bold")).pack(pady=(4, 0))
            tk.Label(box, text=name, fg="#d0daf1", bg="#07142f",
                     font=("Segoe UI", 8)).pack()

    def _sidebar(self, shell):
        side = tk.Frame(shell, bg="#061027", width=225,
                        highlightthickness=1, highlightbackground="#163b7f")
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        for i, (icon, label, active) in enumerate([
            ("⌂", "Home", True), ("◷", "History", False),
            ("⇩", "Downloads", False), ("⚙", "Settings", False)
        ]):
            tk.Button(side, text=f"  {icon}   {label}", anchor="w",
                      command=lambda l=label: self._side_action(l),
                      bg="#1925a8" if active else "#061027",
                      fg="white" if active else "#c1cce5",
                      activebackground="#2838c5", activeforeground="white",
                      relief="flat", bd=0,
                      font=("Segoe UI", 10, "bold" if active else "normal"),
                      padx=16, pady=12).pack(fill="x", padx=12, pady=(14 if i == 0 else 3, 0))

        tk.Frame(side, bg="#17336d", height=1).pack(fill="x", padx=18, pady=18)
        card = tk.Frame(side, bg="#09183a", highlightthickness=1,
                        highlightbackground="#214a96")
        card.pack(fill="x", padx=12)
        tk.Label(card, text="⚡", fg="#c8b5ff", bg="#09183a",
                 font=("Segoe UI", 28, "bold")).pack(pady=(16, 4))
        tk.Label(card, text="Multiple Platforms", fg=TEXT, bg="#09183a",
                 font=("Segoe UI", 10, "bold")).pack()
        tk.Label(card, text="Download public media from\nYouTube, TikTok, Instagram\nand more.",
                 fg=MUTED, bg="#09183a", justify="left",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(7, 16))

        promo = tk.Frame(side, bg="#071634", highlightthickness=1,
                         highlightbackground="#193b79")
        promo.pack(fill="x", padx=12, pady=18)
        tk.Label(promo, text="♛", fg="#d7c5ff", bg="#071634",
                 font=("Segoe UI", 32, "bold")).pack(pady=(15, 4))
        tk.Label(promo, text="Turn Your\nVideos Into Memories", fg=TEXT,
                 bg="#071634", justify="center",
                 font=("Segoe UI", 11, "bold")).pack()
        tk.Label(promo, text="Download. Watch. Anytime.", fg=MUTED,
                 bg="#071634", font=("Segoe UI", 8)).pack(pady=(6, 16))

    def _preview(self):
        tk.Label(self.preview, text="YouTube  ▾", fg=TEXT, bg=PANEL,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(15, 8))
        search = tk.Frame(self.preview, bg="#061027")
        search.pack(fill="x", padx=18)
        tk.Label(search, text="⌕", fg=MUTED, bg="#061027",
                 font=("Segoe UI", 15)).pack(side="left", padx=10)
        self.inner_search = tk.Entry(search, bg="#061027", fg=MUTED,
                                     insertbackground=TEXT, relief="flat",
                                     font=("Segoe UI", 10))
        self.inner_search.pack(fill="x", expand=True, ipady=8)
        self.inner_search.insert(0, "Search YouTube…")
        self.inner_search.bind("<Return>", lambda _e: self._search_from_preview())

        self.thumb = tk.Label(self.preview,
                              text="Paste a public URL above\nand click Go to preview media",
                              fg="#9eacd0", bg="#040a18",
                              font=("Segoe UI", 18, "bold"), justify="center")
        self.thumb.pack(fill="both", expand=True, padx=18, pady=(14, 10))

        info = tk.Frame(self.preview, bg=PANEL)
        info.pack(fill="x", padx=18, pady=(0, 12))
        self.title_label = tk.Label(info, text="No media selected", fg=TEXT, bg=PANEL,
                                    font=("Segoe UI", 14, "bold"), anchor="w",
                                    justify="left", wraplength=700)
        self.title_label.pack(fill="x")
        self.meta_label = tk.Label(
            info, text="Public media only • DRM/login-protected content is not bypassed",
            fg=MUTED, bg=PANEL, font=("Segoe UI", 9), anchor="w"
        )
        self.meta_label.pack(fill="x", pady=(4, 0))

    def _download_panel(self):
        tk.Label(self.panel, text="Download Video", fg=TEXT, bg=PANEL,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=18, pady=(18, 14))
        tabs = tk.Frame(self.panel, bg=PANEL)
        tabs.pack(fill="x", padx=18)
        self.video_btn = tk.Button(tabs, text="▣  Video",
                                   command=lambda: self.set_mode("video"),
                                   bg=PURPLE, fg="white", relief="flat", bd=0,
                                   font=("Segoe UI", 10, "bold"), pady=10)
        self.video_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.audio_btn = tk.Button(tabs, text="♫  Audio",
                                   command=lambda: self.set_mode("audio"),
                                   bg="#0e2044", fg="#aebbd6", relief="flat", bd=0,
                                   font=("Segoe UI", 10, "bold"), pady=10)
        self.audio_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        qhead = tk.Frame(self.panel, bg=PANEL)
        qhead.pack(fill="x", padx=18, pady=(20, 6))
        tk.Label(qhead, text="Select Quality", fg=TEXT, bg=PANEL,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(qhead, text="Real available qualities", fg=CYAN, bg=PANEL,
                 font=("Segoe UI", 8, "bold")).pack(side="right")

        self.quality_list = tk.Listbox(
            self.panel, bg="#07122b", fg="#dce6ff",
            selectbackground="#1f61dd", selectforeground="white",
            relief="flat", bd=0, height=8, font=("Segoe UI", 10), activestyle="none"
        )
        self.quality_list.pack(fill="x", padx=18)
        self.quality_list.bind("<<ListboxSelect>>", self._quality_selected)

        self.quality_hint = tk.Label(
            self.panel, text="Analyze a public URL to see the real source formats.",
            fg=MUTED, bg=PANEL, font=("Segoe UI", 9), wraplength=335, justify="left"
        )
        self.quality_hint.pack(anchor="w", padx=18, pady=(8, 12))

        self.download_btn = tk.Button(
            self.panel, text="⇩  Download", command=self.download, state="disabled",
            bg="#25395f", fg="#7283a5", activebackground=BLUE,
            relief="flat", bd=0, font=("Segoe UI", 12, "bold"), pady=12
        )
        self.download_btn.pack(fill="x", padx=18, pady=(0, 10))

        self.progress = ttk.Progressbar(self.panel, maximum=100, mode="determinate")
        self.progress.pack(fill="x", padx=18, pady=(0, 7))
        self.status = tk.Label(self.panel, text="Ready", fg="#b9c8e6", bg=PANEL,
                               font=("Segoe UI", 9), wraplength=335, justify="left")
        self.status.pack(anchor="w", padx=18)
        self.stats = tk.Label(self.panel, text="0 B  •  —/s  •  ETA —", fg=MUTED,
                              bg=PANEL, font=("Segoe UI", 8))
        self.stats.pack(anchor="w", padx=18, pady=(6, 0))
        self.folder_label = tk.Label(self.panel, text=f"Save: {self.output_dir}",
                                     fg="#687ca8", bg=PANEL, font=("Segoe UI", 8),
                                     wraplength=335, justify="left")
        self.folder_label.pack(anchor="w", padx=18, pady=(8, 0))
        tk.Button(self.panel, text="Choose download folder", command=self.browse,
                  bg="#0e2044", fg="#bdc9e1", relief="flat", bd=0, pady=7
                  ).pack(fill="x", padx=18, pady=(7, 18))

    def _bottom_status(self):
        strip = tk.Frame(self, bg="#040b1c", height=34)
        strip.pack(fill="x", side="bottom")
        strip.pack_propagate(False)
        for text in ("⚡  Fast Downloads", "▣  HD Quality", "♢  Secure & Safe"):
            tk.Label(strip, text=text, fg="#aebcdb", bg="#040b1c",
                     font=("Segoe UI", 8)).pack(side="left", padx=28)
        tk.Label(strip, text="VidLoom • Local Windows downloader", fg="#5f719b",
                 bg="#040b1c", font=("Segoe UI", 8)).pack(side="right", padx=25)

    # ---------- URL/context interactions ----------
    def _entry_context(self, event):
        menu = tk.Menu(self, tearoff=False, bg="#0b1734", fg=TEXT,
                       activebackground=BLUE, activeforeground="white", bd=0)
        menu.add_command(label="Paste", command=self._paste_url)
        menu.add_command(label="Copy", command=self._copy_url)
        menu.add_command(label="Cut", command=self._cut_url)
        menu.add_separator()
        menu.add_command(label="Select All", command=self._select_url)
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()

    def _paste_url(self):
        try:
            value = self.clipboard_get()
            self.url.delete(0, "end")
            self.url.insert(0, normalize_url(value))
            self.url.focus_set()
        except tk.TclError:
            pass

    def _copy_url(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.url.selection_get())
        except tk.TclError:
            self.clipboard_clear()
            self.clipboard_append(self.url.get())

    def _cut_url(self):
        self._copy_url()
        try:
            self.url.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def _select_url(self):
        self.url.select_range(0, "end")
        self.url.icursor("end")

    def _clear_placeholder(self, *_):
        if self.url.get() == "Paste video URL here…":
            self.url.delete(0, "end")

    def _search_from_preview(self):
        text = self.inner_search.get().strip()
        if text and text != "Search YouTube…":
            self.url.delete(0, "end")
            self.url.insert(0, normalize_url(text))
            self.fetch()

    # ---------- app actions ----------
    def _side_action(self, label):
        if label == "Downloads":
            try:
                os.startfile(str(self.output_dir))
            except Exception:
                messagebox.showinfo(APP_NAME, f"Downloads folder:\n{self.output_dir}")
        elif label == "Settings":
            self.browse()
        elif label == "History":
            messagebox.showinfo(APP_NAME, "Download history is stored locally by the app's current download folder.")

    def _install_info(self):
        messagebox.showinfo(APP_NAME, "VidLoom Windows app. Android builds are published separately by the project.")

    def _load_logo(self, size):
        try:
            for path in (
                resource_path("static/logo.png"),
                Path(__file__).resolve().parent.parent / "static" / "logo.png",
            ):
                if path.exists():
                    image = Image.open(path).convert("RGBA")
                    image.thumbnail(size, Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(image)
        except Exception:
            return None
        return None

    def set_mode(self, mode):
        self.mode = mode
        active, inactive = PURPLE, "#0e2044"
        self.video_btn.config(bg=active if mode == "video" else inactive,
                              fg="white" if mode == "video" else "#aebbd6")
        self.audio_btn.config(bg=active if mode == "audio" else inactive,
                              fg="white" if mode == "audio" else "#aebbd6")
        self.download_btn.config(state="disabled")
        self.quality_value = None

    def browse(self):
        selected = filedialog.askdirectory(initialdir=str(self.output_dir))
        if selected:
            self.output_dir = Path(selected)
            self.folder_label.config(text=f"Save: {self.output_dir}")

    # ---------- real yt-dlp detection ----------
    def fetch(self):
        if self.fetching:
            return
        url = normalize_url(self.url.get())
        if not valid_url(url):
            messagebox.showwarning(APP_NAME, "Paste a valid public media URL first.")
            return

        self.url.delete(0, "end")
        self.url.insert(0, url)
        self.info = None
        self.quality_map = {}
        self.quality_value = None
        self.quality_list.delete(0, "end")
        self.download_btn.config(state="disabled", bg="#25395f", fg="#7283a5")
        self.progress["value"] = 0
        self.stats.config(text="Reading source formats…")
        self.status.config(text="Detecting media and reading REAL source formats…")
        self.fetching = True
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            with yt_dlp.YoutubeDL(ydl_options()) as ydl:
                info = ydl.extract_info(url, download=False)
            self.after(0, lambda: self._show_info(info))
        except Exception as exc:
            self.after(0, lambda e=exc: self._fetch_failed(e))
        finally:
            self.fetching = False

    def _show_info(self, info):
        self.info = info
        self.quality_map = available_formats(info)
        self.quality_list.delete(0, "end")

        for height in QUALITYS:
            formats = self.quality_map.get(height, [])
            if formats:
                sizes = [f.get("filesize") or f.get("filesize_approx") for f in formats]
                size = max(sizes) if any(sizes) else None
                suffix = f"  •  {human_bytes(size)}" if size else ""
                self.quality_list.insert("end", f"●  {height}p{suffix}  •  AVAILABLE")
            else:
                self.quality_list.insert("end", f"○  {height}p  •  NOT AVAILABLE")
                self.quality_list.itemconfig("end", fg="#56698f")

        title = info.get("title") or "Untitled media"
        extractor = info.get("extractor_key") or info.get("extractor") or "Source"
        duration = info.get("duration_string") or "Unknown duration"
        self.title_label.config(text=title)
        self.meta_label.config(text=f"{extractor}  •  {duration}  •  Public media only")
        self.status.config(text="Media detected. Select one of the REAL available qualities.")
        if self.quality_map:
            self.quality_hint.config(text="Only exact source heights are selectable. No silent downgrade.")
        else:
            self.quality_hint.config(text="No downloadable video formats were exposed by this public source.")
        self._set_thumbnail(info.get("thumbnail"))

    def _fetch_failed(self, exc):
        self.status.config(text=self.clean_error(exc))
        self.stats.config(text="Detection failed")
        self.quality_hint.config(text="Try another public URL or update VidLoom.")
        self.quality_list.delete(0, "end")
        self.download_btn.config(state="disabled")

    def _set_thumbnail(self, url):
        if not url:
            self.thumb.config(text="No thumbnail available", image="")
            return
        self.thumb.config(text="Loading preview…", image="")
        threading.Thread(target=self._thumbnail_worker, args=(url,), daemon=True).start()

    def _thumbnail_worker(self, url):
        try:
            data = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read()
            image = Image.open(BytesIO(data)).convert("RGB")
            image.thumbnail((900, 500), Image.Resampling.LANCZOS)
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
        selected = self.quality_list.curselection()
        if not selected:
            return
        height = QUALITYS[selected[0]]
        if height not in self.quality_map:
            self.quality_value = None
            self.download_btn.config(state="disabled", bg="#25395f", fg="#7283a5")
            self.quality_hint.config(text="This quality is not available. Please select another quality.")
            return
        selector = exact_selector(self.info, height)
        if not selector:
            self.quality_value = None
            self.download_btn.config(state="disabled", bg="#25395f", fg="#7283a5")
            self.quality_hint.config(text="This exact quality requires FFmpeg or a progressive source stream.")
            return
        self.quality_value = height
        self.download_btn.config(state="normal", bg=BLUE, fg="white")
        self.quality_hint.config(text=f"Selected {height}p. VidLoom will request the exact {height}p source.")

    # ---------- real download/progress ----------
    def download(self):
        if self.downloading or not self.info or not self.quality_value:
            return
        self.downloading = True
        self.download_btn.config(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        target = self.quality_value
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            selector = exact_selector(self.info, target)
            if not selector:
                raise RuntimeError(f"{target}p is not available as a downloadable source format.")

            opts = ydl_options()
            opts.update({
                "outtmpl": str(self.output_dir / "%(title).120s-%(id)s.%(ext)s"),
                "format": selector if self.mode == "video" else "bestaudio/best",
                "progress_hooks": [self.progress_hook],
                "postprocessor_hooks": [self.postprocessor_hook],
            })
            if self.mode == "video" and ffmpeg_available():
                opts["merge_output_format"] = "mp4"
            if self.mode == "audio" and ffmpeg_available():
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url.get().strip()])
            self.after(0, lambda: self._download_done(target))
        except Exception as exc:
            self.after(0, lambda e=exc: self._download_failed(e))
        finally:
            self.downloading = False

    def _download_done(self, target):
        self.progress["value"] = 100
        self.status.config(text=f"Download finished • {target}p • {self.output_dir}")
        self.stats.config(text="100%  •  complete")
        self.download_btn.config(state="normal" if self.quality_value else "disabled")
        messagebox.showinfo(APP_NAME, "Download completed successfully.")

    def _download_failed(self, exc):
        self.status.config(text=self.clean_error(exc))
        self.download_btn.config(state="normal" if self.quality_value else "disabled")

    def progress_hook(self, data):
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = done * 100 / total if total else 0
            speed = data.get("speed") or 0
            eta = data.get("eta")
            self.after(0, lambda p=pct, d=done, t=total, s=speed, e=eta:
                       self._progress_update(p, d, t, s, e))
        elif status == "finished":
            self.after(0, lambda: self.status.config(
                text="Source download finished. Finalizing file…"))

    def postprocessor_hook(self, data):
        self.after(0, lambda: self.status.config(
            text="Merging video and audio with FFmpeg…"))

    def _progress_update(self, pct, done, total, speed, eta):
        self.progress["value"] = max(0, min(100, pct))
        eta_text = f"ETA {int(eta)}s" if eta is not None else "ETA —"
        total_text = human_bytes(total) if total else "—"
        self.status.config(text=f"Downloading… {pct:.1f}%")
        self.stats.config(text=f"{human_bytes(done)} / {total_text}  •  {human_bytes(speed)}/s  •  {eta_text}")

    @staticmethod
    def clean_error(exc):
        text = str(exc).replace("ERROR: ", "").strip()
        low = text.lower()
        if "unsupported url" in low:
            return "This website is not supported by the installed yt-dlp extractor."
        if "private" in low:
            return "This media is private and cannot be downloaded."
        if "login" in low or "sign in" in low or "cookies" in low:
            return "This media requires login and cannot be downloaded here."
        if "drm" in low:
            return "DRM-protected media cannot be downloaded."
        if "tiktok" in low and ("unexpected response" in low or "webpage" in low):
            return "TikTok could not be read right now. Please try a public link again later."
        if "403" in low or "429" in low:
            return "The source rejected the request. Please try again later."
        if "ffmpeg" in low:
            return "FFmpeg is required to merge this video and audio stream."
        if "requested format is not available" in low:
            return "This quality is not available. Please select another quality."
        if "unable to download" in low or "unable to extract" in low:
            return "Unable to analyze or download this link. Please check the URL and try again."
        return text[:400] or "Unable to process this link."


if __name__ == "__main__":
    VidLoomApp().mainloop()
