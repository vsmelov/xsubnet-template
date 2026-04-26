# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import typing

import bittensor as bt

LEGACY_TASK_ALIASES: typing.Dict[str, str] = {
    "Clean-up the guestroom": "CloseSingleDoor",
    "Clean-up the kitchen": "CloseDrawer",
    "Prepare groceries": "PnPCounterToCab",
    "Setup the table": "CoffeeServeMug",
}

ALLOWED_TASKS: typing.Tuple[str, ...] = (
    "PnPCounterToCab",
    "PnPCabToCounter",
    "PnPCounterToSink",
    "PnPSinkToCounter",
    "PnPCounterToMicrowave",
    "PnPMicrowaveToCounter",
    "PnPCounterToStove",
    "PnPStoveToCounter",
    "OpenSingleDoor",
    "CloseSingleDoor",
    "OpenDoubleDoor",
    "CloseDoubleDoor",
    "OpenDrawer",
    "CloseDrawer",
    "TurnOnMicrowave",
    "TurnOffMicrowave",
    "TurnOnSinkFaucet",
    "TurnOffSinkFaucet",
    "TurnSinkSpout",
    "TurnOnStove",
    "TurnOffStove",
    "CoffeeSetupMug",
    "CoffeeServeMug",
    "CoffeePressButton",
)
BETA_PROTOCOL_VERSION = "robokitchen-vla-beta-v1"
INTERNAL_RUNTIME_VERSION = "kitchen-task-api-runtime-v1"

# Stub “result video” for all miners until a real VLA pipeline is wired.
STUB_RESULT_VIDEO_URL = (
    "https://konnex-ai.xyz/videos/results_tidy/40.mp4"
)


def normalize_task(task: typing.Optional[str]) -> str:
    if task is None:
        return ""
    return str(task).strip()


def normalize_task_type(
    task_type: typing.Optional[str],
    task: typing.Optional[str] = None,
) -> str:
    candidate = normalize_task(task_type)
    if candidate in ALLOWED_TASKS:
        return candidate
    legacy = normalize_task(task)
    return LEGACY_TASK_ALIASES.get(legacy, "")


def is_allowed_task(task: str) -> bool:
    return normalize_task_type(task, task) != ""


class VLASynapse(bt.Synapse):
    """
    Chain-facing shim for the robokitchen-vla beta contract.

    Preferred path:
    - validator sends a kitchen task envelope;
    - miner/runtime returns artifact metadata plus a preview video reference;
    - validator/verifier assigns explicit score fields.

    Legacy probe compatibility:
    - `task` may still be supplied as an old demo label;
    - miners expose `video_url` as the convenient quick-look field.
    """

    job_id: typing.Optional[str] = None
    protocol_version: str = BETA_PROTOCOL_VERSION
    task_type: typing.Optional[str] = None
    task: typing.Optional[str] = None
    scene_id: typing.Optional[str] = None
    layout_id: typing.Optional[int] = None
    style_id: typing.Optional[int] = None
    sim_snapshot: typing.Optional[typing.Dict[str, typing.Any]] = None
    reference_frames: typing.Optional[typing.List[str]] = None
    deadline_ms: typing.Optional[int] = None
    validator_nonce: typing.Optional[str] = None

    video_url: typing.Optional[str] = None
    episode_video_ref: typing.Optional[str] = None
    artifact_manifest: typing.Optional[typing.Dict[str, typing.Any]] = None
    action_plan: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None
    policy_trace: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None
    explain: typing.Optional[str] = None
    model_fingerprint: typing.Optional[str] = None
    runtime_stats: typing.Optional[typing.Dict[str, typing.Any]] = None
    score: typing.Optional[float] = None
    score_components: typing.Optional[typing.Dict[str, float]] = None
    score_reason: typing.Optional[str] = None

    def deserialize(self) -> typing.Any:
        if self.score is not None:
            return self.score
        if self.episode_video_ref is not None:
            return self.episode_video_ref
        if self.video_url is not None:
            return self.video_url
        return self.artifact_manifest
