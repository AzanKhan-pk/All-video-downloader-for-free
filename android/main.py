import threading
from pathlib import Path

import yt_dlp
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

QUALITY_ORDER = [2160, 1440, 1080, 720, 480, 360, 240, 144]


def available_heights(info):
    heights = set()
    for f in info.get("formats") or []:
        try: h = int(f.get("height") or 0)
        except (TypeError, ValueError): continue
        if h > 0 and f.get("vcodec") not in (None, "none"): heights.add(h)
    return sorted(heights, reverse=True)


def progressive_heights(info):
    heights = set()
    for f in info.get("formats") or []:
        try: h = int(f.get("height") or 0)
        except (TypeError, ValueError): continue
        if h > 0 and f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none"): heights.add(h)
    return heights


def exact_format(info, height):
    if height not in available_heights(info): return None
    # Android build does not silently downgrade. Without an embedded FFmpeg
    # binary, only a real progressive format containing audio is downloadable.
    if height in progressive_heights(info): return f"best[height={height}][vcodec!=none][acodec!=none]"
    return None


def friendly_error(exc):
    text = str(exc).replace("ERROR: ", "").strip(); low = text.lower()
    if "unsupported url" in low: return "This website is not supported by the installed extractor."
    if "private" in low or "login" in low or "sign in" in low or "cookies" in low: return "This media requires login or is private."
    if "drm" in low: return "DRM-protected media cannot be downloaded."
    if "tiktok" in low and ("challenge" in low or "response" in low): return "TikTok blocked this request. Please try another public link."
    return text[:300] or "Unable to process this link."


class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.padding = dp(14); self.spacing = dp(10)
        with self.canvas.before:
            Color(0.035, 0.065, 0.16, 1)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
        self.bind(pos=self._sync, size=self._sync)
    def _sync(self, *_): self.bg.pos = self.pos; self.bg.size = self.size


class Downloader(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), padding=dp(14), **kwargs)
        self.info = None
        self.selected_quality = None
        self.add_widget(Label(text="[b]VidLoom[/b]", markup=True, font_size="30sp", color=(0.95,0.97,1,1), size_hint_y=None, height=dp(42)))
        self.add_widget(Label(text="Professional Video Downloader", font_size="12sp", color=(0.45,0.75,1,1), size_hint_y=None, height=dp(24)))

        search = Card(orientation="horizontal", size_hint_y=None, height=dp(62))
        self.url = TextInput(hint_text="Paste public video URL…", multiline=False, background_color=(0.02,0.04,0.10,1), foreground_color=(0.9,0.94,1,1), cursor_color=(0.3,0.6,1,1))
        self.fetch_btn = Button(text="GO  →", size_hint_x=None, width=dp(88), background_normal="", background_color=(0.2,0.32,1,1), bold=True)
        self.fetch_btn.bind(on_release=self.fetch)
        search.add_widget(self.url); search.add_widget(self.fetch_btn); self.add_widget(search)

        self.preview = AsyncImage(source="", allow_stretch=True, keep_ratio=True, size_hint_y=None, height=dp(190))
        self.add_widget(self.preview)
        self.title_label = Label(text="Paste a public URL to preview media", font_size="15sp", color=(0.9,0.94,1,1), halign="left", valign="middle", size_hint_y=None, height=dp(45))
        self.add_widget(self.title_label)

        controls = Card(orientation="vertical", size_hint_y=None, height=dp(250))
        mode_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.mode = Spinner(text="Video", values=("Video","Audio"), background_color=(0.25,0.12,0.95,1))
        self.quality = Spinner(text="Select quality", values=tuple(f"{q}p" for q in QUALITY_ORDER), background_color=(0.05,0.20,0.50,1))
        mode_row.add_widget(self.mode); mode_row.add_widget(self.quality); controls.add_widget(mode_row)
        self.download_btn = Button(text="↓  DOWNLOAD", size_hint_y=None, height=dp(52), background_normal="", background_color=(0.18,0.38,1,1), bold=True, disabled=True)
        self.download_btn.bind(on_release=self.download); controls.add_widget(self.download_btn)
        self.status = Label(text="Real source qualities will appear after analysis.", font_size="11sp", color=(0.62,0.69,0.85,1), halign="left", valign="middle")
        controls.add_widget(self.status); self.add_widget(controls)

    def set_status(self, text): Clock.schedule_once(lambda *_: setattr(self.status,"text",text))

    def fetch(self, *_):
        url=self.url.text.strip()
        if not url: self.set_status("Paste a public URL first."); return
        self.fetch_btn.disabled=True; self.download_btn.disabled=True; self.set_status("Analyzing source and reading real formats…")
        threading.Thread(target=self._fetch_worker,args=(url,),daemon=True).start()

    def _fetch_worker(self,url):
        try:
            opts={"quiet":True,"no_warnings":True,"noplaylist":True,"socket_timeout":30,"retries":5,"extractor_args":{"youtube":{"player_client":["android","web"]}}}
            with yt_dlp.YoutubeDL(opts) as ydl: info=ydl.extract_info(url,download=False)
            self.info=info; heights=available_heights(info); progressive=progressive_heights(info)
            vals=[f"{q}p" for q in QUALITY_ORDER if q in heights]
            Clock.schedule_once(lambda *_: setattr(self.quality,"values",tuple(vals)))
            thumb=info.get("thumbnail") or ""
            Clock.schedule_once(lambda *_: setattr(self.preview,"source",thumb))
            title=info.get("title") or "Untitled media"; duration=info.get("duration_string") or "Unknown duration"
            self.set_status(f"{title}\n{duration}\nReal video heights: {', '.join(f'{h}p' for h in heights) or 'none'}\nProgressive with audio: {', '.join(f'{h}p' for h in sorted(progressive,reverse=True)) or 'none'}")
            Clock.schedule_once(lambda *_: setattr(self.title_label,"text",title))
        except Exception as exc: self.set_status(friendly_error(exc))
        finally: Clock.schedule_once(lambda *_: setattr(self.fetch_btn,"disabled",False))

    def download(self, *_):
        if not self.info or self.quality.text == "Select quality": return
        target=int(self.quality.text.replace("p","")); fmt=exact_format(self.info,target)
        if not fmt: self.set_status("This quality is not available as a downloadable Android format. Please select another quality."); return
        self.download_btn.disabled=True; threading.Thread(target=self._download_worker,args=(target,fmt,),daemon=True).start()

    def _download_worker(self,target,fmt):
        try:
            folder=Path(App.get_running_app().user_data_dir)/"VidLoom Downloads"; folder.mkdir(parents=True,exist_ok=True)
            opts={"quiet":True,"no_warnings":True,"noplaylist":True,"continuedl":True,"retries":10,"fragment_retries":10,"socket_timeout":30,"outtmpl":str(folder/"%(title).100s-%(id)s.%(ext)s"),"format":"bestaudio/best" if self.mode.text=="Audio" else fmt,"progress_hooks":[self.progress]}
            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([self.url.text.strip()])
            self.set_status(f"Download complete • {target}p\nSaved in: {folder}")
        except Exception as exc: self.set_status(friendly_error(exc))
        finally: Clock.schedule_once(lambda *_: setattr(self.download_btn,"disabled",False))

    def progress(self,data):
        if data.get("status")=="downloading":
            total=data.get("total_bytes") or data.get("total_bytes_estimate") or 0; done=data.get("downloaded_bytes") or 0; pct=done*100/total if total else 0; speed=data.get("speed") or 0; eta=data.get("eta")
            msg=f"Downloading… {pct:.1f}% • {speed/1024/1024:.2f} MB/s" + (f" • ETA {int(eta)}s" if eta is not None else "")
            self.set_status(msg)
        elif data.get("status")=="finished": self.set_status("Processing downloaded file…")


class VidLoomApp(App):
    title="VidLoom"
    def build(self): return Downloader()


if __name__=="__main__": VidLoomApp().run()
