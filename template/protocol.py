# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import typing

import bittensor as bt

# Simulator tasks (exact strings as in the robot UI).
ALLOWED_TASKS: typing.Tuple[str, ...] = (
    "Clean-up the guestroom",
    "Clean-up the kitchen",
    "Prepare groceries",
    "Setup the table",
)

# Stub “result video” for all miners until a real VLA pipeline is wired.
STUB_RESULT_VIDEO_URL = (
    "https://konnex-ai.xyz/videos/results_tidy/40.mp4"
)


def normalize_task(task: typing.Optional[str]) -> str:
    if task is None:
        return ""
    return str(task).strip()


def is_allowed_task(task: str) -> bool:
    t = normalize_task(task)
    return t in ALLOWED_TASKS


class VLASynapse(bt.Synapse):
    """
    Demo protocol: validator sends a natural-language robot task; miner returns a stub video URL.
    """

    task: str
    video_url: typing.Optional[str] = None

    def deserialize(self) -> typing.Optional[str]:
        return self.video_url
