from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import bittensor as bt


def runtime_base_url(config: Any) -> str:
    try:
        raw = str(getattr(config.neuron, "runtime_base_url", "") or "")
    except Exception:
        return ""
    return raw.rstrip("/")


def runtime_timeout(config: Any) -> float:
    try:
        return float(getattr(config.neuron, "runtime_timeout", 15.0) or 15.0)
    except Exception:
        return 15.0


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        return json.loads(raw)


def try_post_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any] | None:
    if not base_url:
        return None
    try:
        return post_json(base_url, path, payload, timeout_s)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        bt.logging.warning(f"kitchen runtime {path} failed: {e}")
        return None
