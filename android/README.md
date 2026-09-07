# VidLoom Android

Native Android package built with Python/Kivy + yt-dlp. Downloads are performed on the phone rather than through a Vercel/Railway server.

The app discovers the source's real available video heights and lets the user choose a quality. When FFmpeg is available in the Android build, separate video/audio streams can be merged; otherwise the selector prefers progressive formats that already contain both tracks.

Build with the repository's GitHub Actions workflow or locally with Buildozer on Linux/WSL.
