"""Production entrypoint for VidLoom.

This wrapper keeps the original Flask application intact while adding the
runtime media-quality metadata needed by the new downloader UI.
"""
from flask import jsonify, request

import app as core

app = core.app

# Standard choices shown in the UI. Availability is decided from the actual
# formats exposed by yt-dlp; unavailable choices are never silently downgraded.
core.QUALITY_HEIGHTS.clear()
core.QUALITY_HEIGHTS.update({
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "4K": 2160,
})


def _quality_catalog(info):
    formats = info.get("formats") or []
    heights = sorted({
        int(f["height"])
        for f in formats
        if f.get("height") and f.get("vcodec") not in (None, "none")
    })
    catalog = []
    for label, height in core.QUALITY_HEIGHTS.items():
        matches = [f for f in formats if f.get("height") == height and f.get("vcodec") not in (None, "none")]
        has_progressive = any(f.get("acodec") not in (None, "none") for f in matches)
        catalog.append({
            "label": label,
            "height": height,
            "available": bool(matches),
            "has_audio": has_progressive,
        })
    return catalog, heights


def enhanced_api_info():
    try:
        payload = request.get_json(silent=True) or {}
        url = core.clean_url(payload.get("url", ""))
        info = core.get_media_info(url)
        qualities, source_heights = _quality_catalog(info)
        return jsonify({
            "ok": True,
            "video": {
                "id": info.get("id"),
                "title": info.get("title") or "Untitled media",
                "creator": info.get("uploader") or info.get("channel") or "Unknown creator",
                "duration": core.format_duration(info),
                "views": core.format_views(info),
                "thumbnail": info.get("thumbnail"),
                "platform": core.platform_for(url),
                "url": url,
                "qualities": qualities,
                "source_heights": source_heights,
                "is_live": bool(info.get("is_live")),
            },
        })
    except Exception as error:
        core.app.logger.warning("Info error: %s", error)
        return jsonify({"ok": False, "error": core.humanize_error(error)}), 400


# Replace only the view function registered by Flask; all other original
# routes and download-job logic remain untouched.
app.view_functions["api_info"] = enhanced_api_info


def strict_choose_video_format(info, requested_height):
    formats = info.get("formats") or []
    exact = [
        f for f in formats
        if f.get("height") == requested_height
        and f.get("vcodec") not in (None, "none")
    ]
    if not exact:
        raise ValueError(
            f"The quality you selected ({requested_height}p) is not available. Select another quality."
        )

    # Prefer MP4, then the highest-quality exact-height video stream.
    exact.sort(key=lambda f: (
        f.get("ext") == "mp4",
        f.get("acodec") not in (None, "none"),
        float(f.get("tbr") or 0),
    ), reverse=True)

    progressive = [f for f in exact if f.get("acodec") not in (None, "none")]
    if progressive:
        ext = "mp4" if any(f.get("ext") == "mp4" for f in progressive) else progressive[0].get("ext")
        return f"best[height={requested_height}][ext={ext}]/best[height={requested_height}]", requested_height

    if not core.FFMPEG_AVAILABLE:
        raise RuntimeError("This quality has separate video/audio streams and FFmpeg is required to merge them.")

    return (
        f"bestvideo[height={requested_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height={requested_height}]+bestaudio"
    ), requested_height


core.choose_video_format = strict_choose_video_format
