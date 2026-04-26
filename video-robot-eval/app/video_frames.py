"""Video download and frame extraction: prefer ffmpeg, else OpenCV."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import cv2
import requests


def download_video(url: str, dest: Path, timeout: int | None = None) -> None:
    if timeout is None:
        timeout = int(os.environ.get("VIDEO_DOWNLOAD_TIMEOUT_S", "600"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def _extract_ffmpeg(
    video_path: Path,
    out_dir: Path,
    fps: float,
    jpeg_quality: int,
) -> list[tuple[Path, int, float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%05d.jpg")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        "-q:v",
        str(jpeg_quality),
        pattern,
    ]
    subprocess.run(cmd, check=True)
    paths = sorted(out_dir.glob("frame_*.jpg"))
    out: list[tuple[Path, int, float]] = []
    for i, p in enumerate(paths):
        second = round(i / fps, 3) if fps > 0 else float(i)
        out.append((p, i, second))
    return out


def _extract_opencv(
    video_path: Path,
    out_dir: Path,
    fps: float,
    jpeg_quality: int,
) -> list[tuple[Path, int, float]]:
    """Evenly spaced times: one frame every 1/fps seconds of video."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        raise RuntimeError("No frames in video")

    duration_sec = n / native_fps if native_fps > 0 else 0.0
    step_sec = 1.0 / fps if fps > 0 else 1.0

    out: list[tuple[Path, int, float]] = []
    k = 0
    sec = 0.0
    encode = [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, jpeg_quality))]

    while sec < duration_sec - 1e-9:
        frame_idx = int(round(sec * native_fps))
        frame_idx = max(0, min(frame_idx, n - 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        path = out_dir / f"frame_{k + 1:05d}.jpg"
        cv2.imwrite(str(path), frame, encode)
        out.append((path, k, round(sec, 3)))
        k += 1
        sec += step_sec

    cap.release()
    if not out:
        raise RuntimeError("OpenCV extracted zero frames")
    return out


def extract_frames_fps(
    video_path: Path,
    out_dir: Path,
    fps: float = 1.0,
    jpeg_quality: int = 3,
) -> list[tuple[Path, int, float]]:
    """
    Sample frames at `fps` frames per second on the video timeline.
    jpeg_quality: ffmpeg q:v (often 2–5); OpenCV JPEG quality 1–100.
    """
    for p in out_dir.glob("frame_*.jpg"):
        p.unlink(missing_ok=True)

    if shutil.which("ffmpeg"):
        try:
            return _extract_ffmpeg(video_path, out_dir, fps, jpeg_quality)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    q_cv = 85 if jpeg_quality <= 5 else min(95, jpeg_quality * 10)
    return _extract_opencv(video_path, out_dir, fps, q_cv)
