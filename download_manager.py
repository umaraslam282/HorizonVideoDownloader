"""
Horizon Video Downloader v3 — Download Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Centralized concurrent download engine with subprocess isolation.

Architecture
────────────
- Every download gets a unique task_id (UUID) and runs in its own
  daemon thread with an isolated yt-dlp subprocess.
- Progress is parsed from yt-dlp's structured JSON output
  (--progress-template "%(progress)j") — no regex on console text.
- Worker threads push updates to WebSocket clients via an
  asyncio.run_coroutine_threadsafe() bridge.
- Pause/Resume uses psutil to suspend/resume OS-level process threads.
- Cancel kills the entire subprocess tree and cleans up temp files.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import psutil

from config import (
    DEFAULT_DOWNLOAD_DIR,
    FFMPEG_PATH,
    MAX_CONCURRENT_DOWNLOADS,
    OUTPUT_TEMPLATE,
    SUBPROCESS_FLAGS,
    YTDLP_PATH,
    YTDLP_RESILIENCE_FLAGS,
)
from database import insert_download, update_status, update_title

logger = logging.getLogger("hvd.download")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Download Task
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class DownloadTask:
    """
    Represents a single download job with full lifecycle state.

    Public fields are serialized to JSON for the REST API and WebSocket
    broadcasts.  Private fields (_process, _thread, _temp_files) are
    internal bookkeeping only.
    """

    task_id: str
    url: str
    format_type: str  # "video" | "audio"
    quality: str = "best"  # "best","2160","1440","1080","720","480","360"
    audio_format: str = "mp3"  # "mp3","m4a","flac","wav","ogg"
    video_format: str = "mp4"  # "mp4","mkv","webm"
    subtitles: str = "none"  # "none","best","author","auto"
    subtitle_lang: str = "en"  # "en","ur","es","ar","fr","de","hi","ja","ko","zh"
    cookie_file: str | None = None
    playlist: bool = False
    output_dir: str = DEFAULT_DOWNLOAD_DIR
    rate_limit: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str = "queued"
    # Possible statuses:
    #   queued → downloading → completed
    #                        → paused → downloading … → completed
    #                        → cancelled
    #                        → error
    filename: str | None = None
    progress: float = 0.0  # 0.0 – 100.0
    speed: str | None = None
    eta: str | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    output_path: str | None = None

    # ── Internal (not serialized) ─────────────────────────────
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _temp_files: set[str] = field(default_factory=set, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary for API / WS payloads."""
        return {
            "task_id": self.task_id,
            "url": self.url,
            "format_type": self.format_type,
            "quality": self.quality,
            "audio_format": self.audio_format,
            "video_format": self.video_format,
            "output_dir": self.output_dir,
            "status": self.status,
            "filename": self.filename,
            "progress": round(self.progress, 1),
            "speed": self.speed,
            "eta": self.eta,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "output_path": self.output_path,
            "rate_limit": self.rate_limit,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Download Manager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DownloadManager:
    """
    Centralized download engine.

    Usage (wired in server.py lifespan):
        dm = DownloadManager()
        dm.set_event_loop(asyncio.get_running_loop())
        dm.set_broadcast_callback(ws_manager.broadcast)

    Then from any REST route:
        task_id = dm.start_download(url, "video")
    """

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    # ── Wiring (called once during server lifespan startup) ───

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the main asyncio event loop for the thread→async bridge."""
        self._loop = loop

    def set_broadcast_callback(
        self, fn: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Register the async broadcast function (WebSocketManager.broadcast)."""
        self._broadcast_fn = fn

    # ── Public API ────────────────────────────────────────────

    def start_download(
        self,
        url: str,
        format_type: str = "video",
        quality: str = "best",
        audio_format: str = "mp3",
        video_format: str = "mp4",
        subtitles: str = "none",
        subtitle_lang: str = "en",
        cookie_file: str | None = None,
        playlist: bool = False,
        output_dir: str | None = None,
        rate_limit: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> str:
        """
        Create and start a new download task.

        Returns the task_id (12-char hex UUID).
        Raises RuntimeError if the concurrent limit is reached.
        """
        with self._lock:
            active = sum(
                1
                for t in self._tasks.values()
                if t.status in ("queued", "downloading", "paused")
            )
            if active >= MAX_CONCURRENT_DOWNLOADS:
                raise RuntimeError(
                    f"Concurrent download limit ({MAX_CONCURRENT_DOWNLOADS}) reached. "
                    "Cancel or wait for an active download to finish."
                )

            task_id = uuid.uuid4().hex[:12]
            task = DownloadTask(
                task_id=task_id,
                url=url,
                format_type=format_type,
                quality=quality,
                audio_format=audio_format,
                video_format=video_format,
                subtitles=subtitles,
                subtitle_lang=subtitle_lang,
                cookie_file=cookie_file,
                playlist=playlist,
                output_dir=output_dir or DEFAULT_DOWNLOAD_DIR,
                rate_limit=rate_limit,
                start_time=start_time,
                end_time=end_time,
            )
            self._tasks[task_id] = task
            insert_download(task_id, url)

        # Spawn isolated worker thread
        thread = threading.Thread(
            target=self._run_download,
            args=(task,),
            name=f"hvd-worker-{task_id}",
            daemon=True,
        )
        task._thread = thread
        thread.start()

        logger.info(
            f"[{task_id}] Started: {url}  "
            f"format={format_type}  quality={quality}"
        )
        return task_id

    def cancel_download(self, task_id: str) -> bool:
        """
        Immediately terminate a download and clean up temp files.
        Returns True if the task was found and cancelled.
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in ("completed", "cancelled"):
            return False

        self._kill_process_tree(task)
        task.status = "cancelled"
        task.progress = 0.0
        task.speed = None
        task.eta = None
        self._cleanup_temp_files(task)
        self._broadcast_update(task)
        logger.info(f"[{task_id}] Cancelled")
        return True

    def pause_download(self, task_id: str) -> bool:
        """
        Suspend a running download subprocess via psutil.
        Returns True on success.
        """
        task = self._tasks.get(task_id)
        if not task or task.status != "downloading":
            return False

        try:
            if task._process and task._process.poll() is None:
                proc = psutil.Process(task._process.pid)
                # Suspend all threads in the process tree
                for child in proc.children(recursive=True):
                    try:
                        child.suspend()
                    except psutil.NoSuchProcess:
                        pass
                proc.suspend()
                task.status = "paused"
                self._broadcast_update(task)
                logger.info(f"[{task_id}] Paused")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            logger.warning(f"[{task_id}] Pause failed: {exc}")
        return False

    def resume_download(self, task_id: str) -> bool:
        """
        Resume a paused download subprocess via psutil.
        Returns True on success.
        """
        task = self._tasks.get(task_id)
        if not task or task.status != "paused":
            return False

        try:
            if task._process and task._process.poll() is None:
                proc = psutil.Process(task._process.pid)
                proc.resume()
                for child in proc.children(recursive=True):
                    try:
                        child.resume()
                    except psutil.NoSuchProcess:
                        pass
                task.status = "downloading"
                self._broadcast_update(task)
                logger.info(f"[{task_id}] Resumed")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            logger.warning(f"[{task_id}] Resume failed: {exc}")
        return False

    def get_task(self, task_id: str) -> DownloadTask | None:
        """Return a single task by ID, or None."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """Return all tasks as serialized dictionaries (newest first)."""
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks]

    def shutdown(self) -> None:
        """Kill every active download. Called on server shutdown."""
        logger.info("DownloadManager shutting down — terminating active tasks…")
        for task in list(self._tasks.values()):
            if task.status in ("downloading", "paused", "queued"):
                self._kill_process_tree(task)
                task.status = "cancelled"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Worker Thread
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _run_download(self, task: DownloadTask) -> None:
        """
        Worker function — runs in a dedicated daemon thread.
        Launches yt-dlp as a subprocess, streams structured JSON
        progress, and pushes updates to WebSocket clients.
        """
        try:
            cmd = self._build_command(task)
            logger.debug(f"[{task.task_id}] CMD: {' '.join(cmd)}")

            # Ensure output directory exists
            os.makedirs(task.output_dir, exist_ok=True)

            task._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,  # Line-buffered
                creationflags=SUBPROCESS_FLAGS,
                cwd=task.output_dir,
            )
            task.status = "downloading"
            self._broadcast_update(task)

            last_log_time = 0.0
            # ── Stream stdout line by line ────────────────────
            assert task._process.stdout is not None
            for raw_line in task._process.stdout:
                line = raw_line.strip()
                if not line:
                    continue

                # JSON progress from --progress-template
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        self._handle_progress(task, data)
                        if data.get("status") == "downloading":
                            now = time.time()
                            if now - last_log_time >= 1.0:
                                last_log_time = now
                                downloaded = data.get("downloaded_bytes") or 0
                                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                                pct = (downloaded / total * 100) if total > 0 else 0.0
                                spd_mb = (data.get("speed") or 0) / (1024 * 1024)
                                raw_eta = data.get("eta") or 0
                                m, s = divmod(int(raw_eta), 60)
                                fmt_str = f"Progress: {pct:.1f}% | Speed: {spd_mb:.2f} MB/s | ETA: {m:02d}:{s:02d}"
                                self._broadcast_log(task.task_id, fmt_str)
                    except json.JSONDecodeError:
                        logger.debug(f"[{task.task_id}] Non-JSON brace line: {line[:80]}")

                # Final filepath from --print "after_move:…"
                elif line.startswith("HVD_FILEPATH:"):
                    task.output_path = line[len("HVD_FILEPATH:"):]
                    task.filename = Path(task.output_path).name
                    self._broadcast_log(task.task_id, f"File saved: {task.filename}")
                else:
                    self._broadcast_log(task.task_id, line)

            # ── Process exited ────────────────────────────────
            return_code = task._process.wait()

            if task.status == "cancelled":
                return  # Already handled by cancel_download()

            if return_code == 0:
                task.status = "completed"
                task.progress = 100.0
                task.speed = None
                task.eta = None
                logger.info(f"[{task.task_id}] Completed: {task.filename}")
            else:
                task.status = "error"
                task.error_message = f"yt-dlp exited with code {return_code}"
                logger.error(f"[{task.task_id}] Failed (exit {return_code})")

        except FileNotFoundError:
            task.status = "error"
            task.error_message = (
                f"yt-dlp not found at '{YTDLP_PATH}'. "
                "Ensure yt-dlp.exe is in the application directory."
            )
            logger.error(f"[{task.task_id}] {task.error_message}")

        except Exception as exc:
            task.status = "error"
            task.error_message = str(exc)
            logger.exception(f"[{task.task_id}] Worker exception")

        finally:
            db_status = task.status
            if task.status == "error":
                db_status = "failed"
            update_status(task.task_id, db_status)
            self._broadcast_update(task)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Command Builder
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_command(self, task: DownloadTask) -> list[str]:
        """Construct the full yt-dlp command for a task."""
        cmd: list[str] = [
            YTDLP_PATH,
            "--ffmpeg-location", FFMPEG_PATH,
            # Structured progress output (no regex)
            "--newline",
            "--no-colors",
            "--progress-template", "download:%(progress)j",
            "--progress-template", "postprocess:%(progress)j",
            # Print final filepath after all post-processing
            "--print", "after_move:HVD_FILEPATH:%(filepath)s",
            # Output template
            "-o", OUTPUT_TEMPLATE,
            # Network resilience
            *YTDLP_RESILIENCE_FLAGS,
        ]

        # ── Playlist vs Single ────────────────────────────────
        if not task.playlist:
            cmd.append("--no-playlist")
        # (If playlist=True, omit --no-playlist so yt-dlp expands the list)

        # ── Cookie File ───────────────────────────────────────
        if task.cookie_file:
            cmd.extend(["--cookies", task.cookie_file])

        # ── Format Selection ──────────────────────────────────
        if task.format_type == "audio":
            cmd.extend(["-x", "--audio-format", task.audio_format, "--audio-quality", "0"])
        elif task.format_type == "video":
            vcodec_filter = ""
            if task.video_format in ["mov", "avi"]:
                vcodec_filter = "[vcodec^=avc]"
            
            if task.quality == "best" or not task.quality:
                format_str = f"bv*{vcodec_filter}+ba/b"
            else:
                format_str = f"bv*[height<={task.quality}]{vcodec_filter}+ba/b[height<={task.quality}]"
            
            cmd.extend(["-f", format_str, "--merge-output-format", task.video_format])
            if task.video_format == "mov":
                cmd.extend(["--postprocessor-args", "Merger+ffmpeg:-c:a aac"])

        # ── Subtitles ─────────────────────────────────────────
        if task.subtitles != "none":
            lang = task.subtitle_lang or "en"
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", f"{lang}.*"])
            # Embed subs into video container if video download
            if task.format_type == "video":
                cmd.extend(["--embed-subs", "--convert-subs", "srt", "--compat-options", "no-keep-subs"])

        # ── Power-User Features ──────────────────────────────
        if task.rate_limit:
            cmd.extend(["--limit-rate", task.rate_limit])

        if task.start_time or task.end_time:
            st = task.start_time or ""
            et = task.end_time or ""
            cmd.extend(["--download-sections", f"*{st}-{et}"])

        cmd.append("--verbose")
        # URL must be last
        cmd.append(task.url)
        return cmd

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Progress Handler
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _handle_progress(self, task: DownloadTask, data: dict[str, Any]) -> None:
        """Process a parsed JSON progress object from yt-dlp."""
        status = data.get("status", "")

        # Track temp files for targeted cleanup on cancel
        tmpfile = data.get("tmpfilename")
        if tmpfile:
            task._temp_files.add(tmpfile)

        # Extract filename (prefer final name over temp name)
        fname = data.get("filename") or tmpfile
        if fname and not task.output_path:
            task.filename = Path(fname).name
            update_title(task.task_id, Path(fname).stem)

        # Extract title from info_dict if available
        title = data.get("info_dict", {}).get("title")
        if title:
            update_title(task.task_id, title)

        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes", 0)

            if total > 0:
                task.progress = min((downloaded / total) * 100.0, 100.0)

            task.downloaded_bytes = downloaded
            task.total_bytes = total

            # Speed — prefer raw numeric value, fall back to formatted string
            raw_speed = data.get("speed")
            if raw_speed and isinstance(raw_speed, (int, float)):
                task.speed = self._format_speed(raw_speed)
            else:
                task.speed = (data.get("_speed_str") or "").strip() or None

            # ETA — prefer raw seconds, fall back to formatted string
            raw_eta = data.get("eta")
            if raw_eta is not None and isinstance(raw_eta, (int, float)):
                task.eta = self._format_eta(int(raw_eta))
            else:
                task.eta = (data.get("_eta_str") or "").strip() or None

            if task.status != "paused":
                task.status = "downloading"

        elif status == "finished":
            # Download phase complete — post-processing may follow
            task.progress = 100.0
            task.speed = None
            task.eta = None

        # Broadcast every parsed update
        self._broadcast_update(task)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Internal Helpers
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _broadcast_update(self, task: DownloadTask) -> None:
        """
        Push current task state to every connected WebSocket client.
        Thread-safe: uses asyncio.run_coroutine_threadsafe() to bridge
        from worker threads into the server's async event loop.
        """
        if not self._broadcast_fn or not self._loop:
            return

        payload: dict[str, Any] = {"type": "progress", **task.to_dict()}
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_fn(payload), self._loop
            )
        except RuntimeError:
            # Event loop is closed (server shutting down)
            pass

    def _broadcast_log(self, task_id: str, message: str) -> None:
        """Push a raw log line to WebSocket clients."""
        if not self._broadcast_fn or not self._loop:
            return
        payload: dict[str, Any] = {
            "type": "log",
            "task_id": task_id,
            "message": message,
        }
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_fn(payload), self._loop
            )
        except RuntimeError:
            pass

    def _kill_process_tree(self, task: DownloadTask) -> None:
        """Terminate a subprocess and all its child processes."""
        if not task._process:
            return
        try:
            parent = psutil.Process(task._process.pid)
            children = parent.children(recursive=True)
            # Kill children first, then parent
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            task._process.wait(timeout=5)
        except psutil.NoSuchProcess:
            pass  # Already dead
        except subprocess.TimeoutExpired:
            logger.warning(f"[{task.task_id}] Process didn't exit within 5s timeout")
        except Exception as exc:
            logger.warning(f"[{task.task_id}] Kill error: {exc}")

    def _cleanup_temp_files(self, task: DownloadTask) -> None:
        """
        Remove temporary .part / .ytdl files left by a cancelled download.
        Only targets files explicitly tracked via progress updates
        (safe — won't touch unrelated files in the Downloads folder).
        """
        for filepath in task._temp_files:
            try:
                p = Path(filepath)
                if p.exists():
                    p.unlink()
                    logger.debug(f"[{task.task_id}] Cleaned: {p.name}")
            except OSError as exc:
                logger.debug(f"[{task.task_id}] Cleanup skip: {exc}")

        # Also try to remove the .part variant of the main filename
        if task.filename:
            part_file = Path(task.output_dir) / (task.filename + ".part")
            try:
                if part_file.exists():
                    part_file.unlink()
                    logger.debug(f"[{task.task_id}] Cleaned: {part_file.name}")
            except OSError:
                pass

    # ── Formatting Utilities ──────────────────────────────────

    @staticmethod
    def _format_speed(bytes_per_sec: float) -> str:
        """Convert bytes/sec to a human-readable string."""
        if bytes_per_sec <= 0:
            return "0 B/s"
        units = [
            (1024**3, "GB/s"),
            (1024**2, "MB/s"),
            (1024, "KB/s"),
            (1, "B/s"),
        ]
        for threshold, label in units:
            if bytes_per_sec >= threshold:
                value = bytes_per_sec / threshold
                # Use fewer decimals for larger units
                precision = 2 if threshold >= 1024**3 else 1
                return f"{value:.{precision}f} {label}"
        return f"{bytes_per_sec:.0f} B/s"

    @staticmethod
    def _format_eta(seconds: int) -> str:
        """Convert seconds to mm:ss or h:mm:ss."""
        if seconds < 0:
            return "∞"
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
