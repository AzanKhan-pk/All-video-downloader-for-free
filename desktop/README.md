# VidLoom Desktop

Windows desktop version of VidLoom using Python + Tkinter + yt-dlp.

## Run

```powershell
python -m pip install -r requirements.txt
python app.py
```

The app downloads directly to the user's Downloads/VidLoom folder, so it is not limited by Vercel/Railway serverless storage or request timeouts.

## Quality

The quality list is built from the source's actual formats. The selected value is the highest available format at or below the requested resolution; if separate video/audio streams are available, FFmpeg is used to merge them into MP4. If FFmpeg is unavailable, only progressive formats containing both video and audio are selected.
