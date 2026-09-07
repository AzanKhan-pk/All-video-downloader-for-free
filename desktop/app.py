import os
import re
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yt_dlp

APP_NAME = "VidLoom"
QUALITY_MAP = {"Best available": None, "2160p (4K)": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def base_options():
    opts = {
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
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    return opts


def quality_heights(info):
    values = set()
    for f in info.get("formats") or []:
        h = f.get("height")
        if h and f.get("vcodec") not in (None, "none"):
            try:
                values.add(int(h))
            except (TypeError, ValueError):
                pass
    return sorted(values, reverse=True)


def choose_format(info, requested):
    formats = info.get("formats") or []
    heights = quality_heights(info)
    if requested is None:
        requested = max(heights) if heights else None
    lower = [h for h in heights if requested is not None and h <= requested]
    chosen = max(lower) if lower else (min(heights) if heights else requested)
    if chosen is None:
        return "bestvideo+bestaudio/best", "Best available"

    if ffmpeg_available():
        fmt = (
            f"bestvideo[height={chosen}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height={chosen}]+bestaudio/"
            f"best[height={chosen}][ext=mp4]/best[height={chosen}]/best"
        )
    else:
        # Without FFmpeg, never choose video-only streams that would leave the user
        # with a silent file. Prefer progressive formats containing both tracks.
        fmt = (
            f"best[height={chosen}][ext=mp4][vcodec!=none][acodec!=none]/"
            f"best[height<={chosen}][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]"
        )
    return fmt, f"{chosen}p"


class VidLoomApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VidLoom — Video Downloader")
        self.geometry("760x560")
        self.minsize(700, 500)
        self.configure(bg="#081126")
        self.info = None
        self.mode = tk.StringVar(value="Video")
        self.quality = tk.StringVar(value="Best available")
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads" / "VidLoom"))
        self.status = tk.StringVar(value="Paste a public video URL to begin.")
        self.progress = tk.DoubleVar(value=0)
        self._build()

    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", padding=7)
        style.configure("TProgressbar", thickness=12)

        tk.Label(self, text="VidLoom", font=("Segoe UI", 28, "bold"), fg="white", bg="#081126").pack(pady=(28, 3))
        tk.Label(self, text="Fast local video & audio downloader", font=("Segoe UI", 11), fg="#9eacce", bg="#081126").pack()

        card = tk.Frame(self, bg="#0d1935", padx=24, pady=24)
        card.pack(fill="both", expand=True, padx=28, pady=25)

        self.url = tk.Entry(card, font=("Segoe UI", 12), bg="#071024", fg="white", insertbackground="white", relief="flat")
        self.url.pack(fill="x", ipady=12)
        self.url.insert(0, "Paste public video URL…")
        self.url.bind("<FocusIn>", lambda e: self._placeholder())

        self.fetch_btn = tk.Button(card, text="Fetch media", command=self.fetch, bg="#5d32e8", fg="white", relief="flat", font=("Segoe UI", 10, "bold"), padx=18, pady=10)
        self.fetch_btn.pack(anchor="e", pady=12)

        self.meta = tk.Label(card, text="", font=("Segoe UI", 11), fg="#dce5ff", bg="#0d1935", justify="left", wraplength=650)
        self.meta.pack(fill="x", pady=5)

        controls = tk.Frame(card, bg="#0d1935")
        controls.pack(fill="x", pady=14)
        tk.Label(controls, text="Type", fg="#9eacce", bg="#0d1935").grid(row=0, column=0, sticky="w")
        mode_box = ttk.Combobox(controls, textvariable=self.mode, values=["Video", "Audio"], state="readonly", width=18)
        mode_box.grid(row=1, column=0, padx=(0, 14), pady=5, sticky="ew")
        tk.Label(controls, text="Quality", fg="#9eacce", bg="#0d1935").grid(row=0, column=1, sticky="w")
        self.quality_box = ttk.Combobox(controls, textvariable=self.quality, state="readonly", width=22)
        self.quality_box.grid(row=1, column=1, pady=5, sticky="ew")
        controls.columnconfigure(0, weight=1); controls.columnconfigure(1, weight=1)

        tk.Label(controls, text="Save folder", fg="#9eacce", bg="#0d1935").grid(row=2, column=0, sticky="w", pady=(12, 0))
        folder = tk.Entry(controls, textvariable=self.output_dir, bg="#071024", fg="white", relief="flat")
        folder.grid(row=3, column=0, sticky="ew", padx=(0, 8), ipady=8)
        tk.Button(controls, text="Browse", command=self.browse, bg="#1a2b51", fg="white", relief="flat").grid(row=3, column=1, sticky="w")

        self.download_btn = tk.Button(card, text="Download", command=self.download, state="disabled", bg="#16a36b", fg="white", relief="flat", font=("Segoe UI", 11, "bold"), pady=11)
        self.download_btn.pack(fill="x", pady=(10, 8))
        ttk.Progressbar(card, variable=self.progress, maximum=100).pack(fill="x", pady=8)
        tk.Label(card, textvariable=self.status, fg="#aebddd", bg="#0d1935", wraplength=650).pack(anchor="w", pady=5)

    def _placeholder(self):
        if self.url.get() == "Paste public video URL…":
            self.url.delete(0, "end")

    def browse(self):
        chosen = filedialog.askdirectory(initialdir=str(Path.home() / "Downloads"))
        if chosen:
            self.output_dir.set(chosen)

    def fetch(self):
        url = self.url.get().strip()
        if not url or url == "Paste public video URL…":
            messagebox.showwarning(APP_NAME, "Paste a public video URL first.")
            return
        self.fetch_btn.config(state="disabled")
        self.status.set("Reading available qualities…")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            with yt_dlp.YoutubeDL(base_options()) as ydl:
                info = ydl.extract_info(url, download=False)
            self.info = info
            heights = quality_heights(info)
            labels = ["Best available"] + [f"{h}p" for h in heights]
            self.after(0, lambda: self.quality_box.config(values=labels))
            self.after(0, lambda: self.quality.set("Best available"))
            title = info.get("title") or "Untitled"
            duration = info.get("duration_string") or "Unknown duration"
            platform = info.get("extractor_key") or info.get("extractor") or "Media"
            self.after(0, lambda: self.meta.config(text=f"{title}\n{platform}  •  {duration}\nAvailable qualities: {', '.join(f'{h}p' for h in heights) or 'best available'}"))
            self.after(0, lambda: self.status.set("Media found. Choose quality and download."))
            self.after(0, lambda: self.download_btn.config(state="normal"))
        except Exception as e:
            self.after(0, lambda: self.status.set(self.clean_error(e)))
        finally:
            self.after(0, lambda: self.fetch_btn.config(state="normal"))

    @staticmethod
    def clean_error(e):
        text = str(e).replace("ERROR: ", "").strip()
        low = text.lower()
        if "private" in low: return "This media is private."
        if "sign in" in low or "login" in low or "cookies" in low: return "This media requires login and cannot be downloaded here."
        if "drm" in low: return "DRM-protected media cannot be downloaded."
        return text[:300] or "Could not process this link."

    def download(self):
        if not self.info:
            return
        self.download_btn.config(state="disabled")
        self.progress.set(0)
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            out = Path(self.output_dir.get()).expanduser()
            out.mkdir(parents=True, exist_ok=True)
            requested = QUALITY_MAP.get(self.quality.get())
            if self.quality.get().endswith("p") and self.quality.get()[:-1].isdigit():
                requested = int(self.quality.get()[:-1])
            fmt, selected = choose_format(self.info, requested)
            opts = base_options()
            opts["outtmpl"] = str(out / "%(title).120s-%(id)s.%(ext)s")
            opts["format"] = "bestaudio/best" if self.mode.get() == "Audio" else fmt
            opts["progress_hooks"] = [self.progress_hook]
            if self.mode.get() == "Audio" and ffmpeg_available():
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url.get().strip()])
            self.after(0, lambda: self.status.set(f"Download complete — quality: {selected}. Saved in {out}"))
            self.after(0, lambda: messagebox.showinfo(APP_NAME, "Download completed successfully."))
        except Exception as e:
            self.after(0, lambda: self.status.set(self.clean_error(e)))
        finally:
            self.after(0, lambda: self.download_btn.config(state="normal"))

    def progress_hook(self, data):
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            self.after(0, lambda p=pct: self.progress.set(p))
            speed = data.get("speed") or 0
            eta = data.get("eta")
            self.after(0, lambda: self.status.set(f"Downloading… {pct:.1f}%  •  {speed/1024/1024:.2f} MB/s  •  ETA: {eta}s" if eta else f"Downloading… {pct:.1f}%"))
        elif data.get("status") == "finished":
            self.after(0, lambda: self.progress.set(100))


if __name__ == "__main__":
    VidLoomApp().mainloop()
