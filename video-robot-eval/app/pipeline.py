"""
Core video evaluation pipeline (CLI and HTTP service import this module).
"""

from __future__ import annotations

import base64
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import cv2
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.merge import merge_batch_evaluations
from app.prompts import batch_instruction, default_task
from app.schemas import RobotBatchEvaluation
from app.video_frames import download_video, extract_frames_fps

load_dotenv()

IMPORTANCE_PNG_MIN = 0.7


class VideoEvalError(Exception):
    """exit_code matches CLI semantics: 1 config/key, 2 input/video, 3 runtime/model."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


def _b64_jpeg(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _jpeg_path_to_png_base64(path: Path) -> str | None:
    img = cv2.imread(str(path))
    if img is None:
        return None
    ok, buf = cv2.imencode(".png", img)
    if not ok or buf is None:
        return None
    return base64.standard_b64encode(buf.tobytes()).decode("ascii")


def _attach_high_importance_frame_pngs(
    evaluation: dict[str, Any],
    frame_index_to_path: dict[int, Path],
    *,
    threshold: float = IMPORTANCE_PNG_MIN,
) -> int:
    n = 0
    for row in evaluation.get("details", []):
        try:
            imp = float(row.get("importance", 0.0))
        except (TypeError, ValueError):
            continue
        if imp < threshold:
            continue
        idx = row.get("frame_index")
        if idx is None:
            continue
        p = frame_index_to_path.get(int(idx))
        if p is None or not p.is_file():
            continue
        b64 = _jpeg_path_to_png_base64(p)
        if b64:
            row["frame_png_base64"] = b64
            n += 1
    return n


def normalize_report_base64(obj: Any) -> None:
    """Strip whitespace inside frame_png_base64 strings for stable single-line JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "frame_png_base64" and isinstance(v, str):
                obj[k] = "".join(v.split())
            else:
                normalize_report_base64(v)
    elif isinstance(obj, list):
        for item in obj:
            normalize_report_base64(item)


def _extract_token_usage(msg) -> tuple[int, int]:
    pt, ct = 0, 0
    md = getattr(msg, "response_metadata", None) or {}
    tu = md.get("token_usage")
    if isinstance(tu, dict):
        pt = int(tu.get("prompt_tokens") or tu.get("input_tokens") or 0)
        ct = int(tu.get("completion_tokens") or tu.get("output_tokens") or 0)
    um = getattr(msg, "usage_metadata", None)
    if isinstance(um, dict):
        pt = max(pt, int(um.get("input_tokens") or 0))
        ct = max(ct, int(um.get("output_tokens") or 0))
    return pt, ct


def _build_batch_message(
    task: str,
    frames: list[tuple[Path, int, float]],
    frame_step_sec: float,
) -> HumanMessage:
    idx_first = frames[0][1]
    idx_last = frames[-1][1]
    text = batch_instruction(task, idx_first, idx_last, frame_step_sec=frame_step_sec)
    parts: list[dict] = [{"type": "text", "text": text}]
    for path, g_idx, sec in frames:
        parts.append(
            {
                "type": "text",
                "text": f"frame_index={g_idx} timestamp_sec={sec}",
            }
        )
        parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{_b64_jpeg(path)}",
                    "detail": "low",
                },
            }
        )
    return HumanMessage(content=parts)


def _evaluate_one_batch(
    structured,
    task: str,
    batch_frames: list[tuple[Path, int, float]],
    frame_step_sec: float,
) -> tuple[RobotBatchEvaluation, int, int]:
    msg = _build_batch_message(task, batch_frames, frame_step_sec)
    out = structured.invoke([msg])
    raw = None
    parsed = None
    if isinstance(out, RobotBatchEvaluation):
        parsed = out
    elif isinstance(out, dict):
        raw = out.get("raw")
        parsed = out.get("parsed")
        err = out.get("parsing_error")
        if err:
            raise RuntimeError(f"Parsing error: {err}")
    else:
        raise RuntimeError(f"Unexpected structured output type: {type(out)}")

    if not isinstance(parsed, RobotBatchEvaluation):
        raise RuntimeError(f"Parse failure: {out!r}")

    pti, cti = (0, 0)
    if raw is not None:
        pti, cti = _extract_token_usage(raw)
    return parsed, pti, cti


def evaluate_video_report(
    *,
    video_url: str,
    task: str,
    work_dir: Path,
    fps: float = 2.0,
    frames_per_batch: int = 12,
    model: str | None = None,
    usd_in_per_mtok: float = 0.15,
    usd_out_per_mtok: float = 0.60,
    local_video: Path | None = None,
    dry_run_frames: bool = False,
    embed_high_importance_png: bool = True,
    log: bool = True,
) -> dict[str, Any]:
    """
    Download (or use local_video), sample frames, run vision LLM batches, merge, return report dict.
    Raises VideoEvalError on failure. For dry_run_frames, returns a small dict (no OpenAI).
    """
    _log = (lambda m: print(m, file=sys.stderr)) if log else (lambda _m: None)

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = work_dir / "frames_jpg"

    if local_video is not None:
        video_path = local_video.resolve()
        if not video_path.is_file():
            raise VideoEvalError(2, f"Local video not found: {video_path}")
        _log(f"Using local video {video_path} …")
    else:
        video_path = work_dir / "input.mp4"
        _log(f"Downloading {video_url!r} …")
        download_video(video_url, video_path)

    _log(f"Extracting frames at {fps} FPS …")
    if frames_dir.exists():
        for p in frames_dir.glob("frame_*.jpg"):
            p.unlink()
    frame_list = extract_frames_fps(video_path, frames_dir, fps=fps)
    _log(f"Frames: {len(frame_list)}")

    if not frame_list:
        raise VideoEvalError(2, "No frames extracted.")

    if dry_run_frames:
        return {
            "dry_run_frames": True,
            "video_path": str(video_path),
            "frames_total": len(frame_list),
            "fps_sample": fps,
            "first_frame": str(frame_list[0][0]) if frame_list else None,
        }

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise VideoEvalError(1, "OPENAI_API_KEY missing")

    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    llm = ChatOpenAI(
        model=model,
        temperature=0.2,
        api_key=api_key,
    )
    structured = llm.with_structured_output(
        RobotBatchEvaluation,
        include_raw=True,
    )

    batches: list[list[tuple[Path, int, float]]] = []
    for i in range(0, len(frame_list), max(1, frames_per_batch)):
        batches.append(frame_list[i : i + frames_per_batch])

    frame_step_sec = (1.0 / fps) if fps > 0 else 0.5
    max_workers = max(
        1,
        min(len(batches), int(os.environ.get("EVAL_MAX_WORKERS", "8"))),
    )

    total_pt = total_ct = 0
    eval_weights: list[tuple[RobotBatchEvaluation, int, int, int]] = []
    parsed_by_idx: dict[int, RobotBatchEvaluation] = {}

    _log(
        f"Evaluating {len(batches)} batch(es) in parallel (max_workers={max_workers}) …",
    )

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _evaluate_one_batch,
                    structured,
                    task,
                    batch_frames,
                    frame_step_sec,
                ): bi
                for bi, batch_frames in enumerate(batches)
            }
            for fut in as_completed(future_to_idx):
                bi = future_to_idx[fut]
                batch_frames = batches[bi]
                parsed, pti, cti = fut.result()
                total_pt += pti
                total_ct += cti
                parsed_by_idx[bi] = parsed
                _log(
                    f"Batch {bi + 1}/{len(batches)} done ({len(batch_frames)} frames); "
                    f"+{pti} prompt +{cti} completion",
                )
    except Exception as e:
        raise VideoEvalError(3, f"Batch evaluation failed: {e}") from e

    for bi, batch_frames in enumerate(batches):
        ev = parsed_by_idx[bi]
        eval_weights.append(
            (
                ev,
                len(batch_frames),
                batch_frames[0][1],
                batch_frames[-1][1],
            )
        )

    merged = merge_batch_evaluations(eval_weights)
    evaluation_dict = merged.model_dump()
    ptp = (evaluation_dict.get("predicted_task_prompt") or "").strip()
    frame_index_to_path = {g_idx: path for path, g_idx, _sec in frame_list}
    n_png = 0
    if embed_high_importance_png:
        n_png = _attach_high_importance_frame_pngs(evaluation_dict, frame_index_to_path)
        if n_png:
            _log(
                f"Attached {n_png} PNG preview(s) (importance >= {IMPORTANCE_PNG_MIN}).",
            )

    usd = (
        total_pt / 1_000_000 * usd_in_per_mtok
        + total_ct / 1_000_000 * usd_out_per_mtok
    )

    return {
        "video_url": video_url,
        "model": model,
        "predicted_task_prompt": ptp,
        "fps_sample": fps,
        "frames_total": len(frame_list),
        "batches": len(batches),
        "frames_per_batch": frames_per_batch,
        "importance_png_min": IMPORTANCE_PNG_MIN,
        "high_importance_png_embedded": n_png,
        "usage": {
            "prompt_tokens": total_pt,
            "completion_tokens": total_ct,
            "total_tokens": total_pt + total_ct,
        },
        "estimated_usd": {
            "input_rate_per_mtok": usd_in_per_mtok,
            "output_rate_per_mtok": usd_out_per_mtok,
            "total_usd": round(usd, 6),
        },
        "evaluation": evaluation_dict,
    }


def resolve_task(task: str) -> str:
    t = task.strip()
    return t if t else default_task()
