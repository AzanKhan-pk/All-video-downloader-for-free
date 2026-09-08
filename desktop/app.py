import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.request import Request, urlopen

import yt_dlp

APP_NAME = "VidLoom"
QUALITYS = [2160, 1440, 1080, 720, 480, 360, 240, 144]


def ffmpeg_available(): return shutil.which("ffmpeg") is not None

def ydl_options():
    return {"quiet":True,"no_warnings":True,"noplaylist":True,"restrictfilenames":True,"windowsfilenames":True,"continuedl":True,"retries":10,"fragment_retries":10,"file_access_retries":5,"socket_timeout":30,"extractor_args":{"youtube":{"player_client":["android","web"]}}}

def format_heights(info):
    out=set()
    for f in info.get("formats") or []:
        try: h=int(f.get("height") or 0)
        except (TypeError,ValueError): continue
        if h>0 and f.get("vcodec") not in (None,"none"): out.add(h)
    return sorted(out,reverse=True)

def progressive_heights(info):
    out=set()
    for f in info.get("formats") or []:
        try: h=int(f.get("height") or 0)
        except (TypeError,ValueError): continue
        if h>0 and f.get("vcodec") not in (None,"none") and f.get("acodec") not in (None,"none"): out.add(h)
    return out

def exact_format(info,height):
    if height not in format_heights(info): return None
    if ffmpeg_available(): return f"bestvideo[height={height}]+bestaudio/best[height={height}]"
    if height in progressive_heights(info): return f"best[height={height}][vcodec!=none][acodec!=none]"
    return None

def conversion_source(info,target):
    higher=[h for h in format_heights(info) if h>target]
    if not higher or not ffmpeg_available(): return None
    return f"bestvideo[height={min(higher)}]+bestaudio/best[height={min(higher)}]"

def human_bytes(n):
    n=float(n or 0)
    for u in ("B","KB","MB","GB"):
        if n<1024 or u=="GB": return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} GB"

class VidLoomApp(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("VidLoom — Professional Video Downloader"); self.geometry("1180x760"); self.minsize(980,680); self.configure(bg="#050817")
        self.info=None; self.thumb_ref=None; self.output_dir=Path.home()/"Downloads"/"VidLoom"; self.mode="video"; self.quality_value=None; self._build()
    def _build(self):
        style=ttk.Style(self); style.theme_use("clam"); style.configure("Blue.Horizontal.TProgressbar",troughcolor="#101a3a",background="#3b82f6",bordercolor="#101a3a",lightcolor="#3b82f6",darkcolor="#3b82f6")
        top=tk.Frame(self,bg="#050817",height=72); top.pack(fill="x"); tk.Label(top,text="▷",fg="#36d1ff",bg="#050817",font=("Segoe UI",30,"bold")).pack(side="left",padx=(26,8)); brand=tk.Frame(top,bg="#050817"); brand.pack(side="left"); tk.Label(brand,text="VidLoom",fg="white",bg="#050817",font=("Segoe UI",22,"bold")).pack(anchor="w"); tk.Label(brand,text="VIDEO DOWNLOADER",fg="#8d9ac4",bg="#050817",font=("Segoe UI",7,"bold")).pack(anchor="w"); tk.Label(top,text="Professional local downloader",fg="#8d9ac4",bg="#050817",font=("Segoe UI",10)).pack(side="right",padx=28)
        self._search_bar(); self._platforms(); body=tk.Frame(self,bg="#050817"); body.pack(fill="both",expand=True,padx=28,pady=(4,20)); body.columnconfigure(0,weight=3); body.columnconfigure(1,weight=2); body.rowconfigure(0,weight=1)
        self.preview=tk.Frame(body,bg="#09122b",highlightthickness=1,highlightbackground="#1d4ed8"); self.preview.grid(row=0,column=0,sticky="nsew",padx=(0,10)); self._preview_contents(); self.panel=tk.Frame(body,bg="#09122b",highlightthickness=1,highlightbackground="#253b74"); self.panel.grid(row=0,column=1,sticky="nsew",padx=(10,0)); self._download_panel()
    def _search_bar(self):
        wrap=tk.Frame(self,bg="#050817"); wrap.pack(fill="x",padx=36,pady=(8,18)); self.url=tk.Entry(wrap,bg="#0b1430",fg="#dce6ff",insertbackground="white",relief="flat",font=("Segoe UI",12)); self.url.pack(side="left",fill="x",expand=True,ipady=13,padx=(2,10)); self.url.insert(0,"https://paste-a-public-video-url-here"); self.url.bind("<FocusIn>",self._clear_placeholder); tk.Button(wrap,text="GO  →",command=self.fetch,bg="#2563eb",fg="white",activebackground="#3b82f6",relief="flat",font=("Segoe UI",11,"bold"),padx=24,pady=11).pack(side="right")
    def _platforms(self):
        row=tk.Frame(self,bg="#050817"); row.pack(fill="x",padx=40,pady=(0,18))
        for icon,name in [("▶","YouTube"),("♪","TikTok"),("◎","Instagram"),("f","Facebook"),("𝕏","X"),("●","Reddit"),("V","Vimeo"),("P","Pinterest"),("▣","Twitch")]:
            box=tk.Frame(row,bg="#071027",highlightthickness=1,highlightbackground="#182d5d",width=100,height=68); box.pack(side="left",expand=True,fill="x",padx=4); box.pack_propagate(False); tk.Label(box,text=icon,fg="#48a8ff",bg="#071027",font=("Segoe UI",19,"bold")).pack(pady=(6,0)); tk.Label(box,text=name,fg="#c6d1ed",bg="#071027",font=("Segoe UI",8)).pack()
    def _preview_contents(self):
        tk.Label(self.preview,text="MEDIA PREVIEW",fg="#7183b0",bg="#09122b",font=("Segoe UI",9,"bold")).pack(anchor="w",padx=20,pady=(18,10)); self.thumb=tk.Label(self.preview,text="Paste a public URL above\nand click GO",fg="#8291b5",bg="#050817",font=("Segoe UI",18,"bold"),justify="center"); self.thumb.pack(fill="both",expand=True,padx=20,pady=10); self.title_label=tk.Label(self.preview,text="",fg="white",bg="#09122b",font=("Segoe UI",14,"bold"),anchor="w",justify="left",wraplength=650); self.title_label.pack(fill="x",padx=20,pady=(4,2)); self.meta_label=tk.Label(self.preview,text="Public media only • DRM/login-protected media is not bypassed",fg="#7f8fb4",bg="#09122b",font=("Segoe UI",9),anchor="w"); self.meta_label.pack(fill="x",padx=20,pady=(0,18))
    def _download_panel(self):
        tk.Label(self.panel,text="Download Video",fg="white",bg="#09122b",font=("Segoe UI",16,"bold")).pack(anchor="w",padx=20,pady=(18,16)); tabs=tk.Frame(self.panel,bg="#09122b"); tabs.pack(fill="x",padx=20); self.video_btn=tk.Button(tabs,text="▣ Video",command=lambda:self.set_mode("video"),relief="flat",bg="#4f20ff",fg="white",font=("Segoe UI",10,"bold"),pady=10); self.video_btn.pack(side="left",fill="x",expand=True,padx=(0,5)); self.audio_btn=tk.Button(tabs,text="♫ Audio",command=lambda:self.set_mode("audio"),relief="flat",bg="#101b3a",fg="#a8b4d4",font=("Segoe UI",10,"bold"),pady=10); self.audio_btn.pack(side="left",fill="x",expand=True,padx=(5,0)); tk.Label(self.panel,text="Select Quality",fg="white",bg="#09122b",font=("Segoe UI",10,"bold")).pack(anchor="w",padx=20,pady=(22,6)); self.quality_list=tk.Listbox(self.panel,bg="#071027",fg="#dce6ff",selectbackground="#1d4ed8",selectforeground="white",relief="flat",height=9,font=("Segoe UI",10)); self.quality_list.pack(fill="x",padx=20); self.quality_list.bind("<<ListboxSelect>>",self._quality_selected); self.quality_hint=tk.Label(self.panel,text="Analyze a URL to see REAL available qualities.",fg="#8291b5",bg="#09122b",font=("Segoe UI",9),wraplength=330,justify="left"); self.quality_hint.pack(anchor="w",padx=20,pady=(8,12)); self.download_btn=tk.Button(self.panel,text="↓  DOWNLOAD",command=self.download,state="disabled",relief="flat",bg="#2563eb",fg="white",font=("Segoe UI",12,"bold"),pady=12); self.download_btn.pack(fill="x",padx=20,pady=(4,12)); self.progress=ttk.Progressbar(self.panel,style="Blue.Horizontal.TProgressbar",maximum=100); self.progress.pack(fill="x",padx=20,pady=(4,8)); self.status=tk.Label(self.panel,text="Ready",fg="#aab8d7",bg="#09122b",font=("Segoe UI",9),wraplength=330,justify="left"); self.status.pack(anchor="w",padx=20,pady=(0,8)); self.folder_label=tk.Label(self.panel,text=f"Save: {self.output_dir}",fg="#64759d",bg="#09122b",font=("Segoe UI",8),wraplength=330,justify="left"); self.folder_label.pack(anchor="w",padx=20); tk.Button(self.panel,text="Choose folder",command=self.browse,bg="#101b3a",fg="#b8c5e4",relief="flat",pady=7).pack(fill="x",padx=20,pady=(8,18))
    def _clear_placeholder(self,*_):
        if self.url.get().startswith("https://paste-a-public"): self.url.delete(0,"end")
    def set_mode(self,mode):
        self.mode=mode; self.video_btn.config(bg="#4f20ff" if mode=="video" else "#101b3a",fg="white" if mode=="video" else "#a8b4d4"); self.audio_btn.config(bg="#4f20ff" if mode=="audio" else "#101b3a",fg="white" if mode=="audio" else "#a8b4d4")
    def browse(self):
        selected=filedialog.askdirectory(initialdir=str(self.output_dir.parent));
        if selected: self.output_dir=Path(selected); self.folder_label.config(text=f"Save: {self.output_dir}")
    def fetch(self):
        url=self.url.get().strip()
        if not url or url.startswith("https://paste-a-public"): messagebox.showwarning(APP_NAME,"Paste a public video URL first."); return
        self.download_btn.config(state="disabled"); self.status.config(text="Analyzing source and reading real formats…"); threading.Thread(target=self._fetch_worker,args=(url,),daemon=True).start()
    def _fetch_worker(self,url):
        try:
            with yt_dlp.YoutubeDL(ydl_options()) as ydl: info=ydl.extract_info(url,download=False)
            self.info=info; heights=format_heights(info); self.after(0,lambda:self._show_info(info,heights))
        except Exception as exc: self.after(0,lambda:self.status.config(text=self.clean_error(exc)))
    def _show_info(self,info,heights):
        self.quality_list.delete(0,"end")
        for h in QUALITYS: self.quality_list.insert("end",f"{'●' if h in heights else '○'}  {h}p   • {'available' if h in heights else 'unavailable'}")
        self.quality_value=None; self.title_label.config(text=info.get("title") or "Untitled media"); self.meta_label.config(text=f"{info.get('extractor_key') or info.get('extractor') or 'Source'}  •  {info.get('duration_string') or 'Unknown duration'}  •  Public media only"); self.quality_hint.config(text="Only real source heights are selectable. No silent downgrade."); self.status.config(text="Media detected. Select an available quality."); self._set_thumbnail(info.get("thumbnail"))
    def _set_thumbnail(self,url):
        if not url: self.thumb.config(text="No thumbnail available",image=""); return
        self.thumb.config(text="Loading preview…",image=""); threading.Thread(target=self._thumbnail_worker,args=(url,),daemon=True).start()
    def _thumbnail_worker(self,url):
        try:
            from io import BytesIO
            from PIL import Image,ImageTk
            data=urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=15).read(); image=Image.open(BytesIO(data)).convert("RGB"); image.thumbnail((760,390)); photo=ImageTk.PhotoImage(image); self.after(0,lambda p=photo:self._apply_thumbnail(p))
        except Exception: self.after(0,lambda:self.thumb.config(text="Preview unavailable",image=""))
    def _apply_thumbnail(self,photo): self.thumb_ref=photo; self.thumb.config(image=photo,text="")
    def _quality_selected(self,*_):
        if not self.info: return
        sel=self.quality_list.curselection()
        if not sel: return
        h=QUALITYS[sel[0]]
        if h not in format_heights(self.info): self.quality_value=None; self.download_btn.config(state="disabled"); self.quality_hint.config(text="This quality is not available. Please select another quality."); return
        self.quality_value=h; self.download_btn.config(state="normal"); self.quality_hint.config(text=f"Selected {h}p. Exact quality will be requested; lower conversion is used only when FFmpeg is available.")
    def download(self):
        if not self.info or not self.quality_value: return
        self.download_btn.config(state="disabled"); self.progress["value"]=0; threading.Thread(target=self._download_worker,daemon=True).start()
    def _download_worker(self):
        try:
            self.output_dir.mkdir(parents=True,exist_ok=True); target=self.quality_value; fmt=exact_format(self.info,target); convert=False
            if not fmt: fmt=conversion_source(self.info,target); convert=bool(fmt)
            if not fmt: raise RuntimeError(f"{target}p is not available from this source. Please select another quality.")
            opts=ydl_options(); opts.update({"outtmpl":str(self.output_dir/"%(title).120s-%(id)s.%(ext)s"),"format":"bestaudio/best" if self.mode=="audio" else fmt,"progress_hooks":[self.progress_hook]})
            if self.mode=="video" and convert: opts["merge_output_format"]="mp4"; opts["postprocessor_args"]=["-vf",f"scale=-2:{target}","-c:v","libx264","-crf","23","-c:a","aac"]
            elif self.mode=="video" and ffmpeg_available(): opts["merge_output_format"]="mp4"
            if self.mode=="audio" and ffmpeg_available(): opts["postprocessors"]=[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([self.url.get().strip()])
            self.after(0,lambda:self.status.config(text=f"Download complete • {target}p • saved to {self.output_dir}")); self.after(0,lambda:messagebox.showinfo(APP_NAME,"Download completed successfully."))
        except Exception as exc: self.after(0,lambda:self.status.config(text=self.clean_error(exc)))
        finally: self.after(0,lambda:self.download_btn.config(state="normal" if self.quality_value else "disabled"))
    def progress_hook(self,data):
        if data.get("status")=="downloading":
            total=data.get("total_bytes") or data.get("total_bytes_estimate") or 0; done=data.get("downloaded_bytes") or 0; pct=done*100/total if total else 0; speed=data.get("speed") or 0; eta=data.get("eta"); text=f"Downloading… {pct:.1f}% • {human_bytes(speed)}/s" + (f" • ETA {int(eta)}s" if eta is not None else ""); self.after(0,lambda p=pct,t=text,d=done,tt=total:self._update_progress(p,t,d,tt))
    def _update_progress(self,pct,text,done,total): self.progress.config(value=pct); self.status.config(text=text + (f" • {human_bytes(done)} / {human_bytes(total)}" if total else f" • {human_bytes(done)}"))
    @staticmethod
    def clean_error(exc):
        text=str(exc).replace("ERROR: ","").strip(); low=text.lower()
        if "private" in low: return "This media is private and cannot be downloaded."
        if "login" in low or "sign in" in low or "cookies" in low: return "This media requires login and cannot be downloaded here."
        if "drm" in low: return "DRM-protected media cannot be downloaded."
        if "unsupported url" in low: return "This website is not supported by the installed yt-dlp extractor."
        return text[:500] or "Unable to process this link."

if __name__ == "__main__": VidLoomApp().mainloop()
