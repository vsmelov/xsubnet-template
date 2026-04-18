"""
HTTP probe: dendrite + VLASynapse; rewards как у validator (почти равномерно + jitter).
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

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


def _probe_static_root() -> Path:
    return Path(
        os.environ.get(
            "VLA_VIDEO_STATIC_ROOT",
            str(Path(__file__).resolve().parent.parent / "vla-video-static"),
        )
    ).resolve()


def _vars_subdirs(static_root: Path) -> List[Path]:
    vdir = static_root / "vars"
    if not vdir.is_dir():
        return []
    return sorted([p for p in vdir.iterdir() if p.is_dir()])


def _mp4s_sorted_numeric(folder: Path) -> List[Path]:
    files = list(folder.glob("*.mp4"))

    def sort_key(p: Path) -> Tuple[int, str]:
        try:
            return (int(p.stem), p.name)
        except ValueError:
            return (10**18, p.name)

    return sorted(files, key=sort_key)


def _pick_three_videos(folder: Path) -> Optional[List[Path]]:
    """Lowest / middle / highest numeric stem; need at least 3 mp4 files."""
    mp4s = _mp4s_sorted_numeric(folder)
    n = len(mp4s)
    if n < 3:
        return None
    if n == 3:
        return mp4s
    return [mp4s[0], mp4s[n // 2], mp4s[-1]]


def _rel_under_root(root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(root.resolve())
    return rel.as_posix()


def _assign_vars_videos_to_miners(
    miners: List[dict],
    *,
    static_root: Path,
    internal_base: str,
) -> Optional[dict]:
    """
    Random vars/<subfolder>/ with >=3 mp4; slot i -> lowest / mid / highest filename number.
    Sets video_url (analyzer-reachable), static metadata; keeps miner_declared_video_url.
    """
    subs = _vars_subdirs(static_root)
    if not subs:
        bt.logging.warning("[vla-probe vars] no subnet-vla/vla-video-static/vars/ subfolders")
        return None
    eligible = [d for d in subs if _pick_three_videos(d) is not None]
    if not eligible:
        bt.logging.warning("[vla-probe vars] no vars/*/ folder with at least 3 *.mp4 files")
        return None
    folder = random.choice(eligible)
    triple = _pick_three_videos(folder)
    assert triple is not None
    n = len(miners)
    if n < 1 or n > 3:
        bt.logging.warning(
            f"[vla-probe vars] need 1..3 miners, got {len(miners)} — skipping"
        )
        return None
    picked = triple[:n]
    ib = internal_base.strip().rstrip("/")
    labels_all = ("low", "mid", "high")
    labels = labels_all[:n]
    for i, m in enumerate(miners):
        p = picked[i]
        rel = _rel_under_root(static_root, p)
        path_on_probe = f"/videos/{rel}"
        url = f"{ib}{path_on_probe}"
        m["miner_declared_video_url"] = m.get("video_url")
        m["video_url"] = url
        m["vars_video_slot"] = labels[i]
        m["vars_folder"] = folder.name
        m["static_video_relpath"] = rel
        m["static_video_bytes"] = p.stat().st_size if p.is_file() else None
        m["synapse"] = _synapse_payload_from_override(m, url)
    meta = {
        "vars_folder": folder.name,
        "folder_path": str(folder),
        "files": [
            {
                "slot": labels[i],
                "relpath": _rel_under_root(static_root, picked[i]),
                "bytes": picked[i].stat().st_size if picked[i].is_file() else None,
            }
            for i in range(n)
        ],
    }
    bt.logging.info(
        f"[vla-probe vars] picked folder={folder.name!r} "
        f"files={[p.name for p in picked]}"
    )
    return meta


def _synapse_payload_from_override(miner: dict, video_url: str) -> Any:
    syn = miner.get("synapse")
    if isinstance(syn, dict):
        out = dict(syn)
        out["video_url"] = video_url
        return out
    return {
        "video_url": video_url,
        "note": "overridden by probe vars static assignment",
    }


def _apply_longest_gets_max_overall_score(miners: List[dict]) -> Optional[dict]:
    """
    After full analysis, set overall_score on the longest (by file size) miner to
    max(overall_score) across miners with ok ai_verification. Details unchanged.
    """
    ok_idx: List[int] = []
    scores: List[float] = []
    sizes: List[int] = []
    for i, m in enumerate(miners):
        ai = m.get("ai_verification") or {}
        if not ai.get("ok"):
            continue
        an = ai.get("analysis") or {}
        ev = an.get("evaluation") or {}
        if "overall_score" not in ev:
            continue
        try:
            sc = float(ev["overall_score"])
        except (TypeError, ValueError):
            continue
        sz = m.get("static_video_bytes")
        if sz is None:
            continue
        try:
            sz = int(sz)
        except (TypeError, ValueError):
            continue
        ok_idx.append(i)
        scores.append(sc)
        sizes.append(sz)
    if len(ok_idx) != len(miners) or len(scores) != len(miners):
        return None
    k = len(miners)
    longest_i = max(range(k), key=lambda j: sizes[j])
    mx = max(scores)
    m = miners[longest_i]
    ai = m.get("ai_verification") or {}
    an = ai.get("analysis") or {}
    ev = dict(an.get("evaluation") or {})
    prev = ev.get("overall_score")
    ev["overall_score"] = mx
    ev["longest_video_score_pooling"] = {
        "previous_overall_score": prev,
        "pooled_max_overall_score": mx,
        "longest_video_bytes": sizes[longest_i],
        "all_overall_scores_before": [scores[j] for j in range(k)],
    }
    an["evaluation"] = ev
    m["ai_verification"]["analysis"] = an
    return {
        "longest_miner_uid": m.get("uid"),
        "longest_slot_index": longest_i,
        "longest_video_bytes": sizes[longest_i],
        "pooled_max_overall_score": mx,
        "scores_before_pooling": [scores[j] for j in range(k)],
    }


def _probe_video_fields(canonical: Optional[str]) -> dict[str, Optional[str]]:
    """
    If miner URL path is /videos/..., same files are served by vla-probe static handler.
    video_url_on_probe uses VLA_PROBE_PUBLIC_BASE (default http://127.0.0.1:8094 for host browser).
    """
    out: dict[str, Optional[str]] = {
        "video_path_on_probe": None,
        "video_url_on_probe": None,
    }
    if not canonical:
        return out
    path = urlparse(str(canonical).strip()).path or ""
    if not path.startswith("/videos/"):
        return out
    out["video_path_on_probe"] = path
    base = (os.environ.get("VLA_PROBE_PUBLIC_BASE") or "http://127.0.0.1:8094").strip().rstrip(
        "/"
    )
    out["video_url_on_probe"] = f"{base}{path}"
    return out


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


async def _apply_ai_verification_to_miners(
    miners: List[dict],
    task: str,
    analyzer_base_url: str,
    timeout: float,
    *,
    run_id: str,
    embed_png: bool = True,
) -> None:
    """POST each miner's video_url to the analyzer in parallel; attach ai_verification per miner."""
    base = analyzer_base_url.rstrip("/")
    t = httpx.Timeout(timeout, connect=min(30.0, timeout))

    bt.logging.info(
        f"[vla-probe {run_id}] ai_verification: POST {len(miners)} miners -> {base}/v1/analyze "
        f"(timeout_s={timeout:.0f})"
    )

    async with httpx.AsyncClient(timeout=t) as client:

        async def verify_one(m: dict) -> None:
            vu = m.get("video_url")
            if not vu:
                m["ai_verification"] = {"ok": False, "error": "no video_url"}
                return
            try:
                r = await client.post(
                    f"{base}/v1/analyze",
                    json={
                        "video_url": vu,
                        "task": task,
                        "embed_png": embed_png,
                        "fps": 2.0,
                        "frames_per_batch": 12,
                    },
                )
                try:
                    data = r.json()
                except Exception:
                    data = {"raw": r.text}
                if r.status_code >= 400:
                    detail = data
                    if isinstance(data, dict) and "detail" in data:
                        detail = data["detail"]
                    m["ai_verification"] = {
                        "ok": False,
                        "error": detail,
                        "http_status": r.status_code,
                    }
                    return
                if isinstance(data, dict) and data.get("ok"):
                    m["ai_verification"] = {
                        "ok": True,
                        "analysis": data.get("analysis"),
                    }
                else:
                    m["ai_verification"] = {
                        "ok": False,
                        "error": data if isinstance(data, dict) else str(data),
                        "http_status": r.status_code,
                    }
            except Exception as ex:
                m["ai_verification"] = {"ok": False, "error": str(ex)}

        await asyncio.gather(*[verify_one(m) for m in miners])

    for m in miners:
        ai = m.get("ai_verification") or {}
        err = ai.get("error")
        es = repr(err) if err is not None else None
        if es and len(es) > 160:
            es = es[:157] + "..."
        bt.logging.info(
            f"[vla-probe {run_id}] ai_verification uid={m.get('uid')} ok={ai.get('ok')} err={es}"
        )


def _synthetic_miners(n: int, task_n: str) -> List[dict]:
    """Placeholder miners when skip_dendrite: no chain, no axon calls."""
    miners: List[dict] = []
    for slot in range(n):
        miners.append(
            {
                "uid": slot,
                "hotkey_ss58": None,
                "axon": {
                    "ip": None,
                    "port": None,
                    "is_serving": None,
                    "hotkey": None,
                    "dry_run": True,
                },
                "video_url": None,
                "synapse": {
                    "video_url": None,
                    "task": task_n,
                    "dendrite": {
                        "status_code": 200,
                        "status_message": "dry_run (no dendrite)",
                        "process_time": 0.0,
                        "ip": None,
                        "port": None,
                    },
                },
            }
        )
    return miners


async def _skip_dendrite_vla_probe(
    *,
    run_id: str,
    t0: float,
    task_n: str,
    n_miners: int,
    timeout: float,
    using_ai_verification: bool,
    use_vars_static_videos: bool,
    embed_png: bool = True,
) -> dict:
    """
    No Subtensor/Dendrite: assign vars/*.mp4, optional AI analyzer.
    Analyzer URL only from env VLA_VIDEO_ANALYZER_URL on the probe host — not from client JSON.
    """
    bt.logging.info(
        f"[vla-probe {run_id}] skip_dendrite n_miners={n_miners} "
        f"vars={use_vars_static_videos} ai={using_ai_verification}"
    )
    if not use_vars_static_videos:
        return {
            "ok": False,
            "probe_run_id": run_id,
            "error": (
                "skip_dendrite requires use_vars_static_videos "
                "(probe assigns files from vla-video-static/vars)"
            ),
            "allowed_tasks": list(ALLOWED_TASKS),
        }
    miners = _synthetic_miners(n_miners, task_n)
    uids_list = list(range(n_miners))
    static_root = _probe_static_root()
    internal_base = (
        os.environ.get("VLA_PROBE_INTERNAL_BASE")
        or "http://subtensor-vla-probe:8091"
    ).strip()
    vars_meta = _assign_vars_videos_to_miners(
        miners,
        static_root=static_root,
        internal_base=internal_base,
    )
    if vars_meta is None:
        return {
            "ok": False,
            "probe_run_id": run_id,
            "error": (
                "skip_dendrite: vars assignment failed "
                "(need vars/<id>/ with >=3 *.mp4; 1..3 synthetic miners)"
            ),
            "allowed_tasks": list(ALLOWED_TASKS),
        }

    str_responses = [m.get("video_url") for m in miners]
    rewards = get_rewards(_RewardLogCtx(), responses=str_responses)
    rew_list = [float(x) for x in rewards.tolist()]
    for i, r in enumerate(rew_list):
        if i < len(miners):
            miners[i]["reward_share"] = r

    probe_base = (
        (os.environ.get("VLA_PROBE_PUBLIC_BASE") or "http://127.0.0.1:8094")
        .strip()
        .rstrip("/")
    )
    for m in miners:
        m.update(_probe_video_fields(m.get("video_url")))

    analyzer_url: Optional[str] = None
    boost: Optional[dict] = None
    if using_ai_verification:
        analyzer_url = (os.environ.get("VLA_VIDEO_ANALYZER_URL") or "").strip() or None
        if not analyzer_url:
            bt.logging.error(
                f"[vla-probe {run_id}] using_ai_verification but VLA_VIDEO_ANALYZER_URL unset"
            )
            return {
                "ok": False,
                "error": (
                    "using_ai_verification requires VLA_VIDEO_ANALYZER_URL "
                    "in the probe container environment"
                ),
                "allowed_tasks": list(ALLOWED_TASKS),
                "using_ai_verification": True,
                "skip_dendrite": True,
                "dry_run": True,
            }
        v_timeout = max(timeout, 600.0)
        bt.logging.info(
            f"[vla-probe {run_id}] analyzer_url={analyzer_url!r} verify_timeout_s={v_timeout:.0f}"
        )
        await _apply_ai_verification_to_miners(
            miners,
            task_n,
            analyzer_url,
            v_timeout,
            run_id=run_id,
            embed_png=embed_png,
        )
        boost = _apply_longest_gets_max_overall_score(miners)
        if boost:
            bt.logging.info(
                f"[vla-probe {run_id}] longest_video score pooling: {boost!r}"
            )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    call_ms = 0

    out: dict = {
        "ok": True,
        "probe_run_id": run_id,
        "probe_public_base": probe_base,
        "protocol": "subnet-vla VLASynapse",
        "skip_dendrite": True,
        "dry_run": True,
        "request": {
            "task": task_n,
            "allowed_tasks": list(ALLOWED_TASKS),
            "n_miners": n_miners,
        },
        "miner_uids_queried": uids_list,
        "miners": miners,
        "rewards": rew_list,
        "timing_ms": {"total": elapsed_ms, "dendrite_call": call_ms},
    }
    if using_ai_verification:
        out["using_ai_verification"] = True
    out["vars_static_videos"] = vars_meta
    out["use_vars_static_videos"] = True
    if boost is not None:
        out["longest_video_score_pooling"] = boost
    bt.logging.info(
        f"[vla-probe {run_id}] skip_dendrite done total_ms={elapsed_ms} miners={len(miners)}"
    )
    return out


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
    using_ai_verification: bool = False,
    video_analyzer_url: Optional[str] = None,
    use_vars_static_videos: bool = False,
    n_miners: Optional[int] = None,
    skip_dendrite: bool = False,
    embed_png: bool = True,
) -> dict:
    run_id = uuid.uuid4().hex[:10]
    t0 = time.perf_counter()
    task_n = normalize_task(task)
    if not is_allowed_task(task_n):
        bt.logging.warning(
            f"[vla-probe {run_id}] rejected task={task_n!r} (not in allowed list)"
        )
        return {
            "ok": False,
            "probe_run_id": run_id,
            "error": f"task must be one of {ALLOWED_TASKS}",
            "allowed_tasks": list(ALLOWED_TASKS),
        }

    if skip_dendrite:
        nm = n_miners if n_miners is not None else 3
        if nm not in (1, 2, 3):
            return {
                "ok": False,
                "probe_run_id": run_id,
                "error": "skip_dendrite requires n_miners to be 1, 2, or 3",
                "allowed_tasks": list(ALLOWED_TASKS),
            }
        return await _skip_dendrite_vla_probe(
            run_id=run_id,
            t0=t0,
            task_n=task_n,
            n_miners=nm,
            timeout=timeout,
            using_ai_verification=using_ai_verification,
            use_vars_static_videos=use_vars_static_videos,
            embed_png=embed_png,
        )

    wallet = bt.Wallet(name=wallet_name, hotkey=hotkey)
    subtensor = bt.Subtensor(network=chain_endpoint)
    mg = subtensor.metagraph(netuid)

    uids_list = _pick_miner_uids(mg, miner_uids, sample_size)
    bt.logging.info(
        f"[vla-probe {run_id}] start netuid={netuid} chain={chain_endpoint!r} "
        f"uids={uids_list} task={task_n!r} timeout={timeout}s "
        f"n_miners={n_miners!r} ai_verification={using_ai_verification}"
    )
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

    miners: List[dict] = []
    for i, uid in enumerate(uids_list):
        item = raw_list[i] if i < len(raw_list) else None
        url = _extract_url(item)
        miners.append(
            {
                "uid": int(uid),
                "hotkey_ss58": _hotkey_at(mg, uid),
                "axon": _axon_meta(mg, uid),
                "video_url": url,
                "synapse": _synapse_payload(item),
            }
        )

    vars_meta: Optional[dict] = None
    if use_vars_static_videos:
        static_root = _probe_static_root()
        internal_base = (
            os.environ.get("VLA_PROBE_INTERNAL_BASE")
            or "http://subtensor-vla-probe:8091"
        ).strip()
        vars_meta = _assign_vars_videos_to_miners(
            miners,
            static_root=static_root,
            internal_base=internal_base,
        )
        if vars_meta is None:
            bt.logging.error(
                "[vla-probe] use_vars_static_videos set but vars assignment failed "
                "(need vars/<id>/ with >=3 *.mp4 and 1..3 miners)"
            )
            return {
                "ok": False,
                "probe_run_id": run_id,
                "error": (
                    "use_vars_static_videos: no eligible vars/ folder with 3+ mp4 files, "
                    "or miner count not in 1..3"
                ),
                "allowed_tasks": list(ALLOWED_TASKS),
                "protocol": "subnet-vla VLASynapse",
                "netuid": netuid,
                "miner_uids_queried": uids_list,
                "miners": miners,
            }

    str_responses = [m.get("video_url") for m in miners]

    rewards = get_rewards(_RewardLogCtx(), responses=str_responses)
    rew_list = [float(x) for x in rewards.tolist()]
    for i, r in enumerate(rew_list):
        if i < len(miners):
            miners[i]["reward_share"] = r

    probe_base = (
        (os.environ.get("VLA_PROBE_PUBLIC_BASE") or "http://127.0.0.1:8094")
        .strip()
        .rstrip("/")
    )
    for m in miners:
        m.update(_probe_video_fields(m.get("video_url")))

    analyzer_url: Optional[str] = None
    boost: Optional[dict] = None
    if using_ai_verification:
        analyzer_url = (video_analyzer_url or "").strip() or None
        if not analyzer_url:
            analyzer_url = (os.environ.get("VLA_VIDEO_ANALYZER_URL") or "").strip() or None
        if not analyzer_url:
            bt.logging.error(
                f"[vla-probe {run_id}] using_ai_verification but no video_analyzer_url / env"
            )
            return {
                "ok": False,
                "error": (
                    "using_ai_verification requires video_analyzer_url in the request body "
                    "or VLA_VIDEO_ANALYZER_URL in the environment"
                ),
                "allowed_tasks": list(ALLOWED_TASKS),
                "using_ai_verification": True,
                "protocol": "subnet-vla VLASynapse",
                "netuid": netuid,
                "miner_uids_queried": uids_list,
                "miners": miners,
                "rewards": rew_list,
            }
        v_timeout = max(timeout, 600.0)
        bt.logging.info(
            f"[vla-probe {run_id}] analyzer_url={analyzer_url!r} verify_timeout_s={v_timeout:.0f}"
        )
        await _apply_ai_verification_to_miners(
            miners,
            task_n,
            analyzer_url,
            v_timeout,
            run_id=run_id,
            embed_png=embed_png,
        )
        if vars_meta is not None:
            boost = _apply_longest_gets_max_overall_score(miners)
            if boost:
                bt.logging.info(
                    f"[vla-probe {run_id}] longest_video score pooling: {boost!r}"
                )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    call_ms = int((t_after - t_call) * 1000)

    out: dict = {
        "ok": True,
        "probe_run_id": run_id,
        "probe_public_base": probe_base,
        "protocol": "subnet-vla VLASynapse",
        "bittensor_sdk_pinned": "9.7.0 (see requirements.txt)",
        "netuid": netuid,
        "chain_endpoint": chain_endpoint,
        "wallet_coldkey": wallet_name,
        "dendrite_deserialize_flag": not used_deserialize_true,
        "request": {
            "task": task_n,
            "allowed_tasks": list(ALLOWED_TASKS),
            "n_miners": n_miners,
        },
        "miner_uids_queried": uids_list,
        "miners": miners,
        "rewards": rew_list,
        "timing_ms": {"total": elapsed_ms, "dendrite_call": call_ms},
    }
    if using_ai_verification:
        out["using_ai_verification"] = True
        out["video_analyzer_url"] = analyzer_url
    if vars_meta is not None:
        out["vars_static_videos"] = vars_meta
        out["use_vars_static_videos"] = True
    if boost is not None and vars_meta is not None:
        out["longest_video_score_pooling"] = boost
    bt.logging.info(
        f"[vla-probe {run_id}] done ok={out.get('ok')} total_ms={elapsed_ms} "
        f"dendrite_ms={call_ms} miners={len(miners)}"
    )
    return out
