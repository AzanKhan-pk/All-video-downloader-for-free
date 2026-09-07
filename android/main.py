import os
import threading
from pathlib import Path

import yt_dlp
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

QUALITY_ORDER = ["Best available", "2160p (4K)", "1440p", "1080p", "720p", "480p", "360p"]


def available_heights(info):
    heights = set()
    for f in info.get("formats") or []:
        h = f.get("height")
        if h and f.get("vcodec") not in (None, "none"):
            try:
                heights.add(int(h))
            except (TypeError, ValueError):
                pass
    return sorted(heights, reverse=True)


def choose_format(info, requested):
    heights = available_heights(info)
    if requested is None:
        requested = max(heights) if heights else 1080
    lower = [h for h in heights if h <= requested]
    selected = max(lower) if lower else (min(heights) if heights else requested)
    # Android builds intentionally prefer progressive MP4 when FFmpeg is not
    # present. This avoids producing a video-only file with no audio.
    return (
        f"best[height={selected}][ext=mp4][vcodec!=none][acodec!=none]/"
        f"best[height<={selected}][vcodec!=none][acodec!=none]/"
        "best[vcodec!=none][acodec!=none]",
        selected,
    )


class Downloader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=12, padding=18, **kwargs)
        self.info = None
        self.add_widget(Label(text="[b]VidLoom[/b]\nVideo & Audio Downloader", markup=True, font_size="25sp", size_hint_y=None, height=80))
        self.url = TextInput(hint_text="Paste a public video URL…", multiline=False, size_hint_y=None, height=52)
        self.add_widget(self.url)
        self.fetch_btn = Button(text="Fetch media", size_hint_y=None, height=52)
        self.fetch_btn.bind(on_release=self.fetch)
        self.add_widget(self.fetch_btn)
        self.info_label = Label(text="", halign="left", valign="middle")
        self.add_widget(self.info_label)
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        self.quality = Spinner(text="Best available", values=QUALITY_ORDER)
        self.mode = Spinner(text="Video", values=("Video", "Audio"))
        row.add_widget(self.mode); row.add_widget(self.quality)
        self.add_widget(row)
        self.download_btn = Button(text="Download", disabled=True, size_hint_y=None, height=55)
        self.download_btn.bind(on_release=self.download)
        self.add_widget(self.download_btn)
        self.status = Label(text="Downloads are saved to the app's VidLoom folder.", halign="left")
        self.add_widget(self.status)

    def set_status(self, text):
        Clock.schedule_once(lambda *_: setattr(self.status, "text", text))

    def fetch(self, *_):
        url = self.url.text.strip()
        if not url:
            self.set_status("Paste a public URL first.")
            return
        self.fetch_btn.disabled = True
        self.set_status("Reading available qualities…")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 30, "retries": 5}
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.info = ydl.extract_info(url, download=False)
            heights = available_heights(self.info)
            values = ["Best available"] + [f"{h}p" for h in heights]
            Clock.schedule_once(lambda *_: setattr(self.quality, "values", values))
            title = self.info.get("title") or "Untitled"
            duration = self.info.get("duration_string") or "Unknown duration"
            self.set_status(f"Found: {title}\nDuration: {duration}\nAvailable: {', '.join(f'{h}p' for h in heights) or 'best available'}")
            Clock.schedule_once(lambda *_: setattr(self.download_btn, "disabled", False))
        except Exception as e:
            self.set_status(str(e)[:300] or "Could not read this link.")
        finally:
            Clock.schedule_once(lambda *_: setattr(self.fetch_btn, "disabled", False))

    def download(self, *_):
        if not self.info:
            return
        self.download_btn.disabled = True
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            url = self.url.text.strip()
            requested = None
            if self.quality.text != "Best available":
                requested = int(self.quality.text.replace("p", "").replace(" (4K)", ""))
            fmt, selected = choose_format(self.info, requested)
            folder = Path(App.get_running_app().user_data_dir) / "VidLoom Downloads"
            folder.mkdir(parents=True, exist_ok=True)
            opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "continuedl": True,
                "retries": 10,
                "fragment_retries": 10,
                "socket_timeout": 30,
                "outtmpl": str(folder / "%(title).100s-%(id)s.%(ext)s"),
                "progress_hooks": [self.progress],
            }
            opts["format"] = "bestaudio/best" if self.mode.text == "Audio" else fmt
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.set_status(f"Download complete. Quality: {selected}p\nSaved to: {folder}")
        except Exception as e:
            self.set_status(str(e)[:300] or "Download failed.")
        finally:
            Clock.schedule_once(lambda *_: setattr(self.download_btn, "disabled", False))

    def progress(self, data):
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = done / total * 100 if total else 0
            self.set_status(f"Downloading… {pct:.1f}%")
        elif data.get("status") == "finished":
            self.set_status("Processing file…")


class VidLoomApp(App):
    title = "VidLoom"
    def build(self):
        return Downloader()


if __name__ == "__main__":
    VidLoomApp().run()
