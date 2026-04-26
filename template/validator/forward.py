from __future__ import annotations

# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import json
import time
import bittensor as bt

from template.protocol import ALLOWED_TASKS, VLASynapse
from template.runtime_client import runtime_base_url, runtime_timeout, try_post_json
from template.validator.reward import get_rewards
from template.utils.uids import get_random_uids


def _lookup(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _coerce_float(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_kitchen_synapse(step: int, timeout_s: float) -> VLASynapse:
    task_type = ALLOWED_TASKS[step % len(ALLOWED_TASKS)]
    return VLASynapse(
        job_id=f"kitchen-job-{step}",
        task_type=task_type,
        task=task_type,
        scene_id=f"robocasa-scene-{step % 5}",
        layout_id=step % 10,
        style_id=step % 12,
        sim_snapshot={
            "scene_seed": step,
            "appliance_state": "beta-localnet",
        },
        reference_frames=[],
        deadline_ms=int(timeout_s * 1000),
        validator_nonce=f"kitchen-round-{step}",
    )


def _extract_video_ref(response) -> str | None:
    for key in ("episode_video_ref", "video_url"):
        value = _lookup(response, key)
        if value:
            return str(value)
    artifact_manifest = _lookup(response, "artifact_manifest")
    if isinstance(artifact_manifest, dict) and artifact_manifest.get("public_url"):
        return str(artifact_manifest["public_url"])
    return None


def _score_fallback_response(response) -> tuple[float, dict[str, float], str]:
    video_ref = _extract_video_ref(response)
    if not video_ref:
        return 0.0, {
            "overall": 0.0,
            "safety": 0.0,
            "task_success": 0.0,
            "latency": 0.0,
            "reproducibility": 0.0,
        }, "missing artifact"

    process_time = _coerce_float(_lookup(_lookup(response, "dendrite"), "process_time"))
    latency = 0.8 if process_time is None else max(0.35, 1.0 - min(0.65, process_time / 8.0))
    overall = round(0.4 * 0.85 + 0.25 * 0.9 + 0.15 * latency + 0.20 * 0.72, 4)
    return overall, {
        "overall": overall,
        "safety": 0.9,
        "task_success": 0.85,
        "latency": round(latency, 4),
        "reproducibility": 0.72,
    }, "local fallback kitchen heuristic"


def _runtime_payload(synapse: VLASynapse) -> dict:
    return {
        "job_id": synapse.job_id,
        "protocol_version": synapse.protocol_version,
        "task_type": synapse.task_type,
        "scene_id": synapse.scene_id,
        "layout_id": synapse.layout_id,
        "style_id": synapse.style_id,
        "sim_snapshot": synapse.sim_snapshot,
        "reference_frames": list(synapse.reference_frames or []),
        "deadline_ms": synapse.deadline_ms,
        "validator_nonce": synapse.validator_nonce,
    }


def _runtime_submission_payload(synapse: VLASynapse, response) -> dict:
    video_ref = _extract_video_ref(response)
    artifact_manifest = _lookup(response, "artifact_manifest")
    if not isinstance(artifact_manifest, dict):
        artifact_manifest = {
            "job_id": synapse.job_id,
            "task_type": synapse.task_type,
            "artifact_id": f"kitchen-{synapse.job_id}",
            "artifact_type": "episode_video",
            "title": f"Kitchen artifact for {synapse.task_type}",
            "public_url": video_ref,
            "metadata": {"source": "subnet-vla-validator-fallback"},
        }
    artifact_manifest.setdefault("job_id", synapse.job_id)
    artifact_manifest.setdefault("task_type", synapse.task_type)
    artifact_manifest.setdefault("artifact_id", f"kitchen-{synapse.job_id}")
    artifact_manifest.setdefault("artifact_type", "episode_video")
    artifact_manifest.setdefault("title", f"Kitchen artifact for {synapse.task_type}")
    if video_ref and not artifact_manifest.get("public_url"):
        artifact_manifest["public_url"] = video_ref

    return {
        "job_id": synapse.job_id,
        "protocol_version": synapse.protocol_version,
        "miner_hotkey": _lookup(response, "miner_hotkey") or "subnet-vla-miner",
        "action_plan": _lookup(response, "action_plan") or [],
        "policy_trace": _lookup(response, "policy_trace") or [],
        "artifact_manifest": artifact_manifest,
        "episode_video_ref": video_ref,
        "explain": _lookup(response, "explain"),
        "model_fingerprint": _lookup(response, "model_fingerprint") or "subnet-vla-runtime-shim",
        "attempt_index": 0,
        "status": "completed" if video_ref else "missing_artifact",
        "runner": "subnet-vla-miner",
        "timing": _lookup(response, "runtime_stats") or {},
    }


def _extract_runtime_verdict(runtime_response) -> dict | None:
    if not isinstance(runtime_response, dict):
        return None
    verdict = runtime_response.get("verdict")
    if isinstance(verdict, dict):
        return verdict
    return runtime_response


def _score_runtime_response(response, runtime_verdict: dict) -> tuple[float, dict[str, float], str]:
    base = _coerce_float(runtime_verdict.get("overall")) or 0.0
    if not _extract_video_ref(response):
        base = 0.0
    process_time = _coerce_float(_lookup(_lookup(response, "dendrite"), "process_time"))
    speed = 1.0 if process_time is None else max(0.7, 1.0 - min(0.3, process_time / 20.0))
    overall = round(base * speed, 4)
    components = {
        "overall": overall,
        "safety": round((_coerce_float(runtime_verdict.get("safety")) or 0.0) * speed, 4),
        "task_success": round((_coerce_float(runtime_verdict.get("task_success")) or 0.0) * speed, 4),
        "latency": round((_coerce_float(runtime_verdict.get("latency")) or 0.0) * speed, 4),
        "reproducibility": round((_coerce_float(runtime_verdict.get("reproducibility")) or 0.0) * speed, 4),
    }
    return overall, components, str(runtime_verdict.get("evidence") or runtime_verdict.get("verdict") or "runtime verifier")


async def forward(self):
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    synapse = _build_kitchen_synapse(int(self.step), runtime_timeout(self.config))

    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=synapse,
        deserialize=False,
    )

    response_rows: list[dict] = []
    runtime_verdicts: list[dict | None] = []
    synapse_payload = _runtime_payload(synapse)
    base_url = runtime_base_url(self.config)
    timeout_s = runtime_timeout(self.config)
    for response in responses:
        runtime_response = try_post_json(
            base_url,
            "/internal/verify",
            {
                "synapse": synapse_payload,
                "submission": _runtime_submission_payload(synapse, response),
            },
            timeout_s,
        )
        runtime_verdict = _extract_runtime_verdict(runtime_response)
        runtime_verdicts.append(runtime_verdict)
        if isinstance(runtime_verdict, dict):
            score, components, reason = _score_runtime_response(response, runtime_verdict)
        else:
            score, components, reason = _score_fallback_response(response)
        response.score = score
        response.score_components = components
        response.score_reason = reason
        response_rows.append(
            {
                "video_url": _extract_video_ref(response),
                "artifact_manifest": _lookup(response, "artifact_manifest"),
                "score": round(float(score), 4),
                "components": components,
                "reason": reason,
            }
        )

    bt.logging.info(
        f"Kitchen task_type={synapse.task_type!r}, responses={json.dumps(response_rows, ensure_ascii=False)}"
    )

    rewards = get_rewards(self, expected=None, responses=responses)

    scoreboard = {
        "mode": "robokitchen-vla",
        "job_id": synapse.job_id,
        "task_type": synapse.task_type,
        "scene_id": synapse.scene_id,
        "uids": [int(u) for u in miner_uids],
        "responses": response_rows,
        "rewards": [float(x) for x in rewards.tolist()],
        "runtime_verdicts": runtime_verdicts,
    }
    bt.logging.info("VLA_SCOREBOARD " + json.dumps(scoreboard))

    self.update_scores(rewards, miner_uids)
    time.sleep(float(self.config.neuron.forward_sleep))
