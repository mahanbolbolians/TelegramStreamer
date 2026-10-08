import os
import shutil
import asyncio
import logging
import time
from typing import Optional, Callable, Awaitable

logger = logging.getLogger("compressor")

COMPRESSED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "compressed")
TEMP_INPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "temp_downloads")

os.makedirs(COMPRESSED_DIR, exist_ok=True)
os.makedirs(TEMP_INPUT_DIR, exist_ok=True)

def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None

async def probe_duration(file_path: str) -> Optional[float]:
    """Get media duration in seconds using ffprobe if available."""
    if not shutil.which("ffprobe"):
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        val = stdout.decode().strip()
        if val:
            return float(val)
    except Exception as e:
        logger.debug(f"ffprobe duration probe failed: {e}")
    return None

async def run_fast_compression(
    input_path: str,
    output_path: str,
    duration_seconds: Optional[float] = None,
    progress_callback: Optional[Callable[[int, float, str], Awaitable[None]]] = None
) -> bool:
    """
    Compresses video to 720p HD using libx264 veryfast preset and CRF 26.
    Parses -progress pipe:1 to stream percentage, speed, and ETA.
    """
    if not is_ffmpeg_available():
        raise RuntimeError("ffmpeg binary not found in system PATH.")

    # Probe duration if not provided
    if not duration_seconds or duration_seconds <= 0:
        duration_seconds = await probe_duration(input_path)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "26",
        "-vf", "scale='min(1280,iw)':-2",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        output_path
    ]

    logger.info(f"Starting ffmpeg compression: {input_path} -> {output_path}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    last_update_time = 0.0
    out_time_s = 0.0
    speed_str = "1.0x"

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line_str = line.decode(errors="ignore").strip()
            if "=" in line_str:
                k, v = line_str.split("=", 1)
                k = k.strip()
                v = v.strip()

                if k == "out_time_us":
                    try:
                        out_time_s = float(v) / 1000000.0
                    except ValueError:
                        pass
                elif k == "speed":
                    speed_str = v
                elif k == "progress" and v in ("continue", "end"):
                    now = time.time()
                    # Throttle progress updates to avoid spamming callbacks (every 3 seconds)
                    if progress_callback and (now - last_update_time >= 3.0 or v == "end"):
                        pct = 0
                        if duration_seconds and duration_seconds > 0:
                            pct = min(99, int((out_time_s / duration_seconds) * 100))
                        try:
                            await progress_callback(pct, out_time_s, speed_str)
                        except Exception as cb_err:
                            logger.debug(f"Progress callback error: {cb_err}")
                        last_update_time = now

        await proc.wait()
        return proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        logger.error(f"Error during ffmpeg compression: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return False

def purge_old_cache(max_age_hours: int = 24):
    """Purges compressed files older than max_age_hours from disk."""
    now = time.time()
    max_age_sec = max_age_hours * 3600

    for folder in (COMPRESSED_DIR, TEMP_INPUT_DIR):
        if not os.path.exists(folder):
            continue
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            try:
                if os.path.isfile(fpath):
                    if now - os.path.getmtime(fpath) > max_age_sec:
                        os.remove(fpath)
                        logger.info(f"Purged expired cache file: {fname}")
            except Exception as e:
                logger.warning(f"Error purging file {fpath}: {e}")
