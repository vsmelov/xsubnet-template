#!/usr/bin/env python3
"""
Proof-of-concept: оценка выполнения роботом задачи по MP4 + текстовому промпту через OpenAI vision.

Дёшево: gpt-4o-mini + равномерная выборка кадров (видео целиком в Chat Completions не шлётся).

  pip install -r requirements-poc.txt
  set OPENAI_API_KEY=...
  python video_validator_openai_poc.py --video clip.mp4 --prompt "Robot should pick the red cube."

Env:
  OPENAI_API_KEY   — обязательно
  OPENAI_MODEL     — по умолчанию gpt-4o-mini
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

import cv2
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class FrameNote(BaseModel):
    frame_num: int = Field(ge=0, description="Index кадра в исходном видео (0-based)")
    second: float = Field(ge=0.0, description="Время в секундах")
    note: str = Field(description="Короткое наблюдение по этому кадру")


class RobotTaskEvaluation(BaseModel):
    overall_score: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0, description="Насколько движения выглядят безопасно")
    efficiency: float = Field(
        ge=0.0,
        le=1.0,
        description="Нет ли лишних движений / тянет ли резолюцию задачи",
    )
    task_match_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Соответствие тому, что описано в промпте",
    )
    details: list[FrameNote] = Field(
        default_factory=list,
        description="Заметки по ключевым кадрам; привяжи frame_num/second к переданным снимкам",
    )


def sample_frames(
    video_path: Path,
    max_frames: int,
    jpeg_quality: int = 75,
) -> tuple[list[dict], float]:
    """
    Возвращает список элементов {frame_num, second, data_url} и fps.
    data_url — data:image/jpeg;base64,...
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        raise RuntimeError("Video has no frames or unreadable frame count")

    indices: list[int]
    if n <= max_frames:
        indices = list(range(n))
    else:
        step = (n - 1) / (max_frames - 1)
        indices = [int(round(i * step)) for i in range(max_frames)]
        indices = sorted(set(indices))

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
    out: list[dict] = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        ok, buf = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            continue
        b64 = base64.standard_b64encode(buf.tobytes()).decode("ascii")
        second = idx / fps if fps > 0 else 0.0
        out.append(
            {
                "frame_num": idx,
                "second": round(second, 3),
                "data_url": f"data:image/jpeg;base64,{b64}",
            }
        )

    cap.release()
    if not out:
        raise RuntimeError("Failed to extract any frames")
    return out, float(fps)


def build_messages(
    task_prompt: str,
    frames: list[dict],
) -> list[dict]:
    intro = (
        "You are evaluating robot execution from video frames (uniformly sampled from an MP4). "
        "The user describes the intended task. "
        "Return ONLY fields that match the JSON schema you were given. "
        "Scores are floats from 0.0 to 1.0. "
        "In `details`, reference the provided frame indices (frame_num) and times (second) when possible."
    )
    content: list[dict] = [{"type": "text", "text": f"{intro}\n\nTask:\n{task_prompt}"}]
    for i, fr in enumerate(frames):
        content.append(
            {
                "type": "text",
                "text": f"Frame index {fr['frame_num']} (~{fr['second']} s), sample #{i + 1}/{len(frames)}",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": fr["data_url"], "detail": "low"},
            }
        )
    return [{"role": "user", "content": content}]


def run_eval(
    client: OpenAI,
    model: str,
    task_prompt: str,
    frames: list[dict],
) -> RobotTaskEvaluation:
    messages = build_messages(task_prompt, frames)
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=RobotTaskEvaluation,
        temperature=0.2,
    )
    msg = completion.choices[0].message
    if msg.refusal:
        raise RuntimeError(f"Model refused: {msg.refusal}")
    if not msg.parsed:
        raise RuntimeError("No parsed structured output")
    return msg.parsed


def main() -> int:
    p = argparse.ArgumentParser(description="PoC: OpenAI vision eval for robot task video")
    p.add_argument("--video", type=Path, required=True, help="Path to MP4")
    p.add_argument("--prompt", type=str, required=True, help="What the robot should do")
    p.add_argument("--max-frames", type=int, default=12, help="Max frames to send (cost ~ linear)")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL)
    args = p.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY", file=sys.stderr)
        return 1

    if not args.video.is_file():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1

    frames, fps = sample_frames(args.video, args.max_frames)
    print(f"Sampled {len(frames)} frames, fps={fps:.2f}, model={args.model}", file=sys.stderr)

    client = OpenAI()
    result = run_eval(client, args.model, args.prompt, frames)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
