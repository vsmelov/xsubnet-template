# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import time
import typing
import uuid
import bittensor as bt

import template
from template.base.miner import BaseMinerNeuron
from template.protocol import (
    BETA_PROTOCOL_VERSION,
    INTERNAL_RUNTIME_VERSION,
    STUB_RESULT_VIDEO_URL,
    normalize_task,
    normalize_task_type,
)
from template.runtime_client import runtime_base_url, runtime_timeout, try_post_json
from template.vla_stub_rollout_log import run_verbose_stub_rollout


def _default_scene_id(task_type: str) -> str:
    compact = task_type.lower().replace(" ", "-")
    return f"robocasa-{compact}"


def _build_runtime_payload(
    synapse: template.protocol.VLASynapse,
    task_type: str,
    fallback_job_id: str,
    timeout_s: float,
) -> dict[str, typing.Any]:
    job_id = synapse.job_id or fallback_job_id
    return {
        "job_id": job_id,
        "task_type": task_type,
        "scene_id": synapse.scene_id or _default_scene_id(task_type),
        "layout_id": synapse.layout_id,
        "style_id": synapse.style_id,
        "sim_snapshot": synapse.sim_snapshot,
        "reference_frames": list(synapse.reference_frames or []),
        "deadline_ms": int(synapse.deadline_ms or timeout_s * 1000),
        "validator_nonce": synapse.validator_nonce or job_id,
    }


def _apply_runtime_submission(
    synapse: template.protocol.VLASynapse,
    runtime_payload: dict[str, typing.Any],
    runtime_resp: dict[str, typing.Any] | None,
    task_type: str,
    req_id: str,
) -> template.protocol.VLASynapse:
    synapse.job_id = str(runtime_payload["job_id"])
    synapse.protocol_version = BETA_PROTOCOL_VERSION
    synapse.task_type = task_type
    synapse.task = normalize_task(synapse.task) or task_type
    synapse.scene_id = str(runtime_payload["scene_id"])
    synapse.layout_id = runtime_payload.get("layout_id")
    synapse.style_id = runtime_payload.get("style_id")
    synapse.sim_snapshot = runtime_payload.get("sim_snapshot")
    synapse.reference_frames = list(runtime_payload.get("reference_frames") or [])
    synapse.deadline_ms = int(runtime_payload["deadline_ms"])
    synapse.validator_nonce = str(runtime_payload["validator_nonce"])

    if isinstance(runtime_resp, dict):
        submission = runtime_resp.get("submission")
        if not isinstance(submission, dict):
            submission = runtime_resp
        synapse.artifact_manifest = submission.get("artifact_manifest")
        synapse.action_plan = submission.get("action_plan")
        synapse.policy_trace = submission.get("policy_trace")
        synapse.explain = submission.get("explain")
        synapse.model_fingerprint = submission.get("model_fingerprint")
        synapse.runtime_stats = submission.get("runtime_stats") or submission.get("timing")
        synapse.episode_video_ref = submission.get("episode_video_ref")
        public_url = None
        if isinstance(synapse.artifact_manifest, dict):
            public_url = synapse.artifact_manifest.get("public_url")
        synapse.video_url = synapse.episode_video_ref or public_url
        if synapse.video_url:
            return synapse

    synapse.video_url = STUB_RESULT_VIDEO_URL
    synapse.episode_video_ref = STUB_RESULT_VIDEO_URL
    synapse.artifact_manifest = {
        "job_id": synapse.job_id,
        "task_type": task_type,
        "artifact_id": f"kitchen-{req_id}",
        "artifact_type": "episode_video",
        "title": f"Fallback kitchen artifact for {task_type}",
        "public_url": STUB_RESULT_VIDEO_URL,
        "metadata": {
            "task_type": task_type,
            "scene_id": synapse.scene_id,
        },
    }
    synapse.action_plan = [
        {"kind": "macro_task", "task_type": task_type, "scene_id": synapse.scene_id}
    ]
    synapse.policy_trace = [{"step": 0, "note": f"Fallback kitchen shim for {task_type}"}]
    synapse.explain = "Fell back to local kitchen shim stub because runtime response was unavailable."
    synapse.model_fingerprint = "kitchen-chain-shim-fallback"
    synapse.runtime_stats = {
        "mode": "fallback_stub",
        "runtime_version": INTERNAL_RUNTIME_VERSION,
    }
    return synapse


class Miner(BaseMinerNeuron):
    """
    Stub miner: pretends to run a VLA; always returns the same demo video URL for allowed tasks.
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)

    async def forward(
        self, synapse: template.protocol.VLASynapse
    ) -> template.protocol.VLASynapse:
        task_type = normalize_task_type(synapse.task_type, synapse.task)
        if not task_type:
            synapse.video_url = None
            bt.logging.warning(
                f"Unsupported kitchen task_type={synapse.task_type!r} task={synapse.task!r}"
            )
            return synapse

        req_id = str(uuid.uuid4())[:8]
        t0 = time.monotonic()
        payload = _build_runtime_payload(
            synapse,
            task_type,
            fallback_job_id=f"kitchen-job-{req_id}",
            timeout_s=runtime_timeout(self.config),
        )
        runtime_resp = try_post_json(
            runtime_base_url(self.config),
            "/internal/mine",
            payload,
            runtime_timeout(self.config),
        )
        if runtime_resp is None:
            run_verbose_stub_rollout(task_type, req_id)
        synapse = _apply_runtime_submission(
            synapse,
            payload,
            runtime_resp,
            task_type,
            req_id,
        )
        dt_s = time.monotonic() - t0
        bt.logging.info(
            f"Kitchen shim [{req_id}] artifact ready after {dt_s:.2f}s "
            f"task_type={task_type} video_url={synapse.video_url}"
        )
        return synapse

    async def blacklist(
        self, synapse: template.protocol.VLASynapse
    ) -> typing.Tuple[bool, str]:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return True, "Missing dendrite or hotkey"

        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            bt.logging.trace(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        if self.config.blacklist.force_validator_permit:
            if not self.metagraph.validator_permit[uid]:
                bt.logging.warning(
                    f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
                )
                return True, "Non-validator hotkey"

        bt.logging.trace(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, "Hotkey recognized!"

    async def priority(self, synapse: template.protocol.VLASynapse) -> float:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return 0.0

        caller_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        priority = float(self.metagraph.S[caller_uid])
        bt.logging.trace(
            f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}"
        )
        return priority


if __name__ == "__main__":
    with Miner() as miner:
        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)
