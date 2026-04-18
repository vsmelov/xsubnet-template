"""
Robot video eval: ffmpeg time sampling (default 2 FPS ≈ one frame every 0.5 s) →
frame batches (parallel API calls) → LangChain structured output → merge with per-frame importance.

From repo root `subnet-vla/video-robot-eval`:
  pip install -r requirements.txt
  cp .env.example .env   # set OPENAI_API_KEY
  python -m app.main

Docker: see README.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.pipeline import (
    VideoEvalError,
    evaluate_video_report,
    normalize_report_base64,
    resolve_task,
)

load_dotenv()

STDOUT_JSON_MAX_BYTES = 256 * 1024


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def _dumps_report_pretty(report: dict) -> str:
    normalize_report_base64(report)
    return json.dumps(report, indent=2, ensure_ascii=False)


def run(
    video_url: str,
    task: str,
    work_dir: Path,
    fps: float,
    frames_per_batch: int,
    model: str,
    usd_in_per_mtok: float,
    usd_out_per_mtok: float,
    output_path: Path | None = None,
    local_video: Path | None = None,
    dry_run_frames: bool = False,
) -> int:
    try:
        report = evaluate_video_report(
            video_url=video_url,
            task=task,
            work_dir=work_dir,
            fps=fps,
            frames_per_batch=frames_per_batch,
            model=model,
            usd_in_per_mtok=usd_in_per_mtok,
            usd_out_per_mtok=usd_out_per_mtok,
            local_video=local_video,
            dry_run_frames=dry_run_frames,
            embed_high_importance_png=True,
            log=True,
        )
    except VideoEvalError as e:
        print(e.message, file=sys.stderr)
        return e.exit_code

    if dry_run_frames:
        text = json.dumps(report, indent=2, ensure_ascii=False)
        print(text)
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
            print(f"Wrote {output_path}", file=sys.stderr)
        return 0

    text = _dumps_report_pretty(report)
    byte_len = len(text.encode("utf-8"))
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        byte_len = output_path.stat().st_size
        print(
            f"Wrote {output_path} — JSON file size: {byte_len / 1024:.1f} KiB ({byte_len} bytes)",
            file=sys.stderr,
        )
    else:
        print(
            f"JSON size: {byte_len / 1024:.1f} KiB ({byte_len} bytes)",
            file=sys.stderr,
        )
    _ensure_utf8_stdio()
    if byte_len <= STDOUT_JSON_MAX_BYTES:
        try:
            print(text)
        except UnicodeEncodeError:
            print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        where = f" {output_path}" if output_path is not None else ""
        print(
            f"(JSON {byte_len / 1024:.1f} KiB — skipped printing full report to stdout; see{where})",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    _ensure_utf8_stdio()
    p = argparse.ArgumentParser(description="Robot video eval via LangChain + OpenAI vision")
    p.add_argument(
        "--url",
        default="https://konnex-ai.xyz/videos/results_tidy/2497.mp4",
        help="URL MP4",
    )
    p.add_argument(
        "--task",
        default="",
        help="What the robot should do (empty = built-in default task)",
    )
    p.add_argument("--work-dir", type=Path, default=Path("work"))
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Also write the same JSON report to this path (stdout unchanged)",
    )
    p.add_argument(
        "--local-video",
        type=Path,
        default=None,
        help="Local MP4 path instead of downloading --url",
    )
    p.add_argument(
        "--dry-run-frames",
        action="store_true",
        help="Only download/local video and extract frames; skip OpenAI",
    )
    p.add_argument(
        "--fps",
        type=float,
        default=float(os.environ.get("SAMPLE_FPS", "2")),
        help="Temporal sampling rate (ffmpeg fps=); 2 ≈ one frame every 0.5 s",
    )
    p.add_argument(
        "--frames-per-batch",
        type=int,
        default=12,
        help="Vision API batch size (default 12; override per run, not via env)",
    )
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    p.add_argument(
        "--usd-in-per-mtok",
        type=float,
        default=float(os.environ.get("USD_PER_MTOK_INPUT", "0.15")),
    )
    p.add_argument(
        "--usd-out-per-mtok",
        type=float,
        default=float(os.environ.get("USD_PER_MTOK_OUTPUT", "0.60")),
    )
    args = p.parse_args()
    task = resolve_task(args.task)
    return run(
        video_url=args.url,
        task=task,
        work_dir=args.work_dir,
        fps=args.fps,
        frames_per_batch=max(1, args.frames_per_batch),
        model=args.model,
        usd_in_per_mtok=args.usd_in_per_mtok,
        usd_out_per_mtok=args.usd_out_per_mtok,
        output_path=args.output,
        local_video=args.local_video,
        dry_run_frames=args.dry_run_frames,
    )


if __name__ == "__main__":
    raise SystemExit(main())
