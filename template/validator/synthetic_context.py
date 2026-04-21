"""Shared synthetic DroneNavSynapse construction for validator forward and offchain smoke tests."""

from __future__ import annotations

import json
import os
import random
import time

from template.protocol import DEFAULT_SYNTHETIC_INSTRUCTIONS, DroneNavSynapse


def build_synthetic_drone_nav_synapse(
    *,
    validator_step: int = 0,
    instruction: str | None = None,
    task_id: str | None = None,
) -> tuple[DroneNavSynapse, dict[str, object]]:
    """
    Build synapse + context dict (same shape as ``template.validator.forward``).

    ``OPENFLY_SYNTHETIC_UE_SOCKET`` — path checked for existence in synthetic_context_json.
    """
    ins = (instruction or "").strip() or random.choice(DEFAULT_SYNTHETIC_INSTRUCTIONS)
    tid = (task_id or "").strip() or f"round-{int(time.time())}-{random.randint(1000, 9999)}"
    ue_socket = os.environ.get("OPENFLY_SYNTHETIC_UE_SOCKET", "/tmp/unrealcv_9030.socket")
    synthetic_context: dict[str, object] = {
        "synthetic": True,
        "offchain_smoke": False,
        "validator_step": int(validator_step),
        "ue_socket": ue_socket,
        "ue_socket_exists": os.path.exists(ue_socket),
    }
    synapse = DroneNavSynapse(
        instruction=ins,
        task_id=tid,
        synthetic_context_json=json.dumps(synthetic_context, ensure_ascii=False),
    )
    return synapse, synthetic_context


def mark_synapse_offchain_smoke(synapse: DroneNavSynapse) -> None:
    """Tag JSON context so miners can treat smoke traffic differently if needed."""
    try:
        raw = synapse.synthetic_context_json or "{}"
        obj = json.loads(raw) if isinstance(raw, str) else {}
        if not isinstance(obj, dict):
            obj = {}
        obj["offchain_smoke"] = True
        obj["synthetic"] = True
        synapse.synthetic_context_json = json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError, json.JSONDecodeError):
        synapse.synthetic_context_json = json.dumps(
            {"synthetic": True, "offchain_smoke": True}, ensure_ascii=False
        )
