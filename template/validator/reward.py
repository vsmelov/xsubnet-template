# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import typing
import hashlib

import numpy as np
import bittensor as bt


def _coerce_float(value: typing.Any) -> typing.Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _lookup(obj: typing.Any, key: str) -> typing.Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_explicit_score(response: typing.Any) -> typing.Optional[float]:
    direct = _coerce_float(_lookup(response, "score"))
    if direct is not None:
        return direct
    scoring = _lookup(response, "scoring")
    return _coerce_float(_lookup(scoring, "score"))


def _extract_video_ref(response: typing.Any) -> typing.Optional[str]:
    if response is None:
        return None
    if isinstance(response, str):
        out = response.strip()
        return out or None
    for key in ("episode_video_ref", "video_url"):
        value = _lookup(response, key)
        if value:
            out = str(value).strip()
            if out:
                return out
    artifact_manifest = _lookup(response, "artifact_manifest")
    if isinstance(artifact_manifest, dict):
        value = artifact_manifest.get("public_url")
        if value:
            out = str(value).strip()
            if out:
                return out
    return None


def get_rewards(
    self,
    expected: typing.Optional[float] = None,
    responses: typing.Optional[typing.List[typing.Any]] = None,
) -> np.ndarray:
    """
    Reward adapter for the staged VLA demo -> robokitchen chain shim migration.

    Preferred path:
    - validator sets explicit per-response `score`;
    - rewards are proportional to the non-negative score mass.

    Compatibility path:
    - reward non-empty video refs almost uniformly with deterministic jitter.
    """
    responses = list(responses or [])
    n = len(responses)
    if n == 0:
        return np.array([], dtype=np.float32)

    explicit_scores = np.full(n, np.nan, dtype=np.float64)
    has_explicit_scores = False
    for i, response in enumerate(responses):
        score = _extract_explicit_score(response)
        if score is None or not np.isfinite(score):
            continue
        explicit_scores[i] = max(0.0, float(score))
        has_explicit_scores = True

    if has_explicit_scores:
        total = float(np.nansum(explicit_scores))
        if total <= 0.0:
            bt.logging.warning("Kitchen shim scores were present but non-positive.")
            return np.zeros(n, dtype=np.float32)
        return np.nan_to_num(explicit_scores / total, nan=0.0).astype(np.float32)

    weights = np.zeros(n, dtype=np.float64)
    for i, response in enumerate(responses):
        video_ref = _extract_video_ref(response)
        if not video_ref:
            continue
        digest = hashlib.sha256(video_ref.encode("utf-8")).hexdigest()
        jitter = (int(digest[:8], 16) % 401) / 10000.0
        weights[i] = 1.0 + jitter

    total = float(np.sum(weights))
    if total <= 0.0:
        bt.logging.warning("No valid miner artifact for reward.")
        return np.zeros(n, dtype=np.float32)
    return (weights / total).astype(np.float32)
