"""
Horizon Video Downloader v5 — REST API Routes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All HTTP endpoints for download lifecycle management,
video metadata retrieval, and playlist info.

Built on Starlette (pure Python, no Pydantic/Rust dependency).
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from config import SUBPROCESS_FLAGS, YTDLP_PATH

logger = logging.getLogger("hvd.api")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Validation Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VALID_FORMAT_TYPES = {"video", "audio"}
VALID_QUALITIES = {"best", "4320", "2160", "1440", "1080", "720", "480", "360", "144"}
VALID_AUDIO_FORMATS = {"mp3", "m4a", "flac", "wav", "ogg", "alac", "opus"}
VALID_VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov", "avi", "flv"}
VALID_SUBTITLES = {"none", "best", "author", "auto"}
VALID_SUBTITLE_LANGS = {"en", "ur", "es", "ar", "fr", "de", "hi", "ja", "ko", "zh"}


def _error(message: str, status: int = 400) -> JSONResponse:
    """Shorthand for returning a JSON error response."""
    return JSONResponse({"error": message}, status_code=status)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Download Lifecycle Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def start_download(request: Request) -> JSONResponse:
    """POST /api/download — Start a new download job. Returns a unique task_id."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required")

    format_type = body.get("format_type", "video")
    if format_type not in VALID_FORMAT_TYPES:
        return _error(f"'format_type' must be one of: {', '.join(VALID_FORMAT_TYPES)}")

    quality = body.get("quality", "best")
    if quality not in VALID_QUALITIES:
        return _error(f"'quality' must be one of: {', '.join(VALID_QUALITIES)}")

    audio_format = body.get("audio_format", "mp3")
    if audio_format not in VALID_AUDIO_FORMATS:
        return _error(f"'audio_format' must be one of: {', '.join(VALID_AUDIO_FORMATS)}")

    video_format = body.get("video_format", "mp4")
    if video_format not in VALID_VIDEO_FORMATS:
        return _error(f"'video_format' must be one of: {', '.join(VALID_VIDEO_FORMATS)}")

    subtitles = body.get("subtitles", "none")
    if subtitles not in VALID_SUBTITLES:
        return _error(f"'subtitles' must be one of: {', '.join(VALID_SUBTITLES)}")

    subtitle_lang = body.get("subtitle_lang", "en")
    if subtitle_lang not in VALID_SUBTITLE_LANGS:
        return _error(f"'subtitle_lang' must be one of: {', '.join(VALID_SUBTITLE_LANGS)}")

    cookie_file = body.get("cookie_file")  # Optional string or None
    playlist = bool(body.get("playlist", False))
    output_dir = body.get("output_dir")  # Optional string or None
    rate_limit = body.get("rate_limit")
    start_time = body.get("start_time")
    end_time = body.get("end_time")

    dm = request.app.state.download_manager
    try:
        task_id = dm.start_download(
            url=url,
            format_type=format_type,
            quality=quality,
            audio_format=audio_format,
            video_format=video_format,
            subtitles=subtitles,
            subtitle_lang=subtitle_lang,
            cookie_file=cookie_file,
            playlist=playlist,
            output_dir=output_dir,
            rate_limit=rate_limit,
            start_time=start_time,
            end_time=end_time,
        )
        return JSONResponse({"task_id": task_id, "message": "Download started"})
    except RuntimeError as exc:
        return _error(str(exc), status=429)
    except Exception as exc:
        logger.exception("Failed to start download")
        return _error(str(exc), status=500)


async def cancel_download(request: Request) -> JSONResponse:
    """POST /api/cancel/{task_id} — Immediately terminate and clean up."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    success = dm.cancel_download(task_id)
    if not success:
        return _error(f"Task '{task_id}' not found or already finished.", status=404)
    return JSONResponse({"success": True, "message": f"Task {task_id} cancelled"})


async def pause_download(request: Request) -> JSONResponse:
    """POST /api/pause/{task_id} — Suspend a running download process."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    success = dm.pause_download(task_id)
    if not success:
        return _error(f"Task '{task_id}' not found or not in a pausable state.")
    return JSONResponse({"success": True, "message": f"Task {task_id} paused"})


async def resume_download(request: Request) -> JSONResponse:
    """POST /api/resume/{task_id} — Resume a paused download process."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    success = dm.resume_download(task_id)
    if not success:
        return _error(f"Task '{task_id}' not found or not paused.")
    return JSONResponse({"success": True, "message": f"Task {task_id} resumed"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Task Queries
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def list_tasks(request: Request) -> JSONResponse:
    """GET /api/tasks — Return all tasks (active + history), newest first."""
    dm = request.app.state.download_manager
    return JSONResponse({"tasks": dm.get_all_tasks()})


async def get_task(request: Request) -> JSONResponse:
    """GET /api/tasks/{task_id} — Return details for a single task."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)
    if not task:
        return _error(f"Task '{task_id}' not found.", status=404)
    return JSONResponse({"task": task.to_dict()})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Video & Playlist Metadata
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def get_video_info(request: Request) -> JSONResponse:
    """
    POST /api/info — Fetch video metadata (title, duration, thumbnail,
    available formats) via yt-dlp --dump-single-json.
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required")

    try:
        info = await asyncio.to_thread(_fetch_video_info, url)
        return JSONResponse(info)
    except FileNotFoundError:
        return _error(f"yt-dlp not found at '{YTDLP_PATH}'.", status=500)
    except subprocess.TimeoutExpired:
        return _error("yt-dlp timed out fetching video info (30s limit).", status=504)
    except Exception as exc:
        logger.exception("Info fetch failed")
        return _error(str(exc))


async def get_playlist_info(request: Request) -> JSONResponse:
    """
    POST /api/playlist-info — Rapidly fetch playlist metadata using
    yt-dlp --flat-playlist --dump-single-json.

    Returns playlist title, count, and a clean array of entries with
    id, title, url, thumbnail, and duration for each video.
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required")

    cookie_file = body.get("cookie_file")

    try:
        info = await asyncio.to_thread(_fetch_playlist_info, url, cookie_file)
        return JSONResponse(info)
    except FileNotFoundError:
        return _error(f"yt-dlp not found at '{YTDLP_PATH}'.", status=500)
    except subprocess.TimeoutExpired:
        return _error("yt-dlp timed out fetching playlist info (120s limit).", status=504)
    except Exception as exc:
        logger.exception("Playlist info fetch failed")
        return _error(str(exc))


async def update_ytdlp(request: Request) -> JSONResponse:
    """POST /api/update-ytdlp — Run yt-dlp -U to self-update."""
    try:
        result = await asyncio.to_thread(_run_ytdlp_update)
        return JSONResponse(result)
    except FileNotFoundError:
        return _error(f"yt-dlp not found at '{YTDLP_PATH}'.", status=500)
    except subprocess.TimeoutExpired:
        return _error("yt-dlp update timed out (120s limit).", status=504)
    except Exception as exc:
        logger.exception("yt-dlp update failed")
        return _error(str(exc), status=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health Check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def health(request: Request) -> JSONResponse:
    """GET /health — Readiness probe for startup sequencing."""
    return JSONResponse({"status": "ok"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Private Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _fetch_video_info(url: str) -> dict:
    """
    Run yt-dlp --dump-single-json synchronously (called via asyncio.to_thread).
    Returns a curated subset of the full metadata.
    """
    cmd = [
        YTDLP_PATH,
        "--dump-single-json",
        "--no-download",
        "--no-playlist",
        "--no-warnings",
        url,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=SUBPROCESS_FLAGS,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "Unknown error"
        raise RuntimeError(f"yt-dlp info extraction failed: {stderr}")

    raw = json.loads(result.stdout)

    return {
        "title": raw.get("title"),
        "duration": raw.get("duration"),
        "duration_string": raw.get("duration_string"),
        "thumbnail": raw.get("thumbnail"),
        "uploader": raw.get("uploader"),
        "uploader_url": raw.get("uploader_url"),
        "view_count": raw.get("view_count"),
        "upload_date": raw.get("upload_date"),
        "description": (raw.get("description") or "")[:500],
        "webpage_url": raw.get("webpage_url"),
        "formats": _extract_format_options(raw.get("formats") or []),
    }


def _fetch_playlist_info(url: str, cookie_file: str | None = None) -> dict:
    """
    Run yt-dlp --flat-playlist --dump-single-json to rapidly fetch
    playlist metadata without downloading any video data.
    """
    cmd = [
        YTDLP_PATH,
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
    ]
    if cookie_file:
        cmd.extend(["--cookies", cookie_file])
    cmd.append(url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=SUBPROCESS_FLAGS,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "Unknown error"
        raise RuntimeError(f"Playlist fetch failed: {stderr}")

    raw = json.loads(result.stdout)

    entries = []
    for entry in raw.get("entries") or []:
        if not entry:
            continue
        video_id = entry.get("id", "")
        # Resolve thumbnail: try entry's thumbnails, then construct from YouTube ID
        thumb = ""
        thumbs = entry.get("thumbnails")
        if thumbs and isinstance(thumbs, list):
            thumb = thumbs[-1].get("url", "")
        elif entry.get("thumbnail"):
            thumb = entry["thumbnail"]
        elif video_id:
            thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        # Resolve URL: try entry's url/webpage_url, else construct from ID
        video_url = entry.get("url") or entry.get("webpage_url") or ""
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

        entries.append({
            "id": video_id,
            "title": entry.get("title") or "Untitled",
            "url": video_url,
            "thumbnail": thumb,
            "duration": entry.get("duration"),
            "uploader": entry.get("uploader") or entry.get("channel"),
        })

    return {
        "playlist_title": raw.get("title") or "Untitled Playlist",
        "playlist_id": raw.get("id"),
        "uploader": raw.get("uploader") or raw.get("channel"),
        "count": len(entries),
        "entries": entries,
    }


def _run_ytdlp_update() -> dict:
    """
    Download the latest yt-dlp.exe from GitHub directly to a temp file
    and atomically replace the current executable on disk.
    """
    import urllib.request
    import os
    import shutil
    from config import BUNDLE_DIR

    # Resolve actual target path (in case it is non-absolute / command only)
    target_path = Path(YTDLP_PATH)
    if not target_path.is_absolute():
        resolved = shutil.which(YTDLP_PATH)
        if resolved:
            target_path = Path(resolved)
        else:
            target_path = BUNDLE_DIR / "yt-dlp.exe"

    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        logger.info(f"Downloading yt-dlp.exe from {url} to {tmp_path}")
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(tmp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
        
        logger.info(f"Atomic replacement: replacing {target_path} with {tmp_path}")
        os.replace(tmp_path, target_path)
        return {
            "success": True,
            "output": f"Successfully updated yt-dlp.exe at: {target_path}",
        }
    except Exception as exc:
        logger.exception("Failed to update yt-dlp executable")
        if tmp_path.exists():
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return {
            "success": False,
            "output": f"Update failed: {str(exc)}",
        }


def _extract_format_options(formats: list[dict]) -> dict:
    """
    Extract unique video resolutions and audio formats from
    yt-dlp's full format list.
    """
    video_heights: set[int] = set()
    audio_formats: set[str] = set()

    for fmt in formats:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec", "none")
        acodec = fmt.get("acodec", "none")
        ext = fmt.get("ext", "")

        # Video resolutions (only entries with actual video codec)
        if height and vcodec != "none":
            video_heights.add(height)

        # Audio-only formats
        if acodec != "none" and vcodec == "none" and ext:
            audio_formats.add(ext)

    return {
        "video_qualities": sorted(video_heights, reverse=True),
        "audio_formats": sorted(audio_formats),
    }


async def open_folder(request: Request) -> JSONResponse:
    """POST /api/open-folder/{task_id} — Open Windows Explorer with the file highlighted."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)
    if not task:
        return _error(f"Task '{task_id}' not found.", status=404)
    
    filepath = task.output_path
    if not filepath or not Path(filepath).exists():
        fallback_dir = task.output_dir or str(Path.home() / "Downloads")
        if Path(fallback_dir).exists():
            try:
                subprocess.Popen(f'explorer "{fallback_dir}"', creationflags=SUBPROCESS_FLAGS)
                return JSONResponse({"success": True, "message": "Opened download folder"})
            except Exception as e:
                return _error(str(e), status=500)
        return _error("File or folder does not exist on disk.", status=404)

    try:
        cmd = f'explorer /select,"{Path(filepath).resolve()}"'
        subprocess.Popen(cmd, creationflags=SUBPROCESS_FLAGS)
        return JSONResponse({"success": True, "message": "Opened folder with file selected"})
    except Exception as e:
        logger.exception("Failed to open folder")
        return _error(str(e), status=500)


async def fetch_social(request: Request) -> JSONResponse:
    """GET /api/fetch-social — Fetch media info using gallery-dl."""
    import os
    dm = request.app.state.download_manager
    params = request.query_params
    url = params.get("url")
    if not url:
        dm._broadcast_log("social", "Fetch request failed: URL is required.")
        return _error("URL is required.", status=400)
    
    dm._broadcast_log("social", f"Fetching social media metadata for: {url}")
    cookie_file = params.get("cookie_file")
    from config import BUNDLE_DIR
    gallery_dl_bin = "gallery-dl"
    bundle_path = BUNDLE_DIR / "gallery-dl.exe"
    if bundle_path.exists():
        gallery_dl_bin = str(bundle_path)
    
    cmd = [gallery_dl_bin, "-j", url]
    if cookie_file:
        from config import DEFAULT_DOWNLOAD_DIR
        cookie_path = Path(cookie_file)
        if not cookie_path.is_absolute():
            cookie_path = Path(DEFAULT_DOWNLOAD_DIR) / cookie_file
        if cookie_path.exists():
            cmd.extend(["--cookies", str(cookie_path)])
            
    try:
        creation_flags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags
        )
        
        stdout_lines = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line_str = line.strip()
            if line_str:
                stdout_lines.append(line_str)
                dm._broadcast_log("social", f"[Fetch] {line_str}")
                
        proc.wait()
        if proc.returncode != 0:
            err_msg = "".join(stdout_lines[-3:]) or "Unknown error"
            dm._broadcast_log("social", f"Fetch failed (code {proc.returncode}): {err_msg}")
            return _error(f"gallery-dl failed: {err_msg}", status=500)
            
        stdout_str = "\n".join(stdout_lines).strip()
        if not stdout_str:
            dm._broadcast_log("social", "Fetch complete. No output received.")
            return JSONResponse([])
            
        try:
            raw_data = json.loads(stdout_str)
        except json.JSONDecodeError:
            raw_data = []
            for line in stdout_str.splitlines():
                line = line.strip()
                if line:
                    try:
                        raw_data.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                        
        def extract_items(data):
            items = []
            if isinstance(data, dict):
                video_url = data.get("video_url")
                display_url = data.get("display_url")
                direct_url = data.get("url")
                
                target_url = video_url or display_url or direct_url
                if target_url and isinstance(target_url, str) and (target_url.startswith("http://") or target_url.startswith("https://")):
                    url_lower = target_url.lower()
                    if not ("/avatar/" in url_lower or "profile_pic" in url_lower or "anonymous_user" in url_lower or "static" in url_lower or "assets" in url_lower):
                        media_type = "video" if (video_url or (data.get("extension") or "").lower() in ("mp4", "mkv", "webm", "mov") or target_url.split("?")[0].lower().endswith((".mp4", ".mkv", ".webm", ".mov"))) else "image"
                        items.append({
                            "url": target_url,
                            "type": media_type,
                            "thumbnail": display_url or target_url
                        })
                
                for k, v in data.items():
                    items.extend(extract_items(v))
            elif isinstance(data, list):
                for val in data:
                    items.extend(extract_items(val))
            return items
            
        found = extract_items(raw_data)
        seen = set()
        deduped = []
        for item in found:
            if item["url"] not in seen:
                seen.add(item["url"])
                deduped.append(item)
                
        # Group: videos first, then images (filtering out images that are already video thumbnails)
        videos = [item for item in deduped if item["type"] == "video"]
        images = [item for item in deduped if item["type"] == "image"]
        video_thumbnails = {v["thumbnail"] for v in videos if v.get("thumbnail")}
        filtered_images = [img for img in images if img["url"] not in video_thumbnails]
        final_items = videos + filtered_images
        
        dm._broadcast_log("social", f"Fetch complete. Found {len(final_items)} valid media items.")
        return JSONResponse(final_items)
        
    except Exception as e:
        logger.exception("Fetch social media failed")
        dm._broadcast_log("social", f"Fetch exception occurred: {str(e)}")
        return _error(str(e), status=500)


async def download_social(request: Request) -> JSONResponse:
    """POST /api/download-social — Download selected social media URLs."""
    import os
    import time
    import uuid
    import subprocess
    import urllib.request
    from database import insert_download, update_status, update_title
    from config import FFMPEG_PATH, DEFAULT_DOWNLOAD_DIR
    
    dm = request.app.state.download_manager
    body = await request.json()
    urls = body.get("urls")
    output_dir = body.get("output_dir")
    image_format = body.get("image_format", "original")
    video_format = body.get("video_format", "mp4")
    
    if not urls or not isinstance(urls, list):
        dm._broadcast_log("social", "Download request failed: urls parameter missing or invalid.")
        return _error("List of 'urls' is required.", status=400)
        
    out_path = Path(output_dir or DEFAULT_DOWNLOAD_DIR).resolve()
    dm._broadcast_log("social", f"Initiating batch download of {len(urls)} items to: {out_path}")
    try:
        os.makedirs(out_path, exist_ok=True)
    except Exception as e:
        dm._broadcast_log("social", f"Directory creation failed: {str(e)}")
        return _error(f"Cannot create save directory: {str(e)}", status=500)
        
    downloaded = 0
    errors = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.instagram.com/",
        "Accept": "*/*",
    }
    
    for i, url in enumerate(urls):
        task_id = f"soc_{uuid.uuid4().hex[:8]}"
        try:
            parsed_url = Path(url.split("?")[0])
            url_lower = parsed_url.name.lower()
            is_video = url_lower.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi"))
            
            # Determine native extension
            native_suffix = parsed_url.suffix
            if not native_suffix or len(native_suffix) > 5:
                native_suffix = ".mp4" if is_video else ".jpg"
            
            # Determine target extension
            if is_video:
                target_suffix = f".{video_format}"
            else:
                target_suffix = f".{image_format}" if image_format != "original" else native_suffix
                if not target_suffix or len(target_suffix) > 5:
                    target_suffix = ".jpg"
            
            final_filename = f"social_{time.strftime('%Y%m%d_%H%M%S')}_{i}{target_suffix}"
            final_file = out_path / final_filename
            
            # Log final filename to DB
            insert_download(task_id, url, title=final_filename)
            update_status(task_id, "downloading")
            
            # If native format doesn't match target format, download to a temp native file first
            if native_suffix.lower() != target_suffix.lower():
                temp_filename = f"social_temp_{uuid.uuid4().hex[:6]}{native_suffix}"
                native_file = out_path / temp_filename
                
                dm._broadcast_log("social", f"[Batch] Downloading raw stream to temp file: {temp_filename}")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response, open(native_file, "wb") as out_file:
                    out_file.write(response.read())
                    
                dm._broadcast_log("social", f"[FFmpeg] Converting {temp_filename} to {final_filename}")
                creation_flags = 0x08000000 if os.name == "nt" else 0
                conv = subprocess.run(
                    [str(FFMPEG_PATH), "-y", "-i", str(native_file), str(final_file)],
                    capture_output=True,
                    creationflags=creation_flags
                )
                
                if conv.returncode == 0:
                    try:
                        os.remove(native_file)
                    except Exception:
                        pass
                    downloaded += 1
                    update_status(task_id, "completed")
                else:
                    # Fallback if FFmpeg fails
                    dm._broadcast_log("social", f"[Warning] FFmpeg conversion failed (code {conv.returncode}). Keeping native stream.")
                    fallback_filename = f"social_{time.strftime('%Y%m%d_%H%M%S')}_{i}{native_suffix}"
                    fallback_file = out_path / fallback_filename
                    os.replace(native_file, fallback_file)
                    update_title(task_id, fallback_filename)
                    downloaded += 1
                    update_status(task_id, "completed")
            else:
                # Target format matches native format, write directly
                dm._broadcast_log("social", f"[Batch] Downloading item {i+1}/{len(urls)}: {final_filename}")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response, open(final_file, "wb") as out_file:
                    out_file.write(response.read())
                downloaded += 1
                update_status(task_id, "completed")
                
        except Exception as e:
            err_str = f"Item {i+1} failed: {str(e)}"
            errors.append(err_str)
            dm._broadcast_log("social", f"[Error] {err_str}")
            update_status(task_id, "failed")
            
    dm._broadcast_log("social", f"Batch download finished. Successful: {downloaded}/{len(urls)}.")
    if errors and downloaded == 0:
        return _error("; ".join(errors), status=500)
        
    return JSONResponse({
        "success": True,
        "message": f"Successfully downloaded {downloaded}/{len(urls)} items.",
        "errors": errors
    })


async def list_history(request: Request) -> JSONResponse:
    """GET /api/history — Retrieve persistent download history."""
    try:
        from database import get_all_history
        history = get_all_history()
        return JSONResponse(history)
    except Exception as e:
        return _error(str(e), status=500)


# ── Route Table ───────────────────────────────────────────────────

routes = [
    Route("/api/download", start_download, methods=["POST"]),
    Route("/api/cancel/{task_id}", cancel_download, methods=["POST"]),
    Route("/api/pause/{task_id}", pause_download, methods=["POST"]),
    Route("/api/resume/{task_id}", resume_download, methods=["POST"]),
    Route("/api/open-folder/{task_id}", open_folder, methods=["POST"]),
    Route("/api/fetch-social", fetch_social, methods=["GET"]),
    Route("/api/download-social", download_social, methods=["POST"]),
    Route("/api/history", list_history, methods=["GET"]),
    Route("/api/tasks", list_tasks, methods=["GET"]),
    Route("/api/tasks/{task_id}", get_task, methods=["GET"]),
    Route("/api/info", get_video_info, methods=["POST"]),
    Route("/api/playlist-info", get_playlist_info, methods=["POST"]),
    Route("/api/update-ytdlp", update_ytdlp, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
]
