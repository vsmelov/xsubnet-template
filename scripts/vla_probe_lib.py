"""
HTTP probe: dendrite + VLASynapse; rewards как у validator (почти равномерно + jitter).
"""

from __future__ import annotations

import random
import time
from typing import Any, List, Optional

import bittensor as bt

from template.protocol import ALLOWED_TASKS, VLASynapse, is_allowed_task, normalize_task
from template.validator.reward import get_rewards


class _RewardLogCtx:
    pass


def _pick_miner_uids(
    mg: bt.metagraph,
    miner_uids: Optional[List[int]],
    sample_size: int,
) -> List[int]:
    n = int(mg.n)
    if miner_uids is not None and len(miner_uids) > 0:
        uids = [int(u) for u in miner_uids if 0 <= int(u) < n]
        if not uids:
            raise ValueError("miner_uids empty or out of metagraph range")
        return uids
    k = max(1, min(int(sample_size), n))
    candidates = [
        u
        for u in range(n)
        if mg.axons[u].is_serving and not bool(mg.validator_permit[u])
    ]
    if len(candidates) < k:
        candidates = [u for u in range(n) if mg.axons[u].is_serving]
    if len(candidates) < k:
        candidates = list(range(n))
    k = min(k, len(candidates))
    return random.sample(candidates, k)


def _extract_url(item: Any) -> Optional[str]:
    if item is None:
        return None
    if isinstance(item, str):
        return item.strip() or None
    if hasattr(item, "video_url"):
        v = getattr(item, "video_url")
        return str(v).strip() if v else None
    return None


def _dendrite_meta(synapse: Any) -> Any:
    d = getattr(synapse, "dendrite", None)
    if d is None:
        return None
    meta: dict = {}
    for attr in ("status_code", "status_message", "process_time", "ip", "port"):
        if hasattr(d, attr):
            try:
                meta[attr] = getattr(d, attr)
            except Exception:
                meta[attr] = str(getattr(d, attr))
    return meta if meta else str(d)


def _axon_meta(mg: bt.metagraph, uid: int) -> dict:
    ax = mg.axons[uid]
    hk = getattr(ax, "hotkey", None)
    return {
        "ip": getattr(ax, "ip", None),
        "port": getattr(ax, "port", None),
        "is_serving": getattr(ax, "is_serving", None),
        "hotkey": str(hk) if hk is not None else None,
    }


def _synapse_payload(item: Any) -> Any:
    if item is None:
        return None
    if isinstance(item, str):
        return {"deserialized_only": item}
    out: dict = {"video_url": getattr(item, "video_url", None)}
    if hasattr(item, "task"):
        out["task"] = getattr(item, "task")
    out["dendrite"] = _dendrite_meta(item)
    return out


def _hotkey_at(mg: bt.metagraph, uid: int) -> Optional[str]:
    try:
        return str(mg.hotkeys[uid])
    except Exception:
        return None


async def run_vla_probe(
    *,
    netuid: int,
    chain_endpoint: str,
    wallet_name: str,
    hotkey: str = "default",
    task: str,
    miner_uids: Optional[List[int]] = None,
    sample_size: int = 4,
    timeout: float = 60.0,
) -> dict:
    t0 = time.perf_counter()
    task_n = normalize_task(task)
    if not is_allowed_task(task_n):
        return {
            "ok": False,
            "error": f"task must be one of {ALLOWED_TASKS}",
            "allowed_tasks": list(ALLOWED_TASKS),
        }

    wallet = bt.Wallet(name=wallet_name, hotkey=hotkey)
    subtensor = bt.Subtensor(network=chain_endpoint)
    mg = subtensor.metagraph(netuid)

    uids_list = _pick_miner_uids(mg, miner_uids, sample_size)
    synapse = VLASynapse(task=task_n)
    axons = [mg.axons[u] for u in uids_list]

    dendrite = bt.Dendrite(wallet)
    t_call = time.perf_counter()
    raw_out = None
    used_deserialize_true = False
    try:
        raw_out = await dendrite(
            axons,
            synapse=synapse,
            deserialize=False,
            timeout=timeout,
        )
    except TypeError:
        raw_out = await dendrite(
            axons,
            synapse=synapse,
            deserialize=True,
            timeout=timeout,
        )
        used_deserialize_true = True
    t_after = time.perf_counter()

    if raw_out is None:
        raw_list: List[Any] = []
    elif isinstance(raw_out, (list, tuple)):
        raw_list = list(raw_out)
    else:
        raw_list = [raw_out]

    str_responses: List[Optional[str]] = []
    miners: List[dict] = []
    for i, uid in enumerate(uids_list):
        item = raw_list[i] if i < len(raw_list) else None
        url = _extract_url(item)
        str_responses.append(url)
        miners.append(
            {
                "uid": int(uid),
                "hotkey_ss58": _hotkey_at(mg, uid),
                "axon": _axon_meta(mg, uid),
                "video_url": url,
                "synapse": _synapse_payload(item),
            }
        )

    rewards = get_rewards(_RewardLogCtx(), responses=str_responses)
    rew_list = [float(x) for x in rewards.tolist()]
    for i, r in enumerate(rew_list):
        if i < len(miners):
            miners[i]["reward_share"] = r

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    call_ms = int((t_after - t_call) * 1000)

    return {
        "ok": True,
        "protocol": "subnet-vla VLASynapse",
        "bittensor_sdk_pinned": "9.7.0 (see requirements.txt)",
        "netuid": netuid,
        "chain_endpoint": chain_endpoint,
        "wallet_coldkey": wallet_name,
        "dendrite_deserialize_flag": not used_deserialize_true,
        "request": {"task": task_n, "allowed_tasks": list(ALLOWED_TASKS)},
        "miner_uids_queried": uids_list,
        "miners": miners,
        "rewards": rew_list,
        "timing_ms": {"total": elapsed_ms, "dendrite_call": call_ms},
    }
