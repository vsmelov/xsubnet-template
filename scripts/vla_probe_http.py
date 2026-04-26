#!/usr/bin/env python3
"""
subnet-vla-probe HTTP: POST /v1/vla-probe, GET /health, GET/HEAD /videos/<path>
(статика из subnet-vla/vla-video-static, см. docker-compose).
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

import bittensor as bt

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_SCRIPTS))

from vla_probe_lib import run_vla_probe  # noqa: E402


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return int(v)


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return float(v)


DEFAULTS = {
    "netuid": lambda: _env_int("NETUID", 1),
    "wallet_name": lambda: os.environ.get("WALLET_NAME", "vla-val"),
    "hotkey": lambda: os.environ.get("HOTKEY", "default"),
    "chain_endpoint": lambda: os.environ.get(
        "SUBTENSOR_CHAIN",
        "ws://127.0.0.1:9944",
    ),
    "sample_size": lambda: _env_int("PROBE_SAMPLE_SIZE", 4),
    "task": lambda: os.environ.get(
        "PROBE_TASK",
        "Clean-up the guestroom",
    ),
    "timeout": lambda: _env_float("PROBE_TIMEOUT", 60.0),
}


def _merge_body(body: dict | None) -> dict:
    b = dict(body) if isinstance(body, dict) else {}
    sd = b.get("skip_dendrite")
    if sd is None:
        skip = (
            os.environ.get("VLA_PROBE_SKIP_DENDRITE", "").strip().lower()
            in ("1", "true", "yes")
        )
    else:
        skip = bool(sd)

    # Minimal client body: task, n_miners, use_vars_static_videos, using_ai_verification, timeout.
    # Chain / analyzer URL come only from probe container env — not from the frontend.
    if skip:
        out: dict = {
            "skip_dendrite": True,
            "task": str(b.get("task", DEFAULTS["task"]())),
            "timeout": float(b.get("timeout", DEFAULTS["timeout"]())),
            "video_analyzer_url": None,
            "netuid": 0,
            "chain_endpoint": "ws://unused",
            "wallet_name": "_",
            "hotkey": "default",
            "miner_uids": None,
        }
        if b.get("n_miners") is not None:
            try:
                nm = int(b["n_miners"])
            except (TypeError, ValueError) as e:
                raise ValueError("n_miners must be an integer") from e
            if nm not in (1, 2, 3):
                raise ValueError("n_miners must be 1, 2, or 3")
            out["n_miners"] = nm
        else:
            out["n_miners"] = 3
        out["sample_size"] = out["n_miners"]
        uvv = b.get("use_vars_static_videos")
        if uvv is None:
            out["use_vars_static_videos"] = True
        else:
            out["use_vars_static_videos"] = bool(uvv)
        uai = b.get("using_ai_verification")
        if uai is None:
            out["using_ai_verification"] = os.environ.get(
                "VLA_PROBE_USING_AI", "true"
            ).strip().lower() in ("1", "true", "yes")
        else:
            out["using_ai_verification"] = bool(uai)
        out["embed_png"] = True if "embed_png" not in b else bool(b["embed_png"])
        return out

    out = {}
    out["skip_dendrite"] = False
    out["netuid"] = int(b.get("netuid", DEFAULTS["netuid"]()))
    out["wallet_name"] = str(b.get("wallet_name", DEFAULTS["wallet_name"]()))
    out["hotkey"] = str(b.get("hotkey", DEFAULTS["hotkey"]()))
    out["chain_endpoint"] = str(
        b.get("chain_endpoint", DEFAULTS["chain_endpoint"]()),
    )
    out["task"] = str(b.get("task", DEFAULTS["task"]()))
    out["timeout"] = float(b.get("timeout", DEFAULTS["timeout"]()))
    if b.get("n_miners") is not None:
        try:
            nm = int(b["n_miners"])
        except (TypeError, ValueError) as e:
            raise ValueError("n_miners must be an integer") from e
        if nm not in (1, 2, 3):
            raise ValueError("n_miners must be 1, 2, or 3")
        out["n_miners"] = nm
        out["miner_uids"] = None
        out["sample_size"] = nm
    else:
        out["n_miners"] = None
        out["sample_size"] = int(b.get("sample_size", DEFAULTS["sample_size"]()))
        if "miner_uids" in b and b["miner_uids"] is not None:
            out["miner_uids"] = [int(x) for x in b["miner_uids"]]
        else:
            out["miner_uids"] = None
    out["using_ai_verification"] = bool(b.get("using_ai_verification", False))
    vau = b.get("video_analyzer_url")
    out["video_analyzer_url"] = str(vau).strip() if vau else None
    uvv = b.get("use_vars_static_videos")
    if uvv is None:
        out["use_vars_static_videos"] = (
            os.environ.get("VLA_PROBE_VARS_VIDEOS", "").strip().lower()
            in ("1", "true", "yes")
        )
    else:
        out["use_vars_static_videos"] = bool(uvv)
    return out


def _video_static_root() -> Path:
    return Path(
        os.environ.get("VLA_VIDEO_STATIC_ROOT", str(_ROOT / "vla-video-static"))
    ).resolve()


def _resolve_video_file(request_path: str) -> Path | None:
    """Map GET /videos/<relpath> -> file under vla-video-static (no ..)."""
    if not request_path.startswith("/videos/"):
        return None
    rel = request_path[len("/videos/") :].strip("/")
    if not rel:
        return None
    if any(p == ".." for p in rel.replace("\\", "/").split("/")):
        return None
    root = _video_static_root()
    if not root.is_dir():
        return None
    full = (root / rel).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        return None
    return full if full.is_file() else None


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Долгий POST /v1/vla-probe не должен блокировать GET /health и другие запросы."""

    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.client_address[0], self.log_date_time_string(), fmt % args)
        )

    def _send_json(self, status: int, obj: object) -> None:
        try:
            raw = json.dumps(
                obj, ensure_ascii=False, indent=2, default=str
            ).encode("utf-8")
        except Exception as e:
            raw = json.dumps(
                {"ok": False, "error": f"json_encode: {e}"},
                ensure_ascii=False,
            ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _send_video_file(self, file_path: Path) -> None:
        data = file_path.read_bytes()
        ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path.startswith("/videos/"):
            vf = _resolve_video_file(path)
            if vf is None:
                self.send_error(404)
                return
            self._send_video_file(vf)
            return
        if path in ("/health", "/"):
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "subnet-vla-probe",
                    "routes": [
                        "GET /health",
                        "GET /videos/<path>",
                        "HEAD /videos/<path>",
                        "POST /v1/vla-probe",
                    ],
                    "video_static_root": str(_video_static_root()),
                },
            )
            return
        self.send_error(404)

    def do_HEAD(self) -> None:
        path = self.path.split("?")[0]
        if path.startswith("/videos/"):
            vf = _resolve_video_file(path)
            if vf is None:
                self.send_error(404)
                return
            st = vf.stat()
            ctype = mimetypes.guess_type(str(vf))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(st.st_size))
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            return
        if path in ("/health", "/"):
            probe = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(probe)))
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path != "/v1/vla-probe":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                text = (raw.decode("utf-8-sig") or "{}").strip()
                body = json.loads(text or "{}")
            except json.JSONDecodeError as e:
                self._send_json(400, {"ok": False, "error": f"invalid JSON: {e}"})
                return
            if not isinstance(body, dict):
                self._send_json(
                    400,
                    {"ok": False, "error": "JSON body must be an object"},
                )
                return
            try:
                kw = _merge_body(body)
            except ValueError as e:
                self._send_json(400, {"ok": False, "error": str(e)})
                return
            try:
                result = asyncio.run(
                    run_vla_probe(
                        netuid=kw["netuid"],
                        chain_endpoint=kw["chain_endpoint"],
                        wallet_name=kw["wallet_name"],
                        hotkey=kw["hotkey"],
                        task=kw["task"],
                        miner_uids=kw["miner_uids"],
                        sample_size=kw["sample_size"],
                        timeout=kw["timeout"],
                        using_ai_verification=kw["using_ai_verification"],
                        video_analyzer_url=kw["video_analyzer_url"],
                        use_vars_static_videos=kw["use_vars_static_videos"],
                        n_miners=kw.get("n_miners"),
                        skip_dendrite=kw["skip_dendrite"],
                        embed_png=kw["embed_png"],
                    )
                )
            except Exception as e:
                bt.logging.error(f"[vla-probe http] run_vla_probe failed: {e}")
                traceback.print_exc(file=sys.stderr)
                self._send_json(
                    500,
                    {"ok": False, "error": str(e), "type": type(e).__name__},
                )
                return
            status = 200 if result.get("ok") else 400
            bt.logging.info(
                f"[vla-probe http] response HTTP {status} ok={result.get('ok')} "
                f"total_ms={result.get('timing_ms', {}).get('total')}"
            )
            self._send_json(status, result)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            try:
                self._send_json(
                    500,
                    {"ok": False, "error": str(e), "type": type(e).__name__},
                )
            except Exception:
                pass


def main() -> None:
    port = _env_int("PROBE_PORT", 8091)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(
        f"subnet-vla-probe listening on 0.0.0.0:{port} (threaded HTTP; long probe does not block /health)",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
