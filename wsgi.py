"""Production entrypoint for VidLoom."""
from flask import jsonify, request, send_file
from io import BytesIO
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import mimetypes
import os

import app as core
import runtime_patch

app = core.app

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
    catalog = []
    for label, height in core.QUALITY_HEIGHTS.items():
        matches = [
            f for f in formats
            if int(f.get("height") or 0) == height
            and f.get("vcodec") not in (None, "none")
        ]
        sizes = [int(f.get("filesize") or f.get("filesize_approx") or 0) for f in matches]
        catalog.append({
            "label": label,
            "height": height,
            "available": bool(matches),
            "has_audio": any(f.get("acodec") not in (None, "none") for f in matches),
            "filesize": max(sizes or [0]),
        })
    source_heights = sorted({
        int(f["height"])
        for f in formats
        if f.get("height") and f.get("vcodec") not in (None, "none")
    })
    return catalog, source_heights


def _compact_formats(info):
    result, seen = [], set()
    for f in info.get("formats") or []:
        height = int(f.get("height") or 0)
        if height < 144 or f.get("vcodec") in (None, "none"):
            continue
        key = (height, f.get("ext"), f.get("acodec") not in (None, "none"))
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "format_id": str(f.get("format_id") or ""),
            "height": height,
            "ext": f.get("ext") or "",
            "vcodec": "video",
            "acodec": "audio" if f.get("acodec") not in (None, "none") else "none",
            "filesize": int(f.get("filesize") or f.get("filesize_approx") or 0),
        })
    return result


def enhanced_api_info():
    try:
        payload = request.get_json(silent=True) or {}
        url = core.clean_url(payload.get("url", ""))
        info = core.get_media_info(url)
        qualities, source_heights = _quality_catalog(info)
        return jsonify({"ok": True, "video": {
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
            "formats": _compact_formats(info),
            "is_live": bool(info.get("is_live")),
        }})
    except Exception as error:
        core.app.logger.warning("Info error: %s", error)
        return jsonify({"ok": False, "error": core.humanize_error(error)}), 400


app.view_functions["api_info"] = enhanced_api_info


@app.post("/api/quality-info")
def quality_info():
    try:
        payload = request.get_json(silent=True) or {}
        url = core.clean_url(payload.get("url", ""))
        info = core.get_media_info(url)
        qualities, source_heights = _quality_catalog(info)
        return jsonify({
            "ok": True,
            "url": url,
            "title": info.get("title") or "Untitled media",
            "thumbnail": info.get("thumbnail"),
            "platform": core.platform_for(url),
            "qualities": qualities,
            "source_heights": source_heights,
            "formats": _compact_formats(info),
        })
    except Exception as error:
        core.app.logger.warning("Quality info error: %s", error)
        return jsonify({"ok": False, "error": core.humanize_error(error)}), 400


@app.post("/api/image-download")
def image_download():
    """Download the public thumbnail/image exposed by a supported media extractor.
    The client supplies the original supported media URL, not an arbitrary
    remote URL, so the server resolves the image through yt-dlp first."""
    try:
        payload = request.get_json(silent=True) or {}
        media_url = core.clean_url(payload.get("url", ""))
        info = core.get_media_info(media_url)
        image_url = info.get("thumbnail")
        if not image_url:
            return jsonify({"ok": False, "error": "This source did not expose a downloadable image."}), 404
        parsed = urlparse(image_url)
        if parsed.scheme not in {"http", "https"}:
            return jsonify({"ok": False, "error": "Invalid image source."}), 400
        req = Request(image_url, headers={"User-Agent": "Mozilla/5.0 VidLoom/1.0"})
        with urlopen(req, timeout=30) as response:
            data = response.read()
            content_type = response.headers.get_content_type() or "image/jpeg"
        if not content_type.startswith("image/"):
            return jsonify({"ok": False, "error": "The source did not return an image."}), 400
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        safe_title = "".join(c for c in (info.get("title") or "image") if c.isalnum() or c in " ._-").strip()[:80] or "image"
        return send_file(BytesIO(data), mimetype=content_type, as_attachment=True, download_name=f"{safe_title}{ext}")
    except Exception as error:
        core.app.logger.warning("Image download error: %s", error)
        return jsonify({"ok": False, "error": core.humanize_error(error)}), 400


def strict_choose_video_format(info, requested_height):
    formats = info.get("formats") or []
    exact = [
        f for f in formats
        if int(f.get("height") or 0) == requested_height
        and f.get("vcodec") not in (None, "none")
    ]
    if not exact:
        raise ValueError(
            f"The quality you selected ({requested_height}p) is not available. Select another quality."
        )
    progressive = [f for f in exact if f.get("acodec") not in (None, "none")]
    progressive.sort(
        key=lambda f: (f.get("ext") == "mp4", float(f.get("tbr") or 0)),
        reverse=True,
    )
    if progressive:
        ext = "mp4" if any(f.get("ext") == "mp4" for f in progressive) else progressive[0].get("ext")
        return f"best[height={requested_height}][ext={ext}]/best[height={requested_height}]", requested_height
    if not core.FFMPEG_AVAILABLE:
        raise RuntimeError(
            "This quality has separate video/audio streams and FFmpeg is required to merge them."
        )
    return (
        f"bestvideo[height={requested_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height={requested_height}]+bestaudio"
    ), requested_height


core.choose_video_format = strict_choose_video_format
runtime_patch.install(core)

_original_index = app.view_functions["index"]


def enhanced_index():
    response = _original_index()
    if isinstance(response, str):
        import re
        response = re.sub(
            r'<script[^>]+/static/(?:quality-fix|manual-quality|quality-ui-v2)\\.js[^>]*></script>',
            '',
            response,
        )
        response = response.replace(
            "</body>",
            '<script src="/static/quality-final.js?v=2"></script></body>'
        )
    return response


app.view_functions["index"] = enhanced_index
