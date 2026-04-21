# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# TODO(developer): Set your name
# Copyright © 2023 <your name>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import json
import typing

import bittensor as bt

from template.openfly_policy_io import ACTION_LABELS_DRONE_NAV

# Action space aligned with the existing OpenFly dashboard flow.
ACTION_LABELS: dict[int, str] = dict(ACTION_LABELS_DRONE_NAV)
ALLOWED_ACTION_IDS: typing.Tuple[int, ...] = tuple(sorted(ACTION_LABELS.keys()))

DEFAULT_SYNTHETIC_INSTRUCTIONS: typing.Tuple[str, ...] = (
    "Proceed toward the most salient building ahead of the drone.",
    "Move forward and keep the rectangular gray building centered.",
    "Turn left and align with the nearest road corridor.",
    "Strafe right to avoid the obstacle and continue forward.",
    "Stop if the target landmark is reached or motion is unsafe.",
)


class DroneNavSynapse(bt.Synapse):
    """
    Subnet protocol for instruction mining and validator-side verification.

    Validator -> miner:
      - instruction: natural-language navigation instruction
      - task_id: deterministic per-round id
      - synthetic_context_json: optional context (pose/socket/meta)
      - frame_jpeg_b64: optional visual context

    Miner -> validator:
      - action_id: selected action id from ALLOWED_ACTION_IDS
      - confidence: model confidence [0..1], optional
      - miner_response_json: full structured response (competition/debug fields)
      - miner_error: non-empty when miner failed
    """

    version: str = "drone-nav-v1"
    instruction: str
    task_id: str
    synthetic_context_json: typing.Optional[str] = None
    frame_jpeg_b64: typing.Optional[str] = None

    action_id: typing.Optional[int] = None
    confidence: typing.Optional[float] = None
    miner_response_json: typing.Optional[str] = None
    miner_error: typing.Optional[str] = None

    def deserialize(self) -> typing.Dict[str, typing.Any]:
        raw = self.miner_response_json
        if not raw:
            return {
                "action_id": self.action_id,
                "confidence": self.confidence,
                "error": self.miner_error,
            }
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except (TypeError, ValueError):
            pass
        return {
            "action_id": self.action_id,
            "confidence": self.confidence,
            "error": self.miner_error,
            "raw": str(raw),
        }
